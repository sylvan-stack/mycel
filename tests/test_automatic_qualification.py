"""Independent frozen inventory, proof-map and real process boundary regressions.

Protocol fixture outcomes test receiver validation, not a native Build pass.
The process fixtures execute real OS processes without credentials or a store.
"""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel_build._automatic import _sanitize_report
from mycel_build._core import BuildError, digest, json_bytes
from mycel_build import _process
from mycel_build._process import _defer_cleanup_signals, owned_process, run_group
from mycel_build._qualification import automatic_contract, qualification_certificate, requirement_results


try:
    from .test_offline_build import relocation_results
except ImportError:
    from test_offline_build import relocation_results


ROOT = Path(__file__).resolve().parents[1]


def contract_inputs():
    return {'src/mycel/data/requirements.json': (ROOT / 'src/mycel/data/requirements.json').read_bytes(),
        'checks/claims.json': json_bytes({'schema_version': 1, 'implemented': {
            'MYC-13.3': ['test_fixture.Proofs.test_two', 'test_fixture.Proofs.test_one'],
            'MYC-13.4': ['test_fixture.Proofs.test_store'], 'MYC-13.15': ['test_fixture.Proofs.test_one']}}),
        'tests/test_fixture.py': b'''raise AssertionError("receiver must never import frozen tests")
class Proofs:
 @proves("MYC-13.3", "MYC-13.15")
 def test_one(self): raise AssertionError("never execute while discovering")
 @proves("MYC-13.3")
 def test_two(self): pass
 @proves("MYC-13.4", kind="store")
 def test_store(self): pass
 @proves("MYC-13.20", kind="eval")
 def test_eval(self): raise AssertionError("paid or eval dispatch")
 @proves("MYC-13.9", kind="live")
 def test_live(self): raise AssertionError("paid or live dispatch")
'''}


def closed_reply(contract, *, failed=()):
    checks = [{**copy.deepcopy(row), 'status': 'failed' if row['name'] in failed else 'passed',
        'passed': row['name'] not in failed, 'detail': 'private-provider-body'} for row in contract['declarations']]
    requirements = requirement_results(contract, checks)
    implemented = sum(row['status'] == 'implemented' for row in requirements.values())
    return {'passed': not failed, 'executed': True, 'python': '3.14.7', 'machine': 'arm64',
        'isolated': True, 'dontWriteBytecode': True, 'installedProductImports': True, 'build': 10,
        'checks': checks, 'requirements': requirements, 'inventorySha256': contract['inventorySha256'],
        'coverage': {'active': 332, 'implemented': implemented, 'pending': 332 - implemented},
        'gateErrorCount': int(bool(failed)), 'gateErrors': ['private-provider-body'] if failed else []}


def complete_automatic_contract():
    """Synthetic receiver protocol only; no fixture method is executed here."""
    frozen = contract_inputs()
    registry = json.loads(frozen['src/mycel/data/requirements.json'])['requirements']
    declarations, claims = [], {}
    for kind in ('unit', 'store'):
        identifiers = [row['id'] for row in registry if row['kind'] == kind]
        name = 'test_complete.Automatic.test_' + kind
        claims.update({key: [name] for key in identifiers})
        declarations.append(' @proves(' + ', '.join(repr(key) for key in identifiers)
                            + ', kind=' + repr(kind) + ')\n def test_' + kind + '(self): pass\n')
    frozen.pop('tests/test_fixture.py')
    frozen['tests/test_complete.py'] = ('class Automatic:\n' + ''.join(declarations)).encode()
    frozen['checks/claims.json'] = json_bytes({'schema_version': 1, 'implemented': claims})
    return automatic_contract(frozen)


