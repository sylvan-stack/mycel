"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_freshness_store as _support
from test_freshness_store import (
    Deadline,
    DeadlineConnection,
    DeadlineExceeded,
    DependencyApplicationStore,
    DependencyCaptureInputs,
    ExitStack,
    FreshnessScope,
    FreshnessStoreTests,
    LocatedCaptureStore,
    LocationId,
    MutationActivity,
    MycelError,
    SourceResolver,
    StoreCandidates,
    StoreFreshnessAdapter,
    TABLES,
    _Capture,
    _CompleteProducer,
    _RecordingConnection,
    _publication_guards,
    activity_state,
    atomic_transaction,
    checked_store,
    deadline_guard,
    fixtures,
    json,
    load_settings,
    operation_guard,
    patch,
    psycopg,
    run_freshness,
    run_store_freshness,
    time,
    unittest,
)


class FreshnessStoreTests(_support.FreshnessStoreTests):
# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_transitive_glossary_change_reaches_driver_without_repin_or_unrelated_scan
    def test_transitive_glossary_change_reaches_driver_without_repin_or_unrelated_scan(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            pins, outside = self.pins(connection), self.owned(connection, 'outside')
            driver, contract = self.driver.read_bytes(), self.contract.read_bytes()
            key = self.key(connection, 'fixture:@artifact/driver.md#Driver')
            self.glossary.write_bytes(b'# Glossary\nChanged governing definition.\n')
            self.outside.write_bytes(b'# Unrelated\nUnindexed unrelated change.\n')
            captures = []
            actual = _Capture.capture

            def record(capture):
                captures.append(capture.repository.name)
                return actual(capture)

            with patch.object(_Capture, 'capture', record), patch('mycel._embed.embed', side_effect=AssertionError('embedding')):
                result = run_store_freshness(connection, self.settings, ('fixture',),
                    only='docs', deadline=Deadline.after(30), build=1)
            self.assertTrue(result.finished, result)
            statuses = {item.repository: item for item in result.repositories}
            self.assertEqual({name for name, item in statuses.items() if item.scan_required},
                             {'fixture', 'contract', 'glossary'})
            self.assertFalse(statuses['consumer'].scan_required)
            self.assertEqual(statuses['consumer'].status, 'done')
            self.assertNotIn('outside', captures)
            self.assertNotIn('shared', captures)
            self.assertNotIn('disabled', captures)
            self.assertEqual(self.owned(connection, 'outside'), outside)
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual((self.driver.read_bytes(), self.contract.read_bytes()), (driver, contract))
            self.assertEqual(self.key(connection, 'fixture:@artifact/driver.md#Driver'), key)
            reasons = connection.execute("SELECT reason FROM public.mycel_stale_reasons WHERE repository='fixture'").fetchall()
            self.assertTrue(any(row[0]['kind'] == 'upstream_stale' and row[0]['via'][0]['repository'] == 'contract'
                                for row in reasons), reasons)
            requirement = next(item for item in result.chunk_requirements if item.chunk == key)
            self.assertEqual(set(requirement.repositories), {'fixture', 'contract', 'glossary'})
            self.assertTrue(result.complete_for_chunk('fixture', key))
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                selected = snapshot.candidates('governing', only='docs')[0].chunks
                self.assertEqual({chunk.repository for chunk in selected}, {'fixture'})
            entries = connection.execute('SELECT id,repository,invocation,trigger FROM public.mycel_activity').fetchall()
            self.assertTrue(entries)
            self.assertEqual(len({row[2] for row in entries}), 1)
            self.assertEqual({row[3] for row in entries}, {'freshness_check'})
            for identifier, _, _, _ in entries:
                self.assertEqual(activity_state(connection, identifier)['outcome'], 'done')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_embedding_plans').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_transitive_glossary_change_reaches_driver_without_repin_or_unrelated_scan

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_code_only_asserted_governance_checks_documents_outside_shared_selection
    def test_code_only_asserted_governance_checks_documents_outside_shared_selection(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.assert_source(connection, 'contract:@artifact/contract.md#Contract')
            self.glossary.write_bytes(b'# Glossary\nCode governance changed.\n')
            result = run_store_freshness(connection, self.settings, ('fixture',),
                only='code', deadline=Deadline.after(30), build=1)
            self.assertTrue(result.finished, result)
            self.assertEqual({item.repository for item in result.repositories if item.scan_required},
                             {'fixture', 'contract', 'glossary'})
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                chunks = snapshot.candidates('driver', only='code')[0].chunks
                self.assertTrue(chunks)
                self.assertEqual({chunk.repository for chunk in chunks}, {'fixture'})
                self.assertEqual({chunk.origin for chunk in chunks}, {'code'})
                for chunk in chunks:
                    self.assertTrue(result.complete_for_chunk('fixture', chunk.key))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_code_only_asserted_governance_checks_documents_outside_shared_selection

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_no_fresh_reads_known_recursive_sources_and_changes_no_store_row
    def test_no_fresh_reads_known_recursive_sources_and_changes_no_store_row(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.contents(connection)
            self.glossary.write_bytes(b'# Glossary\nA skipped change.\n')
            recording = _RecordingConnection(connection)
            with patch.object(_Capture, 'capture', side_effect=AssertionError('no freshness capture')):
                result = run_store_freshness(recording, self.settings, ('fixture',),
                    only='docs', deadline=Deadline.after(30), no_fresh=True, build=1)
            self.assertFalse(result.finished)
            self.assertEqual({item.repository for item in result.repositories}, {'fixture', 'contract', 'glossary'})
            self.assertEqual({item.status for item in result.repositories}, {'pending'})
            self.assertEqual(self.contents(connection), before)
            self.assertFalse(any(str(sql).lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER'))
                                 for sql in recording.statements))
            self.assertFalse(result.complete_for_chunk('fixture', self.key(connection, 'fixture:@artifact/driver.md#Driver')))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_no_fresh_reads_known_recursive_sources_and_changes_no_store_row

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_busy_downstream_update_is_pending_without_scanning_or_changing_its_files
    def test_busy_downstream_update_is_pending_without_scanning_or_changing_its_files(self):
        with self.base.connect() as connection, self.base.connect() as blocker:
            self.prepare(connection)
            before = self.owned(connection, 'consumer')
            self.glossary.write_bytes(b'# Glossary\nA governing change with busy downstream.\n')
            self.consumer.write_bytes(self.consumer.read_bytes() + b'Unindexed downstream edit.\n')
            with checked_store(blocker), operation_guard(blocker, 'consumer', 'pass'):
                result = run_store_freshness(connection, self.settings, ('fixture',),
                    only='docs', deadline=Deadline.after(30), build=1)
            statuses = {item.repository: item for item in result.repositories}
            self.assertFalse(result.finished)
            self.assertFalse(statuses['consumer'].scan_required)
            self.assertEqual(statuses['consumer'].status, 'pending')
            self.assertTrue(statuses['consumer'].reason)
            self.assertEqual(self.owned(connection, 'consumer'), before)
            self.assertTrue(result.complete_for_chunk('fixture', self.key(connection, 'fixture:@artifact/driver.md#Driver')))
            retry = run_store_freshness(connection, self.settings, ('fixture',),
                only='docs', deadline=Deadline.after(30), build=1)
            self.assertFalse(retry.finished)
            # Its edit still awaits its own ingest; the search must not scan
            # this dependency-only owner to make the status look complete.
            self.assertEqual(self.owned(connection, 'consumer'), before)
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_busy_downstream_update_is_pending_without_scanning_or_changing_its_files

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_newly_captured_ref_extends_same_frontier_before_publication
    def test_newly_captured_ref_extends_same_frontier_before_publication(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            (self.folders['later'] / 'new.md').write_bytes(b'# New\nNewly referenced governing text.\n')
            self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary',
                                                   'later:@artifact/new.md#New'))
            adapter = StoreFreshnessAdapter(connection, self.settings)
            actual, order = adapter.refresh, []

            def record(name, *, deadline):
                outcome = actual(name, deadline=deadline)
                order.append((name, outcome.status))
                return outcome

            with patch.object(adapter, 'refresh', record):
                result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, (result, order))
            self.assertIn(('contract', 'pending'), order)
            self.assertLess(order.index(('later', 'done')), order.index(('contract', 'done')))
            self.assertEqual({item.repository for item in result.repositories if item.scan_required},
                             {'fixture', 'contract', 'glossary', 'later'})
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                self.assertEqual({chunk.repository for chunk in snapshot.candidates('New', only='docs')[0].chunks}, {'fixture'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_newly_captured_ref_extends_same_frontier_before_publication

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source
    def test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            (self.folders['later'] / 'new.md').write_bytes(self.document('New', 'outside:@artifact/deep.md#Deep'))
            (self.folders['later'] / 'unrelated.md').write_bytes(self.document('Unrelated',
                'disabled:@artifact/absent.md#Disabled', 'shared:@artifact/selected.md#Selected'))
            (self.folders['outside'] / 'deep.md').write_bytes(b'# Deep\nA newly discovered governing definition.\n')
            self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary',
                                                   'later:@artifact/new.md#New'))
            adapter = StoreFreshnessAdapter(connection, self.settings)
            actual, order = adapter.refresh, []

            def record(name, *, deadline):
                outcome = actual(name, deadline=deadline)
                order.append((name, outcome.status))
                return outcome

            with patch.object(adapter, 'refresh', record):
                result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, (result, order))
            self.assertIn(('later', 'pending'), order)
            self.assertLess(order.index(('outside', 'done')), order.index(('later', 'done')))
            self.assertLess(order.index(('later', 'done')), order.index(('contract', 'done')))
            self.assertEqual({item.repository for item in result.repositories if item.scan_required},
                             {'fixture', 'contract', 'glossary', 'later', 'outside'})
            self.assertEqual(result.faults, ())
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                self.assertEqual({chunk.repository for chunk in snapshot.candidates('Deep', only='docs')[0].chunks}, {'fixture'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_upstream_file_recursively_exposes_its_own_unindexed_source

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_section_in_existing_source_file_exposes_its_own_upstream
    def test_new_unindexed_section_in_existing_source_file_exposes_its_own_upstream(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            path = self.folders['later'] / 'existing.md'
            path.write_bytes(b'# Old\nAn already indexed section.\n')
            self.publish(connection, 'later')
            path.write_bytes(b'# Old\nAn already indexed section.\n\n# New\n'
                             b'<!-- sources: outside:@artifact/deep.md#Deep -->\nA newly referenced section.\n')
            (self.folders['outside'] / 'deep.md').write_bytes(b'# Deep\nNew governing text.\n')
            self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary',
                                                   'later:@artifact/existing.md#New'))
            adapter = StoreFreshnessAdapter(connection, self.settings)
            actual, order = adapter.refresh, []

            def record(name, *, deadline):
                outcome = actual(name, deadline=deadline)
                order.append((name, outcome.status))
                return outcome

            with patch.object(adapter, 'refresh', record):
                result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, (result, order))
            self.assertIn(('later', 'pending'), order)
            self.assertLess(order.index(('outside', 'done')), order.index(('later', 'done')))
            self.assertEqual(result.faults, ())
            key = self.key(connection, 'fixture:@artifact/driver.md#Driver')
            requirement = next(item for item in result.chunk_requirements if item.chunk == key)
            self.assertEqual(set(requirement.repositories), {'fixture', 'contract', 'glossary', 'later', 'outside'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_new_unindexed_section_in_existing_source_file_exposes_its_own_upstream

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_retained_heading_anchor_exposes_new_sources_before_renamed_chunk_publication
    def test_retained_heading_anchor_exposes_new_sources_before_renamed_chunk_publication(self):
        with self.base.connect() as connection:
            path = self.folders['later'] / 'renamed.md'
            path.write_bytes(self.document('Old', 'glossary:@artifact/glossary.md#Glossary'))
            self.prepare(connection)
            self.publish(connection, 'later')
            self.contract.write_bytes(self.document('Contract', 'glossary:@artifact/glossary.md#Glossary',
                                                   'later:@artifact/renamed.md#Old'))
            self.publish(connection, 'contract')
            original = self.key(connection, 'later:@artifact/renamed.md#Old')
            pins = self.pins(connection)
            # The exact body retains the logical chunk ID under the normal
            # identity planner even though heading and frontmatter refs change.
            path.write_bytes(self.document('New', 'outside:@artifact/deep.md#Deep'))
            (self.folders['outside'] / 'deep.md').write_bytes(b'# Deep\nNew governing text.\n')
            adapter = StoreFreshnessAdapter(connection, self.settings)
            actual, order = adapter.refresh, []

            def record(name, *, deadline):
                outcome = actual(name, deadline=deadline)
                order.append((name, outcome.status))
                return outcome

            with patch.object(adapter, 'refresh', record):
                result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, (result, order))
            self.assertIn(('later', 'pending'), order)
            self.assertLess(order.index(('outside', 'done')), order.index(('later', 'done')))
            self.assertEqual(self.key(connection, 'later:@artifact/renamed.md#New')[0], original[0])
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(result.faults, ())
            key = self.key(connection, 'fixture:@artifact/driver.md#Driver')
            requirement = next(item for item in result.chunk_requirements if item.chunk == key)
            self.assertEqual(set(requirement.repositories), {'fixture', 'contract', 'glossary', 'later', 'outside'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_retained_heading_anchor_exposes_new_sources_before_renamed_chunk_publication

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_valid_unresolved_disabled_and_malformed_refs_have_exact_chunk_faults
    def test_valid_unresolved_disabled_and_malformed_refs_have_exact_chunk_faults(self):
        broken = self.folders['fixture'] / 'broken.md'
        broken.write_bytes(self.document('Broken', 'later:@artifact/missing.md#Missing',
            'disabled:@artifact/no.md#Disabled', 'not a source ref'))
        with self.base.connect() as connection:
            self.prepare(connection)
            result = run_store_freshness(connection, self.settings, ('fixture',),
                only='docs', deadline=Deadline.after(30), build=1)
            self.assertTrue(result.finished, result)
            self.assertIn('later', {item.repository for item in result.repositories})
            self.assertNotIn('disabled', {item.repository for item in result.repositories})
            key = self.key(connection, 'fixture:@artifact/broken.md#Broken')
            independent = self.key(connection, 'fixture:@artifact/independent.md#Independent')
            self.assertFalse(result.complete_for_chunk('fixture', key))
            self.assertTrue(result.complete_for_chunk('fixture', independent))
            self.assertEqual({fault.reason for fault in result.faults if fault.chunk == key},
                             {'missing_file', 'disabled_repository', 'not_a_ref'})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_valid_unresolved_disabled_and_malformed_refs_have_exact_chunk_faults

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_retained_deleted_source_still_requires_its_repository_and_restores_its_pin
    def test_retained_deleted_source_still_requires_its_repository_and_restores_its_pin(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            pins = self.pins(connection)
            self.glossary.unlink()
            self.publish(connection, 'glossary')
            self.assertEqual(self.pins(connection), pins)
            adapter = StoreFreshnessAdapter(connection, self.settings)
            discovery = adapter.discover(FreshnessScope(('fixture',), 'docs'), deadline=Deadline.after(30))
            self.assertIn('glossary', discovery.required_repositories)
            self.assertTrue(any(fault.reason == 'missing_file' for fault in discovery.faults))
            self.glossary.write_bytes(b'# Glossary\nRestored source with changed wording.\n')
            result = run_freshness(FreshnessScope(('fixture',), 'docs'), adapter, deadline=Deadline.after(30))
            self.assertTrue(result.finished, result)
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(result.faults, ())
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_retained_deleted_source_still_requires_its_repository_and_restores_its_pin

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_selected_shared_supplier_is_checked_even_before_new_document_is_indexed
    def test_selected_shared_supplier_is_checked_even_before_new_document_is_indexed(self):
        with self.base.config.open('a') as config:
            config.write('\n[search]\nshared_documents=[{repo="shared",paths=["selected"]}]\n')
        self.reload()
        self.shared.unlink()
        selected = self.folders['shared'] / 'selected'
        selected.mkdir()
        with self.base.connect() as connection:
            self.prepare(connection)
            (selected / 'new.md').write_bytes(self.document('Shared', 'glossary:@artifact/glossary.md#Glossary'))
            result = run_store_freshness(connection, self.settings, ('fixture',),
                only='docs', deadline=Deadline.after(30), build=1)
            self.assertTrue(result.finished, result)
            self.assertIn('shared', {item.repository for item in result.repositories if item.scan_required})
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                chunks = snapshot.candidates('Shared', only='docs')[0].chunks
                self.assertEqual({chunk.repository for chunk in chunks}, {'fixture', 'shared'})
                self.assertNotIn('glossary', {chunk.repository for chunk in chunks})
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_selected_shared_supplier_is_checked_even_before_new_document_is_indexed

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_deadline_at_final_verification_rolls_back_and_releases_locks_for_reads
    def test_deadline_at_final_verification_rolls_back_and_releases_locks_for_reads(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.contents(connection)
            self.glossary.write_bytes(b'# Glossary\nA change that must roll back.\n')
            clock = [0.0]
            deadline = Deadline.after(10, clock=lambda: clock[0])
            actual = _CompleteProducer.verify_in_transaction

            def expire(producer, *args, **kwargs):
                actual(producer, *args, **kwargs)
                clock[0] = 11.0

            adapter = StoreFreshnessAdapter(connection, self.settings)
            adapter.discover(FreshnessScope(('fixture',), 'docs'), deadline=deadline)
            with patch.object(_CompleteProducer, 'verify_in_transaction', expire):
                with self.assertRaises(DeadlineExceeded):
                    adapter.refresh('glossary', deadline=deadline)
            self.assertEqual(self.contents(connection), before)
            self.assertEqual(connection.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
                'AND pid=pg_catalog.pg_backend_pid()').fetchone(), (0,))
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                self.assertTrue(snapshot.candidates('dependant')[0].chunks)
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_deadline_at_final_verification_rolls_back_and_releases_locks_for_reads

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable
    def test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable(self):
        with self.base.connect() as connection:
            proxy = DeadlineConnection(connection)
            before = connection.execute('SHOW statement_timeout').fetchone()
            deadline, started = Deadline.after(0.35), time.monotonic()
            with deadline_guard(deadline):
                proxy.execute('SELECT pg_catalog.pg_sleep(0.18)').fetchone()
                with self.assertRaises((psycopg.errors.QueryCanceled, DeadlineExceeded)):
                    proxy.execute('SELECT pg_catalog.pg_sleep(0.4)').fetchone()
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(connection.execute('SHOW statement_timeout').fetchone(), before)
            self.assertEqual(connection.execute('SELECT 1').fetchone(), (1,))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_cumulative_sql_uses_remaining_deadline_and_timeout_cleanup_is_readable

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_expired_startup_keeps_known_shared_suppliers_and_committed_store_readable
    def test_expired_startup_keeps_known_shared_suppliers_and_committed_store_readable(self):
        with self.base.config.open('a') as config:
            config.write('\n[search]\nshared_documents=[{repo="shared",paths=["selected.md"]}]\n')
        self.reload()
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.contents(connection)
            result = run_store_freshness(connection, self.settings, ('fixture',),
                only='docs', deadline=Deadline.after(0), build=1)
            self.assertFalse(result.finished)
            self.assertEqual({item.repository for item in result.repositories}, {'fixture', 'shared'})
            self.assertEqual({item.status for item in result.repositories}, {'pending'})
            self.assertEqual(self.contents(connection), before)
            with StoreCandidates(connection, self.settings).snapshot(('fixture',)) as snapshot:
                self.assertTrue(snapshot.candidates('dependant')[0].chunks)
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_expired_startup_keeps_known_shared_suppliers_and_committed_store_readable

# TEST-TIER-BEGIN tests/test_freshness_store.py::FreshnessStoreTests.test_activity_finalization_refusal_preserves_committed_prefix_and_reports_pending
    def test_activity_finalization_refusal_preserves_committed_prefix_and_reports_pending(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            pins = self.pins(connection)
            self.glossary.write_bytes(b'# Glossary\nA committed freshness change.\n')
            with patch.object(MutationActivity, 'finish', side_effect=MycelError('busy', 'final audit is busy')):
                result = run_store_freshness(connection, self.settings, ('fixture',),
                    only='docs', deadline=Deadline.after(30), build=1)
            self.assertFalse(result.finished)
            self.assertEqual(result.reason, 'Freshness activity finalization did not complete.')
            self.assertTrue(any(item.status == 'pending' for item in result.repositories))
            self.assertEqual(self.pins(connection), pins)
            self.assertEqual(SourceResolver.from_store(connection, self.settings).resolve(
                'glossary:@artifact/glossary.md#Glossary').selection.members[0].chunk.source,
                self.glossary.read_bytes())
            self.assertEqual(connection.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
                'AND pid=pg_catalog.pg_backend_pid()').fetchone(), (0,))
# TEST-TIER-END tests/test_freshness_store.py::FreshnessStoreTests.test_activity_finalization_refusal_preserves_committed_prefix_and_reports_pending
