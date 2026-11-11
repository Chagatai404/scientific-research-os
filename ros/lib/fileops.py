"""File operations for computer work: one step of a plan the person authorised (docs/core-experience/COMPUTER-ADAPTERS.md §4).

This engine is reached only through ``ros.lib.desktop_operations`` (kind ``computer_file``), as a child process of the
operations worker. It never imports the domain: the packet carries the real paths, the pinned grant roots and what the
record already knows about the step. It never follows a link, never overwrites (the commit is a rename that refuses an
existing target, or ``os.link`` on POSIX), never reports success without re-reading what it wrote, and returns names,
sizes, file ids and SHA-256 digests only, never file contents.

``hooks`` (a dict of callables, Python callers only, never part of a packet) lets the tests stop or disturb a step at
the exact points the design names: ``before_poststat``, ``before_commit``, ``after_commit``, ``write``, ``disk_usage``,
``before_source_removal`` and ``cross_volume``.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: a symlink, junction, mount point or cloud placeholder
CHUNK = 1 << 20
HEADROOM = 0.01
DEVICES = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
PARTIAL = '.ros-partial-'
MANIFEST = 'manifest.json'
ASIDE = '.ros-backup-'


class StepError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- paths --------------------------------------------------------------------------------------------------------------------
def is_link(path) -> bool:
    """A symbolic link, junction or any other reparse point (copied from renderkit: lib modules stay independent)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & REPARSE)


def clean(path) -> str:
    """An absolute local path in plain form, or a refusal: no ``..``, stream, ``\\\\?\\`` form, device name or trailing dot."""
    if not isinstance(path, str) or not path or len(path) > 1000 or '\x00' in path or any(ord(c) < 32 for c in path):
        raise StepError('path_outside_root', 'a path is a plain absolute path')
    text = path.replace('/', os.sep)
    if text.startswith(('\\\\?\\', '\\\\.\\', '\\??\\')) or (os.name == 'nt' and text.startswith('\\\\')):
        raise StepError('path_outside_root', 'long, device and network path forms are refused')
    if not os.path.isabs(text):
        raise StepError('path_outside_root', 'a path is absolute')
    drive, rest = os.path.splitdrive(text)
    if ':' in rest:
        raise StepError('path_outside_root', 'alternate data streams are refused')
    parts = [p for p in rest.split(os.sep) if p]
    for part in parts:
        if part in ('.', '..'):
            raise StepError('path_outside_root', '".." and "." are refused in a path')
        if os.name == 'nt' and (part != part.rstrip(' .') or part.split('.')[0].upper().rstrip(' ') in DEVICES):
            raise StepError('path_outside_root', 'a name ending in a dot or space, or a device name, is refused')
    return os.path.normpath(text)


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def under(path, root) -> bool:
    p, r = _key(path), _key(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def check_root(root):
    """The granted root must still be the folder the person chose: same volume serial and file id, and not a link now."""
    if not isinstance(root, dict) or not isinstance(root.get('path'), str):
        raise StepError('scope_denied', 'no granted root covers this path')
    try:
        st = os.lstat(root['path'])
    except OSError:
        raise StepError('scope_denied', 'the granted folder is missing') from None
    if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & REPARSE:
        raise StepError('path_link_refused', 'the granted folder is now a link or junction')
    if (st.st_dev, st.st_ino) != (root.get('volume_serial'), root.get('file_id')):
        raise StepError('path_link_refused', 'the granted folder was replaced since you granted it')


def check_path(path, root, home=None, need_parent=True):
    """Every component from the root down is checked with lstat; a link anywhere is refused, never followed. Returns the
    path's lstat, or None when it does not exist (its parent must, when ``need_parent``)."""
    path = clean(path)
    check_root(root)
    if not under(path, root['path']):
        raise StepError('path_outside_root', 'the path is outside the granted folder')
    if home and under(path, home):
        raise StepError('scope_denied', 'the Research OS home is never part of computer work')
    rel = os.path.relpath(path, root['path'])
    current, result = root['path'], None
    parts = [] if rel == '.' else rel.split(os.sep)
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            if index < len(parts) - 1 and need_parent:
                raise StepError('path_outside_root', 'a folder on the way does not exist') from None
            return None
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & REPARSE:
            raise StepError('path_link_refused', 'a link, junction or cloud placeholder is on the way; it is never followed')
        result = st
    return result if parts else os.lstat(path)


def fingerprint(st):
    return {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'file_id': st.st_ino, 'volume_serial': st.st_dev}


def _same(a, b):
    return (a.st_size, a.st_mtime_ns, a.st_ino, a.st_dev) == (b.st_size, b.st_mtime_ns, b.st_ino, b.st_dev)


def final_path(fd):
    """The path Windows itself reports for an open handle (``GetFinalPathNameByHandleW``); None elsewhere."""
    if os.name != 'nt':
        return None
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get = kernel.GetFinalPathNameByHandleW
    get.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    size = get(msvcrt.get_osfhandle(fd), buffer, 32768, 0)
    if not size or size >= 32768:
        raise StepError('access_denied', 'Windows could not say where an open file is')
    value = buffer.value
    if value.upper().startswith('\\\\?\\UNC\\'):
        raise StepError('path_outside_root', 'the open file is on a network share')
    return value[4:] if value.startswith('\\\\?\\') else value


def _same_place(fd, path):
    real = final_path(fd)
    if real is not None and _key(real) != _key(path):
        raise StepError('path_link_refused', 'the open file is not at the checked path')


def _code(exc):
    win = getattr(exc, 'winerror', None)
    if exc.errno == errno.ENOSPC or win in (39, 112):
        return 'disk_full'
    return 'access_denied'


def _open_read(path, before):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        st = os.fstat(fd)
        if (st.st_ino, st.st_dev) != (before.st_ino, before.st_dev):
            raise StepError('path_link_refused', 'the file changed identity between the check and the open')
        _same_place(fd, path)
    except BaseException:
        os.close(fd)
        raise
    return fd


def digest(path, before=None):
    """SHA-256 of a regular file, read through a handle checked against its lstat."""
    before = before or os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise StepError('collision', 'not a regular file')
    fd = _open_read(path, before)
    try:
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, CHUNK)
            if not chunk:
                break
            h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fd)


