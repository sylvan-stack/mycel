"""Synthetic, provider-free operator boundaries; no qualification is measured.

All 200-case sets, staged-binding replies and proof-shaped objects below are
controlled unit fixtures. They are never the owner's reviewed release corpus,
actual staged execution, provider results or on-demand requirement acceptance.
"""
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mycel._classification_payload import ReviewerRequest
from mycel._coverage import CheckResult, OnDemandProofs, proves
from mycel._errors import MycelError
from mycel._evaluation_drift import _prepare
from mycel._jev import JevRequest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mycel_provider_operation_script',
                                              ROOT / 'scripts/qualify_providers.py')
operation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = operation
SPEC.loader.exec_module(operation)


def synthetic_suite(path, *, unavailable=False):
    """Distinct, intentionally simple test bytes, not an authored label set."""
    rows = ['schema_version = 1\n']
    for index in range(200):
        critical, unchanged = index < 50, 50 <= index < 100
        expected = 'still_supported' if unchanged else 'needs_review'
        missing = unavailable and index == 199
        if missing:
            expected = 'unresolved'
        before = f'Synthetic unit fixture before {index}.'
        rows.extend(['[[drift]]', f'id = "synthetic-{index}"',
            'before = ' + json.dumps(before),
            'current = ' + json.dumps(before if unchanged else f'Synthetic unit fixture current {index}.'),
            'dependant = ' + json.dumps(f'Synthetic unit fixture claim {index}.'),
            'expect = ' + json.dumps(expected)])
        if critical:
            rows.append('critical = ' + json.dumps([('negation', 'operator', 'permission', 'deletion')[index % 4]]))
        if unchanged:
            rows.append('unchanged = true')
        if missing:
            rows.append('unavailable = ["baseline"]')
    path.write_text('\n'.join(rows) + '\n')


