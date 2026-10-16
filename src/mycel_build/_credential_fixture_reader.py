"""Private stdout-only command for a reviewed public-fixture probe.

No native library is loaded on import. Never call a default keychain or an item
creation/deletion API. stdout is consumed only by installed Credentials, not by
an operation log. The underlying fixture is public regression data.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import signal
import sys

FIXTURE_SHA = '87a34479ff2f4f9fd8c6c982a9e461f637a7bd9b88e82b03f3e765a58bf77582'
PUBLIC_UNLOCK_PASSWORD = b'password'
SERVICE = b'test_service'
ACCOUNT = b'test_account'

class Refusal(Exception):
    pass


def ordinary(path: Path, *, directory=False):
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise Refusal('path')
    st = path.lstat()
    if st.st_uid != os.getuid() or (not directory and st.st_nlink != 1):
        raise Refusal('ownership')
    if directory:
        if not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o700:
            raise Refusal('directory')
    elif not stat.S_ISREG(st.st_mode):
        raise Refusal('file')
    return st


def validate_root(root: Path, expected: dict):
    if root.parent != Path('/private/tmp') or '/login.keychain' in str(root):
        raise Refusal('root')
    st = ordinary(root, directory=True)
    if any((a / '.git').exists() for a in (root, *root.parents)):
        raise Refusal('git')
    actual = {'device':st.st_dev, 'inode':st.st_ino, 'uid':st.st_uid, 'mode':0o700}
    if actual != expected:
        raise Refusal('root_identity')


def native_api():
    # Public, still-declared file-keychain functions. Exact ABI checked against
    # the retained SDK headers; runtime availability is a genuine probe result.
    sec = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    V = ctypes.c_void_p; U = ctypes.c_uint32; I = ctypes.c_int32; B = ctypes.c_ubyte
    signatures = {
      'SecKeychainSetUserInteractionAllowed': ([B], I),
      'SecKeychainOpen': ([ctypes.c_char_p, ctypes.POINTER(V)], I),
      'SecKeychainGetPath': ([V, ctypes.POINTER(U), ctypes.c_void_p], I),
      'SecKeychainUnlock': ([V, U, ctypes.c_void_p, B], I),
      'SecKeychainFindGenericPassword': ([V, U, ctypes.c_char_p, U, ctypes.c_char_p,
                                        ctypes.POINTER(U), ctypes.POINTER(V), V], I),
      'SecKeychainItemFreeContent': ([V, V], I),
      'SecKeychainLock': ([V], I),
    }
    for name,(args,result) in signatures.items():
        function = getattr(sec, name); function.argtypes = args; function.restype = result
    cf.CFRelease.argtypes = [V]; cf.CFRelease.restype = None
    return sec, cf


def handle_path(sec, handle, root):
    size = ctypes.c_uint32(8192)
    buf = ctypes.create_string_buffer(size.value)
    status = sec.SecKeychainGetPath(handle, ctypes.byref(size), buf)
    if status != 0:
        raise Refusal('native_path')
    path = Path(os.fsdecode(buf.value))
    if path.parent != root or path.name not in {'fixture.keychain', 'fixture.keychain-db'}:
        raise Refusal('native_scope')
    ordinary(path)
    return str(path)


def read_fixture(root: Path, expected_root: dict, *, api=None, trace=None):
    """Return a mutable private payload only after native cleanup succeeds."""
    validate_root(root, expected_root)
    fixture = root / 'fixture.keychain'
    ordinary(fixture)
    if hashlib.sha256(fixture.read_bytes()).hexdigest() != FIXTURE_SHA:
        raise Refusal('fixture_digest')
    sec, cf = native_api() if api is None else api
    events = []
    if trace is not None: trace['events'] = events
    handle = ctypes.c_void_p(); data = ctypes.c_void_p()
    length = ctypes.c_uint32(); payload = bytearray(); cleanup_errors = []
    opened = False; private_handle_validated = False; native_buffer_zeroed = False; succeeded = False
    def require(stage, status):
        events.append({'stage':stage, 'status':int(status)})
        if status != 0:
            raise Refusal(stage)
    try:
        require('interaction_disabled', sec.SecKeychainSetUserInteractionAllowed(False))
        require('open_explicit_fixture', sec.SecKeychainOpen(os.fsencode(fixture), ctypes.byref(handle)))
        if not handle.value:
            raise Refusal('null_handle')
        opened = True
        handle_path(sec, handle, root)
        private_handle_validated = True
        password = ctypes.create_string_buffer(PUBLIC_UNLOCK_PASSWORD)
        try:
            require('unlock_explicit_fixture', sec.SecKeychainUnlock(
                handle, len(PUBLIC_UNLOCK_PASSWORD), password, True))
        finally:
            ctypes.memset(password, 0, ctypes.sizeof(password))
        handle_path(sec, handle, root)
        require('find_explicit_fixture_item', sec.SecKeychainFindGenericPassword(
            handle, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT,
            ctypes.byref(length), ctypes.byref(data), None))
        if not data.value or length.value == 0 or length.value > 65536:
            raise Refusal('invalid_payload')
        payload.extend(ctypes.string_at(data, length.value))
        handle_path(sec, handle, root)
        succeeded = True
    finally:
        # Native buffer is zeroed before its supported free routine. Python and
        # product Secret strings do not promise secure memory erasure.
        if data.value:
            if length.value <= 65536:
                ctypes.memset(data, 0, length.value); native_buffer_zeroed = True
            status = int(sec.SecKeychainItemFreeContent(None, data))
            if status != 0: cleanup_errors.append('free_content')
        if private_handle_validated:
            status = int(sec.SecKeychainLock(handle))
            if status != 0: cleanup_errors.append('lock_private_fixture')
        if handle.value:
            cf.CFRelease(handle)
        if not succeeded or cleanup_errors:
            payload[:] = b'\0' * len(payload)
        if trace is not None:
            trace.update({'nativeHandleOpened':opened,'nativeBufferZeroed':native_buffer_zeroed,
                          'nativeCleanupSucceeded':not cleanup_errors,'explicitHandleOnly':True})
        if cleanup_errors:
            raise Refusal('native_cleanup')
    return payload, {'events':events, 'nativeBufferZeroed':native_buffer_zeroed,
                     'nativeCleanupSucceeded':True, 'explicitHandleOnly':True}


def main():
    # Reader is deliberately usable only beneath the pinned installed client.
    # This JSON is a live parent-child linkage, never adoption of native owners.
    if len(sys.argv) != 3:
        return 2
    root = Path(sys.argv[1]); admission = Path(sys.argv[2]); payload = bytearray()
    root_validated = False; details = {}
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(number, lambda signum, frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    result = {'schema':'mycel-public-fixture-reader-observation-v1', 'passed':False,
              'pid':os.getpid(), 'parentPid':os.getppid(), 'credentialOutputPersisted':False,
              'nativeItemCreated':False, 'ownerKeychainSelected':False}
    try:
        ordinary(admission)
        if admission.parent != root:
            raise Refusal('admission_scope')
        auth = json.loads(admission.read_text())
        if (auth['clientPid'] != os.getppid() or auth['readerSha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                or auth['fixtureSha256'] != FIXTURE_SHA):
            raise Refusal('parent_link')
        validate_root(root, auth['rootIdentity']); root_validated = True
        with (root/'reader-live.json').open('x') as f:
            json.dump({'pid':os.getpid(),'pgid':os.getpgrp(),'parentPid':os.getppid(),
                       'readerSha256':auth['readerSha256']},f)
        payload, details = read_fixture(root, auth['rootIdentity'], trace=details)
        result.update(details); result['passed'] = True
        # Persist sanitized metadata BEFORE private output is handed to the
        # installed reader. A killed process never acquires a success claim.
        with (root/'reader-status.json').open('x') as f:
            json.dump(result, f); f.write('\n')
        view = memoryview(payload)
        while view:
            written = os.write(1, view)
            if written <= 0: raise Refusal('private_pipe')
            view = view[written:]
        return 0
    except BaseException:
        # Never print exception objects, streams, passwords or arbitrary bytes.
        return 1
    finally:
        payload[:] = b'\0' * len(payload)
        if root_validated and not (root/'reader-status.json').exists():
            result.update(details)
            try:
                with (root/'reader-status.json').open('x') as f:
                    json.dump(result,f); f.write('\n')
            except BaseException:
                pass

if __name__ == '__main__':
    raise SystemExit(main())