# --- the commit: never an overwrite ----------------------------------------------------------------------------------------
def commit(src, dst):
    """Rename ``src`` to ``dst`` only if ``dst`` does not exist (FileExistsError otherwise)."""
    if os.name == 'nt':
        os.rename(src, dst)  # MoveFileExW without MOVEFILE_REPLACE_EXISTING: refuses an existing target
    else:
        link_commit(src, dst)


def link_commit(src, dst):
    """The POSIX no-replace commit: a hard link fails on an existing target, then the old name goes."""
    os.link(src, dst)
    os.unlink(src)


def _drop_partial(path):
    """Our own staging file from an earlier attempt (its name is derived from the step's key). Returns whether one existed."""
    if not os.path.lexists(path):
        return False
    if is_link(path) or not os.path.isfile(path):
        raise StepError('path_link_refused', 'something that is not our staging file has its name')
    os.unlink(path)
    return True


def _write_all(fd, chunk, hooks):
    if hooks.get('write'):
        hooks['write'](fd, chunk)
    view = memoryview(chunk)
    while view:
        view = view[os.write(fd, view):]


def stage(src, before, partial, hooks):
    """Copy ``src`` into a new ``partial`` (exclusive create), hashing while reading, then fsync and check the source did
    not change meanwhile. Returns ``(sha256, size)``; a failure leaves no partial behind."""
    made = False
    try:
        fd = _open_read(src, before)
        try:
            out = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
            made = True
            try:
                _same_place(out, partial)
                h, size = hashlib.sha256(), 0
                while True:
                    chunk = os.read(fd, CHUNK)
                    if not chunk:
                        break
                    h.update(chunk)
                    _write_all(out, chunk, hooks)
                    size += len(chunk)
                os.fsync(out)
            finally:
                os.close(out)
            if hooks.get('before_poststat'):
                hooks['before_poststat']()
            after = os.fstat(fd)
        finally:
            os.close(fd)
        now = os.lstat(src)
        if size != before.st_size or not _same(after, before) or not _same(now, before):
            raise StepError('source_changed', 'the source changed while it was read; nothing was written')
        os.utime(partial, ns=(before.st_atime_ns, before.st_mtime_ns))
        if digest(partial) != h.hexdigest():
            raise StepError('verify_failed', 'the staged copy does not match what was read')
        return h.hexdigest(), size
    except OSError as exc:
        if made:
            _quiet_unlink(partial)
        raise StepError(_code(exc), 'disk full' if _code(exc) == 'disk_full' else 'access denied') from None
    except BaseException:
        if made:
            _quiet_unlink(partial)
        raise


