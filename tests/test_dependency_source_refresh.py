"""Real-store checks for source passes observing surviving foreign dependants."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._capture import capture_repository
from mycel._coverage import proves
from mycel._dependency_application import DependencyApplicationStore, RetainedDependencyResolver
from mycel._evidence import EvidenceError, EvidenceStore, PinInputs
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import atomic_transaction, operation_guard
from mycel._reconciliation import AssertedRemoval
from mycel._resolver import SourceResolver
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class DependencySourceRefreshStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize(b'# Guide\nSource repository guide.\n')
        self.source = self.base.artifact / 'source.md'
        self.source_bytes = b'# Source\nOriginal governing source.\n'
        self.source.write_bytes(self.source_bytes)
        self.base.commit()
        self.downstream = self.base.base / 'downstream'
        self.downstream.mkdir()
        self.answer = self.downstream / 'answer.md'
        self.answer.write_bytes(b'---\nrole: authored\nsources: ["fixture:@artifact/source.md#Source"]\n---\n'
                                b'# Answer\nUnchanged dependant.\n')
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.downstream]\nenabled=true\n'
                                    + 'artifact_root=' + json.dumps(str(self.downstream)) + '\n')
        self.reload()

    def reload(self):
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)

    def guards(self, connection):
        held = ExitStack()
        held.enter_context(checked_store(connection))
        for repository in sorted(self.base.settings.values['repos']):
            held.enter_context(operation_guard(connection, repository, 'pass'))
        return held

    def publish(self, connection, repository='fixture', *, collect=True, activity=None, reply_counts=None):
        manifest = capture_repository(self.base.settings, repository)
        producer = LocatedDependencyProducer(self.base.settings, captured_at='2026-10-09T11:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest if collect else None, activity=activity)
        with self.guards(connection):
            return LocatedCaptureStore(connection).apply(self.base.settings, manifest,
                batch_handoff=producer, activity=activity, reply_counts=reply_counts)

    def prepare(self, connection):
        self.publish(connection)
        self.publish(connection, 'downstream')
        return self.dependencies(connection)

    def dependencies(self, connection):
        return connection.execute("""SELECT d.id,d.dependant_version,d.kind,d.declaration,d.source_place,d.state,
            d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d
            LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0
            WHERE d.repository='downstream' ORDER BY d.kind,d.id""").fetchall()

    def edges(self, connection):
        return connection.execute("""SELECT e.dependency,e.source_version FROM public.mycel_edges e
            JOIN public.mycel_dependencies d ON d.id=e.dependency WHERE d.repository='downstream'
            ORDER BY e.dependency,e.source_version""").fetchall()

    def role(self, connection):
        return connection.execute("""SELECT l.metadata->>'role' FROM public.mycel_locations l
            JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version
            JOIN public.mycel_chunks c ON c.id=v.chunk_id
            WHERE c.repository='downstream' AND l.kind='disk'""").fetchone()[0]

    def pins(self, rows):
        return [(row[0], row[1], row[2], row[3], row[6], row[7]) for row in rows]

    def state(self, connection):
        tables = ('mycel_repository_state', 'mycel_files', 'mycel_file_aliases', 'mycel_file_versions',
                  'mycel_file_locations', 'mycel_chunks', 'mycel_chunk_versions', 'mycel_locations',
                  'mycel_dependencies', 'mycel_edges', 'mycel_ref_faults', 'mycel_evidence_owners',
                  'mycel_evidence_references', 'mycel_snapshots', 'mycel_manifests', 'mycel_activity',
                  'mycel_activity_files', 'mycel_identity_decisions', 'mycel_activity_classifications')
        return {table: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table} t '
                                          'ORDER BY to_jsonb(t)::text').fetchall() for table in tables}

    @proves('MYC-2.12', 'MYC-2.22', 'MYC-2.8', 'MYC-2.24', 'MYC-16.7', 'MYC-16.13', kind='store')
    def test_source_only_away_and_restoration_preserve_foreign_pin_and_role(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            original_answer = self.answer.read_bytes()
            self.source.unlink()
            result = self.publish(connection)
            missing = self.dependencies(connection)
            self.assertEqual(self.pins(missing), self.pins(before))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')
            state = missing[0][5]
            self.assertEqual((state['sourceState'], state['sourceExistence'], state['reasons']),
                             ('source_removed', 'away', ['source_removed']))
            self.assertEqual(state['sourceAbsence']['state'], 'away')
            self.assertEqual(state['sourceAbsence']['place'], 'fixture:@artifact/source.md#Source')
            self.assertIsInstance(state['sourceAbsence']['previousFileHash'], str)
            self.assertEqual(state['sourceAbsence']['observedAt'], '2026-10-09T11:00:00Z')
            counts = result.counts['dependencyRepositories']['downstream']
            self.assertEqual((counts['pinsCaptured'], counts['pinsInherited'], counts['refsChanged']), (0, 0, 1))
            stable = self.state(connection)
            self.assertFalse(self.publish(connection).changed)
            self.assertEqual(self.state(connection), stable)
            self.source.write_bytes(b'# Source\nChanged restored source.\n')
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual((restored[0][5]['sourceState'], restored[0][5]['sourceExistence'],
                              restored[0][5]['reasons']), ('present', 'present', ['source_changed']))
            self.assertEqual(len(self.edges(connection)), 1)
            self.assertEqual(self.answer.read_bytes(), original_answer)

    @proves('MYC-7.24', 'MYC-2.24', 'MYC-16.7', 'MYC-16.11', 'MYC-16.13', kind='store')
    def test_last_location_deletion_and_recreation_keep_exact_dependant_owned_evidence(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            old_source = self.edges(connection)[0][1]
            baseline = EvidenceStore(connection).read_baseline('downstream', before[0][7])
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            missing = self.dependencies(connection)
            self.assertEqual(self.pins(missing), self.pins(before))
            self.assertEqual(missing[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(missing[0][5]['sourceAbsence']['state'], 'deleted')
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_source,)).fetchone(), (0,))
            retained = EvidenceStore(connection).read_baseline('downstream', before[0][7])
            self.assertEqual(retained.manifest, baseline.manifest)
            self.assertIn(self.source_bytes, [blob.source for blob in retained.snapshots])
            self.source.write_bytes(self.source_bytes)
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual(restored[0][5]['reasons'], [])
            self.assertNotEqual(self.edges(connection)[0][1], old_source)

    @proves('MYC-2.8', 'MYC-16.13', kind='store')
    def test_source_pass_retries_never_resolved_foreign_declaration(self):
        self.source.unlink()
        self.base.commit()
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.assertIsNone(before[0][6])
            self.assertEqual(before[0][5]['sourceState'], 'unresolved')
            self.source.write_bytes(self.source_bytes)
            result = self.publish(connection)
            resolved = self.dependencies(connection)
            self.assertEqual(resolved[0][0:4], before[0][0:4])
            self.assertIsNotNone(resolved[0][6])
            self.assertEqual(resolved[0][5]['sourceState'], 'present')
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['pinsCaptured'], 1)
            self.assertEqual(self.role(connection), 'derived')

    @proves('MYC-16.11', 'MYC-16.13', kind='store')
    def test_disabled_foreign_owner_is_unchanged_by_source_publication(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            edges = self.edges(connection)
            self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
                                                                            '[repos.downstream]\nenabled=false'))
            self.reload()
            self.source.write_bytes(b'# Source\nChange while owner disabled.\n')
            result = self.publish(connection)
            self.assertEqual(self.dependencies(connection), before)
            self.assertEqual(self.edges(connection), edges)
            self.assertNotIn('downstream', result.counts.get('dependencyRepositories', {}))

    @proves('MYC-2.7', 'MYC-2.8', 'MYC-2.12', 'MYC-16.13', kind='store')
    def test_settings_only_source_disable_and_enable_recheck_unchanged_captures(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=true',
                                                                            '[repos.fixture]\nenabled=false'))
            self.reload()
            invalid = self.publish(connection, 'downstream')
            disabled = self.dependencies(connection)
            self.assertTrue(invalid.changed)
            self.assertEqual(self.pins(disabled), self.pins(before))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(disabled[0][5]['sourceExistence'], 'ineligible')
            self.assertEqual(disabled[0][5]['resolution']['state'], 'invalid')
            self.assertEqual(self.role(connection), 'authored')
            self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=false',
                                                                            '[repos.fixture]\nenabled=true'))
            self.reload()
            result = self.publish(connection)
            recovered = self.dependencies(connection)
            self.assertEqual(self.pins(recovered), self.pins(before))
            self.assertEqual(recovered[0][5]['sourceExistence'], 'present')
            self.assertEqual(recovered[0][5]['reasons'], [])
            self.assertEqual(len(self.edges(connection)), 1)
            self.assertEqual(self.role(connection), 'derived')
            self.assertEqual(result.counts['dependencyRepositories']['downstream']['refsChanged'], 1)
            stable = self.state(connection)
            self.publish(connection)
            self.assertEqual(self.state(connection), stable)

    @proves('MYC-2.12', 'MYC-2.24', 'MYC-16.7', 'MYC-16.13', kind='store')
    def test_empty_file_selection_survives_deletion_and_recreation_without_chunk_edges(self):
        self.source.write_bytes(b'')
        self.base.commit()
        self.answer.write_bytes(self.answer.read_bytes().replace(b'source.md#Source', b'source.md'))
        with self.base.connect() as connection:
            before = self.prepare(connection)
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            removed = self.dependencies(connection)
            self.assertEqual(self.pins(removed), self.pins(before))
            self.assertEqual(removed[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(removed[0][5]['sourceAbsence']['previousFileHash'], sha256(b'').hexdigest())
            self.assertEqual(self.role(connection), 'derived')
            self.source.write_bytes(b'')
            self.publish(connection)
            restored = self.dependencies(connection)
            self.assertEqual(self.pins(restored), self.pins(before))
            self.assertEqual((restored[0][5]['sourceExistence'], restored[0][5]['reasons']), ('present', []))
            self.assertEqual(self.edges(connection), [])
            self.assertEqual(self.role(connection), 'derived')

    @proves('MYC-16.7', 'MYC-16.13', kind='store')
    def test_unindexed_removed_foreign_branch_refuses_an_away_observation(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.unlink()
            self.publish(connection)
            self.assertEqual(self.dependencies(connection)[0][5]['sourceExistence'], 'away')
            before = self.state(connection)
            self.base.git('checkout', '--detach')
            self.base.git('branch', '--delete', '--force', 'fixture-main')
            self.assertFalse(self.source.exists())
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)

    @proves('MYC-16.7', 'MYC-16.13', kind='store')
    def test_unindexed_new_foreign_branch_file_refuses_a_deleted_observation(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.unlink()
            self.base.commit()
            self.publish(connection)
            self.assertEqual(self.dependencies(connection)[0][5]['sourceExistence'], 'deleted')
            before = self.state(connection)
            self.base.git('checkout', '-b', 'hidden-source')
            self.source.write_bytes(b'# Source\nNew source held by another local branch.\n')
            self.base.commit()
            self.base.git('checkout', 'fixture-main')
            self.assertFalse(self.source.exists())
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)

    @proves('MYC-16.7', 'MYC-16.13', kind='store')
    def test_unindexed_recreation_of_deleted_moved_source_refuses_original_declaration(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            moved = self.base.artifact / 'moved.md'
            self.source.rename(moved)
            self.base.commit()
            self.publish(connection)
            moved_rows = self.dependencies(connection)
            self.assertEqual(self.pins(moved_rows), self.pins(before))
            self.assertEqual(moved_rows[0][4], 'fixture:@artifact/moved.md#Source')
            moved.unlink()
            self.base.commit()
            self.publish(connection)
            removed = self.dependencies(connection)
            self.assertEqual(removed[0][5]['sourceExistence'], 'deleted')
            self.assertEqual(removed[0][5]['sourceAbsence']['place'], 'fixture:@artifact/moved.md#Source')
            stable = self.state(connection)
            moved.write_bytes(b'# Source\nRecreated current natural place without ingest.\n')
            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, 'downstream')
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), stable)

    @proves('MYC-16.13', 'MYC-12.8', kind='store')
    def test_foreign_current_text_change_and_late_audit_failure_roll_back_source_and_owner(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.state(connection)
            original_answer = self.answer.read_bytes()
            self.source.write_bytes(b'# Source\nChanged source requiring observation.\n')
            actual = DependencyApplicationStore.apply_in_transaction

            def mutate_after_foreign_application(store, *args, **kwargs):
                reply = actual(store, *args, **kwargs)
                owner = store.connection.execute("""SELECT f.repository FROM public.mycel_file_locations l
                    JOIN public.mycel_file_versions v ON v.id=l.file_version
                    JOIN public.mycel_files f ON f.id=v.file_id WHERE l.id=%s""", (args[1],)).fetchone()[0]
                if owner == 'downstream':
                    self.answer.write_bytes(original_answer.replace(b'Unchanged dependant.', b'Changed during pass.'))
                return reply

            with patch.object(DependencyApplicationStore, 'apply_in_transaction', mutate_after_foreign_application):
                with self.assertRaises(EvidenceError) as caught:
                    self.publish(connection)
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)
            self.answer.write_bytes(original_answer)
            with MutationActivity(connection, build=1).session() as activity:
                with patch.object(activity, '_details', side_effect=RuntimeError('late audit failure')):
                    with self.assertRaises(RuntimeError):
                        self.publish(connection, activity=activity)
                self.assertEqual(self.state(connection), before)
                activity.finish('failed', error={'code': 'internal', 'message': 'fixture failed'})

    @proves('MYC-16.13', 'MYC-12.8', kind='store')
    def test_foreign_change_in_reply_callback_refuses_all_prospective_rows(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            before = self.state(connection)
            original_answer = self.answer.read_bytes()
            self.source.write_bytes(b'# Source\nChanged source for late reply guard.\n')

            def late_change(repository, counts):
                self.answer.write_bytes(original_answer.replace(b'Unchanged dependant.', b'Late changed dependant.'))
                return counts

            with self.assertRaises(EvidenceError) as caught:
                self.publish(connection, reply_counts=late_change)
            self.assertEqual(caught.exception.status, 'changed_since_ingest')
            self.assertEqual(self.state(connection), before)

    @proves('MYC-12.4', 'MYC-12.8', 'MYC-16.13', kind='store')
    def test_source_and_foreign_activity_share_one_commit_and_owner_counts(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged source with foreign activity.\n')
            with MutationActivity(connection, build=1).session() as activity:
                result = self.publish(connection, activity=activity)
                foreign_counts = result.counts['dependencyRepositories']['downstream']
                activity.finish('done', counts={('fixture', 'ingest'): result.counts,
                                                ('downstream', 'ingest'): foreign_counts})
            rows = connection.execute('SELECT id,repository,invocation FROM public.mycel_activity ORDER BY repository').fetchall()
            self.assertEqual([row[1] for row in rows], ['downstream', 'fixture'])
            self.assertEqual(rows[0][2], rows[1][2])
            foreign = activity_state(connection, rows[0][0])
            self.assertEqual(foreign['counts'], foreign_counts)
            self.assertEqual(foreign['files'], [])
            self.assertEqual(foreign['decisions'], [])
            self.assertEqual(activity_state(connection, rows[1][0])['counts'], result.counts)

    @proves('MYC-12.4', 'MYC-12.8', 'MYC-16.13', kind='store')
    def test_two_source_only_changes_keep_foreign_cumulative_reply_and_activity_counts(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            committed, previewed = {}, {}

            def add(previous, local):
                # Repository reply portions and current stale/pending state
                # are snapshots; processing counters accumulate per pass.
                return {key: value if key in {'dependencyRepositories', 'stale', 'stalePending'} else
                        add(previous.get(key, {}), value) if isinstance(value, dict) else
                        previous.get(key, 0) + value for key, value in local.items()}

            def cumulative(repository, local):
                value = add(committed.get(repository, {}), local)
                previewed[repository] = value
                return value

            with MutationActivity(connection, build=1).session() as activity:
                for text in (b'First source change.', b'Second source change.'):
                    self.source.write_bytes(b'# Source\n' + text + b'\n')
                    result = self.publish(connection, activity=activity, reply_counts=cumulative)
                    committed = dict(previewed)
                    self.assertEqual(result.counts['dependencyRepositories']['downstream'], committed['downstream'])
                self.assertEqual(committed['downstream']['refsChecked'], 2)
                self.assertEqual(committed['downstream']['refsChanged'], 2)
                self.assertEqual(committed['downstream']['pinsCaptured'], 0)
                self.assertEqual(committed['downstream']['staleChecked'], 2)
                self.assertEqual(committed['downstream']['staleChanged'], 1)
                self.assertEqual(committed['downstream']['staleReasons'], 2)
                self.assertEqual(committed['downstream']['stale'], 1)
                self.assertEqual(committed['fixture']['stalePending'], [])
                entries = connection.execute('SELECT id,repository FROM public.mycel_activity ORDER BY repository').fetchall()
                self.assertEqual([row[1] for row in entries], ['downstream', 'fixture'])
                for identifier, repository in entries:
                    self.assertEqual(activity_state(connection, identifier)['counts'], committed[repository])
                activity.finish('done', counts={(repository, 'ingest'): counts for repository, counts in committed.items()})
            for identifier, repository in entries:
                self.assertEqual(activity_state(connection, identifier)['counts'], committed[repository])

    @proves('MYC-12.4', 'MYC-16.11', 'MYC-16.13', kind='store')
    def test_collection_only_unchanged_pass_reports_and_audits_its_feature_mutation(self):
        with self.base.connect() as connection:
            before = self.prepare(connection)
            old_version = before[0][1]
            self.answer.write_bytes(self.answer.read_bytes().replace(b'Unchanged dependant.', b'Substantive dependant edit.'))
            self.publish(connection, 'downstream', collect=False)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_version,)).fetchone(), (1,))
            with MutationActivity(connection, build=1).session() as activity:
                result = self.publish(connection, 'downstream', activity=activity)
                self.assertTrue(result.changed)
                self.assertEqual(result.counts['collected']['versions'], 1)
                activity.finish('done', counts={('downstream', 'ingest'): result.counts})
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions WHERE id=%s',
                                               (old_version,)).fetchone(), (0,))
            entry = connection.execute('SELECT id,repository FROM public.mycel_activity').fetchone()
            self.assertEqual(entry[1], 'downstream')
            self.assertEqual(activity_state(connection, entry[0])['counts'], result.counts)

    def reread(self, connection, expected):
        settings = load_settings(path=self.base.config, home=self.base.base)
        scope = expected.guards['dependencyApplication']
        base = SourceResolver.from_transaction(connection, settings, kind=scope['kind'], location=scope['locationKey'])
        catalog = RetainedDependencyResolver(base, expected.catalog.anchors, expected.catalog.syntax_faults)
        endpoint = catalog.resolve(expected.dependant.place.address, purpose='endpoint')
        resolution = catalog.resolve(expected.resolution.declaration)
        if endpoint.state != 'resolved':
            raise EvidenceError('changed_since_ingest')
        for file in (endpoint.selection.file,) + ((resolution.selection.file,) if resolution.selection else ()):
            captured = capture_repository(settings, file.repository)
            matches = [item for place in captured.locations if place.id.kind == 'disk' for item in place.files
                       if any(alias.root == file.primary.root and alias.path == file.primary.path for alias in item.aliases)]
            if len(matches) != 1 or matches[0].source != file.source:
                raise EvidenceError('changed_since_ingest')
        values = dict(settings=settings, dependant=endpoint.selection.members[0], dependant_file=endpoint.selection.file,
                      resolution=resolution, catalog=catalog)
        if isinstance(expected, PinInputs):
            values['selection'] = resolution.selection
        return replace(expected, **values)

    def apply_assertions(self, connection, **kwargs):
        located = connection.execute("""SELECT l.id,cl.chunk_version FROM public.mycel_file_locations l
            JOIN public.mycel_file_versions v ON v.id=l.file_version JOIN public.mycel_files f ON f.id=v.file_id
            JOIN public.mycel_locations cl ON cl.file_location=l.id
            WHERE f.repository='downstream' AND l.kind='disk'""").fetchone()
        with self.guards(connection), atomic_transaction(connection):
            return DependencyApplicationStore(connection).apply_in_transaction(self.base.settings, str(located[0]), located[1],
                captured_at='2026-10-09T11:00:00Z', reread=lambda expected: self.reread(connection, expected), **kwargs)

    @proves('MYC-2.10', 'MYC-2.12', 'MYC-16.11', 'MYC-16.13', kind='store')
    def test_declared_and_asserted_same_source_survive_each_others_removal(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.apply_assertions(connection, assertions=('fixture:@artifact/source.md#Source',))
            both = self.dependencies(connection)
            self.assertEqual({row[2] for row in both}, {'declared', 'asserted'})
            self.assertEqual(len(self.edges(connection)), 2)
            declared = next(row for row in both if row[2] == 'declared')
            self.apply_assertions(connection, remove_assertions=(AssertedRemoval(
                SourceAddress('fixture', 'artifact', 'source.md', 'Source'), 'chunk'),))
            self.assertEqual(self.pins(self.dependencies(connection)), self.pins([declared]))
            self.apply_assertions(connection, assertions=('fixture:@artifact/source.md#Source',))
            asserted = next(row for row in self.dependencies(connection) if row[2] == 'asserted')
            self.answer.write_bytes(b'---\nrole: authored\n---\n# Answer\nUnchanged dependant.\n')
            self.publish(connection, 'downstream')
            self.assertEqual(self.pins(self.dependencies(connection)), self.pins([asserted]))
            self.assertEqual(self.role(connection), 'derived')
            self.apply_assertions(connection, remove_assertions=(AssertedRemoval(
                SourceAddress('fixture', 'artifact', 'source.md', 'Source'), 'chunk'),))
            self.assertEqual(self.dependencies(connection), [])
            self.assertEqual(self.role(connection), 'authored')
