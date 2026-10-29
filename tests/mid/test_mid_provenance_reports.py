
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportUnitTests.test_invalid_report_arguments_stop_before_settings_store_and_children
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Invalid report arguments stop before settings store and children.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_invalid_report_arguments_stop_before_settings_store_and_children(self):
#         with patch('mycel._cli.invocation_store') as store, patch('subprocess.Popen') as child:
#             for handler, arguments in ((handle_stale, ('extra',)), (handle_status, ('extra',)),
#                     (handle_drifts, ('extra',)), (handle_drifts, ('--closed', '--closed')),
#                     (handle_drifts, ('--dry-run',))):
#                 with self.subTest(arguments=arguments), self.assertRaises(MycelError) as failure:
#                     handler(Invocation('drifts', arguments=arguments))
#                 self.assertEqual(failure.exception.code, 'invalid_input')
#             store.assert_not_called()
#             child.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportStoreTests.test_public_current_closed_reports_count_work_pairs_and_completed_support_without_writes
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Public current closed reports count work pairs and completed support without writes.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_public_current_closed_reports_count_work_pairs_and_completed_support_without_writes(self):
#         with self.base.connect() as connection:
#             self.helper.prepare(connection)
#             self.helper.change(connection)
#             before = self.state(connection)
#             with self.no_work():
#                 status, reply = self.invoke(connection, 'drifts')
#             self.assertEqual(status, 0, reply)
#             result = reply['repositories'][0]['result']
#             self.assertEqual((len(result['drifts']), len(result['drifts'][0]['sources'])), (1, 3))
#             self.assertEqual(result['counts']['work']['currentOpen'], 1)
#             self.assertEqual(result['counts']['pairs']['currentOpen'], 3)
#             self.assertEqual(result['counts']['stages']['pending_jev'], 3)
#             self.assertEqual(self.state(connection), before)
#             drift = self.helper.one(connection)
#             first = self.helper.reason(drift, 1)
#             self.helper.record(connection, drift, first, status='pending_debounce')
#             self.assertEqual(ProvenanceReports(connection).drifts('downstream')['counts']['stages']['pending_debounce'], 1)
#             self.helper.record(connection, drift, first, status='needs_llm_review',
#                 canonical_input_hash='a' * 64,
#                 evidence={'jev': {'provider': 'typesafe', 'model': 'jev-1.13.0', 'inputHash': 'a' * 64}})
#             self.helper.record(connection, drift, self.helper.reason(drift, 2), status='error',
#                                evidence={'reason': 'authentication'})
#             self.helper.record(connection, drift, self.helper.reason(drift, 3), judgement='insufficient_evidence')
#             before = self.state(connection)
#             with self.no_work():
#                 mixed = ProvenanceReports(connection).drifts('downstream')
#             stages = mixed['counts']['stages']
#             self.assertEqual((stages['needs_llm_review'], stages['error'], stages['complete']), (1, 1, 1))
#             self.assertEqual(mixed['counts']['judgements']['insufficient_evidence'], 1)
#             self.assertEqual(mixed['counts']['unresolvedFaults'], 1)
#             evidence = self.helper.reason(mixed['drifts'][0], 1)['classification']
#             self.assertEqual((evidence['inputHash'], evidence['evidence']['jev']['model']), ('a' * 64, 'jev-1.13.0'))
#             self.assertEqual(self.state(connection), before)
#             drift = self.helper.one(connection)
#             for source in list(drift['sources']):
#                 drift = self.helper.support(connection, drift, source)
#             before = self.state(connection)
#             with self.no_work():
#                 status, opened = self.invoke(connection, 'drifts')
#                 closed_status, closed = self.invoke(connection, 'drifts', '--closed')
#                 current_status, current = self.invoke(connection, 'status')
#             self.assertEqual((status, closed_status, current_status), (0, 0, 0))
#             self.assertEqual(opened['repositories'][0]['result']['drifts'], [])
#             report = closed['repositories'][0]['result']
#             self.assertEqual((len(report['drifts']), report['drifts'][0]['state']), (1, 'closed'))
#             self.assertEqual(report['drifts'][0]['closed']['because'], 'still_supported')
#             self.assertEqual(report['counts']['pairs']['currentClosed'], 3)
#             self.assertEqual(report['counts']['stages']['complete'], 3)
#             self.assertEqual(report['counts']['judgements']['still_supported'], 3)
#             self.assertEqual(current['repositories'][0]['result']['drifts'], report['counts'])
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportStoreTests.test_generated_index_staleness_keeps_separate_regeneration_work_and_canonical_sources
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Generated index staleness keeps separate regeneration work and canonical sources.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_generated_index_staleness_keeps_separate_regeneration_work_and_canonical_sources(self):
#         from mycel._locks import invocation_guard
#         helper = fixtures.generated.GeneratedStoreTests()
#         helper.fixture, helper.base = self.fixture, self.base
#         with self.base.connect() as connection:
#             self.helper.prepare(connection)
#             with invocation_guard(connection) as invocation:
#                 capture = helper.capture(connection, self.helper.addresses[0], owner='fixture')
#                 summary = helper.publish(connection, invocation, helper.lease(connection, invocation, capture))
#             self.helper.change(connection, 1)
#             before = self.state(connection)
#             with self.no_work():
#                 reports = ProvenanceReports(connection)
#                 work = reports.drifts('fixture')
#                 stale = reports.stale('fixture')
#                 status = reports.status('fixture')
#             self.assertEqual(work['drifts'], [])
#             regeneration, = work['regeneration']
#             self.assertEqual(regeneration['place']['address'], summary.place.address)
#             self.assertEqual(work['counts']['regeneration'], 1)
#             self.assertEqual(work['counts']['work']['currentOpen'], 0)
#             generated, = stale['stale']
#             self.assertEqual(generated['chunk']['address'], summary.place.address)
#             self.assertEqual(generated['chunk']['root'], 'index')
#             self.assertEqual(generated['sources'][0]['address'], self.helper.addresses[0])
#             self.assertEqual((status['stale'], status['drifts']['regeneration']), (1, 1))
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportStoreTests.test_off_disk_work_and_removed_version_history_require_explicit_filters_and_keep_locations
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Off disk work and removed version history require explicit filters and keep locations.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_off_disk_work_and_removed_version_history_require_explicit_filters_and_keep_locations(self):
#         (self.fixture.downstream / 'keep.md').write_bytes(b'# Keep\nIndependent document.\n')
#         self.base.git('init', '--initial-branch=dependant-main', cwd=self.fixture.downstream)
#         self.base.commit(cwd=self.fixture.downstream)
#         self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
#             '[repos.downstream]\nenabled=true\ncode_root=' + json.dumps(str(self.fixture.downstream))))
#         self.fixture.reload()
#         with self.base.connect() as connection:
#             self.helper.prepare(connection)
#             self.helper.change(connection, 1)
#             original = self.helper.one(connection)
#             self.fixture.answer.unlink()
#             self.fixture.publish(connection, 'downstream')
#             self.helper.sync(connection)
#             before = self.state(connection)
#             with self.no_work():
#                 reports = ProvenanceReports(connection)
#                 self.assertEqual(reports.drifts('downstream')['drifts'], [])
#                 self.assertEqual(reports.drifts('downstream', closed=True)['drifts'], [])
#                 all_versions = reports.drifts('downstream', all_versions=True)
#                 status = reports.status('downstream')
#             inactive, = all_versions['drifts']
#             self.assertEqual((inactive['id'], inactive['current'], inactive['state']), (original['id'], False, 'open'))
#             self.assertTrue(any(location['kind'] == 'branch' for location in inactive['locations']))
#             self.assertEqual((all_versions['counts']['work']['inactiveOpen'],
#                               all_versions['counts']['pairs']['inactiveOpen'],
#                               all_versions['counts']['inactiveVersions']), (1, 1, 1))
#             self.assertEqual(status['stale'], 0)
#             self.assertEqual(self.state(connection), before)
#             self.base.commit(cwd=self.fixture.downstream)
#             self.fixture.publish(connection, 'downstream')
#             self.helper.sync(connection)
#             before = self.state(connection)
#             with self.no_work():
#                 self.assertEqual(reports.drifts('downstream', all_versions=True)['drifts'], [])
#                 removed, = reports.drifts('downstream', closed=True, all_versions=True)['drifts']
#             self.assertEqual((removed['id'], removed['closed']['because']), (original['id'], 'version_removed'))
#             self.assertEqual(removed['locations'], [])
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportStoreTests.test_stale_report_keeps_all_changed_removed_and_upstream_sources_and_classification_evidence
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Stale report keeps all changed removed and upstream sources and classification evidence.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_stale_report_keeps_all_changed_removed_and_upstream_sources_and_classification_evidence(self):
#         tail = self.base.base / 'tail'
#         tail.mkdir()
#         (tail / 'tail.md').write_bytes(b'---\nsources: ["downstream:@artifact/answer.md#Answer", '
#             b'"fixture:@artifact/source3.md#Source3"]\n---\n# Tail\nUnchanged tail.\n')
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.tail]\nenabled=true\n'
#                                     + 'artifact_root=' + json.dumps(str(tail)) + '\n')
#         self.fixture.reload()
#         with self.base.connect() as connection:
#             self.helper.prepare(connection)
#             self.fixture.publish(connection, 'tail')
#             self.helper.extra[0].unlink()
#             self.helper.change(connection, 1, 3)
#             drift = self.helper.one(connection)
#             self.helper.support(connection, drift, self.helper.reason(drift, 1))
#             before = self.state(connection)
#             with self.no_work():
#                 status, reply = self.invoke(connection, 'stale', repositories=('downstream', 'tail'))
#             self.assertEqual(status, 0, reply)
#             downstream, later = (entry['result'] for entry in reply['repositories'])
#             first, = downstream['stale']
#             last, = later['stale']
#             self.assertEqual((downstream['count'], later['count']), (1, 1))
#             self.assertEqual(first['chunk']['address'], 'downstream:@artifact/answer.md#Answer')
#             self.assertEqual({reason['kind'] for reason in first['reasons']}, {'source_changed', 'source_removed'})
#             self.assertEqual({source['address'] for source in first['sources']}, set(self.helper.addresses))
#             classified = next(reason for reason in first['reasons'] if reason['source']['address'] == self.helper.addresses[0])
#             self.assertEqual(classified['classification']['judgement'], 'still_supported')
#             self.assertEqual(classified['classification']['status'], 'complete')
#             self.assertEqual(len(last['reasons']), 4)
#             self.assertEqual(last['reasons'][0]['kind'], 'source_changed')
#             for reason in last['reasons'][1:]:
#                 self.assertEqual(reason['kind'], 'upstream_stale')
#                 self.assertEqual([place['address'] for place in reason['via']], ['downstream:@artifact/answer.md#Answer'])
#             self.assertTrue(all(reason['source']['root'] == 'artifact' and reason['source']['path']
#                                 for reason in first['reasons'] + last['reasons']))
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_provenance_reports.py::ProvenanceReportStoreTests.test_repository_status_counts_current_stale_and_every_unresolved_invalid_ref_occurrence
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Repository status counts current stale and every unresolved invalid ref occurrence.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_provenance_reports.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repository_status_counts_current_stale_and_every_unresolved_invalid_ref_occurrence(self):
#         self.helper.write_answer(*self.helper.addresses, 'fixture:@artifact/missing.md#Missing',
#             'fixture:missing.md#Missing', 'unknown:@artifact/source.md', 'disabled:@artifact/source.md', 'not a ref')
#         self.base.config.write_text(self.base.config.read_text() + '\n[repos.disabled]\nenabled=false\n')
#         self.fixture.reload()
#         with self.base.connect() as connection:
#             self.helper.prepare(connection)
#             self.helper.change(connection, 1)
#             before = self.state(connection)
#             with self.no_work():
#                 status, reply = self.invoke(connection, 'status', repositories=('downstream', 'unknown'))
#                 fresh_status, fresh = self.invoke(connection, 'status', repositories=('fixture',))
#             self.assertEqual(status, 1, reply)
#             entries = {entry['repository']: entry for entry in reply['repositories']}
#             current = entries['downstream']['result']
#             self.assertEqual((current['chunks']['onDisk'], current['stale'], current['refs'], current['unresolvedRefs'],
#                               current['invalidRefs'], current['refFaults']), (1, 1, 8, 2, 2, 5))
#             self.assertGreaterEqual(current['drifts']['unresolvedFaults'], 4)
#             self.assertEqual(entries['unknown']['error']['code'], 'unknown_repository')
#             self.assertEqual(fresh_status, 0, fresh)
#             source = fresh['repositories'][0]['result']
#             self.assertEqual((source['stale'], source['unresolvedRefs'], source['invalidRefs']), (0, 0, 0))
#             self.assertEqual(self.state(connection), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END
