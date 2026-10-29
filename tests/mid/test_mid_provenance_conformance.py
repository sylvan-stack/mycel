"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_provenance_conformance as _support
# from test_provenance_conformance import (
#     ProvenanceConformanceStoreTests,
#     StringIO,
#     classifiers,
#     json,
#     patch,
#     run,
#     unittest,
# )


# class ProvenanceConformanceStoreTests(_support.ProvenanceConformanceStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_provenance_conformance.py::ProvenanceConformanceStoreTests.test_public_cli_preserves_all_five_provenance_contracts_in_one_index
#     def test_public_cli_preserves_all_five_provenance_contracts_in_one_index(self):
#         downstream = self.fixture.fixture.fixture.downstream
#         warning = downstream / 'notice.md'
#         warning.write_text('---\nrole: authored\n---\n# Notice\nRelated independent warning.\n')
#         observer = downstream / 'observer.md'
#         observer.write_text('---\nrole: authored\nsources: ["downstream:@artifact/notice.md#Notice"]\n---\n'
#                             '# Observer\nThis rests on the independent notice, not its related source.\n')
#         for number in range(12):
#             (self.base.artifact / ('note' + str(number).zfill(2) + '.md')).write_text(
#                 '# Note' + str(number) + '\nComplete source note ' + str(number) + '.\n')
#         self.fixture.write_reviewer()
#         self.base.config.write_text(self.base.config.read_text() + '\n[summaries]\ncommand=' +
#             json.dumps([sys.executable, '-c', 'raise SystemExit("unexpected real summary adapter")']) + '\n')
#         self.base.settings = load_settings(path=self.base.config, home=self.base.base)
#         self.base.commit()
#         self.invoke('ingest', '--repo', 'fixture', '--repo', 'downstream')
#         answer = 'downstream:@artifact/answer.md#Answer'
#         notice = 'downstream:@artifact/notice.md#Notice'
#         source = self.fixture.fixture.addresses[0]
#         self.assertTrue(self.invoke('relate', notice, source)['changed'])
#         verification = self.invoke('confirm', answer, '--by', 'conformance-owner', '--how', 'check')
#         self.assertEqual((verification['by'], verification['how']), ('conformance-owner', 'check'))
#         self.assertEqual(self.invoke('verifications', '--repo', 'downstream')['verifications'][0]['id'], verification['id'])
#         at = datetime.now(timezone.utc) + timedelta(seconds=1)
#         changed = self.fixture.fixture.fixture.source
#         changed.write_bytes(changed.read_bytes().replace(b'Original governing source.', b'Original governing source!'))
#         os.utime(changed, (at.timestamp(), at.timestamp()))
#         self.base.commit()
#         self.invoke('ingest', '--repo', 'fixture')
#         initial = self.repository(self.invoke('drifts', '--repo', 'downstream'), 'downstream')
#         self.assertTrue(initial['drifts'])
#         read_answer = self.invoke('read', answer, '--no-fresh')
#         read_notice = self.invoke('read', notice, '--no-fresh')
#         self.assertTrue(read_answer['stale'])
#         self.assertTrue(any(reason['edge'] == 'related' for reason in read_notice['staleReasons']))
#         self.assertFalse(self.invoke('read', 'downstream:@artifact/observer.md#Observer', '--no-fresh')['stale'])
#         calls = []
#         now = [at]
#         def jev(decision, deadline, cancelled):
#             calls.append(('jev', decision.as_dict()))
#             if decision.payload['current']['state'] == 'deleted':
#                 probabilities = {name: Decimal(int(name == 'needs_review')) for name in LABELS}
#                 return route_response(decision, JevResponse(decision.payload['models']['jev']['model'],
#                     'needs_review', probabilities, Decimal(1), {'input_tokens': 0, 'output_tokens': 0}, False))
#             probabilities = {name: Decimal('0.6') if name == 'still_supported' else Decimal('0.2') for name in LABELS}
#             return route_response(decision, JevResponse(decision.payload['models']['jev']['model'],
#                 'still_supported', probabilities, Decimal('0.4'), {'input_tokens': 0, 'output_tokens': 0}, False))
#         def reviewer(decision, deadline, cancelled):
#             calls.append(('review', decision.as_dict()))
#             return ReviewerSuccess(ReviewerRequest(decision, 1), 'still_supported',
#                 'Controlled service-free support judgement.', (decision.evidence_locators[0],), None)
#         dependencies = ClassifyDependencies(utc_now=lambda: now[0].isoformat(),
#             jev_factory=lambda *_: classifiers._ScriptedJev(jev),
#             reviewer_factory=lambda *_: classifiers._ScriptedReviewer(reviewer))
#         with self.base.connect() as connection:
#             notice_member = SourceResolver.from_store(connection, self.base.settings).resolve(notice).selection.members[0]
#             notice_version = notice_member.chunk.version
#             self.assertIsNotNone(connection.execute('SELECT id FROM public.mycel_chunk_versions WHERE id=%s',
#                 (notice_version,)).fetchone())
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies WHERE dependant_version=%s',
#                 (notice_version,)).fetchone(), (0,))
#             def pins():
#                 return {table: connection.execute('SELECT to_jsonb(t),xmin::text FROM public.' + table +
#                     ' t ORDER BY to_jsonb(t)::text').fetchall() for table in
#                     ('mycel_dependencies', 'mycel_edges', 'mycel_relations', 'mycel_verifications')}
#             before_semantic = pins()
#             stale_ids = connection.execute("SELECT id,chunk_version,dependency FROM public.mycel_stale_reasons WHERE repository='downstream' ORDER BY id").fetchall()
#             with patch('mycel._classify.ClassifyDependencies', return_value=dependencies), \
#                     patch('mycel._credentials.Credentials.require_jev_key', side_effect=AssertionError('real key')):
#                 waiting = self.repository(self.invoke('classify', '--repo', 'downstream'), 'downstream')
#                 self.assertGreater(waiting['pendingDebounce'], 0)
#                 self.assertEqual(calls, [])
#                 now[0] = at + timedelta(seconds=301)
#                 complete = self.repository(self.invoke('classify', '--repo', 'downstream'), 'downstream')
#             self.assertGreater(complete['jevCalls'], 0)
#             self.assertEqual(complete['reviewCalls'], complete['jevCalls'])
#             self.assertEqual(pins(), before_semantic)
#             self.assertEqual(connection.execute("SELECT id,chunk_version,dependency FROM public.mycel_stale_reasons WHERE repository='downstream' ORDER BY id").fetchall(), stale_ids)
#             self.assertEqual(self.repository(self.invoke('drifts', '--repo', 'downstream'), 'downstream')['drifts'], [])
#             closed = self.repository(self.invoke('drifts', '--repo', 'downstream', '--closed'), 'downstream')['drifts']
#             self.assertTrue(closed)
#             self.assertTrue(all(row['closed']['because'] == 'still_supported' for row in closed))
#             self.assertTrue(self.invoke('read', answer, '--no-fresh')['stale'])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges e JOIN public.mycel_dependencies d '
#                 'ON d.id=e.dependency WHERE d.dependant_version=%s', (notice_version,)).fetchone(), (0,))
#             # The first classifier deliberately advanced its observation clock
#             # past the quiet period. Keep the later normal deletion producer's
#             # timestamp monotonic with that actual retained successful read;
#             # advancing only the classifier clock cannot move a tombstone.
#             retained_reads = [datetime.fromisoformat(observation['lastObservedAt'])
#                 for (state,) in connection.execute(
#                     "SELECT state FROM public.mycel_drifts WHERE repository='downstream'").fetchall()
#                 for observation in state.get('classificationObservations', {}).values()
#                 if observation.get('lastObservedAt')]
#             self.assertTrue(retained_reads)
#             removal_observed = max(datetime.now(timezone.utc), now[0], *retained_reads) + timedelta(seconds=1)
#             changed.unlink(); self.base.commit()
#             with patch('mycel._ingest.datetime') as producer_clock:
#                 producer_clock.now.return_value = removal_observed
#                 self.invoke('ingest', '--repo', 'fixture')
#             retained_removals = [datetime.fromisoformat(state['sourceAbsence']['observedAt'])
#                 for (state,) in connection.execute(
#                     "SELECT state FROM public.mycel_dependencies WHERE repository='downstream' AND source_place=%s",
#                     (source,)).fetchall() if state.get('sourceAbsence')]
#             self.assertTrue(retained_removals)
#             self.assertTrue(all(value == removal_observed and value > max(retained_reads)
#                 for value in retained_removals))
#             removed = self.invoke('read', answer, '--no-fresh')
#             self.assertTrue(any(row['kind'] == 'source_removed' for row in removed['staleReasons']))
#             self.assertIsNotNone(connection.execute('SELECT id FROM public.mycel_verifications WHERE id=%s', (verification['id'],)).fetchone())
#             # A removal is classified from the real retained complete baseline
#             # and canonical tombstone, through the same public command.
#             calls_before_removal = len(calls)
#             now[0] = max(now[0], *retained_reads, *retained_removals) + timedelta(
#                 seconds=self.base.settings.values['drifts']['debounce_seconds'] + 1)
#             before_removed_classification = pins()
#             with patch('mycel._classify.ClassifyDependencies', return_value=dependencies), \
#                     patch('mycel._credentials.Credentials.require_jev_key', side_effect=AssertionError('real key')):
#                 removed_classification = self.repository(self.invoke('classify', '--repo', 'downstream'), 'downstream')
#             self.assertGreater(removed_classification['jevCalls'], 0)
#             tombstones = [payload for stage, payload in calls[calls_before_removal:]
#                 if stage == 'jev' and payload['current']['state'] == 'deleted']
#             self.assertTrue(tombstones)
#             self.assertTrue(all(payload['current']['members'] == [] for payload in tombstones))
#             self.assertTrue(all(any('Original governing source.' in member['text']
#                 for member in payload['before']) for payload in tombstones))
#             self.assertEqual(pins(), before_removed_classification)
#             needs_review = self.repository(self.invoke('drifts', '--repo', 'downstream'), 'downstream')['drifts']
#             removed_reasons = [reason for drift in needs_review for reason in drift['sources']
#                 if reason['active'] and reason['source']['address'] == source and reason['kind'] == 'source_removed']
#             self.assertTrue(removed_reasons)
#             self.assertTrue(all(reason['classification'].get('judgement') == 'needs_review'
#                 for reason in removed_reasons))
#             # Embedding/summary services are explicit local stand-ins. All
#             # pending plan commits, generated edge publication and regeneration
#             # still run through the normal public CLI and real store.
#             with ExitStack() as stack:
#                 stack.enter_context(patch('mycel._credentials.Credentials.require_embedding_key', side_effect=AssertionError('real key')))
#                 stack.enter_context(patch('mycel._embed.VoyageClient', side_effect=lambda *_a, **_k: summaries.LocalEmbedding()))
#                 self.invoke('embed', '--repo', 'fixture')
#                 stack.enter_context(patch('mycel._summary_build.SummaryWriter', side_effect=lambda *_a, **_k: summaries.LocalWriter(response=b'First complete generated summary.\n')))
#                 stack.enter_context(patch('mycel._summary_build.VoyageClient', side_effect=lambda *_a, **_k: summaries.LocalEmbedding()))
#                 built = self.invoke('summaries', 'build', '--repo', 'fixture')
#                 self.assertGreater(built['written'], 0)
#                 generated_before = connection.execute("SELECT c.id,v.id,v.source_bytes,g.state FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_generated_state g ON g.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index' WHERE c.repository='fixture' ORDER BY c.id").fetchall()
#                 self.assertTrue(generated_before)
#                 self.assertGreater(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE repository='fixture' AND kind='generated'").fetchone()[0], 0)
#                 note = self.base.artifact / 'note00.md'; note.write_text('# Note0\nSubstantively changed complete source note.\n')
#                 self.base.commit(); self.invoke('ingest', '--repo', 'fixture')
#                 status = self.invoke('summaries', 'status', '--repo', 'fixture')
#                 self.assertGreater(sum(row['stale'] for row in status['levels']), 0)
#                 self.assertTrue(self.repository(self.invoke('drifts', '--repo', 'fixture'), 'fixture')['regeneration'])
#                 stack.enter_context(patch('mycel._summary_regenerate.SummaryWriter', side_effect=lambda *_a, **_k: summaries.LocalWriter(response=b'Regenerated complete summary with updated source.\n')))
#                 stack.enter_context(patch('mycel._summary_regenerate.VoyageClient', side_effect=lambda *_a, **_k: summaries.LocalEmbedding()))
#                 regenerated = self.invoke('summaries', 'regenerate', '--repo', 'fixture')
#                 self.assertGreater(regenerated['written'], 0)
#                 self.assertEqual(sum(row['stale'] for row in self.invoke('summaries', 'status', '--repo', 'fixture')['levels']), 0)
#                 generated_after = connection.execute("SELECT c.id,v.id,v.source_bytes,g.state FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_generated_state g ON g.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index' WHERE c.repository='fixture' ORDER BY c.id").fetchall()
#                 self.assertNotEqual(generated_before, generated_after)
#             self.assertTrue(self.invoke('read', answer, '--no-fresh')['stale'])
#             self.assertFalse(connection.execute('SELECT 1 FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL').fetchall())
# TEST-TIER-DISABLED-END tests/test_provenance_conformance.py::ProvenanceConformanceStoreTests.test_public_cli_preserves_all_five_provenance_contracts_in_one_index


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:6
# from contextlib import ExitStack
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:6

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:7
# from datetime import datetime, timedelta, timezone
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:7

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:8
# from decimal import Decimal
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:11
# import os
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:12
# import sys
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:16
# from mycel._classification_payload import LABELS, ReviewerRequest
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:16

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:17
# from mycel._classification_runner import ClassifyDependencies
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:17

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:19
# from mycel._jev import JevResponse, route_response
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:19

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:20
# from mycel._reviewer import ReviewerSuccess
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:20

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:21
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:21

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:22
# from mycel._settings import load_settings
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:22

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:26
#     from . import test_summary_build as summaries
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:26

# TEST-TIER-IMPORTS-BEGIN tests/test_provenance_conformance.py:29
#     import test_summary_build as summaries
# TEST-TIER-IMPORTS-END tests/test_provenance_conformance.py:29

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
