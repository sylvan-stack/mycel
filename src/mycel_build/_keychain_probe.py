"""Actual installed reader over a current owned public-dummy Keychain copy.

No item creation/deletion/default/search-list setters or provider/DB APIs exist
on this path. Preference equality is scoped to the actual probe profile view.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from ._core import BuildError, digest, json_bytes, read_json, validate_manifest
from ._credential_contract import (FALSE_FIELDS, TRUE_FIELDS, HELPERS, PROVENANCE,
                                    credential_probe_passed, public_fixture)
from ._process import owned_process, group_absent, _defer_cleanup_signals


def _binding(path):
    return {'path':str(path),'sha256':digest(path.read_bytes())}


def _root_identity(root):
    st=root.lstat()
    if (root.resolve()!=root or root.parent!=Path('/private/tmp') or '/login.keychain' in str(root)
        or not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o700 or st.st_uid!=os.getuid()
        or any((p/'.git').exists() for p in (root,*root.parents))):
        raise BuildError('refused','The private credential fixture location is unsafe.')
    return {'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'mode':0o700}


def _safe_remove(root,identity):
    if _root_identity(root)!=identity: return False
    entries=list(root.rglob('*'))
    if len(entries)>512 or any(p.is_symlink() or p.lstat().st_uid!=os.getuid()
        or not (p.is_dir() or (p.is_file() and p.lstat().st_nlink==1)) for p in entries):
        return False
    shutil.rmtree(root)
    return not root.exists()


def _reader_cleanup(root,*,client_pid,reader_sha):
    marker=root/'reader-live.json'
    if not marker.exists():
        return None, (root/'reader-launch-attempt.json').exists()
    if marker.is_symlink() or marker.stat().st_nlink!=1:
        raise BuildError('refused','The current credential reader marker is unsafe.')
    live=read_json(marker)
    if (type(live.get('pid')) is not int or type(live.get('pgid')) is not int
        or live['pid']<=0 or live['pgid']<=0 or live['pgid']==os.getpgrp()
        or live['pid']!=live['pgid'] or live.get('parentPid')!=client_pid
        or live.get('readerSha256')!=reader_sha):
        raise BuildError('refused','The current credential reader launch is unconfirmed.')
    # This startup marker belongs to the CURRENT pinned child below the live
    # parent handle. It never adopts a historical process or native keychain.
    for number in (signal.SIGINT,signal.SIGTERM,signal.SIGKILL):
        if group_absent(live['pgid']): return True,False
        try: os.killpg(live['pgid'],number)
        except ProcessLookupError: return True,False
        until=time.monotonic()+1
        while time.monotonic()<until:
            if group_absent(live['pgid']): return True,False
            time.sleep(.01)
    return group_absent(live['pgid']),False


def _run_installed(context,root,status,*,timeout):
    context_path=root/'context.json';context_path.write_bytes(json_bytes(context))
    (root/'client-admission.json').write_bytes(json_bytes({'parentPid':os.getpid(),
        'contextSha256':digest(context_path.read_bytes()),'rootIdentity':_root_identity(root)}))
    home=Path.home().resolve()
    profile=('(version 1)(allow default)(deny network*)(deny file-write*)'
        '(allow file-write* (subpath '+json.dumps(str(root))+') (literal "/dev/null") (literal "/private/dev/null"))'
        '(deny file-read* (subpath '+json.dumps(str(home/'Library/Keychains'))+'))')
    command=['/usr/bin/sandbox-exec','-p',profile,context['interpreter']['resolvedPath'],'-I','-B',
             context['client']['path'],str(root),str(context_path)]
    status['spawnAttempted']=True
    try:
        with owned_process(command,cwd=root,env={'HOME':str(home),'TMPDIR':str(root/'temp'),
            'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8'},stdin=subprocess.PIPE) as process:
            status['pid']=process.pid
            output,errors=process.communicate(input=b'',timeout=timeout)
            status['unexpectedStreams']=bool(output or errors)
            # Neither arbitrary stream is persisted, hashed or included in errors.
            if output or errors or process.returncode!=0:
                raise BuildError('refused','The installed private credential client did not pass.')
            result=read_json(root/'client-result.json')
            if result.get('passed') is not True: raise BuildError('refused','The private credential observation did not pass.')
        status.update(processReaped=process.returncode is not None,processGroupAbsent=group_absent(process.pid))
        return result
    except BaseException as error:
        actual=getattr(error,'process_state',{})
        status.update(actual)
        raise


def probe_private_keychain(program: Path, target: str, *, source_root: Path, number: str,
                           source_identity: dict | None = None, program_manifest: list | None = None,
                           timeout=30) -> dict:
    """Run a new credential fixture for this staged Build; never replay a receipt."""
    started=time.monotonic();root=None;identity=None;frozen=None;client=None;status={};check_inputs=[]
    result={'schemaVersion':2,'mechanism':'public_apple_fixture_explicit_handle_key_command',
        'passed':False,'executed':False,'target':target,'build':int(number,16),
        'sourceInputsSha256':None,'programManifestSha256':None,'fixtureProvenance':dict(PROVENANCE),
        'helperSha256':{},'profilePreferenceValues':None,'nativeApiEvents':[],
        'observedSignals':[],'errors':[],'reason':'The current private credential check did not complete.'}
    result.update({k:False for k in TRUE_FIELDS});result.update({k:False for k in FALSE_FIELDS})
    try:
        if (target!='macos-arm64' or sys.platform!='darwin' or type(timeout) not in {int,float}
            or not math.isfinite(timeout) or not 0<timeout<=35):
            raise BuildError('refused','The private credential platform or deadline is unsupported.')
        if not isinstance(source_identity,dict) or not isinstance(program_manifest,list):
            raise BuildError('refused','Current Build credential provenance is required.')
        from ._staging import source_inputs, check_input_manifest, input_manifest
        current,frozen=source_inputs(source_root)
        if current!=source_identity: raise BuildError('refused','Current source changed before credential qualification.')
        check_inputs=check_input_manifest(input_manifest(frozen))
        program=program.resolve(strict=True)
        expected=digest(json_bytes(program_manifest));validate_manifest(program,program_manifest,expected)
        result.update(sourceInputsSha256=current['inputsSha256'],programManifestSha256=expected,
                      helperSha256={p:digest(frozen[p]) for p in HELPERS})
        raw=public_fixture(frozen)
        root=Path(tempfile.mkdtemp(prefix='mycel-public-fixture-',dir='/private/tmp')).resolve();root.chmod(0o700)
        identity=_root_identity(root)
        (root/'fixture.keychain').write_bytes(raw);(root/'fixture.keychain').chmod(0o600)
        for directory in ('home','temp'):(root/directory).mkdir(mode=0o700)
        for name,source in [('reader.py',HELPERS[0]),('client.py',HELPERS[1])]:
            (root/name).write_bytes(frozen[source]);(root/name).chmod(0o600)
        modules={}
        for name in ('credentials','settings','safeguards'):
            path=program/f'runtime/lib/python3.14/site-packages/mycel/_{name}.py'
            if path.read_bytes()!=frozen[f'src/mycel/_{name}.py']:
                raise BuildError('refused','Installed credential modules differ from current source.')
            modules[name]=_binding(path)
        interpreter=(program/'runtime/bin/python3').resolve(strict=True)
        if not interpreter.is_relative_to(program):raise BuildError('refused','Installed interpreter escaped its Build.')
        context={'program':str(program),'interpreter':{'resolvedPath':str(interpreter)},
            'reader':_binding(root/'reader.py'),'client':_binding(root/'client.py'),'installedModules':modules,
            'fixture':{'sha256':PROVENANCE['sha256']}}
        result['privateFixtureMaterialized']=True;result['executed']=True
        client=_run_installed(context,root,status,timeout=timeout)
        native=client['readerObservation']
        result.update(privateNativeHandleValidated=native.get('explicitHandleOnly') is True,
            installedCredentialsRead=client.get('installedCredentialsRead') is True,
            dummyValueMatchedPrivately=client.get('dummyValueMatchedPrivately') is True,
            nativeBufferZeroed=native.get('nativeBufferZeroed') is True,
            nativeCleanupSucceeded=native.get('nativeCleanupSucceeded') is True,
            clientNetworkDenied=True,clientKeychainFileReadDenialApplied=True,
            nativeApiEvents=native.get('events',[]),profilePreferenceValues={'scope':'probe_profile_view',
                'before':client['ownerPreferencePathsBefore'],'after':client['ownerPreferencePathsAfter'],
                'unchanged':client.get('ownerPreferenceValuesUnchanged') is True})
    except (KeyboardInterrupt,SystemExit):
        result['interrupted']=True
        raise
    except Exception:
        result['errors'].append('The current private credential observation failed or was unavailable.')
    finally:
        with _defer_cleanup_signals():
            try:
                result['observedSignals']=list(status.get('observedSignals',[]))
                result['unknownLaunch']=bool(status.get('spawnOutcomeUnconfirmed') or
                    (status.get('spawnAttempted') and not status.get('pid')))
                result['clientProcessReaped']=status.get('processReaped') is True
                result['clientProcessGroupAbsent']=status.get('processGroupAbsent') is True
                if root is not None and identity is not None:
                    reader_absent,unknown=_reader_cleanup(root,client_pid=status.get('pid'),
                        reader_sha=digest(frozen[HELPERS[0]]))
                    result['privateReaderGroupAbsent']=reader_absent is True
                    result['unknownLaunch'] |= unknown
                    if (result['clientProcessGroupAbsent'] and reader_absent is True
                        and not result['unknownLaunch']):result['fixtureCleaned']=_safe_remove(root,identity)
                    if not result['fixtureCleaned']:result['retainedPrivateFixture']=str(root)
                if frozen is not None:
                    after,_=source_inputs(source_root)
                    validate_manifest(program,program_manifest,digest(json_bytes(program_manifest)))
                    result['programAndSourcePreserved']=after==source_identity
            except Exception:
                result['errors'].append('Private credential cleanup or retained-input verification failed.')
            result['elapsedSeconds']=max(0,time.monotonic()-started)
    if source_identity is not None and frozen is not None:
        result['passed']=credential_probe_passed({**result,'passed':True},number=number,target=target,
            source_sha256=source_identity['inputsSha256'],program_sha256=result['programManifestSha256'],check_inputs=check_inputs)
    result['reason']='The current installed private credential check passed.' if result['passed'] else result['reason']
    return result
