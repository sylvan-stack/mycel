#!/usr/bin/env python3
"""Inspect an exact provider operation; --live explicitly executes its one group.

The default path reads local inputs only. Reports are diagnostic records, never
deserializable OnDemandProofs. Run live with the selected staged interpreter
under -I -B; development imports cannot stand in for an immutable Build.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
# Import the installed product first. An isolated staged interpreter must never
# fall back to source product modules. A development interpreter may use source.
try:
    import mycel
except ModuleNotFoundError:
    if sys.flags.isolated:
        raise
    sys.path.append(str(SOURCE_ROOT / 'src'))
    import mycel
# Build-side verifiers are not shipped in the product wheel. Appending their
# source directory does not replace the already imported mycel package's path.
if str(SOURCE_ROOT / 'src') not in sys.path:
    sys.path.append(str(SOURCE_ROOT / 'src'))

from mycel._classification_payload import ReviewCommandIdentity
from mycel._classification_runner import _bytes
from mycel._errors import MycelError
from mycel._evaluation import load_evaluation_file
from mycel._evaluation_drift import _prepare
from mycel._evaluation_live import _pipeline
from mycel._provider_qualification import (
    CRITICAL_CATEGORIES,
    profile_fingerprint,
    semantic_fingerprint,
)
from mycel._settings import load_settings
from mycel_build._core import BuildError, read_json, validate_manifest
from mycel_build._registry import read_guard, read_record, registry_path, run_guard
from mycel_build._staging import source_inputs, verify_source

SCHEMA = 'mycel-provider-operation-v1'
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_FIXTURE_AT = '2000-01-01T00:00:00+00:00'


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


def _digest(value):
    return sha256(_json(value)).hexdigest()


def _refuse(message):
    raise MycelError('refused', message)


def _program_stamp(program):
    """Cheap refusal guard after a complete immutable-manifest verification.

    The full manifest is hashed before and after the group. Between requests,
    refuse any changed inode, link, metadata or file set rather than repeatedly
    hashing the entire bundled runtime inside each short provider deadline.
    Access times are intentionally excluded; reads must not invalidate a run.
    """
    if program.is_symlink() or not program.is_dir():
        _refuse('The selected staged program is no longer a real directory.')
    rows = []
    for path in (program, *sorted(program.rglob('*'))):
        info = path.lstat()
        rows.append([path.relative_to(program).as_posix(), info.st_dev, info.st_ino,
            info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            os.readlink(path) if stat.S_ISLNK(info.st_mode) else None])
    return _digest(rows)


@dataclass(frozen=True)
class OperationPlan:
    settings_path: Path
    suite_path: Path
    repository: str
    build_registry: Path | None
    build: str | None
    _report_bytes: bytes = field(repr=False)
    settings: object = field(repr=False, compare=False)
    suite: object = field(repr=False, compare=False)

    @property
    def report(self):
        return json.loads(self._report_bytes)


def _staged_binding(root, number):
    """Read-only binding to actual installed imports, runtime and frozen bytes."""
    from mycel._build_identity import current_build
    root = registry_path(root)
    with read_guard(root):
        record = read_record(root, number)
        if (record['status'] not in {'building', 'working'}
                or record.get('program') != 'program'
                or record.get('filesManifest') != 'files.json'):
            _refuse('The selected Build has no usable immutable staged program.')
        folder = root / number
        program = folder / 'program'
        if (program.is_symlink() or not program.is_dir()
                or not program.resolve().is_relative_to(folder.resolve())):
            _refuse('The selected staged program is missing, symlinked or outside its Build.')
        interpreter = (program / 'runtime/bin/python3').resolve()
        package = program / 'runtime/lib/python3.14/site-packages/mycel'
        if (not sys.flags.isolated or not sys.dont_write_bytecode
                or Path(sys.executable).resolve() != interpreter
                or not interpreter.is_relative_to(program)
                or Path(mycel.__file__).resolve().parent != package
                or tuple(Path(path).resolve() for path in mycel.__path__) != (package,)
                or current_build() != int(number, 16)):
            _refuse('Live qualification requires this Build\'s isolated staged interpreter and product imports.')
        for name, module in tuple(sys.modules.items()):
            if name == 'mycel' or name.startswith('mycel.'):
                origin = getattr(module, '__file__', None)
                if origin is not None and not Path(origin).resolve().is_relative_to(package):
                    _refuse('An imported product module is outside the selected Build.')
        validate_manifest(program, read_json(folder / 'files.json'), record['filesSha256'])
        binding = verify_source(SOURCE_ROOT, root, number)
        if not binding['matches']:
            _refuse('The source and complete check inputs differ from the selected Build.')
        return {'registry': str(root), 'build': number, 'program': str(program),
                'interpreter': str(interpreter), 'package': str(package),
                'sourceInputsSha256': record['source']['inputsSha256'],
                'checkManifestSha256': record['checkManifestSha256'],
                'filesSha256': record['filesSha256'],
                'programStampSha256': _program_stamp(program),
                'buildRecordSha256': sha256((folder / 'build.json').read_bytes()).hexdigest()}


def prepare_operation(*, settings_path, suite_path, repository,
                      build_registry=None, build=None):
    """Validate and size complete inputs without credentials, children or calls.

    The local git inspection in source_inputs is read-only. Reviewer inspection
    hashes the executable but never launches it. A missing profile leaves sizes
    unknown rather than substituting a fictional identity.
    """
    if (build_registry is None) != (build is None):
        raise MycelError('invalid_input', 'Select the Build registry and number together.')
    settings_path, suite_path = Path(settings_path).absolute(), Path(suite_path).absolute()
    root = None if build_registry is None else Path(build_registry).absolute()
    source, frozen = source_inputs(SOURCE_ROOT)
    settings_raw = settings_path.read_bytes()
    settings = load_settings(path=settings_path)
    settings.require_valid(require_store=False)
    settings.require_current()
    suite = load_evaluation_file(suite_path)
    blockers = []
    if (repository not in settings.values['repos']
            or repository in settings.values['organizations']
            or not settings.values['repos'][repository]['enabled']):
        blockers.append('Select one enabled configured repository, not an organization.')
    groups = {}
    for case in suite.drifts:
        groups.setdefault(semantic_fingerprint(case), []).append(case)
    critical = sum(any(case.critical for case in group) for group in groups.values())
    unchanged = sum(any(case.unchanged for case in group) for group in groups.values())
    categories = {tag for case in suite.drifts for tag in case.critical}
    if len(groups) < 200 or critical < 50 or unchanged < 50:
        blockers.append('The distinct labelled coverage floors are 200 pairs, 50 critical and 50 unchanged/cosmetic.')
    if not CRITICAL_CATEGORIES <= categories:
        blockers.append('Critical coverage must include negation, operator, permission and deletion.')
    if any(len({case.expect for case in group}) != 1 for group in groups.values()):
        blockers.append('Duplicate semantic fixtures have conflicting ground-truth labels.')
    options = settings.values['drifts']
    command = None
    if options.get('review_command'):
        command = ReviewCommandIdentity.inspect(options['review_command'],
            options['review_revision'], settings._home or Path.home())
    if command is None or not command.available:
        blockers.append('The actual independent reviewer command/profile is unavailable.')
    pipeline = _pipeline(settings, command)
    rows, counts = [], dict(unavailable=0, unknown=0, jevReady=0,
                            directReview=0, reviewerUnfit=0, possibleComparative=0)
    max_calls = {'embedding': 2, 'jev': 0, 'review': 0}
    # This fixed capture time is outside semantic input identity. It keeps the
    # same exact-byte plan reproducible and spends no quiet-period/provider work.
    for ordinal, case in enumerate(suite.drifts):
        row = {'id': case.id, 'semanticHash': semantic_fingerprint(case),
               'inputHash': None, 'jevBytes': None, 'reviewBytes': None,
               'maxCalls': {'jev': 0, 'review': 0}}
        if case.unavailable:
            row['route'] = 'unavailable_no_call'
            counts['unavailable'] += 1
        elif command is None or not command.available:
            row['route'] = 'profile_unknown'
            counts['unknown'] += 1
        else:
            prepared, _, _ = _prepare(case, ordinal, repository, settings, command, _FIXTURE_AT)
            sizes = _bytes(prepared, options)
            jev_fit = sizes['jev'] <= options['max_input_bytes']
            review_fit = sizes['review'] <= options['review_max_input_bytes']
            row.update(inputHash=prepared.input_hash, jevBytes=sizes['jev'],
                       reviewBytes=sizes['review'], reviewTimeoutMs=sizes['reviewTimeoutMs'])
            row['route'] = 'jev_ready' if jev_fit else 'direct_review'
            counts['jevReady' if jev_fit else 'directReview'] += 1
            counts['reviewerUnfit'] += int(not review_fit)
            counts['possibleComparative'] += int(jev_fit and review_fit)
            row['reviewFits'] = review_fit
            row['maxCalls'] = {'jev': options['attempts'] if jev_fit else 0,
                               'review': options['attempts'] if review_fit else 0}
            for stage, calls in row['maxCalls'].items():
                max_calls[stage] += calls
        rows.append(row)
    if counts['reviewerUnfit']:
        blockers.append('A complete reviewer request exceeds its configured cap; the full possible route does not fit.')
    if command is not None and command.available and not counts['possibleComparative']:
        blockers.append('No complete fixture can receive both Jev and reviewer adjudication; comparison cannot qualify.')
    staged = None
    if root is None:
        blockers.append('No verified staged Build was selected; development preflight cannot authorize live execution.')
    else:
        try:
            staged = _staged_binding(root, build)
        except (BuildError, MycelError) as error:
            blockers.append(str(error))
    settings.require_current()
    final_source, final_frozen = source_inputs(SOURCE_ROOT)
    if source != final_source or frozen != final_frozen:
        _refuse('Source inputs changed during provider preflight.')
    if settings_raw != settings_path.read_bytes() or suite.file_hash != sha256(suite_path.read_bytes()).hexdigest():
        _refuse('Settings or evaluation bytes changed during provider preflight.')
    report = {'schema': SCHEMA, 'repository': repository,
        'source': {'root': str(SOURCE_ROOT), **source, 'inputs': len(frozen)},
        'settings': {'path': str(settings_path), 'sha256': sha256(settings_raw).hexdigest(),
                     'home': str(settings._home)},
        'suite': {'path': str(suite.file), 'sha256': suite.file_hash, 'cases': len(suite.drifts),
                  'distinctCases': len(groups), 'criticalCases': critical, 'unchangedCases': unchanged,
                  'criticalCategories': sorted(categories)},
        'embedding': {**{key: settings.values['embedding'][key] for key in ('model', 'dimensions')},
                      'attemptsPerInput': 1, 'requestsMaximum': 2},
        'pipeline': pipeline, 'profileFingerprint': profile_fingerprint(pipeline),
        'command': (None if command is None else
            {'commandHash': command.command_hash, 'executableSha256': command.payload['executableSha256']}),
        'limits': {key: options[key] for key in ('candidates', 'at_once', 'seconds', 'attempts',
            'jev_timeout_seconds', 'review_timeout_seconds', 'max_input_bytes', 'review_max_input_bytes')},
        'staged': staged, 'routes': counts, 'maxCalls': max_calls, 'results': rows,
        'comparisonOutcome': 'unknown until actual routed common-case measurements',
        'requestFit': 'local serialized byte caps only; provider tokenizer/context fit remains unverified',
        'usage': None, 'cost': None, 'providerExecution': False, 'qualified': False,
        'automaticBuildQualification': False, 'liveReady': not blockers, 'blockers': blockers}
    report['planSha256'] = _digest(report)
    return OperationPlan(settings_path, suite_path, repository, root, build,
                         _json(report), settings, suite)


@contextmanager
def _hold_build(plan):
    with ExitStack() as held:
        with read_guard(plan.build_registry):
            held.enter_context(run_guard(plan.build_registry, plan.build))
        yield


def _recheck(plan, expected):
    current = prepare_operation(settings_path=plan.settings_path, suite_path=plan.suite_path,
        repository=plan.repository, build_registry=plan.build_registry, build=plan.build)
    if current.report['planSha256'] != expected or not current.report['liveReady']:
        _refuse('The reviewed provider plan no longer binds these exact inputs and staged program.')
    return current


class _BoundSettings:
    """Keep existing adapter guards bound to the reviewed external inputs too."""
    def __init__(self, plan):
        self._plan = plan
        self._original = plan.settings
        self.values = self._original.values
        self._home = self._original._home

    def __getattr__(self, name):
        return getattr(self._original, name)

    def require_valid(self, require_store=True):
        self._original.require_valid(require_store=require_store)

    def require_current(self):
        self._original.require_current()
        report = self._plan.report
        if (sha256(self._plan.settings_path.read_bytes()).hexdigest() != report['settings']['sha256']
                or sha256(self._plan.suite_path.read_bytes()).hexdigest() != report['suite']['sha256']):
            _refuse('Reviewed settings or fixture bytes changed before another provider boundary.')
        source, _ = source_inputs(SOURCE_ROOT)
        if any(source[key] != report['source'][key] for key in ('commit', 'dirty', 'inputsSha256')):
            _refuse('Reviewed source inputs changed before another provider boundary.')
        options = self.values['drifts']
        command = ReviewCommandIdentity.inspect(options['review_command'],
            options['review_revision'], self._home or Path.home())
        if (not command.available or command.command_hash != report['command']['commandHash']
                or command.payload['executableSha256'] != report['command']['executableSha256']):
            _refuse('The reviewed command changed before another provider boundary.')
        staged = report['staged']
        if (_program_stamp(Path(staged['program'])) != staged['programStampSha256']
                or sha256((self._plan.build_registry / self._plan.build / 'build.json').read_bytes()).hexdigest()
                != staged['buildRecordSha256']):
            _refuse('The staged program or Build record changed before another provider boundary.')


def _write_record(folder, name, value):
    with (folder / name).open('xb') as stream:
        (folder / name).chmod(0o600)
        stream.write(_json(value))


# TEST-TIER-DISABLED-BEGIN scripts/qualify_providers.py::run_operation
# def run_operation(plan, *, expected_plan_sha256, output_dir):
#     """One explicit group; return original in-process proofs and diagnostic data.
#
#     This API is an operator action just like --live, not an automatic test or
#     permission probe. Its returned proof objects may be consumed in this same
#     process. Saved records cannot recreate them after the caller exits.
#     """
#     if (type(plan) is not OperationPlan or not isinstance(expected_plan_sha256, str)
#             or _HASH.fullmatch(expected_plan_sha256) is None
#             or plan.report['planSha256'] != expected_plan_sha256
#             or not plan.report['liveReady'] or plan.build_registry is None or plan.build is None):
#         _refuse('Explicit execution requires a ready, exactly reviewed staged provider plan.')
#     output = Path(output_dir).absolute()
#     # Result transcripts must remain separate from tracked source inputs.
#     if output.resolve().is_relative_to(SOURCE_ROOT.resolve()):
#         _refuse('Retain provider reports outside the source repository.')
#     with _hold_build(plan):
#         current = _recheck(plan, expected_plan_sha256)
#         output.mkdir(mode=0o700)  # Exclusive: never replace an earlier operation.
#         output.chmod(0o700)
#         _write_record(output, 'preflight.json', current.report)
#         # Recheck after establishing retention, before any credential boundary.
#         current = _recheck(plan, expected_plan_sha256)
#         reports, proofs = {}, ()
#         receipt = {'schema': SCHEMA, 'recordedAt': datetime.now(timezone.utc).isoformat(),
#             'planSha256': expected_plan_sha256, 'build': plan.build,
#             'implementationIdentity': current.report['source']['inputsSha256'],
#             'providerGroupInvocations': 0, 'deploymentConsumerInvocations': 0,
#             'passed': False, 'savedRecordsAreProofObjects': False,
#             'automaticBuildQualification': False, 'checks': []}
#         identity = receipt['implementationIdentity']
#         bound_settings = _BoundSettings(current)
#         try:
#             receipt['providerGroupInvocations'] = 1
#             bound_settings.require_current()
#             provider_proofs, reports = run_provider_checks(bound_settings, current.suite,
#                 repository=plan.repository, build=plan.build,
#                 implementation_identity=identity, live=True)
#             proofs = (provider_proofs,)
#             _recheck(plan, expected_plan_sha256)
#             receipt['deploymentConsumerInvocations'] = 1
#             proofs, reports = run_provider_deployment_checks(bound_settings, current.suite,
#                 provider_proofs, reports, repository=plan.repository, build=plan.build,
#                 implementation_identity=identity, live=True)
#             _recheck(plan, expected_plan_sha256)
#             receipt['passed'] = (len(proofs) == 2 and all(proof.checks for proof in proofs)
#                 and all(check.status == 'passed' for proof in proofs for check in proof.checks)
#                 and reports.get('deployment', {}).get('sameProcessProviderGroupConsumed') is True)
#         except KeyboardInterrupt:
#             receipt['failure'] = 'interrupted'
#         except (MycelError, BuildError):
#             receipt['failure'] = 'operation_refused_or_bindings_changed'
#         except Exception:
#             # Provider/OS/adapter messages may contain private data. Preserve
#             # returned reports, but never serialize arbitrary exception text.
#             receipt['failure'] = 'operation_failed'
#         finally:
#             receipt['checks'] = [asdict(check) for proof in proofs for check in proof.checks]
#             _write_record(output, 'reports.json', reports)
#             _write_record(output, 'receipt.json', receipt)
#         return proofs, reports, receipt
# TEST-TIER-DISABLED-END scripts/qualify_providers.py::run_operation
def run_operation(plan, *, expected_plan_sha256, output_dir):
    raise RuntimeError('Tests are commented under the tier policy; see TESTS.md. Restore only in an explicitly requested testing task.')  # TEST-TIER-REFUSAL


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', required=True, type=Path)
    parser.add_argument('--suite', required=True, type=Path)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--build-registry', type=Path)
    parser.add_argument('--build')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--expect-plan-sha256')
    parser.add_argument('--output-dir', type=Path)
    arguments = parser.parse_args(argv)
    if arguments.live and (not arguments.expect_plan_sha256 or arguments.output_dir is None):
        parser.error('--live requires --expect-plan-sha256 and --output-dir')
    if not arguments.live and (arguments.expect_plan_sha256 or arguments.output_dir is not None):
        parser.error('--expect-plan-sha256 and --output-dir require --live')
    try:
        plan = prepare_operation(settings_path=arguments.settings, suite_path=arguments.suite,
            repository=arguments.repo, build_registry=arguments.build_registry, build=arguments.build)
        if not arguments.live:
            print(_json(plan.report).decode(), end='')
            return 0 if plan.report['liveReady'] else 1
        _, _, receipt = run_operation(plan, expected_plan_sha256=arguments.expect_plan_sha256,
                                      output_dir=arguments.output_dir)
        print(_json(receipt).decode(), end='')
        return 0 if receipt['passed'] else 2 if receipt.get('failure') == 'interrupted' else 1
    except (MycelError, BuildError, OSError, ValueError):
        print(_json({'schema': SCHEMA, 'passed': False,
                     'failure': 'invalid_or_unavailable_operation_inputs'}).decode(), end='')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN scripts/qualify_providers.py:12
# from dataclasses import asdict, dataclass, field
# TEST-TIER-IMPORTS-END scripts/qualify_providers.py:12
# TEST-TIER-IMPORTS-BEGIN scripts/qualify_providers.py:13
# from datetime import datetime, timezone
# TEST-TIER-IMPORTS-END scripts/qualify_providers.py:13
# TEST-TIER-IMPORTS-BEGIN scripts/qualify_providers.py:44
# from mycel._provider_checks import run_provider_checks
# TEST-TIER-IMPORTS-END scripts/qualify_providers.py:44
# TEST-TIER-IMPORTS-BEGIN scripts/qualify_providers.py:45
# from mycel._provider_deployment import run_provider_deployment_checks
# TEST-TIER-IMPORTS-END scripts/qualify_providers.py:45
