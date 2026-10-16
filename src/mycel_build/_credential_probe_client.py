"""Actual installed Credentials boundary; entered only by reviewed outer controls.

The public fixture value travels from the native reader through production
run_child into Credentials in memory. No value, length or digest is reported.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import sys


def bound(row):
    p = Path(row['path'])
    if not p.is_absolute() or p.resolve(strict=True) != p or not p.is_file():
        raise RuntimeError('binding')
    if hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
        raise RuntimeError('digest')
    return p


def preferences():
    """Read-only path metadata. No keychain item/ACL or secret is queried."""
    sec = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    V=ctypes.c_void_p; U=ctypes.c_uint32; I=ctypes.c_int32
    sec.SecKeychainCopySearchList.argtypes=[ctypes.POINTER(V)]; sec.SecKeychainCopySearchList.restype=I
    sec.SecKeychainCopyDefault.argtypes=[ctypes.POINTER(V)]; sec.SecKeychainCopyDefault.restype=I
    sec.SecKeychainGetPath.argtypes=[V,ctypes.POINTER(U),V]; sec.SecKeychainGetPath.restype=I
    cf.CFArrayGetCount.argtypes=[V]; cf.CFArrayGetCount.restype=ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes=[V,ctypes.c_long]; cf.CFArrayGetValueAtIndex.restype=V
    cf.CFRelease.argtypes=[V]; cf.CFRelease.restype=None
    def path(handle):
        size=U(8192); buffer=ctypes.create_string_buffer(size.value)
        status=int(sec.SecKeychainGetPath(handle,ctypes.byref(size),buffer))
        if status: raise RuntimeError('preference_path')
        return os.fsdecode(buffer.value)
    search=V(); default=V(); result={}
    try:
        status=int(sec.SecKeychainCopySearchList(ctypes.byref(search)))
        if status or not search.value: raise RuntimeError('search_metadata')
        count=cf.CFArrayGetCount(search)
        if not 0 <= count <= 128: raise RuntimeError('search_count')
        result['searchList']=[path(cf.CFArrayGetValueAtIndex(search,i)) for i in range(count)]
        status=int(sec.SecKeychainCopyDefault(ctypes.byref(default)))
        # A genuine no-default result is observable, never replaced or repaired.
        if status not in {0,-25307}: raise RuntimeError('default_metadata')
        if (status==0) != bool(default.value): raise RuntimeError('default_shape')
        result['defaultStatus']=status; result['defaultPath']=path(default) if default.value else None
        return result
    finally:
        if default.value: cf.CFRelease(default)
        if search.value: cf.CFRelease(search)


def main():
    if len(sys.argv)!=3: return 2
    root=Path(sys.argv[1]); context_path=Path(sys.argv[2]); report={
      'schema':'mycel-syl148-public-fixture-installed-credential-observation-v1',
      'passed':False,'errors':[], 'installedCredentialsRead':False,
      'dummyValueMatchedPrivately':False,'credentialOutputPersisted':False,
      'nativeItemCreated':False,'providerCalls':0,'databaseConnections':0,
      'ownerPreferencesRestored':False,'daemonIsolationClaimed':False,
      'pid':os.getpid(),'parentPid':os.getppid(),
    }
    for number in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM):
        signal.signal(number,lambda signum,frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    before=None; after=None; root_validated=False
    try:
        context=json.loads(context_path.read_text())
        # Parent supplied a live root descriptor after its exclusive allocation.
        admission=json.loads((root/'client-admission.json').read_text())
        st=root.lstat()
        if (root.parent!=Path('/private/tmp') or root.resolve()!=root or '/login.keychain' in str(root)
            or not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o700 or st.st_uid!=os.getuid()
            or admission['parentPid']!=os.getppid() or admission['contextSha256']!=hashlib.sha256(context_path.read_bytes()).hexdigest()
            or admission['rootIdentity']!={'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'mode':0o700}):
            raise RuntimeError('live_root')
        root_validated=True
        program=Path(context['program'])
        if program.resolve(strict=True)!=program or Path(sys.executable).resolve()!=Path(context['interpreter']['resolvedPath']):
            raise RuntimeError('installed_interpreter')
        reader=bound(context['reader']); bound(context['client'])
        for row in context['installedModules'].values(): bound(row)
        # This is the exact literal command production resolve_command will use.
        command=[str(Path(sys.executable).resolve()),'-I','-B',str(reader),str(root),str(root/'reader-admission.json')]
        def audit(event,args):
            if event.startswith('socket.') or event in {'os.system','os.posix_spawn','os.posix_spawnp'}:
                raise RuntimeError('external_operation')
            if event=='subprocess.Popen':
                if list(args[1])!=command: raise RuntimeError('unapproved_child')
                with (root/'reader-launch-attempt.json').open('x') as f:
                    json.dump({'clientPid':os.getpid(),'readerSha256':context['reader']['sha256']},f)
        sys.addaudithook(audit)
        # No development path is inserted. -I uses the current staged installed wheel.
        from mycel._credentials import Credentials
        from mycel._settings import load_settings
        from mycel._safeguards import InvocationPolicy
        import mycel._credentials as credentials_module
        import mycel._settings as settings_module
        import mycel._safeguards as safeguards_module
        for name,module in [('credentials',credentials_module),('settings',settings_module),('safeguards',safeguards_module)]:
            if Path(module.__file__).resolve()!=Path(context['installedModules'][name]['path']):
                raise RuntimeError('installed_origin')
        before=preferences()
        if any(str(root) in p for p in before['searchList']) or (before['defaultPath'] and str(root) in before['defaultPath']):
            raise RuntimeError('unexpected_preference_membership')
        settings_path=root/'settings.toml'
        text='[store]\naddress = "postgresql://fixture@127.0.0.1:1/not_connected"\n[embedding]\nkey_command = '+json.dumps(command)+'\n'
        with settings_path.open('x') as f:f.write(text)
        settings_path.chmod(0o600)
        settings=load_settings(path=settings_path,home=root/'home'); settings.require_valid()
        with (root/'reader-admission.json').open('x') as f:
            json.dump({'clientPid':os.getpid(),'rootIdentity':admission['rootIdentity'],
              'readerSha256':context['reader']['sha256'],'fixtureSha256':context['fixture']['sha256']},f)
        credential=Credentials(settings,InvocationPolicy('embed'),home=root/'home').embedding_key()
        if credential is None or not secrets.compare_digest(credential.reveal(),'test_password'):
            raise RuntimeError('private_value_unavailable_or_different')
        del credential
        report['installedCredentialsRead']=True; report['dummyValueMatchedPrivately']=True
        native=json.loads((root/'reader-status.json').read_text())
        if (native.get('passed') is not True or native.get('explicitHandleOnly') is not True
            or native.get('nativeCleanupSucceeded') is not True or native.get('nativeBufferZeroed') is not True
            or native.get('parentPid')!=os.getpid()): raise RuntimeError('native_observation')
        report['readerObservation']=native
        after=preferences()
        report['ownerPreferencePathsBefore']=before; report['ownerPreferencePathsAfter']=after
        report['ownerPreferenceValuesUnchanged']=before==after
        if before!=after: raise RuntimeError('preference_values_changed')
        report['passed']=True
    except BaseException:
        # Exception objects can include arbitrary command output; never log them.
        report['errors'].append('Private fixture boundary did not complete; inspect sanitized native stages if retained.')
    finally:
        # A late metadata read failure is a failure, not an inferred unchanged state.
        if before is not None and after is None:
            try:
                after=preferences(); report['ownerPreferencePathsBefore']=before; report['ownerPreferencePathsAfter']=after
                report['ownerPreferenceValuesUnchanged']=before==after
            except BaseException: report['ownerPreferenceValuesUnchanged']=None
        report['hostKernel']=list(os.uname())
        if root_validated:
            with (root/'client-result.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    return 0 if report['passed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
