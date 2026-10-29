"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_evaluation_drift as _support
# from test_evaluation_drift import (
#     AT,
#     DriftCase,
#     DriftEvaluationTests,
#     EvaluationSet,
#     ExitStack,
#     Path,
#     cases,
#     json,
#     load_settings,
#     patch,
#     settings,
#     suite,
#     unittest,
# )


# class DriftEvaluationTests(_support.DriftEvaluationTests):
# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_all_cases_run_in_bounded_batches_without_provider_identity_or_measurement_claims
#     def test_all_cases_run_in_bounded_batches_without_provider_identity_or_measurement_claims(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             before = loaded.file.read_bytes()
#             clock_values = []
#             clock_mutex = threading.Lock()
#             def clock():
#                 with clock_mutex:
#                     value = len(clock_values) / 1000
#                     clock_values.append(value)
#                     return value
#             with patch('mycel._classification_runner.Credentials', side_effect=AssertionError('credentials')), \
#                     patch('mycel._classification_runner.ReviewerClient', side_effect=AssertionError('real reviewer')), \
#                     patch('mycel._database.store_connection', side_effect=AssertionError('store')):
#                 report = evaluation.run_drift_evaluation(suite(cases()), loaded, repository='fixture', build='development',
#                     dependencies=ClassifyDependencies(monotonic=clock, utc_now=lambda: AT,
#                         jev_factory=lambda *_: evaluation._Jev(), reviewer_factory=lambda *_: evaluation._Reviewer()))
#             self.assertEqual((report['cases'], report['distinctCases'], report['routedCases']), (5, 5, 2))
#             self.assertEqual([row['cases'] for row in report['batches']], [2, 2, 1])
#             self.assertTrue(all(row['correct'] for row in report['results']))
#             self.assertEqual([row['actual'] for row in report['results']],
#                              ['still_supported', 'needs_review', 'needs_review', 'unresolved', 'needs_review'])
#             self.assertEqual(report['pipeline']['mode'], 'deterministic-stand-ins')
#             self.assertEqual(report['pipeline']['reviewer']['provider'], evaluation.STANDIN_PROVIDER)
#             self.assertFalse(report['live'] or report['qualified'] or report['incomplete'])
#             self.assertEqual((report['usage'], report['cost']), (None, None))
#             self.assertAlmostEqual(report['elapsedMs'], (clock_values[-1] - clock_values[0]) * 1000)
#             self.assertGreater(report['elapsedMs'], 0)
#             self.assertTrue(all(row['usage'] is None and row['cost'] is None
#                                 and type(row['elapsedMs']) in {int, float} and math.isfinite(row['elapsedMs'])
#                                 and row['elapsedMs'] >= 0
#                                 for row in report['results']))
#             self.assertEqual(report['results'][3]['attempts'], 0)
#             self.assertNotIn('inputHash', report['results'][3])
#             self.assertEqual(loaded.file.read_bytes(), before)
#
#             # Duplicate semantic inputs share one lease counter even when all
#             # four adapters hold their evidence at the same time.
#             parallel_root = Path(temporary) / 'parallel'
#             parallel_root.mkdir()
#             parallel = settings(parallel_root, candidates=4)
#             parallel.file.write_text(parallel.file.read_text().replace('at_once=1', 'at_once=4'))
#             parallel = load_settings(path=parallel.file, home=parallel_root)
#             parallel_before = parallel.file.read_bytes()
#             stores, overlapping = [], []
#             def store_factory(*args, **kwargs):
#                 store = evaluation.FixtureStore(*args, **kwargs)
#                 stores.append(store)
#                 return store
#             def observe_overlap():
#                 with stores[0].call_mutex:
#                     overlapping.append(dict(stores[0].leases))
#             rendezvous = threading.Barrier(4, action=observe_overlap)
#             class ParallelJev(evaluation._Jev):
#                 def classify(self, *args, **kwargs):
#                     value = super().classify(*args, **kwargs)
#                     rendezvous.wait(timeout=4)
#                     return value
#             duplicates = tuple(replace(cases()[1], id='parallel-' + str(index)) for index in range(4))
#             with patch('mycel._classification_runner.Credentials', side_effect=AssertionError('credentials')), \
#                     patch('mycel._classification_runner.ReviewerClient', side_effect=AssertionError('real reviewer')), \
#                     patch('mycel._database.store_connection', side_effect=AssertionError('store')):
#                 concurrent = evaluation.run_drift_evaluation(suite(duplicates), parallel,
#                     repository='fixture', build='development', store_factory=store_factory,
#                     dependencies=ClassifyDependencies(utc_now=lambda: AT,
#                         jev_factory=lambda *_: ParallelJev(), reviewer_factory=lambda *_: evaluation._Reviewer()))
#             self.assertEqual(parallel.values['drifts']['at_once'], 4)
#             self.assertEqual((concurrent['cases'], concurrent['distinctCases']), (4, 1))
#             self.assertEqual(concurrent['batches'], [
#                 {'cases': 4, 'incomplete': False, 'jevStandinCalls': 4, 'reviewStandinCalls': 4}])
#             self.assertEqual(len(overlapping), 1)
#             self.assertEqual(list(overlapping[0].values()), [4])
#             self.assertEqual(len({row['inputHash'] for row in concurrent['results']}), 1)
#             self.assertTrue(all(row['actual'] == 'needs_review' and row['correct']
#                                 and row['standinCalls'] == {'jev': 1, 'review': 1}
#                                 for row in concurrent['results']))
#             self.assertFalse(concurrent['incomplete'] or rendezvous.broken)
#             self.assertEqual(rendezvous.n_waiting, 0)
#             self.assertTrue(stores[0].leases)
#             self.assertTrue(all(value == 0 for value in stores[0].leases.values()))
#             self.assertEqual(parallel.file.read_bytes(), parallel_before)
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_all_cases_run_in_bounded_batches_without_provider_identity_or_measurement_claims

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_expected_labels_identifiers_and_coverage_annotations_never_change_decision_or_routing
#     def test_expected_labels_identifiers_and_coverage_annotations_never_change_decision_or_routing(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             first = DriftCase('label-a', 'old', 'claim', 'needs_review', current='new', critical=('permission',))
#             second = replace(first, id='label-b', expect='still_supported', critical=(), unchanged=True)
#             left = evaluation.run_drift_evaluation(suite((first,)), loaded, repository='fixture', build='development')
#             right = evaluation.run_drift_evaluation(suite((second,)), loaded, repository='fixture', build='development')
#             for name in ('actual', 'inputHash', 'jev', 'review', 'escalation', 'attempts', 'inputBytes', 'lifecycle'):
#                 self.assertEqual(left['results'][0][name], right['results'][0][name], name)
#             self.assertTrue(left['results'][0]['correct'])
#             self.assertFalse(right['results'][0]['correct'])
#             duplicate = evaluation.run_drift_evaluation(suite((first, second)), loaded,
#                                                        repository='fixture', build='development')
#             self.assertEqual((duplicate['cases'], duplicate['distinctCases']), (2, 1))
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_expected_labels_identifiers_and_coverage_annotations_never_change_decision_or_routing

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_canonical_snapshots_context_and_tombstone_survive_real_guard_reconstruction
#     def test_complete_canonical_snapshots_context_and_tombstone_survive_real_guard_reconstruction(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             retained = []
#             def store(*args, **kwargs):
#                 value = evaluation.FixtureStore(*args, **kwargs)
#                 retained.append(value)
#                 return value
#             selected = cases()[2:3] + cases()[4:5]
#             report = evaluation.run_drift_evaluation(suite(selected), loaded, repository='fixture',
#                 build='development', dependencies=ClassifyDependencies(utc_now=lambda: AT,
#                     jev_factory=lambda *_: evaluation._Jev(), reviewer_factory=lambda *_: evaluation._Reviewer()),
#                 store_factory=store)
#             preparations = list(retained[0].preparations.values())
#             self.assertEqual(preparations[0].decision.payload['current']['state'], 'deleted')
#             self.assertEqual(preparations[0].decision.payload['current']['members'], ())
#             self.assertEqual(preparations[1].decision.payload['context'][0]['evidence']['text'], 'full context\n')
#             for prepared in preparations:
#                 self.assertEqual(DecisionPayload.from_bytes(prepared.decision.canonical_bytes,
#                     prepared.input_hash), prepared.decision)
#                 self.assertEqual(EvidenceBundle.from_bytes(prepared.bundle.canonical_bytes,
#                     prepared.bundle.evidence_hash), prepared.bundle)
#                 self.assertEqual(prepared.input_hash, sha256(prepared.decision.canonical_bytes).hexdigest())
#                 self.assertTrue(all(value == 0 for value in retained[0].leases.values()))
#             view = evaluation._Settings(loaded)
#             self.assertEqual(retained[0].check(view, preparations[0], stage='jev',
#                 at='2026-10-15T11:59:58+00:00'), {'allowed': False, 'reason': 'pending_debounce'})
#             captured = retained[0].captures[preparations[0].reason_id][0]
#             # A corrupt retained blob is rejected at a fresh guard, before a
#             # call or cache application. Snapshot's constructor itself also
#             # enforces its bytes; bypass only that fixture construction here.
#             from types import SimpleNamespace
#             retained[0].captures[preparations[0].reason_id] = (
#                 SimpleNamespace(evidence=captured.evidence, source=b'corrupt retained bytes'),)
#             self.assertEqual(retained[0].check(view, preparations[0], stage='application', at=AT),
#                              {'allowed': False, 'reason': 'snapshot_corrupt'})
#             self.assertTrue(all(row['correct'] for row in report['results']))
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_canonical_snapshots_context_and_tombstone_survive_real_guard_reconstruction

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_obsolete_stage_never_calls_adapters_or_applies_and_releases_every_lease
#     def test_obsolete_stage_never_calls_adapters_or_applies_and_releases_every_lease(self):
#         class Obsolete(evaluation.FixtureStore):
#             @contextmanager
#             def stage(self, settings, prepared, *, stage, at):
#                 self.preparations[prepared.reason_id] = replace(prepared, pair_hash='f' * 64)
#                 with super().stage(settings, prepared, stage=stage, at=at) as result:
#                     yield result
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             report = evaluation.run_drift_evaluation(suite(cases()[1:2]), loaded,
#                 repository='fixture', build='development', store_factory=Obsolete)
#             self.assertEqual(sum(row['jevStandinCalls'] + row['reviewStandinCalls'] for row in report['batches']), 0)
#             self.assertEqual(report['results'][0]['actual'], 'unresolved')
#             self.assertTrue(report['results'][0]['lifecycle']['obsolete'])
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_obsolete_stage_never_calls_adapters_or_applies_and_releases_every_lease

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_cancellation_retains_every_unprocessed_case_and_never_qualifies
#     def test_cancellation_retains_every_unprocessed_case_and_never_qualifies(self):
#         cancelled = threading.Event()
#         class Stop(evaluation._Jev):
#             def classify(self, *args, **kwargs):
#                 value = super().classify(*args, **kwargs)
#                 cancelled.set()
#                 return value
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             report = evaluation.run_drift_evaluation(suite(cases()), loaded, repository='fixture',
#                 build='development', dependencies=ClassifyDependencies(cancelled=cancelled.is_set,
#                     jev_factory=lambda *_: Stop(), reviewer_factory=lambda *_: evaluation._Reviewer()))
#             self.assertEqual(len(report['results']), 5)
#             self.assertTrue(report['incomplete'])
#             self.assertFalse(report['qualified'])
#             self.assertTrue(all(row['actual'] == 'unresolved' for row in report['results']))
#             self.assertEqual(sum(row['jevStandinCalls'] for row in report['batches']), 1)
#             self.assertEqual(sum(row['reviewStandinCalls'] for row in report['batches']), 0)
#             self.assertTrue(all(row['elapsedMs'] >= 0 for row in report['results']))
#
#             # Real Python SIGINT between batches must not escape the evaluator
#             # or start another adapter. Preserve the caller's signal handler.
#             original_handler = signal.signal(signal.SIGINT, signal.default_int_handler)
#             try:
#                 factories = []
#                 def interrupted_factory(*args, **kwargs):
#                     factories.append(kwargs['offset'])
#                     if len(factories) == 2:
#                         signal.raise_signal(signal.SIGINT)
#                     return evaluation.FixtureStore(*args, **kwargs)
#                 between = evaluation.run_drift_evaluation(suite(cases()), loaded,
#                     repository='fixture', build='development', store_factory=interrupted_factory)
#                 self.assertEqual(factories, [0, 2])
#                 self.assertTrue(between['incomplete'] and between['interrupted'])
#                 self.assertEqual([row['actual'] for row in between['results'][:2]],
#                                  ['still_supported', 'needs_review'])
#                 self.assertTrue(all(not row['processed'] and row['elapsedMs'] == 0
#                                     and 'inputHash' not in row for row in between['results'][2:]))
#
#                 # A signal in canonical assembly has a measured started case,
#                 # but no fabricated request hash for its unfinished payload.
#                 original_prepare = evaluation._prepare
#                 calls = []
#                 def interrupted_prepare(*args, **kwargs):
#                     calls.append(args[1])
#                     if len(calls) == 2:
#                         signal.raise_signal(signal.SIGINT)
#                     return original_prepare(*args, **kwargs)
#                 with patch.object(evaluation, '_prepare', side_effect=interrupted_prepare):
#                     assembly = evaluation.run_drift_evaluation(suite(cases()), loaded,
#                         repository='fixture', build='development')
#                 self.assertTrue(assembly['incomplete'] and assembly['interrupted'])
#                 self.assertEqual(calls, [0, 1])
#                 self.assertEqual(sum(row['attempts'] for row in assembly['results']), 0)
#                 self.assertIn('inputHash', assembly['results'][0])
#                 self.assertNotIn('inputHash', assembly['results'][1])
#                 self.assertTrue(all(row['elapsedMs'] >= 0 for row in assembly['results']))
#                 self.assertTrue(all(not row['processed'] and row['elapsedMs'] == 0
#                                     for row in assembly['results'][2:]))
#             finally:
#                 signal.signal(signal.SIGINT, original_handler)
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_cancellation_retains_every_unprocessed_case_and_never_qualifies

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_live_requires_separate_explicit_pipeline_before_standin_or_credentials
#     def test_live_requires_separate_explicit_pipeline_before_standin_or_credentials(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             before = loaded.file.read_bytes()
#             with patch.object(evaluation, 'FixtureStore', side_effect=AssertionError('stand-in')), \
#                     patch('mycel._classification_runner.Credentials', side_effect=AssertionError('credential')), \
#                     patch('mycel._evaluation_live.Credentials', side_effect=AssertionError('live credential')):
#                 report = evaluation.run_drift_evaluation(suite(cases()), loaded,
#                     repository='fixture', build='development', live=True)
#             self.assertTrue(report['live'])
#             self.assertFalse(report['qualified'])
#             self.assertEqual(report['batches'], [])
#             self.assertEqual(report['cases'], len(cases()))
#             self.assertTrue(all(row['actual'] == 'unresolved' and row['attempts'] == 0 for row in report['results']))
#             self.assertTrue(any('reviewer' in reason for reason in report['qualificationFailures']))
#             self.assertEqual(loaded.file.read_bytes(), before)
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_live_requires_separate_explicit_pipeline_before_standin_or_credentials

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_real_reviewer_retry_exact_cache_and_revision_guards_join_the_finite_runner
#     def test_real_reviewer_retry_exact_cache_and_revision_guards_join_the_finite_runner(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             loaded = settings(root)
#             view = evaluation._Settings(loaded)
#             counter = root / 'attempt-count'
#             code = '''import json,pathlib,sys
# raw=sys.stdin.buffer.read()
# assert raw.endswith(b'\\n')
# request=json.loads(raw)
# path=pathlib.Path(sys.argv[1]);n=int(path.read_text())+1 if path.exists() else 1
# path.write_text(str(n))
# reply={key:request[key] for key in ('protocol','inputHash','provider','model','adapterRevision','commandHash')}
# if n==1:
#  reply['error']={'code':'connection','message':'private raw detail'}
#  print(json.dumps(reply),flush=True);sys.exit(1)
# reply.update(judgement='needs_review',rationale='Changed fixture input.',evidence=[request['payload']['current']['locator']])
# print(json.dumps(reply),flush=True)
# '''
#             view.values['drifts']['review_command'] = [sys.executable, '-c', code, str(counter)]
#             command = ReviewCommandIdentity.inspect(view.values['drifts']['review_command'],
#                                                     evaluation.STANDIN_REVISION, root)
#             store = evaluation.FixtureStore(cases()[1:2], 'fixture', view, command, at=AT)
#             dependencies = ClassifyDependencies(utc_now=lambda: AT,
#                 jev_factory=lambda *_: evaluation._Jev(),
#                 reviewer_factory=lambda settings, policy, command: ReviewerClient(policy, command,
#                     home=root, limits=ReviewerLimits(timeout_seconds=2)))
#             with patch('mycel._classification_runner.Credentials', side_effect=AssertionError('credential')):
#                 first = run_classification(store, view, 'fixture', dependencies=dependencies)
#                 second = run_classification(store, view, 'fixture', dependencies=dependencies)
#                 view.values['drifts']['review_revision'] = 'fixture-revision-v2'
#                 revised = run_classification(store, view, 'fixture', dependencies=dependencies)
#             self.assertEqual((first['jevCalls'], first['reviewCalls'], first['completed']), (1, 2, 1))
#             self.assertEqual([row['status'] for row in first['pairs'][0]['classification']['evidence']['attempts']],
#                              ['complete', 'error', 'complete'])
#             self.assertEqual((second['jevCalls'], second['reviewCalls'], second['reused']), (0, 0, 1))
#             self.assertEqual((revised['jevCalls'], revised['reviewCalls'], revised['obsolete']), (0, 0, 1))
#             self.assertEqual(counter.read_text(), '2')
#             self.assertTrue(all(count == 0 for count in store.leases.values()))
#             self.assertNotIn('private raw detail', json.dumps(first))
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_real_reviewer_retry_exact_cache_and_revision_guards_join_the_finite_runner

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_public_default_nonlive_handler_uses_real_pipeline_without_store_or_service_calls
#     def test_public_default_nonlive_handler_uses_real_pipeline_without_store_or_service_calls(self):
#         from io import StringIO
#         from mycel._cli import run
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             loaded = settings(root)
#             loaded.file.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n' + loaded.file.read_text())
#             (root / 'evaluation.toml').write_text(
#                 '[[drift]]\nid="public"\nbefore="allow()"\ncurrent="deny()"\n'
#                 'dependant="allow() remains permitted"\nexpect="needs_review"\n'
#                 'context=["Complete unchanged caller context.\\n"]\ncritical=["permission"]\n')
#             before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
#             output, diagnostic = StringIO(), StringIO()
#             with patch.dict(os.environ, {'MYCEL_CONFIG': str(loaded.file)}), \
#                     patch('mycel._build_identity.current_build', return_value=None):
#                 status = run(('evaluate', '--repo', 'fixture', '--kind', 'drift'),
#                              stdout=output, stderr=diagnostic)
#             report = json.loads(output.getvalue())
#             self.assertEqual((status, diagnostic.getvalue()), (0, ''), report)
#             self.assertEqual((report['cases'], report['routedCases'], report['results'][0]['actual']),
#                              (1, 1, 'needs_review'))
#             self.assertEqual(report['results'][0]['standinCalls'], {'jev': 1, 'review': 1})
#             self.assertEqual(report['pipeline']['mode'], 'deterministic-stand-ins')
#             self.assertFalse(report['qualified'] or report['live'])
#             self.assertEqual({p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_public_default_nonlive_handler_uses_real_pipeline_without_store_or_service_calls

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_more_than_default_production_cap_is_processed_in_complete_bounded_batches
#     def test_more_than_default_production_cap_is_processed_in_complete_bounded_batches(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary), candidates=17)
#             selected = tuple(DriftCase(str(index), f'value = {index}', 'Keep the value.',
#                 'still_supported', current=f'value = {index}', unchanged=True) for index in range(105))
#             report = evaluation.run_drift_evaluation(suite(selected), loaded,
#                 repository='fixture', build='development')
#             self.assertEqual((report['cases'], report['distinctCases']), (105, 105))
#             self.assertEqual([row['cases'] for row in report['batches']], [17, 17, 17, 17, 17, 17, 3])
#             self.assertEqual(sum(row['jevStandinCalls'] for row in report['batches']), 105)
#             self.assertEqual([row['id'] for row in report['results']], [str(index) for index in range(105)])
#             self.assertTrue(all(row['correct'] and row['processed'] for row in report['results']))
#             self.assertFalse(report['incomplete'] or report['qualified'])
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_more_than_default_production_cap_is_processed_in_complete_bounded_batches

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_oversized_input_routes_or_refuses_without_truncating_any_context
#     def test_complete_oversized_input_routes_or_refuses_without_truncating_any_context(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             loaded = settings(root)
#             loaded.file.write_text(loaded.file.read_text() + 'max_input_bytes=1\n')
#             loaded = load_settings(path=loaded.file, home=root)
#             text = 'unchanged full caller ' * 200 + 'EXACT END\n'
#             selected = DriftCase('large', 'old', 'claim', 'needs_review', current='new', context=(text,))
#             captured = []
#             class Reviewer(evaluation._Reviewer):
#                 def classify(self, decision, **kwargs):
#                     captured.append(decision)
#                     return super().classify(decision, **kwargs)
#             report = evaluation.run_drift_evaluation(suite((selected,)), loaded,
#                 repository='fixture', build='development', dependencies=ClassifyDependencies(
#                     jev_factory=lambda *_: self.fail('An oversized Jev request must not launch.'),
#                     reviewer_factory=lambda *_: Reviewer()))
#             row = report['results'][0]
#             self.assertEqual(row['standinCalls'], {'jev': 0, 'review': 1})
#             self.assertEqual(row['escalation'], 'jev_input_too_large')
#             self.assertEqual(captured[0].payload['context'][0]['evidence']['text'], text)
#             self.assertEqual(row['inputBytes'], len(captured[0].canonical_bytes))
#             loaded.file.write_text(loaded.file.read_text() + 'review_max_input_bytes=1\n')
#             loaded = load_settings(path=loaded.file, home=root)
#             refused = evaluation.run_drift_evaluation(suite((selected,)), loaded,
#                 repository='fixture', build='development', dependencies=ClassifyDependencies(
#                     jev_factory=lambda *_: self.fail('oversized Jev'),
#                     reviewer_factory=lambda *_: self.fail('oversized reviewer')))
#             self.assertEqual(refused['results'][0]['standinCalls'], {'jev': 0, 'review': 0})
#             self.assertEqual(refused['results'][0]['actual'], 'unresolved')
#             self.assertIn('review_input_too_large', refused['results'][0]['error']['message'])
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_complete_oversized_input_routes_or_refuses_without_truncating_any_context

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_each_unavailable_required_evidence_kind_has_no_canonical_request_or_adapter_call
#     def test_each_unavailable_required_evidence_kind_has_no_canonical_request_or_adapter_call(self):
#         with tempfile.TemporaryDirectory() as temporary:
#             loaded = settings(Path(temporary))
#             selected = tuple(DriftCase(kind, 'complete old bytes', 'complete dependant',
#                 'unresolved', current='complete new bytes', context=('complete context',),
#                 unavailable=(kind,)) for kind in ('baseline', 'dependant', 'context'))
#             report = evaluation.run_drift_evaluation(suite(selected), loaded,
#                 repository='fixture', build='development', dependencies=ClassifyDependencies(
#                     jev_factory=lambda *_: self.fail('unavailable evidence Jev'),
#                     reviewer_factory=lambda *_: self.fail('unavailable evidence reviewer')))
#             self.assertTrue(all(row['actual'] == 'unresolved' and row['correct'] and row['attempts'] == 0
#                 and row['inputBytes'] is None and 'inputHash' not in row for row in report['results']))
#             self.assertTrue(all(row['jevStandinCalls'] == row['reviewStandinCalls'] == 0 for row in report['batches']))
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_each_unavailable_required_evidence_kind_has_no_canonical_request_or_adapter_call

# TEST-TIER-DISABLED-BEGIN tests/test_evaluation_drift.py::DriftEvaluationTests.test_public_interruption_and_incomplete_reports_keep_partial_reply_with_nonzero_status
#     def test_public_interruption_and_incomplete_reports_keep_partial_reply_with_nonzero_status(self):
#         from io import StringIO
#         from mycel._cli import run
#         from mycel._evaluate import evaluate
#         with tempfile.TemporaryDirectory() as temporary:
#             root = Path(temporary)
#             loaded = settings(root)
#             loaded.file.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n' + loaded.file.read_text())
#             (root / 'evaluation.toml').write_text(
#                 '[[drift]]\nid="stopped"\nbefore="old"\ncurrent="new"\ndependant="claim"\nexpect="needs_review"\n')
#             original = signal.signal(signal.SIGINT, signal.default_int_handler)
#             try:
#                 output, diagnostic = StringIO(), StringIO()
#                 def interrupted_prepare(*args, **kwargs):
#                     signal.raise_signal(signal.SIGINT)
#                 with patch.dict(os.environ, {'MYCEL_CONFIG': str(loaded.file)}), \
#                         patch('mycel._build_identity.current_build', return_value=None), \
#                         patch.object(evaluation, '_prepare', side_effect=interrupted_prepare):
#                     status = run(('evaluate', '--repo', 'fixture', '--kind', 'drift'),
#                         stdout=output, stderr=diagnostic)
#                 report = json.loads(output.getvalue())
#                 self.assertEqual((status, diagnostic.getvalue()), (2, ''))
#                 self.assertTrue(report['interrupted'] and report['incomplete'])
#                 self.assertEqual(len(report['results']), 1)
#                 self.assertEqual(report['results'][0]['actual'], 'unresolved')
#                 self.assertEqual(report['results'][0]['attempts'], 0)
#                 self.assertFalse(report['qualified'])
#             finally:
#                 signal.signal(signal.SIGINT, original)
#             # The injected adapter obeys the same public result contract. A
#             # bounded deadline failure differs from caller interruption, and
#             # qualified=false alone does not turn a completed reply into failure.
#             for incomplete, expected_status in ((True, 1), (False, 0)):
#                 output, diagnostic = StringIO(), StringIO()
#                 def adapter(*args, **kwargs):
#                     return {'kind': 'drift', 'qualified': False, 'incomplete': incomplete,
#                             'interrupted': False, 'results': []}
#                 handler = lambda invocation: evaluate(invocation, drift=adapter)
#                 with patch.dict(os.environ, {'MYCEL_CONFIG': str(loaded.file)}), \
#                         patch('mycel._build_identity.current_build', return_value=None):
#                     status = run(('evaluate', '--repo', 'fixture', '--kind', 'drift'),
#                         handlers={'evaluate': handler}, stdout=output, stderr=diagnostic)
#                 self.assertEqual((status, diagnostic.getvalue()), (expected_status, ''))
#                 self.assertEqual(json.loads(output.getvalue())['incomplete'], incomplete)
# TEST-TIER-DISABLED-END tests/test_evaluation_drift.py::DriftEvaluationTests.test_public_interruption_and_incomplete_reports_keep_partial_reply_with_nonzero_status


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:2
# from contextlib import ExitStack, contextmanager
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:3
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:4
# from hashlib import sha256
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:6
# import math
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:6

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:7
# import os
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:9
# import sys
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:9

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:10
# import signal
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:11
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:12
# import threading
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:16
# from mycel._classification_payload import DecisionPayload, EvidenceBundle, ReviewCommandIdentity
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:17
# from mycel._classification_runner import ClassifyDependencies, run_classification
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:18
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:18

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:20
# from mycel import _evaluation_drift as evaluation
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:20

# TEST-TIER-IMPORTS-BEGIN tests/test_evaluation_drift.py:21
# from mycel._reviewer import ReviewerClient, ReviewerLimits
# TEST-TIER-IMPORTS-END tests/test_evaluation_drift.py:21

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