class AutomaticQualificationTests(unittest.TestCase):
    @proves('MYC-13.1', 'MYC-13.2', 'MYC-13.3', 'MYC-13.15', kind='unit')
    def test_inventory_is_independent_frozen_metadata_and_never_imports_or_selects_eval_live(self):
        frozen = contract_inputs()
        before = copy.deepcopy(frozen)
        contract = automatic_contract(frozen)
        self.assertEqual(frozen, before)
        self.assertEqual([row['name'] for row in contract['declarations']], [
            'test_fixture.Proofs.test_one', 'test_fixture.Proofs.test_store', 'test_fixture.Proofs.test_two'])
        self.assertEqual([row['kind'] for row in contract['declarations']], ['unit', 'store', 'unit'])
        self.assertEqual(contract['declarations'][0]['requirements'], ['MYC-13.3', 'MYC-13.15'])
        result = _sanitize_report(json_bytes(closed_reply(contract)), 10, contract=contract)
        self.assertTrue(result['completeFrozenInventory'])
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['requirements']), 332)
        self.assertEqual(result['requirements']['MYC-13.3']['verified_by'],
            ['test_fixture.Proofs.test_two', 'test_fixture.Proofs.test_one'])
        for key in ('MYC-13.9', 'MYC-13.20'):
            self.assertEqual(result['requirements'][key]['status'], 'pending')
            self.assertEqual(result['requirements'][key]['verified_by'], [])
        self.assertNotIn('private-provider-body', json.dumps(result))

    @proves('MYC-13.1', 'MYC-13.3', 'MYC-13.15', kind='unit')
    def test_receiver_refuses_omitted_substituted_extra_and_reordered_requirement_results(self):
        contract = automatic_contract(contract_inputs())
        for mutation in (
            lambda data: data['checks'].pop(),
            lambda data: data['checks'][0].update(name='test_fixture.Other.test_replacement'),
            lambda data: data['checks'].append({**data['checks'][0], 'name': 'test_extra.Extra.test_one'}),
            lambda data: data['checks'][0]['requirements'].reverse(),
            lambda data: data['checks'][0].update(kind='store'),
            lambda data: data.update(inventorySha256='f' * 64)):
            with self.subTest(mutation=mutation):
                reply = closed_reply(contract)
                mutation(reply)
                # Even a child's self-consistent proof map cannot define what
                # the independently frozen receiver expected to execute.
                reply['requirements'] = requirement_results(contract, reply['checks'])
                count = sum(row['status'] == 'implemented' for row in reply['requirements'].values())
                reply['coverage'].update(implemented=count, pending=332 - count)
                with self.assertRaises(BuildError) as error:
                    _sanitize_report(json_bytes(reply), 10, contract=contract)
                self.assertEqual(error.exception.code, 'refused')

    @proves('MYC-13.2', 'MYC-13.15', kind='unit')
    def test_full_proof_map_refuses_fabricated_provider_acceptance_counts_and_claim_order(self):
        contract = automatic_contract(contract_inputs())
        for mutation in (
            lambda data: data['requirements']['MYC-13.3']['verified_by'].reverse(),
            lambda data: data['requirements']['MYC-13.9'].update(status='implemented', verified_by=['saved.live.report']),
            lambda data: data['requirements']['MYC-13.20'].update(status='implemented', verified_by=['saved.eval.report']),
            lambda data: data['requirements'].pop('MYC-9.10'),
            lambda data: data['coverage'].update(implemented=332, pending=0)):
            reply = closed_reply(contract)
            mutation(reply)
            with self.subTest(mutation=mutation), self.assertRaises(BuildError):
                _sanitize_report(json_bytes(reply), 10, contract=contract)

    @proves('MYC-13.3', 'MYC-13.15', kind='unit')
    def test_frozen_missing_duplicate_wrong_kind_and_unmapped_claims_refuse_before_execution(self):
        original = contract_inputs()
        for mutation in (
            lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'].replace(b'@proves("MYC-13.3")', b'@unknown')}),
            lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'] + b'\nclass Proofs:\n @proves("MYC-13.3")\n def test_one(self): pass\n'}),
            lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'].replace(b'"MYC-13.4", kind="store"', b'"MYC-13.4", kind="unit"')}),
            lambda data: data.update({'checks/claims.json': json_bytes({'schema_version': 1, 'implemented': {'MYC-13.3': ['not.executed']}})})):
            frozen = copy.deepcopy(original)
            mutation(frozen)
            with self.subTest(mutation=mutation), self.assertRaises(BuildError):
                automatic_contract(frozen)

    @proves('MYC-13.1', 'MYC-13.15', kind='unit')
    def test_failed_store_outcome_retains_every_name_and_pending_requirement_without_private_details(self):
        contract = automatic_contract(contract_inputs())
        reply = closed_reply(contract, failed=('test_fixture.Proofs.test_store',))
        result = _sanitize_report(json_bytes(reply), 10, contract=contract)
        self.assertFalse(result['passed'])
        self.assertEqual([row['name'] for row in result['checks']], [row['name'] for row in contract['declarations']])
        self.assertEqual(result['checks'][1]['status'], 'failed')
        self.assertEqual(result['requirements']['MYC-13.4']['status'], 'pending')
        self.assertEqual(result['requirements']['MYC-13.3']['status'], 'implemented')
        self.assertNotIn('private-provider-body', json.dumps(result))

    @proves('MYC-13.1', 'MYC-13.15', 'MYC-13.16', kind='unit')
    def test_certificate_requires_every_executed_group_and_binds_manifests_results_and_proofs(self):
        contract = complete_automatic_contract()
        automatic = _sanitize_report(json_bytes(closed_reply(contract)), 10, contract=contract)
        automatic['sourceInputsSha256'] = 'b' * 64
        names = ('installed_native_and_two_path_probe', 'independent_launcher_bootstrap_two_path_probe',
            'installed_automatic_unit_store_gate', 'packaged_selector_and_cli_two_path_probe')
        native, launcher, packaged = relocation_results(10)
        results = [{'name': name, **row} for name, row in zip(names,
            (native, launcher, automatic, packaged), strict=True)]
        options = {'number': 'a', 'source': {'commit': 'a' * 40, 'dirty': True, 'inputsSha256': 'b' * 64},
            'check_inputs': [{'path': 'tests/test_fixture.py', 'sha256': 'c' * 64, 'size': 10}],
            'program_sha256': 'd' * 64, 'launcher_sha256': 'e' * 64, 'target': 'macos-arm64',
            'runtime': {'python': '3.14.7'}, 'results': results}
        certificate = qualification_certificate(**options)
        self.assertIsNotNone(certificate)
        for row in automatic['requirements'].values():
            self.assertEqual(row['status'], 'implemented' if row['kind'] in {'unit', 'store'} else 'pending')
        self.assertEqual(certificate['resultsSha256'], digest(json_bytes(results)))
        self.assertEqual(certificate['requirementsSha256'], digest(json_bytes(automatic['requirements'])))
        self.assertEqual(certificate['checkInputsSha256'], digest(json_bytes(options['check_inputs'])))
        self.assertEqual(certificate['sha256'], digest(json_bytes({k: v for k, v in certificate.items() if k != 'sha256'})))
        for field in ('program_sha256', 'launcher_sha256'):
            changed = {**options, field: 'f' * 64}
            self.assertNotEqual(qualification_certificate(**changed)['sha256'], certificate['sha256'])
        for index in range(4):
            for flag in ('passed', 'executed'):
                changed = copy.deepcopy(results)
                changed[index][flag] = False
                self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        self.assertIsNone(qualification_certificate(**{**options, 'results': results[:-1]}))
        for index in (0, 1, 3):
            changed = copy.deepcopy(results)
            changed[index]['relocations'].pop()
            self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[3]['relocations'][1]['cases'].pop()
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[3]['relocations'][1]['cases'][-1]['name'] = 'invented_passed_case'
        self.assertEqual(len(changed[3]['relocations'][1]['cases']), 16)
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[3]['relocations'][0]['cases'][:2] = reversed(changed[3]['relocations'][0]['cases'][:2])
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[0]['relocations'][1]['build'] = 11
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[2]['requirements']['MYC-15.11'].update(status='pending', verified_by=[])
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        changed = copy.deepcopy(results)
        changed[2]['completeFrozenInventory'] = False
        self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
        for field, value in (('build', 11), ('sourceInputsSha256', 'f' * 64)):
            changed = copy.deepcopy(results)
            changed[2][field] = value
            self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))

    @proves('MYC-13.16', kind='unit')
    def test_real_group_preserves_raw_binary_streams_status_arguments_and_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, '-I', '-B', '-c',
                'import json,os,sys;sys.stdout.buffer.write(json.dumps([os.getcwd(),sys.argv[1:]]).encode()+b"\\n\\0\\xff");'
                'sys.stderr.buffer.write(b"\\xfeerror\\0");raise SystemExit(7)', 'with spaces', '', '$(literal)']
            reply = run_group(command, cwd=directory, timeout=10)
            header, tail = reply.stdout.split(b'\n', 1)
            self.assertEqual(json.loads(header), [str(Path(directory).resolve()), ['with spaces', '', '$(literal)']])
            self.assertEqual((reply.returncode, tail, reply.stderr), (7, b'\0\xff', b'\xfeerror\0'))

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'child.pid'
            code = ('import os,signal,subprocess,sys,time;'
                'signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                'p=subprocess.Popen([sys.executable,"-I","-B","-c",'
                '"import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"]);'
                'open(sys.argv[1],"w").write(str(p.pid));time.sleep(60)')
            with self.assertRaises(subprocess.TimeoutExpired):
                run_group([sys.executable, '-I', '-B', '-c', code, str(marker)], timeout=1)
            self.assertTrue(marker.is_file())
            child = int(marker.read_text())
            until = time.monotonic() + 2
            while time.monotonic() < until:
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail('a fixture descendant survived the bounded timeout cleanup')
            actual = subprocess.Popen
            created = []
            def start(*args, **options):
                process = actual(*args, **options)
                created.append(process.pid)
                communicate = process.communicate
                first = True
                repeated = False
                def interrupted(*values, **keywords):
                    nonlocal first, repeated
                    if first:
                        first = False
                        raise KeyboardInterrupt
                    if not repeated:
                        repeated = True
                        os.kill(os.getpid(), signal.SIGINT)
                    return communicate(*values, **keywords)
                process.communicate = interrupted
                return process
            handler = signal.getsignal(signal.SIGINT)
            try:
                with patch('mycel_build._process.subprocess.Popen', side_effect=start), self.assertRaises(KeyboardInterrupt):
                    run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
                self.assertEqual(signal.getsignal(signal.SIGINT), handler)
                self.assertEqual(len(created), 1)
                with self.assertRaises(ProcessLookupError):
                    os.kill(created[0], 0)
            finally:
                for identifier in created:
                    try:
                        os.killpg(identifier, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped(self):
        actual = subprocess.Popen
        created = []
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
        def spawn(*args, **options):
            process = actual(*args, **options)
            created.append(process.pid)
            # This is the old donor's uncovered successful-spawn/assignment gap.
            # The caught signal must not escape until the real handle is owned.
            os.kill(os.getpid(), signal.SIGTERM)
            return process
        try:
            with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), \
                    self.assertRaises(KeyboardInterrupt) as error:
                run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
            self.assertEqual(error.exception.signum, signal.SIGTERM)
            state = error.exception.process_state
            self.assertTrue(state['spawnAttempted'])
            self.assertTrue(state['spawnConfirmed'])
            self.assertFalse(state['spawnOutcomeUnconfirmed'])
            self.assertEqual(state['pid'], created[0])
            self.assertTrue(state['processReaped'])
            self.assertTrue(state['processGroupAbsent'])
            with self.assertRaises(ProcessLookupError):
                os.kill(created[0], 0)
            self.assertEqual({number: signal.getsignal(number) for number in before}, before)
        finally:
            for identifier in created:
                try:
                    os.killpg(identifier, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup(self):
        class Deadline(KeyboardInterrupt):
            pass
        actual = subprocess.Popen
        created, observed = [], []
        def deadline(number, frame):
            observed.append(number)
            raise Deadline()
        def spawn(*args, **options):
            process = actual(*args, **options)
            created.append(process.pid)
            os.kill(os.getpid(), signal.SIGALRM)
            return process
        previous = signal.signal(signal.SIGALRM, deadline)
        try:
            with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), self.assertRaises(Deadline) as error:
                run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
            self.assertEqual(observed, [signal.SIGALRM])
            self.assertTrue(error.exception.process_state['processReaped'])
            self.assertTrue(error.exception.process_state['processGroupAbsent'])
            self.assertIs(signal.getsignal(signal.SIGALRM), deadline)
            with self.assertRaises(ProcessLookupError):
                os.kill(created[0], 0)
        finally:
            signal.signal(signal.SIGALRM, previous)
            for identifier in created:
                try:
                    os.killpg(identifier, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_failed_unconfirmed_spawn_never_signals_a_guessed_group_or_claims_reaping(self):
        with patch('mycel_build._process.subprocess.Popen', side_effect=OSError('not launched')), \
                patch('mycel_build._process.os.killpg') as groups, self.assertRaises(OSError) as error:
            run_group(['unavailable-build-check'], timeout=10)
        groups.assert_not_called()
        self.assertEqual(error.exception.process_state, {
            'spawnAttempted': True, 'spawnConfirmed': False, 'pid': None,
            'processReaped': None, 'processGroupAbsent': None,
            'spawnOutcomeUnconfirmed': True, 'observedSignals': [], 'observedSignalEvents': []})

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_cancellation_queued_during_error_cleanup_is_delivered_after_owned_group_and_pipes_close(self):
        actual_end = _process._end_group
        for failure in (subprocess.TimeoutExpired(['fixture'], 1), BuildError('refused', 'fixture body failure')):
            with self.subTest(error=type(failure).__name__):
                created, delivered = [], []
                def cancel(number, frame):
                    process = created[0]
                    self.assertIsNotNone(process.poll())
                    self.assertTrue(all(stream is None or stream.closed
                                        for stream in (process.stdin, process.stdout, process.stderr)))
                    with self.assertRaises(ProcessLookupError):
                        os.killpg(process.pid, 0)
                    delivered.append(number)
                    raise KeyboardInterrupt('queued cancellation')
                def cleanup(process, **options):
                    os.kill(os.getpid(), signal.SIGINT)
                    return actual_end(process, **options)
                previous = signal.signal(signal.SIGINT, cancel)
                try:
                    with patch('mycel_build._process._end_group', side_effect=cleanup), \
                            self.assertRaises(KeyboardInterrupt) as error:
                        with owned_process([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'],
                                           stdin=subprocess.PIPE) as process:
                            created.append(process)
                            raise failure
                    self.assertIs(error.exception.__cause__, failure)
                    self.assertEqual(delivered, [signal.SIGINT])
                    state = error.exception.process_state
                    self.assertTrue(state['processReaped'])
                    self.assertTrue(state['processGroupAbsent'])
                    self.assertEqual(state['observedSignalEvents'], [
                        {'signal': signal.SIGINT, 'phase': 'cleanup', 'delivered': True}])
                    self.assertIs(signal.getsignal(signal.SIGINT), cancel)
                finally:
                    signal.signal(signal.SIGINT, previous)
                    for process in created:
                        if process.poll() is None:
                            actual_end(process)
                        for stream in (process.stdin, process.stdout, process.stderr):
                            if stream is not None:
                                stream.close()

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_cleanup_signal_deferral_delivers_with_an_ordinary_exception_in_flight(self):
        failure = BuildError('refused', 'fixture cleanup failure')
        finished, delivered = [], []
        def cancel(number, frame):
            self.assertEqual(finished, [True])
            delivered.append(number)
            raise KeyboardInterrupt('deferred cancellation')
        previous = signal.signal(signal.SIGINT, cancel)
        try:
            with self.assertRaises(KeyboardInterrupt) as error:
                with _defer_cleanup_signals():
                    try:
                        raise failure
                    finally:
                        os.kill(os.getpid(), signal.SIGINT)
                        finished.append(True)
            self.assertIs(error.exception.__cause__, failure)
            self.assertEqual(delivered, [signal.SIGINT])
            self.assertEqual(error.exception.deferred_signals, [signal.SIGINT])
            self.assertIs(signal.getsignal(signal.SIGINT), cancel)
        finally:
            signal.signal(signal.SIGINT, previous)

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_already_delivered_cancellation_is_not_dispatched_again_after_an_ordinary_failure(self):
        class Delivered(KeyboardInterrupt):
            pass
        delivered, created = [], []
        failure = subprocess.TimeoutExpired(['fixture'], 1)
        def cancel(number, frame):
            delivered.append(number)
            raise Delivered()
        previous = signal.signal(signal.SIGINT, cancel)
        try:
            with self.assertRaises(subprocess.TimeoutExpired) as error:
                with owned_process([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'],
                                   stdin=subprocess.PIPE) as process:
                    created.append(process)
                    with self.assertRaises(Delivered):
                        os.kill(os.getpid(), signal.SIGINT)
                    raise failure
            self.assertIs(error.exception, failure)
            self.assertEqual(delivered, [signal.SIGINT])
            self.assertEqual(error.exception.process_state['observedSignalEvents'], [
                {'signal': signal.SIGINT, 'phase': 'running', 'delivered': True}])
            self.assertTrue(error.exception.process_state['processReaped'])
            self.assertTrue(error.exception.process_state['processGroupAbsent'])
            self.assertTrue(all(stream is None or stream.closed
                                for stream in (created[0].stdin, created[0].stdout, created[0].stderr)))
            with self.assertRaises(ProcessLookupError):
                os.killpg(created[0].pid, 0)
        finally:
            signal.signal(signal.SIGINT, previous)
            for process in created:
                if process.poll() is None:
                    _process._end_group(process)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()

    @proves('MYC-13.1', 'MYC-13.16', kind='unit')
    def test_unbounded_or_invalid_deadline_refuses_before_spawning(self):
        with patch('mycel_build._process.subprocess.Popen') as spawn:
            for timeout in (0, -1, True, float('inf'), float('nan'), 5401, '10'):
                with self.subTest(timeout=timeout), self.assertRaises(BuildError):
                    run_group(['never-run'], timeout=timeout)
            spawn.assert_not_called()