def _quiet_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _space(folder, size, hooks):
    free = (hooks.get('disk_usage') or shutil.disk_usage)(folder).free
    if free < size * (1 + HEADROOM) + 4096:
        raise StepError('disk_full', 'not enough free space for this file')


# --- the steps --------------------------------------------------------------------------------------------------------------
def _ok(phase, phases, **extra):
    return {'ok': phase in ('verified', 'skipped_identical', 'committed'), 'phase': phase, 'phases': phases, **extra}


def _fail(code, message, phases=()):
    terminal = 'needs_attention' if code == 'needs_attention' else 'failed'
    return {'ok': False, 'phase': terminal, 'code': code, 'error': message[:300], 'phases': [*phases, {'phase': terminal, 'code': code}]}


def _ours(p):
    """Whether the destination did not exist before this step first started (so a file there now is ours)."""
    first = p.get('first') or {}
    return first.get('dst_existed') is False


def _copy(p, hooks, src=None, src_root=None):
    src, dst = src or p['src'], p['dst']
    sst = check_path(src, src_root or p['src_root'], None if src_root else p.get('home'))
    if sst is None or not stat.S_ISREG(sst.st_mode):
        raise StepError('source_changed', 'the source file is missing')
    dst_st = check_path(dst, p['dst_root'], p.get('home'))
    parent = os.path.dirname(dst)
    partial = os.path.join(parent, PARTIAL + p['key'][:32])
    aside = os.path.join(parent, ASIDE + p['key'][:32])
    phases = [{'phase': 'reconciled', 'partial_removed': True}] if _drop_partial(partial) else []
    if os.path.lexists(aside):
        return _finish_replace(p, dst, aside, phases, hooks, reconcile=True)
    if dst_st is not None:
        if not stat.S_ISREG(dst_st.st_mode):
            raise StepError('collision', 'something that is not a file has the destination name')
        source_sha, dst_sha = digest(src, sst), digest(dst, dst_st)
        if source_sha == dst_sha:
            if _ours(p):
                return _ok('verified', phases + [{'phase': 'committed', 'sha256': dst_sha, 'size': dst_st.st_size, 'file_id': dst_st.st_ino, 'reconciled': True},
                                                 {'phase': 'verified', 'sha256': dst_sha}])
            return _ok('skipped_identical', phases + [{'phase': 'skipped_identical', 'sha256': dst_sha, 'size': dst_st.st_size}])
        if p.get('on_collision') != 'replace':
            raise StepError('collision', 'a different file already has the destination name; nothing was overwritten')
        if p.get('mode') == 'reconcile':
            return _ok('interrupted', phases + [{'phase': 'interrupted'}])
        return _replace(p, src, sst, dst, dst_st, partial, aside, phases, hooks)
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', phases + [{'phase': 'interrupted'}])
    _space(parent, sst.st_size, hooks)
    sha, size = stage(src, sst, partial, hooks)
    staged = os.lstat(partial)
    phases.append({'phase': 'staged', 'size': size, 'sha256': sha})
    if hooks.get('before_commit'):
        hooks['before_commit']()
    try:
        commit(partial, dst)
    except FileExistsError:
        _quiet_unlink(partial)
        raise StepError('collision', 'a file appeared at the destination; nothing was overwritten') from None
    if hooks.get('after_commit'):
        hooks['after_commit']()
    now = os.lstat(dst)
    if now.st_ino != staged.st_ino or now.st_size != size:
        return _fail('needs_attention', 'the destination changed right after it was written', phases)
    phases.append({'phase': 'committed', 'sha256': sha, 'size': size, 'file_id': now.st_ino, 'src': fingerprint(sst)})
    phases.append({'phase': 'verified', 'sha256': sha})
    return _ok('verified', phases)


