"""Credential references and the stores they point into. Standard library only; imports nothing from ``ros``.

A provider profile records *where* a key lives, never the key: ``{"store": "env", "name": "MY_API_KEY"}`` (headless use:
the variable of the process that runs the work) or ``{"store": "os", "name": "ResearchOS:<label>"}`` (desktop use: the
operating system's credential store, today the Windows Credential Manager). ``resolve`` reads the value at the moment of
use and returns an opaque ``Secret``: it prints as ``[credential]``, refuses JSON and pickling, and only ``reveal()`` gives
the value to the transport that sends it. Nothing is cached, so a replaced key is used on the next request and a revoked
(deleted or unset) one stops the next request with ``CredentialMissing``. No error message repeats a value it was given.
"""
from __future__ import annotations

import json
import os
import re

STORES = ('env', 'os')
NAMESPACE = 'ResearchOS:'
ENV_NAME = re.compile(r'[A-Z_][A-Z0-9_]{0,63}')
OS_NAME = re.compile(r'ResearchOS:[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
HIDDEN = '[hidden]'
MIN_KEY = 4  # a shorter value cannot be told apart from ordinary text, so it cannot be scrubbed safely: it is refused instead

# Environment variables that would make a subscription CLI bill an API account or a cloud platform instead of the person's login.
PAID_ENV = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX')
# The legacy variable a local OpenAI-compatible server's key was once read from (providers.local): a key like any other.
LEGACY_ENV = ('ROS_LOCAL_API_KEY',)
# The variable names that any profile read in this process refers to (upper-cased; Windows names are case-insensitive). Add-only: a profile
# removed later keeps its name hidden from children, which is harmless. See ``child_env``.
_REFERENCED = set()


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


def note_env_references(refs) -> None:
    """Remember the variable names of the ``env`` references among ``refs`` (anything else is ignored), so that no child process this
    program starts inherits a key a provider profile points to."""
    for ref in refs or ():
        if isinstance(ref, dict) and ref.get('store') == 'env' and isinstance(ref.get('name'), str) and ENV_NAME.fullmatch(ref['name']):
            _REFERENCED.add(ref['name'].upper())


def forget_env_references() -> None:
    """Empty the remembered names (tests)."""
    _REFERENCED.clear()


def referenced_env() -> frozenset:
    return frozenset(_REFERENCED)


def child_env(base=None, *, names=(), keep=(), **extra) -> dict:
    """The environment of a child process: ``base`` (default: this process's) without the paid API variables (``PAID_ENV``), without
    every variable some provider profile refers to as a credential (plus ``names``), and with ``extra`` added. ``keep`` names variables
    that this one child needs (the credential worker reading its own reference) and so stay. Names compare case-insensitively."""
    hidden = ({n.upper() for n in (*PAID_ENV, *LEGACY_ENV)} | _REFERENCED | {str(n).upper() for n in names}) - {str(n).upper() for n in keep}
    return {**{k: v for k, v in (os.environ if base is None else base).items() if k.upper() not in hidden}, **extra}


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
    if len(value.strip()) < MIN_KEY:
        raise CredentialInvalid(f'The credential ({describe(ref)}) is shorter than {MIN_KEY} characters, which is too short to be a key and could not be kept out of '
                                'logs and records. Nothing was sent and no other provider was used.')
    return Secret(value.strip())


def status(ref, environ=None) -> str:
    """``present``, ``missing``, ``unavailable`` or ``invalid``; never the value."""
    try:
        resolve(ref, environ)
        return 'present'
    except CredentialMissing: return 'missing'
    except CredentialUnavailable: return 'unavailable'
    except CredentialInvalid: return 'invalid'


def spellings(value) -> list:
    """Every way ``value`` can appear in text: itself and its JSON-string forms (escaped quotes, backslashes, control characters and
    non-ASCII escaped or as is), longest first so a longer form is never left half-replaced by a shorter one."""
    forms = {value, json.dumps(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1]}
    return sorted((f for f in forms if len(f) >= MIN_KEY), key=len, reverse=True)


def scrub(text, *secrets) -> str:
    """``text`` with every credential value, in every spelling, replaced by ``[hidden]`` (a server may echo the key in an error, and a
    tool result is JSON). Scrub *before* shortening a text: a cut can leave half a key that no exact match finds. A value shorter than
    ``MIN_KEY`` is never scrubbed (``resolve`` refuses such a credential)."""
    text = str(text)
    for secret in secrets:
        value = secret.reveal() if isinstance(secret, Secret) else secret
        if isinstance(value, str):
            for form in spellings(value): text = text.replace(form, HIDDEN)
    return text


def decode_blob(data: bytes) -> str:
    """The text of a stored credential blob. Research OS writes UTF-8; the Windows ``cmdkey`` tool and other programs write UTF-16LE
    (with or without a byte-order mark). Trailing NULs are dropped. Anything else is refused without repeating its bytes."""
    data = bytes(data)
    candidates = []
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'): candidates.append('utf-16')
    candidates += ['utf-8', 'utf-16-le'] if len(data) % 2 == 0 else ['utf-8']
    for encoding in candidates:
        try: text = data.decode(encoding, errors='strict').lstrip('\ufeff').rstrip('\x00')
        except UnicodeDecodeError: continue
        if '\x00' not in text and not any(ord(c) < 32 and c not in '\t\r\n' for c in text): return text
    raise CredentialUnavailable('The stored credential is not text Research OS can read (UTF-8 or UTF-16); store it again.')


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
        return decode_blob(data)
    finally:
        lib.CredFree(found)


def os_store_write(name: str, value: str) -> None:
    """Store (or replace) ``value`` under ``name`` for the current Windows user. The person's own act, done by the desktop host."""
    api = _advapi()
    if api is None: raise CredentialUnavailable('The OS credential store is unavailable on this computer.')
    _namespaced(name)
    data = str(value).strip().encode('utf-8')
    if len(data) < MIN_KEY or len(data) > MAX_BLOB: raise CredentialInvalid(f'A stored credential is {MIN_KEY} to {MAX_BLOB} bytes.')
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
