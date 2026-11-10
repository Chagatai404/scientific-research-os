"""Credential references and the stores they point into. Standard library only; imports nothing from ``ros``.

A provider profile records *where* a key lives, never the key: ``{"store": "env", "name": "MY_API_KEY"}`` (headless use:
the variable of the process that runs the work) or ``{"store": "os", "name": "ResearchOS:<label>"}`` (desktop use: the
operating system's credential store, today the Windows Credential Manager). ``resolve`` reads the value at the moment of
use and returns an opaque ``Secret``: it prints as ``[credential]``, refuses JSON and pickling, and only ``reveal()`` gives
the value to the transport that sends it. Nothing is cached, so a replaced key is used on the next request and a revoked
(deleted or unset) one stops the next request with ``CredentialMissing``. No error message repeats a value it was given.
"""
from __future__ import annotations

import os
import re

STORES = ('env', 'os')
NAMESPACE = 'ResearchOS:'
ENV_NAME = re.compile(r'[A-Z_][A-Z0-9_]{0,63}')
OS_NAME = re.compile(r'ResearchOS:[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
HIDDEN = '[hidden]'


class CredentialError(ValueError):
    """A credential could not be used. Nothing was sent, and no other provider or paid route was tried instead."""
    code = 'credential_error'


class CredentialInvalid(CredentialError):
    code = 'credential_reference_invalid'


class CredentialMissing(CredentialError):
    code = 'credential_missing'


class CredentialUnavailable(CredentialError):
    code = 'credential_store_unavailable'


class Secret:
    """A credential value in memory. Never printed, serialised or pickled; ``reveal()`` is for the transport only."""
    __slots__ = ('_value',)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self): return '[credential]'
    __str__ = __repr__

    def __format__(self, spec): return '[credential]'

    def __reduce_ex__(self, protocol): raise TypeError('a credential cannot be serialised')

    def __bool__(self): return bool(self._value)


def reference(value) -> dict:
    """The normalised reference ``{"store", "name"}``. Anything else (a value, an extra field, a name that is not a
    variable or namespaced store name) is refused without repeating what was given."""
    if not isinstance(value, dict) or set(value) != {'store', 'name'} or value.get('store') not in STORES or not isinstance(value.get('name'), str):
        raise CredentialInvalid('A credential reference is exactly {"store": "env" or "os", "name": ...}; a key value is never accepted.')
    store, name = value['store'], value['name']
    if store == 'env' and not ENV_NAME.fullmatch(name):
        raise CredentialInvalid('An environment reference names a variable (capital letters, digits and _); never paste the key itself.')
    if store == 'os' and not OS_NAME.fullmatch(name):
        raise CredentialInvalid(f'An OS credential store reference is a name in the {NAMESPACE} namespace; never paste the key itself.')
    return {'store': store, 'name': name}


def describe(ref: dict) -> str:
    ref = reference(ref)
    return f"environment variable {ref['name']}" if ref['store'] == 'env' else f"OS credential {ref['name']}"


def resolve(ref, environ=None) -> Secret:
    """The value the reference points to, read now. Raises ``CredentialMissing`` (absent, empty, revoked),
    ``CredentialUnavailable`` (the store does not exist here) or ``CredentialInvalid``."""
    ref = reference(ref)
    if ref['store'] == 'env':
        value = (os.environ if environ is None else environ).get(ref['name'], '')
    else:
        if _advapi() is None:
            raise CredentialUnavailable('The OS credential store is unavailable on this computer; use an environment reference instead.')
        value = _os_read(ref['name']) or ''
    if not value.strip():
        raise CredentialMissing(f'The credential ({describe(ref)}) is missing or revoked. Nothing was sent and no other provider was used.')
    return Secret(value.strip())


def status(ref, environ=None) -> str:
    """``present``, ``missing``, ``unavailable`` or ``invalid``; never the value."""
    try:
        resolve(ref, environ)
        return 'present'
    except CredentialMissing: return 'missing'
    except CredentialUnavailable: return 'unavailable'
    except CredentialInvalid: return 'invalid'


