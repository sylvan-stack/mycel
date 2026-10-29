"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_evaluation_retrieval as _support
from test_evaluation_retrieval import (CandidateSnapshot ,RetrievalQuery ,StoreRetrieval ,_Vectors ,_forbid_side_effects ,_state ,atomic_transaction ,patch)


class EvaluationRetrievalStoreTests(_support.EvaluationRetrievalStoreTests):


# TEST-TIER-BEGIN tests/test_evaluation_retrieval.py::EvaluationRetrievalStoreTests.test_peer_publication_cannot_mix_actual_ranking_expectations_or_fingerprints_between_queries
    def test_peer_publication_cannot_mix_actual_ranking_expectations_or_fingerprints_between_queries(self):
        with self.base.connection() as connection, self.base.connection() as writer:
            old = self.seed(connection, path='needle.py', name='Needle', source='needle original\n', cosine=.8)
            self.seed(connection, path='stable.py', name='Stable', source='needle stable\n', cosine=.6)
            queries = (RetrievalQuery('how does needle work', ('fixture:@code/needle.py#Needle',), 'code'),) * 2
            vectors = _Vectors(connection, self.vector)
            actual_ranked = CandidateSnapshot.ranked
            committed, current, calls = [], [], []

            def ranked(snapshot, *arguments, **options):
                self.assertEqual(vectors.queries, list(queries))
                result = actual_ranked(snapshot, *arguments, **options)
                if not calls:
                    with atomic_transaction(writer):
                        writer.execute("UPDATE public.mycel_locations SET kind='branch',location='old' "
                                       'WHERE chunk_version=%s', (old[2],))
                        writer.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old' "
                            'WHERE file_version IN (SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', (old[0],))
                        current.append(self.seed(writer, file_id=old[0], chunk_id=old[1], path='needle.py',
                            name='NewNeedle', source='needle newer publication\n', cosine=.1))
                    committed.append(_state(writer))
                calls.append(result)
                return result

            with _forbid_side_effects(), patch.object(CandidateSnapshot, 'ranked', ranked):
                report = self.measure(connection, queries, vectors=vectors)
            self.assertEqual(len(calls), 2)
            for row in report['results']:
                self.assertEqual((row['returned'][0]['id'], row['returned'][0]['version']), (str(old[1]), old[2]))
                self.assertEqual(row['expected'][0]['resolved']['version'], old[2])
                self.assertEqual(row['expected'][0]['position'], 1)
            self.assertEqual(_state(writer), committed[0])
            with StoreRetrieval(connection, self.settings).snapshot('fixture') as after:
                self.assertNotEqual(report['indexFingerprint'], after.index_fingerprint)
                self.assertEqual(after.resolver.resolve('fixture:@code/needle.py#Needle', purpose='read').fault, 'missing_name')
                member = after.resolver.resolve('fixture:@code/needle.py#NewNeedle', purpose='read').selection.members[0]
                self.assertEqual(member.chunk.version, current[0][2])
            self.assertEqual(_state(writer), committed[0])
# TEST-TIER-END tests/test_evaluation_retrieval.py::EvaluationRetrievalStoreTests.test_peer_publication_cannot_mix_actual_ranking_expectations_or_fingerprints_between_queries
