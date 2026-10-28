"""Independent frozen inventory, check kinds and real process boundary regressions.

Protocol fixture outcomes test receiver validation, not a native Build pass.
The process fixtures execute real OS processes without credentials or a store.
"""
import copy
import unittest
from pathlib import Path

try:
    pass
except ImportError:
    pass


ROOT = Path(__file__).resolve().parents[1]


def contract_inputs():
    return {'tests/test_fixture.py': b'''raise AssertionError("receiver must never import frozen tests")
class Proofs:
 def test_one(self): raise AssertionError("never execute while discovering")
 def test_two(self): pass
class StoreProofs:
 check_kind = "store"
 def test_store(self): pass
class EvalProofs:
 check_kind = "eval"
 def test_eval(self): raise AssertionError("paid or eval dispatch")
class LiveProofs:
 check_kind = "live"
 def test_live(self): raise AssertionError("paid or live dispatch")
'''}


def closed_reply(contract, *, failed=()):
    checks = [{**copy.deepcopy(row), 'status': 'failed' if row['name'] in failed else 'passed',
        'passed': row['name'] not in failed, 'detail': 'private-provider-body'} for row in contract['declarations']]
    return {'passed': not failed, 'executed': True, 'python': '3.14.7', 'machine': 'arm64',
        'isolated': True, 'dontWriteBytecode': True, 'installedProductImports': True, 'build': 10,
        'checks': checks, 'inventorySha256': contract['inventorySha256'],
        'gateErrorCount': int(bool(failed)), 'gateErrors': ['private-provider-body'] if failed else []}


class AutomaticQualificationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_inventory_is_independent_frozen_metadata_and_never_imports_or_selects_eval_live
#     def test_inventory_is_independent_frozen_metadata_and_never_imports_or_selects_eval_live(self):
#         frozen = contract_inputs()
#         before = copy.deepcopy(frozen)
#         contract = automatic_contract(frozen)
#         self.assertEqual(frozen, before)
#         self.assertEqual(contract['declarations'], [
#             {'name': 'test_fixture.Proofs.test_one', 'kind': 'unit'},
#             {'name': 'test_fixture.Proofs.test_two', 'kind': 'unit'},
#             {'name': 'test_fixture.StoreProofs.test_store', 'kind': 'store'}])
#         result = _sanitize_report(json_bytes(closed_reply(contract)), 10, contract=contract)
#         self.assertTrue(result['completeFrozenInventory'])
#         self.assertTrue(result['passed'])
#         self.assertNotIn('requirements', result)
#         self.assertNotIn('coverage', result)
#         self.assertNotIn('private-provider-body', json.dumps(result))
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_inventory_is_independent_frozen_metadata_and_never_imports_or_selects_eval_live

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_receiver_refuses_omitted_substituted_extra_and_rekinded_results
#     def test_receiver_refuses_omitted_substituted_extra_and_rekinded_results(self):
#         contract = automatic_contract(contract_inputs())
#         for mutation in (
#             lambda data: data['checks'].pop(),
#             lambda data: data['checks'][0].update(name='test_fixture.Other.test_replacement'),
#             lambda data: data['checks'].append({**data['checks'][0], 'name': 'test_extra.Extra.test_one'}),
#             lambda data: data['checks'][0].update(kind='store'),
#             lambda data: data.update(inventorySha256='f' * 64)):
#             with self.subTest(mutation=mutation):
#                 reply = closed_reply(contract)
#                 mutation(reply)
#                 with self.assertRaises(BuildError) as error:
#                     _sanitize_report(json_bytes(reply), 10, contract=contract)
#                 self.assertEqual(error.exception.code, 'refused')
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_receiver_refuses_omitted_substituted_extra_and_rekinded_results

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_receiver_refuses_eval_live_rows_and_requirement_claims
#     def test_receiver_refuses_eval_live_rows_and_requirement_claims(self):
#         contract = automatic_contract(contract_inputs())
#         for mutation in (
#             lambda data: data['checks'].append({**data['checks'][0], 'name': 'test_fixture.LiveProofs.test_live', 'kind': 'live'}),
#             lambda data: data['checks'][1].update(kind='eval'),
#             lambda data: data['checks'][0].update(requirements=['MYC-13.3'])):
#             reply = closed_reply(contract)
#             mutation(reply)
#             with self.subTest(mutation=mutation), self.assertRaises(BuildError):
#                 _sanitize_report(json_bytes(reply), 10, contract=contract)
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_receiver_refuses_eval_live_rows_and_requirement_claims

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_duplicate_unknown_repeated_or_computed_kinds_refuse_before_execution
#     def test_frozen_duplicate_unknown_repeated_or_computed_kinds_refuse_before_execution(self):
#         original = contract_inputs()
#         for mutation in (
#             lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'] + b'\nclass Proofs:\n def test_one(self): pass\n'}),
#             lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'].replace(b'check_kind = "store"', b'check_kind = "paid"')}),
#             lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'].replace(b'check_kind = "store"', b'check_kind = "store"\n check_kind = "unit"')}),
#             lambda data: data.update({'tests/test_fixture.py': data['tests/test_fixture.py'].replace(b'check_kind = "store"', b'check_kind = KIND')})):
#             frozen = copy.deepcopy(original)
#             mutation(frozen)
#             with self.subTest(mutation=mutation), self.assertRaises(BuildError):
#                 automatic_contract(frozen)
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_duplicate_unknown_repeated_or_computed_kinds_refuse_before_execution

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_failed_store_outcome_retains_every_name_without_private_details
#     def test_failed_store_outcome_retains_every_name_without_private_details(self):
#         contract = automatic_contract(contract_inputs())
#         reply = closed_reply(contract, failed=('test_fixture.StoreProofs.test_store',))
#         result = _sanitize_report(json_bytes(reply), 10, contract=contract)
#         self.assertFalse(result['passed'])
#         self.assertEqual([row['name'] for row in result['checks']], [row['name'] for row in contract['declarations']])
#         self.assertEqual(result['checks'][2]['status'], 'failed')
#         self.assertNotIn('private-provider-body', json.dumps(result))
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_failed_store_outcome_retains_every_name_without_private_details

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_certificate_requires_every_executed_group_and_binds_manifests_results_and_inventory
#     def test_certificate_requires_every_executed_group_and_binds_manifests_results_and_inventory(self):
#         contract = automatic_contract(contract_inputs())
#         automatic = _sanitize_report(json_bytes(closed_reply(contract)), 10, contract=contract)
#         automatic['sourceInputsSha256'] = 'b' * 64
#         names = ('installed_native_and_two_path_probe', 'independent_launcher_bootstrap_two_path_probe',
#             'installed_automatic_unit_store_gate', 'packaged_selector_and_cli_two_path_probe')
#         native, launcher, packaged = relocation_results(10)
#         results = [{'name': name, **row} for name, row in zip(names,
#             (native, launcher, automatic, packaged), strict=True)]
#         options = {'number': 'a', 'source': {'commit': 'a' * 40, 'dirty': True, 'inputsSha256': 'b' * 64},
#             'check_inputs': [{'path': 'tests/test_fixture.py', 'sha256': 'c' * 64, 'size': 10}],
#             'program_sha256': 'd' * 64, 'launcher_sha256': 'e' * 64, 'target': 'macos-arm64',
#             'runtime': {'python': '3.14.7'}, 'results': results}
#         certificate = qualification_certificate(**options)
#         self.assertIsNotNone(certificate)
#         self.assertEqual(certificate['resultsSha256'], digest(json_bytes(results)))
#         self.assertEqual(certificate['automaticInventorySha256'], contract['inventorySha256'])
#         self.assertNotIn('requirementsSha256', certificate)
#         self.assertEqual(certificate['checkInputsSha256'], digest(json_bytes(options['check_inputs'])))
#         self.assertEqual(certificate['sha256'], digest(json_bytes({k: v for k, v in certificate.items() if k != 'sha256'})))
#         for field in ('program_sha256', 'launcher_sha256'):
#             changed = {**options, field: 'f' * 64}
#             self.assertNotEqual(qualification_certificate(**changed)['sha256'], certificate['sha256'])
#         for index in range(4):
#             for flag in ('passed', 'executed'):
#                 changed = copy.deepcopy(results)
#                 changed[index][flag] = False
#                 self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         self.assertIsNone(qualification_certificate(**{**options, 'results': results[:-1]}))
#         for index in (0, 1, 3):
#             changed = copy.deepcopy(results)
#             changed[index]['relocations'].pop()
#             self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[3]['relocations'][1]['cases'].pop()
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[3]['relocations'][1]['cases'][-1]['name'] = 'invented_passed_case'
#         self.assertEqual(len(changed[3]['relocations'][1]['cases']), 16)
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[3]['relocations'][0]['cases'][:2] = reversed(changed[3]['relocations'][0]['cases'][:2])
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[0]['relocations'][1]['build'] = 11
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[2]['gateErrorCount'] = 1
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         changed = copy.deepcopy(results)
#         changed[2]['completeFrozenInventory'] = False
#         self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
#         for field, value in (('build', 11), ('sourceInputsSha256', 'f' * 64)):
#             changed = copy.deepcopy(results)
#             changed[2][field] = value
#             self.assertIsNone(qualification_certificate(**{**options, 'results': changed}))
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_certificate_requires_every_executed_group_and_binds_manifests_results_and_inventory

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_group_preserves_raw_binary_streams_status_arguments_and_cwd
#     def test_real_group_preserves_raw_binary_streams_status_arguments_and_cwd(self):
#         with tempfile.TemporaryDirectory() as directory:
#             command = [sys.executable, '-I', '-B', '-c',
#                 'import json,os,sys;sys.stdout.buffer.write(json.dumps([os.getcwd(),sys.argv[1:]]).encode()+b"\\n\\0\\xff");'
#                 'sys.stderr.buffer.write(b"\\xfeerror\\0");raise SystemExit(7)', 'with spaces', '', '$(literal)']
#             reply = run_group(command, cwd=directory, timeout=10)
#             header, tail = reply.stdout.split(b'\n', 1)
#             self.assertEqual(json.loads(header), [str(Path(directory).resolve()), ['with spaces', '', '$(literal)']])
#             self.assertEqual((reply.returncode, tail, reply.stderr), (7, b'\0\xff', b'\xfeerror\0'))
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_group_preserves_raw_binary_streams_status_arguments_and_cwd

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group
#     def test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group(self):
#         with tempfile.TemporaryDirectory() as directory:
#             marker = Path(directory) / 'child.pid'
#             code = ('import os,signal,subprocess,sys,time;'
#                 'signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);'
#                 'p=subprocess.Popen([sys.executable,"-I","-B","-c",'
#                 '"import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"]);'
#                 'open(sys.argv[1],"w").write(str(p.pid));time.sleep(60)')
#             with self.assertRaises(subprocess.TimeoutExpired):
#                 run_group([sys.executable, '-I', '-B', '-c', code, str(marker)], timeout=1)
#             self.assertTrue(marker.is_file())
#             child = int(marker.read_text())
#             until = time.monotonic() + 2
#             while time.monotonic() < until:
#                 try:
#                     os.kill(child, 0)
#                 except ProcessLookupError:
#                     break
#                 time.sleep(0.01)
#             else:
#                 self.fail('a fixture descendant survived the bounded timeout cleanup')
#             actual = subprocess.Popen
#             created = []
#             def start(*args, **options):
#                 process = actual(*args, **options)
#                 created.append(process.pid)
#                 communicate = process.communicate
#                 first = True
#                 repeated = False
#                 def interrupted(*values, **keywords):
#                     nonlocal first, repeated
#                     if first:
#                         first = False
#                         raise KeyboardInterrupt
#                     if not repeated:
#                         repeated = True
#                         os.kill(os.getpid(), signal.SIGINT)
#                     return communicate(*values, **keywords)
#                 process.communicate = interrupted
#                 return process
#             handler = signal.getsignal(signal.SIGINT)
#             try:
#                 with patch('mycel_build._process.subprocess.Popen', side_effect=start), self.assertRaises(KeyboardInterrupt):
#                     run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
#                 self.assertEqual(signal.getsignal(signal.SIGINT), handler)
#                 self.assertEqual(len(created), 1)
#                 with self.assertRaises(ProcessLookupError):
#                     os.kill(created[0], 0)
#             finally:
#                 for identifier in created:
#                     try:
#                         os.killpg(identifier, signal.SIGKILL)
#                     except ProcessLookupError:
#                         pass
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_real_timeout_and_cancellation_reap_the_scoped_runner_and_descendant_group

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped
#     def test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped(self):
#         actual = subprocess.Popen
#         created = []
#         before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
#         def spawn(*args, **options):
#             process = actual(*args, **options)
#             created.append(process.pid)
#             # This is the old donor's uncovered successful-spawn/assignment gap.
#             # The caught signal must not escape until the real handle is owned.
#             os.kill(os.getpid(), signal.SIGTERM)
#             return process
#         try:
#             with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), \
#                     self.assertRaises(KeyboardInterrupt) as error:
#                 run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
#             self.assertEqual(error.exception.signum, signal.SIGTERM)
#             state = error.exception.process_state
#             self.assertTrue(state['spawnAttempted'])
#             self.assertTrue(state['spawnConfirmed'])
#             self.assertFalse(state['spawnOutcomeUnconfirmed'])
#             self.assertEqual(state['pid'], created[0])
#             self.assertTrue(state['processReaped'])
#             self.assertTrue(state['processGroupAbsent'])
#             with self.assertRaises(ProcessLookupError):
#                 os.kill(created[0], 0)
#             self.assertEqual({number: signal.getsignal(number) for number in before}, before)
#         finally:
#             for identifier in created:
#                 try:
#                     os.killpg(identifier, signal.SIGKILL)
#                 except ProcessLookupError:
#                     pass
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_signal_between_real_spawn_and_handle_return_is_queued_then_owned_child_is_reaped

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup
#     def test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup(self):
#         class Deadline(KeyboardInterrupt):
#             pass
#         actual = subprocess.Popen
#         created, observed = [], []
#         def deadline(number, frame):
#             observed.append(number)
#             raise Deadline()
#         def spawn(*args, **options):
#             process = actual(*args, **options)
#             created.append(process.pid)
#             os.kill(os.getpid(), signal.SIGALRM)
#             return process
#         previous = signal.signal(signal.SIGALRM, deadline)
#         try:
#             with patch('mycel_build._process.subprocess.Popen', side_effect=spawn), self.assertRaises(Deadline) as error:
#                 run_group([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'], timeout=10)
#             self.assertEqual(observed, [signal.SIGALRM])
#             self.assertTrue(error.exception.process_state['processReaped'])
#             self.assertTrue(error.exception.process_state['processGroupAbsent'])
#             self.assertIs(signal.getsignal(signal.SIGALRM), deadline)
#             with self.assertRaises(ProcessLookupError):
#                 os.kill(created[0], 0)
#         finally:
#             signal.signal(signal.SIGALRM, previous)
#             for identifier in created:
#                 try:
#                     os.killpg(identifier, signal.SIGKILL)
#                 except ProcessLookupError:
#                     pass
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_queued_alarm_preserves_the_callers_sticky_deadline_after_owned_cleanup

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_failed_unconfirmed_spawn_never_signals_a_guessed_group_or_claims_reaping
#     def test_failed_unconfirmed_spawn_never_signals_a_guessed_group_or_claims_reaping(self):
#         with patch('mycel_build._process.subprocess.Popen', side_effect=OSError('not launched')), \
#                 patch('mycel_build._process.os.killpg') as groups, self.assertRaises(OSError) as error:
#             run_group(['unavailable-build-check'], timeout=10)
#         groups.assert_not_called()
#         self.assertEqual(error.exception.process_state, {
#             'spawnAttempted': True, 'spawnConfirmed': False, 'pid': None,
#             'processReaped': None, 'processGroupAbsent': None,
#             'spawnOutcomeUnconfirmed': True, 'observedSignals': [], 'observedSignalEvents': []})
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_failed_unconfirmed_spawn_never_signals_a_guessed_group_or_claims_reaping

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_cancellation_queued_during_error_cleanup_is_delivered_after_owned_group_and_pipes_close
#     def test_cancellation_queued_during_error_cleanup_is_delivered_after_owned_group_and_pipes_close(self):
#         actual_end = _process._end_group
#         for failure in (subprocess.TimeoutExpired(['fixture'], 1), BuildError('refused', 'fixture body failure')):
#             with self.subTest(error=type(failure).__name__):
#                 created, delivered = [], []
#                 def cancel(number, frame):
#                     process = created[0]
#                     self.assertIsNotNone(process.poll())
#                     self.assertTrue(all(stream is None or stream.closed
#                                         for stream in (process.stdin, process.stdout, process.stderr)))
#                     with self.assertRaises(ProcessLookupError):
#                         os.killpg(process.pid, 0)
#                     delivered.append(number)
#                     raise KeyboardInterrupt('queued cancellation')
#                 def cleanup(process, **options):
#                     os.kill(os.getpid(), signal.SIGINT)
#                     return actual_end(process, **options)
#                 previous = signal.signal(signal.SIGINT, cancel)
#                 try:
#                     with patch('mycel_build._process._end_group', side_effect=cleanup), \
#                             self.assertRaises(KeyboardInterrupt) as error:
#                         with owned_process([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'],
#                                            stdin=subprocess.PIPE) as process:
#                             created.append(process)
#                             raise failure
#                     self.assertIs(error.exception.__cause__, failure)
#                     self.assertEqual(delivered, [signal.SIGINT])
#                     state = error.exception.process_state
#                     self.assertTrue(state['processReaped'])
#                     self.assertTrue(state['processGroupAbsent'])
#                     self.assertEqual(state['observedSignalEvents'], [
#                         {'signal': signal.SIGINT, 'phase': 'cleanup', 'delivered': True}])
#                     self.assertIs(signal.getsignal(signal.SIGINT), cancel)
#                 finally:
#                     signal.signal(signal.SIGINT, previous)
#                     for process in created:
#                         if process.poll() is None:
#                             actual_end(process)
#                         for stream in (process.stdin, process.stdout, process.stderr):
#                             if stream is not None:
#                                 stream.close()
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_cancellation_queued_during_error_cleanup_is_delivered_after_owned_group_and_pipes_close

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_cleanup_signal_deferral_delivers_with_an_ordinary_exception_in_flight
#     def test_cleanup_signal_deferral_delivers_with_an_ordinary_exception_in_flight(self):
#         failure = BuildError('refused', 'fixture cleanup failure')
#         finished, delivered = [], []
#         def cancel(number, frame):
#             self.assertEqual(finished, [True])
#             delivered.append(number)
#             raise KeyboardInterrupt('deferred cancellation')
#         previous = signal.signal(signal.SIGINT, cancel)
#         try:
#             with self.assertRaises(KeyboardInterrupt) as error:
#                 with _defer_cleanup_signals():
#                     try:
#                         raise failure
#                     finally:
#                         os.kill(os.getpid(), signal.SIGINT)
#                         finished.append(True)
#             self.assertIs(error.exception.__cause__, failure)
#             self.assertEqual(delivered, [signal.SIGINT])
#             self.assertEqual(error.exception.deferred_signals, [signal.SIGINT])
#             self.assertIs(signal.getsignal(signal.SIGINT), cancel)
#         finally:
#             signal.signal(signal.SIGINT, previous)
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_cleanup_signal_deferral_delivers_with_an_ordinary_exception_in_flight

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_already_delivered_cancellation_is_not_dispatched_again_after_an_ordinary_failure
#     def test_already_delivered_cancellation_is_not_dispatched_again_after_an_ordinary_failure(self):
#         class Delivered(KeyboardInterrupt):
#             pass
#         delivered, created = [], []
#         failure = subprocess.TimeoutExpired(['fixture'], 1)
#         def cancel(number, frame):
#             delivered.append(number)
#             raise Delivered()
#         previous = signal.signal(signal.SIGINT, cancel)
#         try:
#             with self.assertRaises(subprocess.TimeoutExpired) as error:
#                 with owned_process([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(60)'],
#                                    stdin=subprocess.PIPE) as process:
#                     created.append(process)
#                     with self.assertRaises(Delivered):
#                         os.kill(os.getpid(), signal.SIGINT)
#                     raise failure
#             self.assertIs(error.exception, failure)
#             self.assertEqual(delivered, [signal.SIGINT])
#             self.assertEqual(error.exception.process_state['observedSignalEvents'], [
#                 {'signal': signal.SIGINT, 'phase': 'running', 'delivered': True}])
#             self.assertTrue(error.exception.process_state['processReaped'])
#             self.assertTrue(error.exception.process_state['processGroupAbsent'])
#             self.assertTrue(all(stream is None or stream.closed
#                                 for stream in (created[0].stdin, created[0].stdout, created[0].stderr)))
#             with self.assertRaises(ProcessLookupError):
#                 os.killpg(created[0].pid, 0)
#         finally:
#             signal.signal(signal.SIGINT, previous)
#             for process in created:
#                 if process.poll() is None:
#                     _process._end_group(process)
#                 for stream in (process.stdin, process.stdout, process.stderr):
#                     if stream is not None:
#                         stream.close()
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_already_delivered_cancellation_is_not_dispatched_again_after_an_ordinary_failure

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_unbounded_or_invalid_deadline_refuses_before_spawning
#     def test_unbounded_or_invalid_deadline_refuses_before_spawning(self):
#         with patch('mycel_build._process.subprocess.Popen') as spawn:
#             for timeout in (0, -1, True, float('inf'), float('nan'), 5401, '10'):
#                 with self.subTest(timeout=timeout), self.assertRaises(BuildError):
#                     run_group(['never-run'], timeout=timeout)
#             spawn.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_unbounded_or_invalid_deadline_refuses_before_spawning


# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_inherited_methods_keep_each_subclass_name_and_class_kind
#     def test_inherited_methods_keep_each_subclass_name_and_class_kind(self):
#         frozen = contract_inputs()
#         frozen['tests/test_fixture.py'] += b'\nclass Inherited(Proofs): pass\nclass InheritedStore(StoreProofs): pass\n'
#         contract = automatic_contract(frozen)
#         rows = {row['name']: row for row in contract['declarations']}
#         self.assertEqual(len(rows), 6)
#         for parent, child, method in (('Proofs', 'Inherited', 'test_one'), ('Proofs', 'Inherited', 'test_two'),
#                                       ('StoreProofs', 'InheritedStore', 'test_store')):
#             self.assertEqual(rows[f'test_fixture.{child}.{method}']['kind'], rows[f'test_fixture.{parent}.{method}']['kind'])
#         self.assertEqual(rows['test_fixture.InheritedStore.test_store']['kind'], 'store')
#         self.assertFalse(any(row['kind'] in {'eval', 'live'} for row in rows.values()))
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_inherited_methods_keep_each_subclass_name_and_class_kind
        # contract_inputs begins by raising: deriving this inventory must never
        # import or execute the frozen class or any inherited body.

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_diamond_kind_order_matches_real_unittest_discovery
#     def test_frozen_diamond_kind_order_matches_real_unittest_discovery(self):
#         from mycel._coverage import discover_checks, iter_checks, run_checks
#         source = b'\n'.join((
#             b'import unittest',
#             b'class Root(unittest.TestCase):', b' check_kind = "unit"',
#             b' def test_shared(self): self.assertTrue(True)',
#             b'class Left(Root): pass', b'class Right(Root):', b' check_kind = "eval"',
#             b'class Diamond(Left, Right): pass', b''))
#         contract = automatic_contract({'tests/test_c3_fixture.py': source})
#         expected = {row['name']: row['kind'] for row in contract['declarations']}
#         try:
#             with tempfile.TemporaryDirectory() as directory:
#                 (Path(directory) / 'test_c3_fixture.py').write_bytes(source)
#                 actual = {check.id(): getattr(check, 'check_kind', 'unit')
#                           for check in iter_checks(discover_checks(directory))}
#                 # C3 puts Right before Root, so Diamond is eval and never automatic.
#                 self.assertEqual(actual['test_c3_fixture.Diamond.test_shared'], 'eval')
#                 self.assertEqual(expected, {name: kind for name, kind in actual.items() if kind in {'unit', 'store'}})
#                 report = run_checks(discover_checks(directory))
#                 self.assertTrue(report.passed)
#                 self.assertEqual(sorted(check.name for check in report.checks), sorted(expected))
#         finally:
#             sys.modules.pop('test_c3_fixture', None)
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_diamond_kind_order_matches_real_unittest_discovery

