"""Run a program inside a Windows AppContainer with a Job Object around it. Standard library only (ctypes); imports nothing from ``ros``.

An AppContainer is a real operating-system boundary, unlike Python audit hooks or a low-integrity token (ctypes and native code
step around hooks; low integrity blocks writes but not reads or network). A process started here has:

- no network at all, loopback included (no capability is ever passed, so ``internetClient`` and friends are absent);
- read access only to the folders passed as ``read_dirs`` and write access only to ``write_dirs`` (their ACLs are extended with the
  container's own SID; the container is otherwise denied everything the user can read, such as the profile folder), plus what Windows
  already lets every AppContainer read (``C:\\Windows``, ``C:\\Program Files``);
- no child processes (``PROCESS_CREATION_CHILD_PROCESS_RESTRICTED`` and a Job Object active-process limit of 1);
- a Job Object that kills it when the handle closes, and limits its CPU time and memory;
- only the three standard pipes inherited (an explicit handle list), so no socket or file of the parent leaks into it.

``available()`` says whether this computer can run it. Nothing here falls back to an unconfined process: a caller that gets
``(False, reason)`` must report the reason and not run the program. Kernel exploits are outside what any user-mode boundary stops.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

NAME = 'ros.render.sandbox.v1'
WINDOWS = os.name == 'nt'

if WINDOWS:
    import ctypes
    from ctypes import wintypes as wt

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    userenv = ctypes.WinDLL('userenv', use_last_error=True)
    adv = ctypes.WinDLL('advapi32', use_last_error=True)

    HANDLE, PVOID, LPVOID = wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p
    PSID = ctypes.c_void_p

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('Sid', PSID), ('Attributes', wt.DWORD)]

    class SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [('AppContainerSid', PSID), ('Capabilities', ctypes.POINTER(SID_AND_ATTRIBUTES)), ('CapabilityCount', wt.DWORD), ('Reserved', wt.DWORD)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [('cb', wt.DWORD), ('lpReserved', wt.LPWSTR), ('lpDesktop', wt.LPWSTR), ('lpTitle', wt.LPWSTR), ('dwX', wt.DWORD), ('dwY', wt.DWORD),
                    ('dwXSize', wt.DWORD), ('dwYSize', wt.DWORD), ('dwXCountChars', wt.DWORD), ('dwYCountChars', wt.DWORD), ('dwFillAttribute', wt.DWORD),
                    ('dwFlags', wt.DWORD), ('wShowWindow', wt.WORD), ('cbReserved2', wt.WORD), ('lpReserved2', ctypes.c_void_p), ('hStdInput', HANDLE),
                    ('hStdOutput', HANDLE), ('hStdError', HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [('StartupInfo', STARTUPINFOW), ('lpAttributeList', ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [('hProcess', HANDLE), ('hThread', HANDLE), ('dwProcessId', wt.DWORD), ('dwThreadId', wt.DWORD)]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('nLength', wt.DWORD), ('lpSecurityDescriptor', ctypes.c_void_p), ('bInheritHandle', wt.BOOL)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong), ('LimitFlags', wt.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wt.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wt.DWORD), ('SchedulingClass', wt.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION), ('IoInfo', IO_COUNTERS), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
        _fields_ = [('UIRestrictionsClass', wt.DWORD)]

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [('TotalUserTime', ctypes.c_longlong), ('TotalKernelTime', ctypes.c_longlong), ('ThisPeriodTotalUserTime', ctypes.c_longlong),
                    ('ThisPeriodTotalKernelTime', ctypes.c_longlong), ('TotalPageFaultCount', wt.DWORD), ('TotalProcesses', wt.DWORD),
                    ('ActiveProcesses', wt.DWORD), ('TotalTerminatedProcesses', wt.DWORD)]

    k32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                                   ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION)]
    k32.CreateProcessW.restype = wt.BOOL
    k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    k32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
    k32.CreateJobObjectW.restype = HANDLE
    k32.SetInformationJobObject.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    k32.QueryInformationJobObject.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p]
    k32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
    k32.TerminateJobObject.argtypes = [HANDLE, wt.UINT]
    k32.ResumeThread.argtypes = [HANDLE]
    k32.WaitForSingleObject.argtypes = [HANDLE, wt.DWORD]
    k32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(wt.DWORD)]
    k32.CloseHandle.argtypes = [HANDLE]
    k32.TerminateProcess.argtypes = [HANDLE, wt.UINT]
    k32.CreatePipe.argtypes = [ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE), ctypes.c_void_p, wt.DWORD]
    k32.SetHandleInformation.argtypes = [HANDLE, wt.DWORD, wt.DWORD]
    k32.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    k32.PeekNamedPipe.argtypes = [HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    k32.LocalFree.restype = ctypes.c_void_p
    userenv.CreateAppContainerProfile.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(PSID)]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [wt.LPCWSTR, ctypes.POINTER(PSID)]
    userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wt.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    adv.ConvertSidToStringSidW.argtypes = [PSID, ctypes.POINTER(wt.LPWSTR)]
    adv.FreeSid.argtypes = [PSID]
    adv.FreeSid.restype = PSID

    EXTENDED_STARTUPINFO_PRESENT, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, DETACHED_PROCESS = 0x00080000, 0x4, 0x400, 0x8
    STARTF_USESTDHANDLES = 0x100
    ATTR_HANDLE_LIST, ATTR_SECURITY_CAPABILITIES, ATTR_CHILD_PROCESS_POLICY = 0x20002, 0x20009, 0x2000E
    ATTR_MITIGATION = 0x20007
    HRESULT_ALREADY_EXISTS = -2147024713  # 0x800700B7
    JOB_KILL_ON_CLOSE, JOB_ACTIVE_PROCESS, JOB_TIME, JOB_PROCESS_MEMORY, JOB_DIE_ON_EXCEPTION = 0x2000, 0x8, 0x4, 0x100, 0x400
    UI_RESTRICT_ALL = 0xFF  # handles, readclipboard, writeclipboard, systemparameters, displaysettings, globalatoms, desktop, exitwindows


def _text_sid(sid) -> str:
    out = wt.LPWSTR()
    if not adv.ConvertSidToStringSidW(sid, ctypes.byref(out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return out.value
    finally:
        k32.LocalFree(out)


def container_sid() -> str:
    """The textual SID of this program's AppContainer, creating its profile the first time. Raises OSError when the API is missing."""
    if not WINDOWS:
        raise OSError('AppContainers exist only on Windows')
    sid = PSID()
    hr = userenv.CreateAppContainerProfile(NAME, 'Research OS renderer', 'Runs figure scripts without network or file access', None, 0, ctypes.byref(sid))
    if hr == HRESULT_ALREADY_EXISTS:
        hr = userenv.DeriveAppContainerSidFromAppContainerName(NAME, ctypes.byref(sid))
    if hr != 0:
        raise OSError('the Windows AppContainer profile could not be created (HRESULT 0x%08X)' % (hr & 0xFFFFFFFF))
    try:
        return _text_sid(sid)
    finally:
        adv.FreeSid(sid)


