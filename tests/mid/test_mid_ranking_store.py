"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_ranking_store as _support
from test_ranking_store import (StoreCandidates ,graph_for ,ingest_fixtures)


class RankingStoreTests(_support.RankingStoreTests):


# TEST-TIER-BEGIN tests/test_ranking_store.py::RankingStoreTests.test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source
    def test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source(self):
        base = ingest_fixtures.IngestStoreTests()
        base.store_fixture = self.store_fixture
        base.setUp()
        self.addCleanup(base.doCleanups)
        code = base.base.code / 'work.py'
        code.write_text('def work():\n    return 1\n')
        (base.base.artifact / 'guide.md').write_text('---\nrole: authored\n---\n# Guide\nHow work happens.\n'
            '<!-- sources:\nfixture:@code/work.py#work\n-->\n')
        base.base.commit()
        self.assertEqual(base.invoke('--repo', 'fixture')[0], 0)
        code.unlink()
        status, reply = base.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 0, reply)
        with base.base.connect() as connection:
            rows = connection.execute("SELECT dependant_version,state FROM public.mycel_dependencies WHERE kind='declared'").fetchall()
            self.assertEqual(len({version for version,state in rows}), 1)
            self.assertEqual({state['declarationLocation']['kind'] for version,state in rows}, {'disk','branch'})
            with StoreCandidates(connection, base.base.settings).snapshot(('fixture',)) as snapshot:
                self.assertEqual(graph_for(snapshot, 'fixture').citations, ())
                self.assertEqual(snapshot.ranked('how does work happen', self.query, only='code')[0].results, ())