def _replace(p, src, sst, dst, dst_st, partial, aside, phases, hooks):
    """Overwrite with a backup: stage and verify the new bytes, set the old file aside in its own folder (a no-replace
    rename), commit, then keep the old bytes in the Research OS undo folder."""
    _space(os.path.dirname(dst), sst.st_size, hooks)
    sha, size = stage(src, sst, partial, hooks)
    phases.append({'phase': 'staged', 'size': size, 'sha256': sha})
    old_sha = digest(dst, dst_st)
    commit(dst, aside)
    if hooks.get('before_commit'):
        hooks['before_commit']()
    try:
        commit(partial, dst)
    except FileExistsError:
        commit(aside, dst) if not os.path.lexists(dst) else None
        _quiet_unlink(partial)
        raise StepError('collision', 'a file appeared at the destination; nothing was overwritten') from None
    if hooks.get('after_commit'):
        hooks['after_commit']()
    phases.append({'phase': 'committed', 'sha256': sha, 'size': size, 'file_id': os.lstat(dst).st_ino, 'replaced_sha256': old_sha, 'src': fingerprint(sst)})
    return _finish_replace(p, dst, aside, phases, hooks, sha=sha)


def _finish_replace(p, dst, aside, phases, hooks, reconcile=False, sha=None):
    """Move the set-aside old file into the undo folder. On a resume: a missing destination gets the old file back."""
    if not os.path.lexists(dst):
        commit(aside, dst)
        return _ok('interrupted', phases + [{'phase': 'reconciled', 'restored': True}, {'phase': 'interrupted'}])
    undo = p.get('undo_dir')
    if not undo:
        raise StepError('scope_denied', 'no undo folder for the replaced file')
    os.makedirs(undo, exist_ok=True)
    target = os.path.join(undo, os.path.basename(dst))
    ast = os.lstat(aside)
    old_sha = digest(aside, ast)
    if os.path.lexists(target):
        if digest(target) != old_sha:
            raise StepError('collision', 'the undo folder already holds a different file')
    else:
        partial = os.path.join(undo, PARTIAL + p['key'][:32])
        _drop_partial(partial)
        staged, _ = stage(aside, ast, partial, hooks)
        commit(partial, target)
        if digest(target) != staged:
            raise StepError('verify_failed', 'the kept copy of the old file does not match')
    os.unlink(aside)
    new_sha = sha or digest(dst)
    out = phases + ([{'phase': 'reconciled', 'aside_kept': True}] if reconcile else [])
    if reconcile:
        out.append({'phase': 'committed', 'sha256': new_sha, 'size': os.lstat(dst).st_size, 'replaced_sha256': old_sha, 'reconciled': True})
    out.append({'phase': 'verified', 'sha256': new_sha, 'backup': target, 'backup_sha256': old_sha})
    return _ok('verified', out, reversible=True)


