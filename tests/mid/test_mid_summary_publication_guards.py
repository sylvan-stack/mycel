"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_publication_guards as _support
from test_summary_publication_guards import (
    ExitStack,
    StringIO,
    SummaryPublicationGuardsStoreTests,
    TABLES,
    json,
    load_settings,
    operation_guard,
    patch,
    run,
    summaries,
    time,
    unittest,
)


class SummaryPublicationGuardsStoreTests(_support.SummaryPublicationGuardsStoreTests):
# TEST-TIER-BEGIN tests/test_summary_publication_guards.py::SummaryPublicationGuardsStoreTests.test_build_regenerate_and_memberless_delete_guard_affected_owners_only_after_services
    def test_build_regenerate_and_memberless_delete_guard_affected_owners_only_after_services(self):
        with self.base.connect() as connection, ExitStack() as services:
            writer = self.service_callback('writer')
            vector = self.service_callback('embedding')
            for module, response in (
                    ('mycel._summary_build', b'Complete public generated summary.\n'),
                    ('mycel._summary_regenerate', b'Updated public generated summary from changed sources.\n')):
                services.enter_context(patch(module + '.SummaryWriter', side_effect=lambda *_a, response=response, **_k:
                    summaries.LocalWriter(writer, response=response)))
                services.enter_context(patch(module + '.VoyageClient', side_effect=lambda *_a, **_k:
                    summaries.LocalEmbedding(vector)))
            services.enter_context(patch('mycel._embed.VoyageClient', side_effect=lambda *_a, **_k:
                summaries.LocalEmbedding(vector)))
            services.enter_context(patch('mycel._credentials.Credentials.require_embedding_key',
                side_effect=AssertionError('A local service stand-in must not request a real key.')))

            self.busy_route(connection, 'build', 'build_busy')
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind='summary'").fetchone(), (0,))
            built = self.retry_with_disjoint_busy(connection, 'build', 'build_retry')
            self.assertEqual((built['written'], built['replaced']), (1, True))
            first = connection.execute("SELECT c.id,v.id,v.source_bytes FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id WHERE c.kind='summary'").fetchall()
            self.assertEqual(len(first), 1)
            self.assertGreater(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='generated'").fetchone()[0], 0)

            note = self.base.artifact / 'note00.md'
            note.write_text('# Part0\nSubstantively changed complete source note.\n')
            self.base.commit()
            self.invoke('ingest', '--repo', 'fixture')
            self.services.update(phase='reembed', probe=('fixture', 'downstream'))
            self.invoke('embed', '--repo', 'fixture')
            self.assertGreater(sum(level['stale'] for level in self.invoke('summaries', 'status', '--repo', 'fixture')['levels']), 0)
            self.busy_route(connection, 'regenerate', 'regenerate_busy')
            self.assertEqual(connection.execute("SELECT c.id,v.id,v.source_bytes FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id WHERE c.kind='summary'").fetchall(), first)
            regenerated = self.retry_with_disjoint_busy(connection, 'regenerate', 'regenerate_retry')
            self.assertEqual((regenerated['written'], regenerated['deleted']), (1, 0))
            second = connection.execute("SELECT c.id,v.id,v.source_bytes FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id WHERE c.kind='summary'").fetchall()
            self.assertNotEqual(first, second)
            self.assertEqual(sum(level['stale'] for level in self.invoke('summaries', 'status', '--repo', 'fixture')['levels']), 0)

            for path in self.base.artifact.glob('*.md'):
                path.unlink()
            self.base.commit()
            self.invoke('ingest', '--repo', 'fixture', '--confirm-empty')
            self.assertGreater(sum(level['stale'] for level in self.invoke('summaries', 'status', '--repo', 'fixture')['levels']), 0)
            self.busy_route(connection, 'regenerate', 'delete_busy')
            self.assertEqual(connection.execute("SELECT c.id,v.id,v.source_bytes FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id WHERE c.kind='summary'").fetchall(), second)
            removed = self.retry_with_disjoint_busy(connection, 'regenerate', 'delete_retry')
            self.assertEqual((removed['written'], removed['deleted']), (0, 1))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind='summary'").fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL").fetchone(), (0,))
            for phase in ('build_busy', 'build_retry', 'regenerate_busy', 'regenerate_retry'):
                self.assertEqual({kind for observed, kind, _ in self.observations if observed == phase}, {'writer', 'embedding'})
            self.assertFalse(any(phase.startswith('delete_') for phase, _, _ in self.observations))
# TEST-TIER-END tests/test_summary_publication_guards.py::SummaryPublicationGuardsStoreTests.test_build_regenerate_and_memberless_delete_guard_affected_owners_only_after_services