def existing_sid() -> str | None:
    """The textual SID of the container's name, without creating its profile (the SID follows from the name alone); None off Windows."""
    if not WINDOWS:
        return None
    sid = PSID()
    if userenv.DeriveAppContainerSidFromAppContainerName(NAME, ctypes.byref(sid)) != 0:
        return None
    try:
        return _text_sid(sid)
    finally:
        adv.FreeSid(sid)


def delete_profile() -> bool:
    """Unregister the container's profile (what uninstalling does). True when it was removed or was not there."""
    if not WINDOWS:
        return True
    hr = userenv.DeleteAppContainerProfile(NAME)
    return hr == 0 or (hr & 0xFFFF) in (2, 3)  # removed, or no such profile


def grant(path, sid: str, write: bool = False) -> None:
    """Give the container read+execute (or modify) on a folder and everything below it, through icacls (a Windows tool). Needs the
    caller to own the folder or hold WRITE_DAC on it; raises OSError otherwise, and never touches anything the caller does not own."""
    rights = '(OI)(CI)(M)' if write else '(OI)(CI)(RX)'
    done = subprocess.run(['icacls', str(path), '/grant', f'*{sid}:{rights}', '/C', '/Q'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if done.returncode != 0:
        raise OSError('could not set folder permissions for the sandbox on %s: %s' % (path, (done.stdout + done.stderr).strip()[:300]))


def revoke(path, sid: str) -> None:
    subprocess.run(['icacls', str(path), '/remove', f'*{sid}', '/T', '/C', '/Q'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)


def _env_block(env: dict) -> ctypes.Array:
    text = ''.join(f'{k}={v}\0' for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())) + '\0'
    block = (ctypes.c_wchar * len(text))()
    block[:] = text  # slice assignment keeps the embedded NULs that separate the entries
    return block


def _pipe():
    """A pipe whose write end the child inherits and whose read end it does not."""
    read, write = HANDLE(), HANDLE()
    attrs = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)
    if not k32.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(attrs), 1 << 16):
        raise ctypes.WinError(ctypes.get_last_error())
    k32.SetHandleInformation(read, 1, 0)
    return read, write