class ProviderOperationTests(unittest.TestCase):
    @contextmanager
    def fixture(self, *, reviewer=True, staged=False, unavailable=False, limits=''):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reviewer_file = root / 'synthetic-reviewer'
            reviewer_file.write_text('#!/bin/sh\nexit 99\n')
            reviewer_file.chmod(0o700)  # Inspection only; no test executes it.
            settings = root / 'config.toml'
            text = ('[store]\naddress="postgresql://unit@localhost:55432/synthetic_only"\n'
                    '[repos.synthetic]\nenabled=true\nartifact_root=' + json.dumps(str(root)) + '\n'
                    '[drifts]\n' + limits)
            if reviewer:
                text += ('review_command=' + json.dumps([str(reviewer_file)]) + '\n'
                         'review_provider="synthetic-provider"\nreview_model="synthetic-model-1"\n'
                         'review_revision="synthetic-adapter-v1"\n')
            settings.write_text(text)
            suite = root / 'synthetic-unit-cases.toml'
            synthetic_suite(suite, unavailable=unavailable)
            source = {'commit': 'synthetic-unit-commit', 'dirty': True, 'inputsSha256': 'a' * 64}
            frozen = {'src/mycel/data/requirements.json':
                      (ROOT / 'src/mycel/data/requirements.json').read_bytes()}
            staged_shape = {'registry': str(root / 'synthetic-registry'), 'build': '1',
                'program': str(root / 'synthetic-program'), 'sourceInputsSha256': 'a' * 64,
                'filesSha256': 'b' * 64, 'programStampSha256': 'synthetic-metadata-stamp'}
            record = root / 'synthetic-registry/1/build.json'
            record.parent.mkdir(parents=True)
            record.write_text('{"syntheticUnitFixtureOnly":true}\n')
            staged_shape['buildRecordSha256'] = sha256(record.read_bytes()).hexdigest()
            arguments = {'settings_path': settings, 'suite_path': suite, 'repository': 'synthetic'}
            if staged:
                arguments.update(build_registry=root / 'synthetic-registry', build='1')
            with patch.object(operation, 'source_inputs', return_value=(source, frozen)), \
                    patch.object(operation, '_staged_binding', return_value=staged_shape), \
                    patch.object(operation, '_program_stamp', return_value='synthetic-metadata-stamp'):
                yield root, arguments, reviewer_file, source, staged_shape

    @proves('MYC-13.2', 'MYC-14.12')
    def test_default_and_missing_profile_are_local_and_never_probe_credentials_or_models(self):
        for configured in (False, True):
            with self.subTest(configured=configured), self.fixture(reviewer=configured) as (_, args, _, _, _), \
                    patch('mycel._credentials.Credentials', side_effect=AssertionError('credential')), \
                    patch('mycel._safeguards.run_resolved_reviewer', side_effect=AssertionError('child')), \
                    patch('socket.create_connection', side_effect=AssertionError('network')), \
                    patch('mycel._embedding_live.load_tokenizer', side_effect=AssertionError('tokenizer')), \
                    patch.object(operation, 'run_provider_checks', side_effect=AssertionError('provider')):
                plan = operation.prepare_operation(**args)
                self.assertFalse(plan.report['liveReady'])
                self.assertFalse(plan.report['providerExecution'] or plan.report['qualified'])
                if not configured:
                    self.assertEqual(plan.report['routes']['unknown'], 200)
                    self.assertTrue(all(row['inputHash'] is None for row in plan.report['results']))
                printed = io.StringIO()
                with patch('sys.stdout', printed):
                    status = operation.main(['--settings', str(args['settings_path']),
                        '--suite', str(args['suite_path']), '--repo', 'synthetic'])
                self.assertEqual(status, 1)
                self.assertFalse(json.loads(printed.getvalue())['providerExecution'])

    @proves('MYC-13.15', 'MYC-14.20')
    def test_complete_serialized_bytes_lf_and_unavailable_no_call_are_exact(self):
        with self.fixture(staged=True, unavailable=True) as (_, args, _, _, _):
            plan = operation.prepare_operation(**args)
            self.assertTrue(plan.report['liveReady'])  # Mocked stage binding, not native evidence.
            command = operation.ReviewCommandIdentity.inspect(
                plan.settings.values['drifts']['review_command'],
                plan.settings.values['drifts']['review_revision'], plan.settings._home)
            prepared, _, _ = _prepare(plan.suite.drifts[0], 0, 'synthetic',
                plan.settings, command, operation._FIXTURE_AT)
            row = plan.report['results'][0]
            request = ReviewerRequest(prepared.decision, row['reviewTimeoutMs'])
            self.assertEqual(row['jevBytes'], len(JevRequest(prepared.decision).body))
            self.assertEqual(row['reviewBytes'], len(request.canonical_bytes) + 1)
            self.assertEqual(request.transmitted_bytes[-1:], b'\n')
            missing = plan.report['results'][-1]
            self.assertEqual(missing['route'], 'unavailable_no_call')
            self.assertIsNone(missing['inputHash'])
            self.assertEqual(missing['maxCalls'], {'jev': 0, 'review': 0})
            self.assertEqual(plan.report['routes']['possibleComparative'], 199)
            self.assertEqual(plan.report['maxCalls'], {'embedding': 2, 'jev': 398, 'review': 398})
            self.assertNotIn('Synthetic unit fixture before', plan._report_bytes.decode())

    @proves('MYC-13.15', 'MYC-14.20')
    def test_direct_review_and_unfit_review_block_unmeasurable_comparison_without_dispatch(self):
        for limits, direct, unfit in (('max_input_bytes=1\n', 200, 0),
                                      ('review_max_input_bytes=1\n', 0, 200)):
            with self.subTest(limits=limits), self.fixture(staged=True, limits=limits) as (root, args, _, _, _), \
                    patch.object(operation, 'run_provider_checks', side_effect=AssertionError('provider')):
                plan = operation.prepare_operation(**args)
                self.assertEqual(plan.report['routes']['directReview'], direct)
                self.assertEqual(plan.report['routes']['reviewerUnfit'], unfit)
                self.assertEqual(plan.report['routes']['possibleComparative'], 0)
                self.assertFalse(plan.report['liveReady'])
                with self.assertRaises(MycelError):
                    operation.run_operation(plan, expected_plan_sha256=plan.report['planSha256'],
                                            output_dir=root / 'must-not-exist')
                self.assertFalse((root / 'must-not-exist').exists())

    @proves('MYC-13.2', 'MYC-13.15')
    def test_changed_bound_inputs_refuse_before_any_provider_or_retention_write(self):
        for change in ('settings', 'suite', 'command', 'source', 'program', 'expected'):
            with self.subTest(change=change), self.fixture(staged=True) as (root, args, command, source, stage), \
                    patch.object(operation, '_hold_build', return_value=nullcontext()), \
                    patch.object(operation, 'run_provider_checks', side_effect=AssertionError('provider')):
                plan = operation.prepare_operation(**args)
                expected = plan.report['planSha256']
                if change == 'settings':
                    args['settings_path'].write_text(args['settings_path'].read_text() + '\n# changed bytes\n')
                if change == 'suite':
                    args['suite_path'].write_text(args['suite_path'].read_text() + '\n# changed bytes\n')
                if change == 'command':
                    command.write_text(command.read_text() + '# changed executable\n')
                if change == 'source':
                    source['inputsSha256'] = 'c' * 64
                if change == 'program':
                    stage['filesSha256'] = 'e' * 64
                if change == 'expected':
                    expected = 'f' * 64
                output = root / 'must-not-exist'
                with self.assertRaises(MycelError):
                    operation.run_operation(plan, expected_plan_sha256=expected, output_dir=output)
                self.assertFalse(output.exists())

    @proves('MYC-13.2', 'MYC-14.12')
    def test_development_imports_cannot_claim_staged_identity(self):
        # Read-only stage metadata is controlled; the interpreter/product are
        # the real development imports, which must be refused before hashing.
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(operation, 'read_guard', return_value=nullcontext()), \
                patch.object(operation, 'read_record', return_value={'status': 'building',
                    'program': 'program', 'filesManifest': 'files.json'}), \
                patch.object(operation, 'validate_manifest', side_effect=AssertionError('manifest')), \
                patch.object(operation, 'verify_source', side_effect=AssertionError('source')):
            with self.assertRaises(MycelError):
                operation._staged_binding(Path(temporary), '1')

    @proves('MYC-13.2', 'MYC-14.12')
    def test_staged_program_symlink_refuses_before_resolution_erases_it(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(operation, 'read_guard', return_value=nullcontext()), \
                patch.object(operation, 'read_record', return_value={'status': 'building',
                    'program': 'program', 'filesManifest': 'files.json'}), \
                patch.object(operation, 'validate_manifest', side_effect=AssertionError('manifest')):
            root = Path(temporary)
            (root / '1').mkdir()
            (root / 'elsewhere').mkdir()
            (root / '1/program').symlink_to(root / 'elsewhere', target_is_directory=True)
            with self.assertRaises(MycelError) as raised:
                operation._staged_binding(root, '1')
            self.assertIn('symlinked', str(raised.exception))

    @proves('MYC-13.2', 'MYC-14.12')
    def test_existing_per_call_settings_guards_catch_external_byte_changes(self):
        for change in ('settings', 'suite', 'source', 'command', 'program', 'build-record'):
            with self.subTest(change=change), self.fixture(staged=True) as (root, args, command, source, _):
                plan = operation.prepare_operation(**args)
                bound = operation._BoundSettings(plan)
                bound.require_current()
                if change == 'settings':
                    args['settings_path'].write_text(args['settings_path'].read_text() + '# changed bytes only\n')
                if change == 'suite':
                    args['suite_path'].write_text(args['suite_path'].read_text() + '# changed bytes only\n')
                if change == 'source':
                    source['inputsSha256'] = 'c' * 64
                if change == 'command':
                    command.write_text(command.read_text() + '# modified\n')
                if change == 'program':
                    operation._program_stamp.return_value = 'changed-metadata'
                if change == 'build-record':
                    (root / 'synthetic-registry/1/build.json').write_text('{}\n')
                with self.assertRaises(MycelError):
                    bound.require_current()

    @proves('MYC-13.2', 'MYC-13.15')
    def test_live_group_passes_original_objects_once_and_retains_diagnostics_only(self):
        with self.fixture(staged=True) as (root, args, _, _, _), \
                patch.object(operation, '_hold_build', return_value=nullcontext()):
            plan = operation.prepare_operation(**args)
            identity = plan.report['source']['inputsSha256']
            # Proof-shaped arithmetic fixtures are never real live evidence.
            provider = OnDemandProofs(identity, (CheckResult('synthetic.provider',
                'live', ('MYC-13.9',), 'passed'),))
            consumer = OnDemandProofs(identity, (CheckResult('synthetic.consumer',
                'live', ('MYC-14.22',), 'passed'),))
            reports = {'syntheticUnitFixtureOnly': True}
            seen = []
            def produce(*positional, **keywords):
                seen.append('146')
                self.assertTrue(keywords['live'])
                return provider, reports
            def consume(settings, suite, supplied, supplied_reports, **keywords):
                seen.append('147')
                self.assertIs(supplied, provider)
                self.assertIs(supplied_reports, reports)
                reports['deployment'] = {'sameProcessProviderGroupConsumed': True}
                return (supplied, consumer), reports
            output = root / 'retained-unit-only'
            with patch.object(operation, 'run_provider_checks', side_effect=produce) as producer, \
                    patch.object(operation, 'run_provider_deployment_checks', side_effect=consume) as receiver:
                proofs, returned, receipt = operation.run_operation(plan,
                    expected_plan_sha256=plan.report['planSha256'], output_dir=output)
            self.assertIs(proofs[0], provider)
            self.assertIs(proofs[1], consumer)
            self.assertIs(returned, reports)
            self.assertEqual(seen, ['146', '147'])
            producer.assert_called_once()
            receiver.assert_called_once()
            self.assertTrue(receipt['passed'])  # Synthetic seam only, not provider qualification.
            retained = json.loads((output / 'receipt.json').read_bytes())
            self.assertFalse(retained['savedRecordsAreProofObjects'])
            self.assertFalse(retained['automaticBuildQualification'])
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir()))
            self.assertEqual(json.loads((output / 'reports.json').read_bytes()), reports)
            with patch.object(operation, 'run_provider_checks', side_effect=AssertionError('repeat')), \
                    self.assertRaises(FileExistsError):
                operation.run_operation(plan, expected_plan_sha256=plan.report['planSha256'], output_dir=output)

    @proves('MYC-13.2', 'MYC-13.15')
    def test_failed_or_interrupted_group_is_retained_without_repeat_or_fabricated_checks(self):
        for failure in ('provider-failed', 'consumer-refused', 'interrupted'):
            with self.subTest(failure=failure), self.fixture(staged=True) as (root, args, _, _, _), \
                    patch.object(operation, '_hold_build', return_value=nullcontext()):
                plan = operation.prepare_operation(**args)
                proof = OnDemandProofs(plan.report['source']['inputsSha256'], (CheckResult('synthetic.failed',
                    'live', ('MYC-13.9',), 'failed'),))
                reports = {'syntheticUnitFixtureOnly': True}
                with patch.object(operation, 'run_provider_checks', return_value=(proof, reports)) as producer, \
                        patch.object(operation, 'run_provider_deployment_checks',
                            return_value=((proof, proof), reports)) as consumer:
                    if failure == 'consumer-refused':
                        consumer.side_effect = MycelError('refused', 'synthetic refusal')
                    if failure == 'interrupted':
                        producer.side_effect = KeyboardInterrupt()
                    proofs, returned, receipt = operation.run_operation(plan,
                        expected_plan_sha256=plan.report['planSha256'], output_dir=root / 'retained-unit-only')
                producer.assert_called_once()
                self.assertFalse(receipt['passed'])
                if failure == 'interrupted':
                    consumer.assert_not_called()
                    self.assertEqual(proofs, ())
                    self.assertEqual(returned, {})
                    self.assertEqual(receipt['checks'], [])
                    self.assertEqual(receipt['failure'], 'interrupted')
                else:
                    consumer.assert_called_once()
                    self.assertIs(proofs[0], proof)
                    self.assertIs(returned, reports)

    @proves('MYC-13.2', 'MYC-13.15')
    def test_coverage_floors_and_source_or_settings_race_are_local_refusals(self):
        with self.fixture(staged=True) as (_, args, _, source, _):
            raw = args['suite_path'].read_text()
            args['suite_path'].write_text(raw[:raw.index('[[drift]]', raw.index('[[drift]]') + 1)])
            plan = operation.prepare_operation(**args)
            self.assertFalse(plan.report['liveReady'])
            self.assertEqual(plan.report['suite']['distinctCases'], 1)
            original = operation.source_inputs.return_value
            changed = (dict(source, inputsSha256='f' * 64), original[1])
            with patch.object(operation, 'source_inputs', side_effect=(original, changed)):
                with self.assertRaises(MycelError):
                    operation.prepare_operation(**args)
            original_loader = operation.load_settings
            def editing_loader(**keywords):
                settings = original_loader(**keywords)
                args['settings_path'].write_text(args['settings_path'].read_text() + '# concurrent edit\n')
                return settings
            with patch.object(operation, 'load_settings', side_effect=editing_loader):
                with self.assertRaises(MycelError):
                    operation.prepare_operation(**args)


if __name__ == '__main__':
    unittest.main()