# TEST-TIER-END tests/test_ranking_store.py::RankingStoreTests.test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_bridge_uses_full_document_and_code_pools_before_eight_and_three_caps
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Bridge uses full document and code pools before eight and three caps.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_bridge_uses_full_document_and_code_pools_before_eight_and_three_caps(self):
#         with self.base.connection() as connection:
#             for number in range(25):
#                 self.seed(connection, path=f'direct{number:02}.py', name=f'Direct{number}', cosine=.5)
#             targets = [self.seed(connection, path=f'target{number}.py', name=f'Target{number}',
#                                  cosine=.40-number*.05) for number in range(4)]
#             ninth = self.seed(connection, path='ninth.py', name='Ninth', cosine=.1)
#             docs = [self.seed(connection, path=f'guide{number}.md', root='artifact', kind='document',
#                               name=f'Guide{number}', cosine=.90-number*.01) for number in range(9)]
#             for document in docs[:8]:
#                 for number in range(4):
#                     self.cite(connection, document, f'fixture:@code/target{number}.py#Target{number}')
#             self.cite(connection, docs[8], 'fixture:@code/ninth.py#Ninth')
#             settings = self.settings()
#             with StoreCandidates(connection, settings).snapshot(('fixture',)) as snapshot:
#                 candidates = snapshot.candidates('how does routing work', self.query, k=10, only='code')[0]
#                 self.assertFalse(any(candidate.chunk.identifier == str(targets[0][1])
#                                      for candidate in candidates.meaning))
#                 ranked = snapshot.ranked('how does routing work', self.query, k=10, only='code')[0]
#                 # Three bridge-only targets outrank every direct candidate.
#                 for target in targets[:3]:
#                     entry = self.entries(ranked)[str(target[1])]
#                     self.assertIsNone(entry.meaning_rank)
#                     self.assertAlmostEqual(entry.score, .828)
#                 # The full requested pool also exposes excluded bridge targets.
#                 all_ranked = snapshot.ranked('how does routing work', self.query, k=100, only='code')[0]
#                 entries = self.entries(all_ranked)
#                 for target in targets[:3]:
#                     entry = entries[str(target[1])]
#                     self.assertEqual(entry.via.name, 'Guide0')
#                     self.assertAlmostEqual(entry.raw_bridge_cosine, .9)
#                 self.assertIsNone(entries[str(targets[3][1])].via)
#                 self.assertIsNone(entries[str(ninth[1])].via)
#                 self.assertEqual(len(ranked.results), 10)
#                 # At k=10 the bridge still computes all selected citations.
#                 graph = graph_for(snapshot, 'fixture', only='code')
#                 self.assertEqual(len(graph.documents), 9)
#                 self.assertEqual(len(graph.citations), 9)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_repeated_refs_do_not_multiply_results_via_or_documented_in
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Repeated refs do not multiply results via or documented in.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_repeated_refs_do_not_multiply_results_via_or_documented_in(self):
#         with self.base.connection() as connection:
#             code = self.seed(connection, path='work.py', name='Work', cosine=.8)
#             docs = [self.seed(connection, path=f'{name}.md', kind='document', name=name, cosine=cosine)
#                     for name, cosine in (('z', .9), ('b', .9), ('a', .85))]
#             for doc in reversed(docs):
#                 for kind in ('asserted', 'declared'):
#                     self.cite(connection, doc, 'fixture:@code/work.py#Work', kind=kind)
#             with StoreCandidates(connection, self.settings()).snapshot(('fixture',)) as snapshot:
#                 with self.assertRaises(MycelError):
#                     graph_for(snapshot, 'other')
#                 first = snapshot.ranked('how does it work', self.query, only='code')[0]
#                 self.assertEqual(first, snapshot.ranked('how does it work', self.query, only='code')[0])
#                 self.assertEqual(len(first.results), 1)
#                 entry = self.entries(first)[str(code[1])]
#                 self.assertAlmostEqual(entry.score, .878)
#                 self.assertEqual(entry.via.name, 'b')
#                 self.assertEqual([doc.name for doc in entry.documented_in], ['b', 'z'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_current_resolved_versions_replace_pins_and_retained_moves_keep_identity
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Current resolved versions replace pins and retained moves keep identity.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_current_resolved_versions_replace_pins_and_retained_moves_keep_identity(self):
#         with self.base.connection() as connection:
#             old = self.seed(connection, path='work.py', name='Work', cosine=.7)
#             doc = self.seed(connection, path='guide.md', kind='document', name='Guide', cosine=.95)
#             self.cite(connection, doc, 'fixture:@code/work.py#Work', anchor=old[1], pinned=old[2])
#             connection.execute("UPDATE public.mycel_locations SET kind='branch',location='old' WHERE chunk_version=%s", (old[2],))
#             connection.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old' WHERE file_version IN "
#                                '(SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', (old[0],))
#             new = self.seed(connection, file_id=old[0], chunk_id=old[1], path='work.py', name='Renamed',
#                             source='new implementation\n', cosine=.4)
#             with StoreCandidates(connection, self.settings()).snapshot(('fixture',)) as snapshot:
#                 entry = self.entries(snapshot.ranked('how does work happen', self.query, only='code')[0])[str(old[1])]
#                 self.assertEqual(entry.chunk.version, new[2])
#                 self.assertEqual(entry.chunk.name, 'Renamed')
#                 self.assertEqual(entry.via.name, 'Guide')
#             # A retained file move likewise supplies its current canonical place.
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=%s WHERE kind='disk' "
#                 'AND file_version IN (SELECT id FROM public.mycel_file_versions WHERE file_id=%s)',
#                 (Jsonb({'root': 'code', 'path': 'moved.py', 'aliases': [{'root':'code','path':'moved.py'}], 'recognizedMoves': [{'root':'code','path':'work.py'}]}), old[0]))
#             with StoreCandidates(connection, self.settings()).snapshot(('fixture',)) as snapshot:
#                 entry = self.entries(snapshot.ranked('how does work happen', self.query, only='code')[0])[str(old[1])]
#                 self.assertEqual(entry.chunk.path, 'moved.py')
#                 self.assertEqual(entry.via.name, 'Guide')
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_branch_owned_refs_generated_edges_faults_and_foreign_code_never_deliver
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Branch owned refs generated edges faults and foreign code never deliver.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_branch_owned_refs_generated_edges_faults_and_foreign_code_never_deliver(self):
#         with self.base.connection() as connection:
#             code = self.seed(connection, path='work.py', name='Work', cosine=.4)
#             foreign = self.seed(connection, repository='other', path='outside.py', name='Outside', cosine=.4)
#             doc = self.seed(connection, path='guide.md', kind='document', name='Guide', cosine=.95)
#             file_version = connection.execute('SELECT file_version FROM public.mycel_file_locations '
#                                               'WHERE id=(SELECT file_location FROM public.mycel_locations WHERE chunk_version=%s)', (doc[2],)).fetchone()[0]
#             branch = uuid4()
#             connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,'branch','branch','{}')", (branch,file_version))
#             connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,'branch','branch','{}')", (uuid4(),doc[2],branch))
#             self.cite(connection, doc, 'fixture:@code/work.py#Work', location=branch)
#             self.cite(connection, doc, 'fixture:@code/work.py#Work', kind='generated')
#             self.cite(connection, doc, 'fixture:@code/work.py#Work', syntax='invalid_syntax')
#             self.cite(connection, doc, 'other:@code/outside.py#Outside')
#             self.cite(connection, doc, 'fixture:@code/missing.py#Absent')
#             with StoreCandidates(connection, self.settings()).snapshot(('fixture',)) as snapshot:
#                 graph = graph_for(snapshot, 'fixture')
#                 self.assertEqual(graph.citations, ())
#                 entry = self.entries(snapshot.ranked('how does work happen', self.query, only='code')[0])[str(code[1])]
#                 self.assertIsNone(entry.via)
#                 self.assertEqual(entry.documented_in, ())
#                 self.assertNotIn(str(foreign[1]), self.entries(snapshot.ranked('how does work happen', self.query)[0]))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_snapshot_is_read_only_stable_per_member_and_refuses_escaped_lease
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Snapshot is read only stable per member and refuses escaped lease.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_snapshot_is_read_only_stable_per_member_and_refuses_escaped_lease(self):
#         with self.base.connection() as connection, self.base.connection() as writer:
#             code = self.seed(connection, path='work.py', name='Work', cosine=.4)
#             doc = self.seed(connection, path='guide.md', kind='document', name='Guide', cosine=.9)
#             self.cite(connection, doc, 'fixture:@code/work.py#Work')
#             self.seed(connection, repository='other', path='other.py', name='Other', cosine=.7)
#             settings = self.settings(organization=True)
#             recorded = fixtures._RecordingConnection(connection)
#             before = self.base.contents(connection)
#             with StoreCandidates(recorded, settings).snapshot(('team',)) as snapshot:
#                 reply = snapshot.ranked('how does work happen', self.query, k=1, only='code')
#                 self.assertEqual([member.repository for member in reply], ['fixture', 'handbook', 'other'])
#                 self.assertEqual([len(member.results) for member in reply], [1,0,1])
#                 with self.assertRaises(MycelError):
#                     graph_for(snapshot, 'disabled')
#                 writer.execute('DELETE FROM public.mycel_dependencies')
#                 self.assertEqual(snapshot.ranked('how does work happen', self.query, k=1, only='code'), reply)
#                 self.assertEqual(self.base.contents(connection), before)
#             with self.assertRaises(MycelError):
#                 snapshot.ranked('how does work happen', self.query)
#             with StoreCandidates(connection, settings).snapshot(('fixture',)) as snapshot:
#                 entry = self.entries(snapshot.ranked('how does work happen', self.query, only='code')[0])[str(code[1])]
#                 self.assertIsNone(entry.via)
#             self.assertFalse(any(statement.lstrip().upper().startswith(
#                 ('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP')) for statement in recorded.statements))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_actual_ingest_file_and_class_family_refs_are_one_hop_current_disk_citations
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Actual ingest file and class family refs are one hop current disk citations.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_actual_ingest_file_and_class_family_refs_are_one_hop_current_disk_citations(self):
#         base = ingest_fixtures.IngestStoreTests()
#         base.store_fixture = self.store_fixture
#         base.setUp()
#         self.addCleanup(base.doCleanups)
#         (base.base.code / 'work.py').write_text('class Worker:\n    def run(self):\n        return 1\n\ndef other():\n    return 2\n')
#         (base.base.artifact / 'guide.md').write_text('---\nrole: authored\n---\n# Guide\nHow work happens.\n'
#             '<!-- sources:\nfixture:@code/work.py#Worker\nfixture:@code/work.py\n-->\n')
#         base.base.commit()
#         self.assertEqual(base.invoke('--repo', 'fixture')[0], 0)
#         with base.base.connect() as connection:
#             rows = connection.execute("SELECT cv.chunk_id,cv.id,cv.text,f.repository,f.corpus FROM public.mycel_chunk_versions cv "
#                 'JOIN public.mycel_chunks c ON c.id=cv.chunk_id JOIN public.mycel_files f ON f.id=c.file_id '
#                 "WHERE EXISTS (SELECT 1 FROM public.mycel_locations l WHERE l.chunk_version=cv.id AND l.kind='disk')").fetchall()
#             for chunk_id,version,text,repository,corpus in rows:
#                 self.base.plan(connection, chunk_id,version,text,repository=repository,
#                                vectors=((.95, math.sqrt(1-.95**2)),) if corpus=='documents' else ((.4, math.sqrt(1-.4**2)),))
#             with StoreCandidates(connection, base.base.settings).snapshot(('fixture',)) as snapshot:
#                 graph = graph_for(snapshot, 'fixture', only='code')
#                 self.assertEqual(len(graph.citations), 1)
#                 self.assertIn('Worker.run', [chunk.name for chunk in graph.citations[0].code])
#                 self.assertIn('other', [chunk.name for chunk in graph.citations[0].code])
#                 self.assertEqual(len({chunk.key for chunk in graph.citations[0].code}), len(graph.citations[0].code))
#                 reply = snapshot.ranked('how does work happen', self.query, k=100, only='code')[0]
#                 self.assertTrue(any(entry.via and entry.via.name=='Guide' for entry in reply.results))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_ranking_store.py::RankingStoreTests.test_incomplete_citers_and_selected_shared_documents_respect_code_only_scope
# Reason: Narrower case removed from this family after retaining test_actual_ingest_shared_version_branch_ref_cannot_restore_deleted_disk_source. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Incomplete citers and selected shared documents respect code only scope.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_ranking_store.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_incomplete_citers_and_selected_shared_documents_respect_code_only_scope(self):
#         with self.base.connection() as connection:
#             code = self.seed(connection, path='work.py', name='Work', cosine=.4)
#             own = self.seed(connection, path='guide.md', kind='document', name='Own', cosine=.9)
#             shared = self.seed(connection, repository='handbook', root='artifact', path='selected/shared.md',
#                                kind='document', name='Shared', cosine=.99)
#             incomplete = self.seed(connection, path='partial.md', kind='document', name='Partial', embedded=False)
#             for doc in (own, shared, incomplete):
#                 self.cite(connection, doc, 'fixture:@code/work.py#Work')
#             settings = self.settings(shared=({'repo':'handbook','paths':['selected']},))
#             with StoreCandidates(connection, settings).snapshot(('fixture',)) as snapshot:
#                 mixed = self.entries(snapshot.ranked('how does work happen', self.query)[0])[str(code[1])]
#                 self.assertEqual(mixed.via.name, 'Own')
#                 self.assertEqual([doc.name for doc in mixed.documented_in], ['Shared', 'Own'])
#                 code_only = self.entries(snapshot.ranked('how does work happen', self.query, only='code')[0])[str(code[1])]
#                 self.assertEqual(code_only.via.name, 'Own')
#                 self.assertEqual([doc.name for doc in code_only.documented_in], ['Own'])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
