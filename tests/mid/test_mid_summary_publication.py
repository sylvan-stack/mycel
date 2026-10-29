"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_publication as _support
from test_summary_publication import (SummaryPublicationStore ,atomic_transaction ,fixtures ,invocation_guard ,operation_guard ,patch)


class SummaryPublicationStoreTests(_support.SummaryPublicationStoreTests):


# TEST-TIER-BEGIN tests/test_summary_publication.py::SummaryPublicationStoreTests.test_private_owner_transfer_rolls_back_with_publication_and_confirmed_commit_cleanup_needs_no_sql
    def test_private_owner_transfer_rolls_back_with_publication_and_confirmed_commit_cleanup_needs_no_sql(self):
        with self.base.connect() as connection:
            self.fixture.fixture.prepare(connection)
            with invocation_guard(connection) as invocation, operation_guard(connection, 'fixture', 'summaries'):
                publisher = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                staged = self.staged(publisher, connection)
                with self.assertRaises(RuntimeError):
                    with self.fixture.fixture.guards(connection), atomic_transaction(connection):
                        publisher.publish_in_transaction((self.embedding(staged),), fixtures.METADATA,
                            guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                        publisher.verify_in_transaction()
                        publisher.release_in_transaction()
                        raise RuntimeError('outer commit cancelled')
                self.assertEqual(self.current(connection), [])
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners "
                    "WHERE kind='summary_generation'").fetchone(), (1,))
                publisher.discard()
                second = SummaryPublicationStore(connection, self.base.settings, invocation, 'fixture')
                staged = self.staged(second, connection)
                with self.fixture.fixture.guards(connection), atomic_transaction(connection):
                    second.publish_in_transaction((self.embedding(staged),), fixtures.METADATA,
                        guarded_repositories=tuple(sorted(self.base.settings.values['repos'])))
                    second.verify_in_transaction()
                    second.release_in_transaction()
                second.confirm_release()
                with patch('mycel._summary_publication.checked_store', side_effect=AssertionError('committed cleanup touched SQL')):
                    second.release()
                self.assertEqual(len(self.current(connection)), 1)
# TEST-TIER-END tests/test_summary_publication.py::SummaryPublicationStoreTests.test_private_owner_transfer_rolls_back_with_publication_and_confirmed_commit_cleanup_needs_no_sql