def scrub(text, *secrets) -> str:
    """``text`` with every exact credential value replaced by ``[hidden]`` (a server may echo the key in an error)."""
    text = str(text)
    for secret in secrets:
        value = secret.reveal() if isinstance(secret, Secret) else secret
        if isinstance(value, str) and len(value) >= 4: text = text.replace(value, HIDDEN)
    return text


# --- Windows Credential Manager (advapi32), stdlib ctypes only ------------------------------------------------------------------
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_BLOB = 5 * 512
_API = {}


def _advapi():
    """The advapi32 functions, or None where there is no Windows Credential Manager."""
    if 'api' in _API: return _API['api']
    api = None
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [('dwLowDateTime', wintypes.DWORD), ('dwHighDateTime', wintypes.DWORD)]

            class CREDENTIALW(ctypes.Structure):
                _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
                            ('LastWritten', FILETIME), ('CredentialBlobSize', wintypes.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                            ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                            ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]
            lib = ctypes.WinDLL('advapi32', use_last_error=True)
            lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
            lib.CredReadW.restype = wintypes.BOOL
            lib.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
            lib.CredWriteW.restype = wintypes.BOOL
            lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            lib.CredDeleteW.restype = wintypes.BOOL
            lib.CredFree.argtypes = [ctypes.c_void_p]
            lib.CredFree.restype = None
            api = {'lib': lib, 'ctypes': ctypes, 'CREDENTIALW': CREDENTIALW}
        except (OSError, AttributeError, ImportError):
            api = None
    _API['api'] = api
    return api


def os_store_available() -> bool:
    return _advapi() is not None


def _namespaced(name):
    if not isinstance(name, str) or not OS_NAME.fullmatch(name):
        raise CredentialInvalid(f'Only names in the {NAMESPACE} namespace are read, written or deleted.')
    return name


def _os_read(name):
    api = _advapi()
    if api is None: raise CredentialUnavailable('The OS credential store is unavailable on this computer.')
    ctypes, lib = api['ctypes'], api['lib']
    found = ctypes.POINTER(api['CREDENTIALW'])()
    if not lib.CredReadW(_namespaced(name), CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND: return None
        raise CredentialUnavailable('The OS credential store could not be read.')
    try:
        size = found.contents.CredentialBlobSize
        data = ctypes.string_at(found.contents.CredentialBlob, size) if size else b''
        return data.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        raise CredentialUnavailable('The stored credential is not in the format Research OS writes; store it again.') from None
    finally:
        lib.CredFree(found)


def os_store_write(name: str, value: str) -> None:
    """Store (or replace) ``value`` under ``name`` for the current Windows user. The person's own act, done by the desktop host."""
    api = _advapi()
    if api is None: raise CredentialUnavailable('The OS credential store is unavailable on this computer.')
    _namespaced(name)
    data = str(value).strip().encode('utf-8')
    if not data or len(data) > MAX_BLOB: raise CredentialInvalid('A stored credential is 1 to 2560 bytes.')
    ctypes, lib = api['ctypes'], api['lib']
    blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    cred = api['CREDENTIALW']()
    cred.Type, cred.TargetName, cred.Persist = CRED_TYPE_GENERIC, name, CRED_PERSIST_LOCAL_MACHINE
    cred.CredentialBlobSize, cred.CredentialBlob = len(data), ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    cred.UserName = 'research-os'
    if not lib.CredWriteW(ctypes.byref(cred), 0):
        raise CredentialUnavailable('The OS credential store refused the write.')


def os_store_delete(name: str) -> bool:
    """Revoke: delete the entry. False when there was none."""
    api = _advapi()
    if api is None: raise CredentialUnavailable('The OS credential store is unavailable on this computer.')
    _namespaced(name)
    ctypes, lib = api['ctypes'], api['lib']
    if lib.CredDeleteW(name, CRED_TYPE_GENERIC, 0): return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND: return False
    raise CredentialUnavailable('The OS credential store refused the deletion.')