def _drain(handle, limit: int, sink: list, flag: dict) -> None:
    """Read a pipe to its end, keeping the first ``limit`` bytes; more than that marks the run as too chatty."""
    buffer, got, total = ctypes.create_string_buffer(8192), wt.DWORD(), 0
    while k32.ReadFile(handle, buffer, 8192, ctypes.byref(got), None) and got.value:
        total += got.value
        if sum(map(len, sink)) < limit:
            sink.append(buffer.raw[:got.value])
        if total > limit * 4:
            flag['chatty'] = True


def run(argv, cwd, env, *, read_dirs=(), write_dirs=(), wall=60.0, cpu=60.0, memory=1 << 30, max_output=65536, watch=None, watch_bytes=256 << 20,
        cancel=None) -> dict:
    """Run ``argv`` (argv[0] is a full path) in the AppContainer. Returns ``{code, stdout, stderr, seconds, ended}`` where ``ended`` is
    ``exit``, ``timeout``, ``cancelled``, ``cpu``, ``output`` or ``disk``. ``read_dirs`` and ``write_dirs`` must already be granted
    (``prepare``). ``watch`` is a folder whose total size is held under ``watch_bytes`` while the program runs. Raises OSError when the
    boundary cannot be set up; the program has not run then."""
    if not WINDOWS:
        raise OSError('AppContainers exist only on Windows')
    sid_text = container_sid()
    sid = PSID()
    hr = userenv.DeriveAppContainerSidFromAppContainerName(NAME, ctypes.byref(sid))
    if hr != 0:
        raise OSError('the AppContainer SID could not be derived (HRESULT 0x%08X)' % (hr & 0xFFFFFFFF))
    handles = []
    job = HANDLE()
    try:
        out_r, out_w = _pipe(); err_r, err_w = _pipe(); in_r, in_w = _pipe()
        handles += [out_r, err_r, in_w]
        k32.CloseHandle(in_w); handles.remove(in_w)  # the child reads end-of-file at once
        k32.SetHandleInformation(in_r, 1, 1)  # it is the child's end of the stdin pipe
        # --- attribute list: container, no child processes, only these pipes inherited
        caps = SECURITY_CAPABILITIES(sid, None, 0, 0)  # no capability: no internet, no loopback, no files outside the grants
        policy = wt.DWORD(1)  # PROCESS_CREATION_CHILD_PROCESS_RESTRICTED
        inherit = (HANDLE * 3)(in_r, out_w, err_w)
        size = ctypes.c_size_t()
        k32.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
        attrs = ctypes.create_string_buffer(size.value)
        if not k32.InitializeProcThreadAttributeList(attrs, 3, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for attribute, value, length in ((ATTR_SECURITY_CAPABILITIES, ctypes.byref(caps), ctypes.sizeof(caps)),
                                             (ATTR_CHILD_PROCESS_POLICY, ctypes.byref(policy), ctypes.sizeof(policy)),
                                             (ATTR_HANDLE_LIST, ctypes.byref(inherit), ctypes.sizeof(inherit))):
                if not k32.UpdateProcThreadAttribute(attrs, 0, attribute, value, length, None, None):
                    raise ctypes.WinError(ctypes.get_last_error())
            # --- job: kill on close, one process, CPU and memory limits, no UI access
            job = k32.CreateJobObjectW(None, None)
            limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limits.BasicLimitInformation.LimitFlags = JOB_KILL_ON_CLOSE | JOB_ACTIVE_PROCESS | JOB_TIME | JOB_PROCESS_MEMORY | JOB_DIE_ON_EXCEPTION
            limits.BasicLimitInformation.ActiveProcessLimit = 1
            limits.BasicLimitInformation.PerJobUserTimeLimit = int(cpu * 10_000_000)
            limits.ProcessMemoryLimit = int(memory)
            if not k32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            ui = JOBOBJECT_BASIC_UI_RESTRICTIONS(UI_RESTRICT_ALL)
            k32.SetInformationJobObject(job, 4, ctypes.byref(ui), ctypes.sizeof(ui))
            info = STARTUPINFOEXW()
            info.StartupInfo.cb = ctypes.sizeof(info)
            info.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            info.StartupInfo.hStdInput, info.StartupInfo.hStdOutput, info.StartupInfo.hStdError = in_r, out_w, err_w
            info.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
            proc = PROCESS_INFORMATION()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in argv]), 32768)
            flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | DETACHED_PROCESS
            if not k32.CreateProcessW(str(argv[0]), command, None, None, True, flags, _env_block(env) if env is not None else None, str(cwd), ctypes.byref(info), ctypes.byref(proc)):
                raise OSError('the sandboxed program could not start: ' + str(ctypes.WinError(ctypes.get_last_error())))
        finally:
            k32.DeleteProcThreadAttributeList(attrs)
        handles += [proc.hProcess, proc.hThread]
        if not k32.AssignProcessToJobObject(job, proc.hProcess):
            error = ctypes.WinError(ctypes.get_last_error())
            k32.TerminateProcess(proc.hProcess, 1)
            raise OSError('the sandboxed program could not be put in its job: ' + str(error))
        for h in (in_r, out_w, err_w):
            k32.CloseHandle(h)
        started = time.monotonic()
        out, err, flag = [], [], {}
        readers = [threading.Thread(target=_drain, args=(h, max_output, sink, flag), daemon=True) for h, sink in ((out_r, out), (err_r, err))]
        for t in readers: t.start()
        k32.ResumeThread(proc.hThread)
        ended, last_check = 'exit', 0.0
        while True:
            if k32.WaitForSingleObject(proc.hProcess, 100) == 0:
                break
            now = time.monotonic()
            if cancel is not None and cancel.is_set(): ended = 'cancelled'
            elif now - started > wall: ended = 'timeout'
            elif flag.get('chatty'): ended = 'output'
            elif watch and now - last_check > .5:
                last_check = now
                if _tree_size(watch) > watch_bytes: ended = 'disk'
            if ended != 'exit':
                k32.TerminateJobObject(job, 1)
                k32.WaitForSingleObject(proc.hProcess, 5000)
                break
        code = wt.DWORD()
        k32.GetExitCodeProcess(proc.hProcess, ctypes.byref(code))
        if ended == 'exit' and code.value == 1816:  # ERROR_NOT_ENOUGH_QUOTA: the CPU limit ended the job
            ended = 'cpu'
        for t in readers: t.join(2)
        return {'code': code.value, 'stdout': b''.join(out)[:max_output].decode('utf-8', 'replace'), 'stderr': b''.join(err)[:max_output].decode('utf-8', 'replace'),
                'seconds': round(time.monotonic() - started, 2), 'ended': ended}
    finally:
        if job:
            k32.TerminateJobObject(job, 1)
            k32.CloseHandle(job)
        for h in handles:
            k32.CloseHandle(h)
        adv.FreeSid(sid)


def _tree_size(folder) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def available() -> tuple[bool, str]:
    """Whether this computer can create the container and its job. The reason is plain words for the person."""
    if not WINDOWS:
        return False, 'the safe renderer runs only on Windows (AppContainer); there is no verified equivalent on this system'
    try:
        container_sid()
    except OSError as exc:
        return False, str(exc)
    return True, ''
