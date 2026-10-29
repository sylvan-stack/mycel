# Mid-tier source from scripts/qualify_providers.py; see MID_TIER.md.
# Shared helpers and refusal entry points remain at the original path.

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

raise RuntimeError("Mid-tier checks require an explicitly requested testing task; see MID_TIER.md.")