def _move(p, hooks):
    src, dst = p['src'], p['dst']
    sst = check_path(src, p['src_root'], p.get('home'))
    dst_st = check_path(dst, p['dst_root'], p.get('home'))
    first = (p.get('first') or {}).get('src') or {}
    committed = (p.get('recorded') or {}).get('committed')
    parent = os.path.dirname(dst)
    phases = [{'phase': 'reconciled', 'partial_removed': True}] if _drop_partial(os.path.join(parent, PARTIAL + p['key'][:32])) else []
    if sst is None:
        if dst_st is not None and _ours(p) and (dst_st.st_ino == first.get('file_id') or committed and digest(dst, dst_st) == committed.get('sha256')):
            sha = committed.get('sha256') if committed else digest(dst, dst_st)
            return _ok('verified', phases + [{'phase': 'committed', 'sha256': sha, 'size': dst_st.st_size, 'file_id': dst_st.st_ino, 'reconciled': True},
                                             {'phase': 'source_removed', 'reconciled': True}, {'phase': 'verified', 'sha256': sha}])
        raise StepError('source_changed', 'the source is missing')
    if not stat.S_ISREG(sst.st_mode):
        raise StepError('source_changed', 'the source is not a file')
    if dst_st is not None:
        if not _ours(p) or not stat.S_ISREG(dst_st.st_mode):
            raise StepError('collision', 'something already has the destination name; nothing was moved')
        # Our own committed copy of a move across volumes: the source goes only if it is exactly what was copied.
        dst_sha = digest(dst, dst_st)
        if first and (sst.st_size, sst.st_mtime_ns, sst.st_ino) != (first.get('size'), first.get('mtime_ns'), first.get('file_id')):
            raise StepError('source_changed', 'the source changed after it was copied; both files are kept')
        if digest(src, sst) != dst_sha or (committed and committed.get('sha256') != dst_sha):
            raise StepError('source_changed', 'the source and its copy differ; both files are kept')
        if not committed:
            return _ok('committed', phases + [{'phase': 'committed', 'sha256': dst_sha, 'size': dst_st.st_size, 'file_id': dst_st.st_ino, 'reconciled': True}])
        if p.get('mode') == 'reconcile':
            return _ok('committed', phases)
        if hooks.get('before_source_removal'):
            hooks['before_source_removal']()
        now = os.lstat(src)
        if not _same(now, sst):
            raise StepError('source_changed', 'the source changed just before it was removed; both files are kept')
        os.unlink(src)
        return _ok('verified', phases + [{'phase': 'source_removed'}, {'phase': 'verified', 'sha256': dst_sha}])
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', phases + [{'phase': 'interrupted'}])
    same_volume = sst.st_dev == os.lstat(parent).st_dev and not hooks.get('cross_volume')
    if same_volume:
        sha = digest(src, sst)
        try:
            commit(src, dst)
        except FileExistsError:
            raise StepError('collision', 'a file appeared at the destination; nothing was moved') from None
        now = os.lstat(dst)
        if now.st_ino != sst.st_ino or now.st_size != sst.st_size or os.path.lexists(src):
            return _fail('needs_attention', 'the moved file is not where it should be', phases)
        return _ok('verified', phases + [{'phase': 'committed', 'sha256': sha, 'size': now.st_size, 'file_id': now.st_ino, 'src': fingerprint(sst)},
                                         {'phase': 'source_removed'}, {'phase': 'verified', 'sha256': sha}])
    # Across volumes: copy, verify and commit now; the source is removed by the next call, after the commit is recorded.
    result = _copy(dict(p, on_collision='stop'), hooks)
    committed = next(x for x in result['phases'] if x['phase'] == 'committed')
    return _ok('committed', [x for x in result['phases'] if x['phase'] != 'verified'], sha256=committed['sha256'])


def _rename(p, hooks):
    src, dst = p['src'], p['dst']
    sst = check_path(src, p['src_root'], p.get('home'))
    dst_st = check_path(dst, p['dst_root'], p.get('home'))
    first = (p.get('first') or {}).get('src') or {}
    if sst is None:
        if dst_st is not None and _ours(p) and dst_st.st_ino == first.get('file_id'):
            return _ok('verified', [{'phase': 'committed', 'file_id': dst_st.st_ino, 'reconciled': True}, {'phase': 'verified'}])
        raise StepError('source_changed', 'the source is missing')
    if dst_st is not None:
        raise StepError('collision', 'something already has the new name; nothing was renamed')
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', [{'phase': 'interrupted'}])
    if stat.S_ISDIR(sst.st_mode) and os.name != 'nt':
        raise StepError('unsupported_op', 'renaming a folder without overwriting is supported on Windows only')
    try:
        commit(src, dst)
    except FileExistsError:
        raise StepError('collision', 'something appeared with the new name; nothing was renamed') from None
    now = os.lstat(dst)
    if now.st_ino != sst.st_ino:
        return _fail('needs_attention', 'the renamed item is not where it should be')
    return _ok('verified', [{'phase': 'committed', 'file_id': now.st_ino, 'size': now.st_size, 'src': fingerprint(sst)}, {'phase': 'verified'}])