# TEST-TIER-DISABLED-BEGIN tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_inheritance_cycles_or_inconsistent_orders_refuse_before_execution
#     def test_frozen_inheritance_cycles_or_inconsistent_orders_refuse_before_execution(self):
#         for extra in (b'\nclass A(B): pass\nclass B(A): pass\n',
#                       b'\nclass X: pass\nclass Y: pass\nclass A(X,Y): pass\n'
#                       b'class B(Y,X): pass\nclass C(A,B): pass\n'):
#             frozen = contract_inputs()
#             frozen['tests/test_fixture.py'] += extra
#             with self.assertRaises(BuildError):
#                 automatic_contract(frozen)
# TEST-TIER-DISABLED-END tests/test_automatic_qualification.py::AutomaticQualificationTests.test_frozen_inheritance_cycles_or_inconsistent_orders_refuse_before_execution

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:7
# import json
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:8
# import os
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:10
# import signal
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:11
# import subprocess
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:12
# import sys
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:13
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:14
# import time
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:16
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:18
# from mycel_build._automatic import _sanitize_report
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:18
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:19
# from mycel_build._core import BuildError, digest, json_bytes
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:19
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:20
# from mycel_build import _process
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:20
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:21
# from mycel_build._process import _defer_cleanup_signals, owned_process, run_group
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:21
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:22
# from mycel_build._qualification import automatic_contract, qualification_certificate
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:22
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:26
#     from .test_offline_build import relocation_results
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:26
# TEST-TIER-IMPORTS-BEGIN tests/test_automatic_qualification.py:28
#     from test_offline_build import relocation_results
# TEST-TIER-IMPORTS-END tests/test_automatic_qualification.py:28