def _mkdir(p, hooks):
    dst = p['dst']
    st = check_path(dst, p['dst_root'], p.get('home'))
    if st is not None:
        if stat.S_ISDIR(st.st_mode):
            return _ok('verified', [{'phase': 'committed', 'reconciled': True}, {'phase': 'verified'}]) if _ours(p) else \
                _ok('skipped_identical', [{'phase': 'skipped_identical'}])
        raise StepError('collision', 'a file already has the folder name')
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', [{'phase': 'interrupted'}])
    os.mkdir(dst)
    st = os.lstat(dst)
    if not stat.S_ISDIR(st.st_mode) or getattr(st, 'st_file_attributes', 0) & REPARSE:
        return _fail('needs_attention', 'the new folder is not a plain folder')
    return _ok('verified', [{'phase': 'committed', 'file_id': st.st_ino}, {'phase': 'verified'}])


def _rmdir(p, hooks):
    src = p['src']
    st = check_path(src, p['src_root'], p.get('home'))
    if st is None:
        return _ok('verified', [{'phase': 'verified', 'reconciled': True}])
    if not stat.S_ISDIR(st.st_mode):
        raise StepError('collision', 'not a folder')
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', [{'phase': 'interrupted'}])
    try:
        os.rmdir(src)  # only ever an empty folder
    except OSError as exc:
        if exc.errno in (errno.ENOTEMPTY, errno.EEXIST) or getattr(exc, 'winerror', None) == 145:
            return _fail('needs_attention', 'the folder is not empty, so it was left in place')
        raise
    return _ok('verified', [{'phase': 'committed'}, {'phase': 'verified'}])


def _to_bin(p, hooks):
    """A delete goes first into the workspace's Research OS bin (a quarantine folder in the Research OS home, not the Windows
    Recycle Bin): a no-overwrite move, verified, with a manifest (original path, SHA-256, size, deleted_at) beside it, so it can
    be put back until the bin's retention ends."""
    src, entry = p['src'], p['dst']
    st = check_path(src, p['src_root'], p.get('home'))
    if st is not None and p.get('expect_sha256') and (not stat.S_ISREG(st.st_mode) or digest(src, st) != p['expect_sha256']):
        return _fail('needs_attention', 'the file changed since the plan was approved, so it was left in place')
    check_root(p['dst_root'])
    os.makedirs(os.path.dirname(entry), exist_ok=True)
    result = _move(dict(p, home=None), hooks)
    if result['phase'] == 'verified':
        sha = next((x.get('sha256') for x in result['phases'] if x.get('sha256')), None)
        manifest = os.path.join(os.path.dirname(entry), MANIFEST)
        if not os.path.lexists(manifest):
            body = {'original': src, 'sha256': sha, 'size': os.lstat(entry).st_size, 'deleted_at': p['deleted_at'], 'key': p['key']}
            with open(manifest, 'x', encoding='utf-8') as stream:
                json.dump(body, stream)
        for x in result['phases']:
            if x['phase'] == 'verified':
                x.update(bin=entry, deleted_at=p['deleted_at'])
        result['reversible'] = True
    return result


def _unbin(p, hooks):
    """Put an item back from the bin to where it was; never over something that took its place."""
    check_path(p['dst'], p['dst_root'], p.get('home'))
    result = _move(dict(p, home=None), hooks)
    if result['phase'] == 'verified':
        folder = os.path.dirname(p['src'])
        manifest = os.path.join(folder, MANIFEST)
        if os.path.isfile(manifest) and not is_link(manifest):
            os.unlink(manifest)
        try:
            os.rmdir(folder)
        except OSError:
            pass
    return result


def _delete(p, hooks):
    """Delete for good: only when the person's approval of this exact action said so, and only the exact bytes approved."""
    src = p['src']
    st = check_path(src, p['src_root'], p.get('home'))
    if st is None:
        if (p.get('first') or {}).get('src'):
            return _ok('verified', [{'phase': 'committed', 'reconciled': True}, {'phase': 'verified', 'reconciled': True}], reversible=False)
        raise StepError('source_changed', 'the file is missing')
    if not stat.S_ISREG(st.st_mode):
        raise StepError('unsupported_op', 'only a file is deleted for good; an emptied folder is removed by its own step')
    if not p.get('expect_sha256') or digest(src, st) != p['expect_sha256']:
        return _fail('needs_attention', 'the file changed since you approved deleting it, so it was left in place')
    if p.get('mode') == 'reconcile':
        return _ok('interrupted', [{'phase': 'interrupted'}])
    os.unlink(src)
    return _ok('verified', [{'phase': 'committed', 'sha256': p['expect_sha256'], 'size': st.st_size}, {'phase': 'verified', 'sha256': p['expect_sha256']}],
               reversible=False)


def _restore(p, hooks):
    """Undo of a replace: the current file goes aside (into the undo folder) and the kept old bytes come back."""
    current = check_path(p['dst'], p['dst_root'], p.get('home'))
    if current is None or not stat.S_ISREG(current.st_mode):
        return _fail('needs_attention', 'the file to restore over is missing')
    if p.get('expect_sha256') and digest(p['dst'], current) != p['expect_sha256']:
        return _fail('needs_attention', 'the file changed since it was replaced, so it was left as it is')
    return _copy(dict(p, on_collision='replace', home=None), hooks, src=p['src'], src_root=p['src_root'])


def _purge_inside(folder):
    """Empty one real folder. Every child is looked at with ``lstat`` (never ``is_dir``, which follows a junction on older Pythons): a
    symlink, junction or other reparse point is removed as the entry it is and never entered, so what it points at is untouched."""
    with os.scandir(folder) as found:
        children = [(entry.path, entry.name) for entry in found]
    for child, _name in children:
        try:
            st = os.lstat(child)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & REPARSE:
            try:
                os.unlink(child)
            except OSError:
                os.rmdir(child)  # a junction is removed as a folder entry, never entered
        elif stat.S_ISDIR(st.st_mode):
            _purge_inside(child)
            os.rmdir(child)
        else:
            os.unlink(child)


def purge_entry(bin_root, entry):
    """Remove one bin entry (its folder: the item and its manifest) once its retention ended. Only a plain folder directly in the
    bin is removed; a link found inside is removed itself, never followed. Returns whether it was removed."""
    path = os.path.join(bin_root, entry)
    if os.path.dirname(os.path.normpath(path)) != os.path.normpath(bin_root) or not os.path.isdir(path) or is_link(path):
        return False
    _purge_inside(path)
    os.rmdir(path)
    return True


STEPS = {'copy': _copy, 'move': _move, 'rename': _rename, 'mkdir': _mkdir, 'rmdir': _rmdir, 'trash': _to_bin,
         'delete_bin': _to_bin, 'delete_permanent': _delete, 'unbin': _unbin, 'restore': _restore}


def run(packet, hooks=None):
    """One step. Returns ``{ok, phase, phases, code?, error?}``; never raises for an expected refusal."""
    hooks = hooks or {}
    try:
        if not isinstance(packet, dict) or packet.get('op') not in STEPS or not isinstance(packet.get('key'), str):
            raise StepError('unsupported_op', 'unknown file operation')
        return STEPS[packet['op']](packet, hooks)
    except StepError as exc:
        return _fail(exc.code, str(exc))
    except OSError as exc:
        return _fail(_code(exc), 'the disk is full' if _code(exc) == 'disk_full' else 'access was denied (' + type(exc).__name__ + ')')
