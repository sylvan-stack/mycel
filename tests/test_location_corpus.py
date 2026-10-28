"""Strict location corpus ownership and actual mixed disk/Git publication."""
import unittest
from hashlib import sha256

from mycel._capture import (
    CapturedFile,
    CapturedLocation,
    CaptureManifest,
    FileAlias,
    LocationId,
    capture_repository,
    parse_history_record,
)
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._markdown import split_markdown
from mycel._store import TABLES

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class LocationCorpusUnitTests(unittest.TestCase):
    def document(self):
        raw = b'# Guide\nExact retained body.\n'
        alias = FileAlias('artifact', 'guide.md')
        captured = CapturedFile(alias, (alias,), 'documents', raw, sha256(raw).hexdigest(), split_markdown(raw))
        policy = 'a' * 64
        metadata = {'root': alias.root, 'path': alias.path,
            'aliases': [{'root': alias.root, 'path': alias.path}],
            'parseHistory': parse_history_record(captured, policy)}
        row = ('file', alias.root, alias.path, 'code', 'location', 'version', raw, metadata)
        manifest = CaptureManifest('fixture', policy, (CapturedLocation(
            LocationId('disk', None, 'disk'), None, (captured,), True),), True)
        return captured, row, manifest

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusUnitTests.test_strict_metadata_does_not_coerce_default_or_let_prior_metadata_override_capture
#     def test_strict_metadata_does_not_coerce_default_or_let_prior_metadata_override_capture(self):
#         captured, row, _ = self.document()
#         self.assertIsNone(location_corpus({}, legacy=True))
#         for value in (None, True, 1, [], {}, '', 'document', 'CODE'):
#             with self.subTest(value=value), self.assertRaises(MycelError):
#                 location_corpus({'corpus': value}, legacy=True)
#         self.assertEqual(_location_rows([(*row[:7], {**row[7], 'corpus': 'documents'})])[0][3], 'documents')
#         require_captured_corpus({'corpus': 'documents'}, captured)
#         with self.assertRaises(MycelError):
#             require_captured_corpus({'corpus': 'code'}, captured)
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusUnitTests.test_strict_metadata_does_not_coerce_default_or_let_prior_metadata_override_capture

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusUnitTests.test_legacy_history_is_not_advisory_reuse_and_prior_empty_guard_needs_checked_evidence
#     def test_legacy_history_is_not_advisory_reuse_and_prior_empty_guard_needs_checked_evidence(self):
#         _, row, manifest = self.document()
#         history = _parse_history('fixture', [row])
#         self.assertEqual(history.disk.files, ())
#         # The legacy guard can establish ownership from complete parser bytes,
#         # aliases and hashes, but a parser type tag by itself proves nothing.
#         _guard_disk_corpora([row], manifest, False)
#         empty = replace(manifest, locations=(replace(manifest.disk, files=()),))
#         with self.assertRaises(MycelError):
#             _guard_disk_corpora([row], empty, False)
#         corrupt = (*row[:7], {**row[7], 'parseHistory': {'parsed': {'type': 'MarkdownDocument'}}})
#         with self.assertRaises(MycelError):
#             _guard_disk_corpora([corrupt], manifest, False)
#         _guard_disk_corpora([corrupt], manifest, True)
#         contradictory = (*row[:7], {**row[7], 'corpus': 'code'})
#         for confirmed in (False, True):
#             with self.assertRaises(MycelError):
#                 _guard_disk_corpora([contradictory], manifest, confirmed)
#         with self.assertRaises(MycelError):
#             _parse_history('fixture', [contradictory])
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusUnitTests.test_legacy_history_is_not_advisory_reuse_and_prior_empty_guard_needs_checked_evidence


class LocationCorpusStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.raw = b'---\ngenerated: true\n---\n# Historical\nOriginal generated text.\n'
        self.generated = self.base.artifact / 'generated.md'
        self.generated.write_bytes(self.raw)
        (self.base.artifact / 'keeper.md').write_bytes(b'# Keeper\nIndependent document.\n')
        (self.base.code / 'keeper.py').write_bytes(b'def keeper():\n    return 1\n')
        self.source = self.base.artifact / 'source.md'
        self.source.write_bytes(b'# Source\nOriginal source.\n')
        self.base.git('init', '--initial-branch=fixture-main')
        self.commit = self.base.commit()

    def publish(self, connection, *, activity=None, **kwargs):
        manifest = capture_repository(self.base.settings, 'fixture')
        producer = LocatedDependencyProducer(self.base.settings, captured_at='2026-10-11T12:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest)
        return LocatedCaptureStore(connection).apply(self.base.settings, manifest,
            batch_handoff=producer, activity=activity, **kwargs)

    def state(self, connection):
        # Quiet repeats/failures preserve every feature and activity row,
        # including location metadata and xmin. Invocation liveness records
        # have their own lifecycle and are created by each activity session.
        return {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
                    'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES
                if table.name not in ('mycel_invocations', 'mycel_lock_keys')}

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusStoreTests.test_checked_source_binding_writes_corpus_on_update_and_insert_without_inventing_legacy_git_ownership
#     def test_checked_source_binding_writes_corpus_on_update_and_insert_without_inventing_legacy_git_ownership(self):
#         from mycel._source_bindings import bind_disk_file
#         from uuid import uuid4
#         with self.base.connect() as connection:
#             captured = next(file for file in capture_repository(self.base.settings, 'fixture').disk.files
#                             if file.primary.path == 'generated.md')
#             binding = bind_disk_file(connection, self.base.settings, 'fixture', captured)
#             metadata = connection.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s',
#                 (binding.location,)).fetchone()[0]
#             self.assertEqual(metadata['corpus'], 'documents')
#             legacy = uuid4()
#             connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
#                 (legacy, binding.version, 'branch', 'legacy-main', Jsonb({'auditTag': 'retained'})))
#             self.generated.rename(self.base.artifact / 'generated.py')
#             captured = next(file for file in capture_repository(self.base.settings, 'fixture').disk.files
#                             if file.primary.path == 'generated.py')
#             updated = bind_disk_file(connection, self.base.settings, 'fixture', captured,
#                 recognized_move=binding.identifier)
#             self.assertEqual((updated.identifier, updated.version, updated.location),
#                              (binding.identifier, binding.version, binding.location))
#             self.assertEqual(connection.execute('SELECT metadata->>\'corpus\' FROM public.mycel_file_locations WHERE id=%s',
#                 (updated.location,)).fetchone(), ('code',))
#             retained = connection.execute('SELECT metadata FROM public.mycel_file_locations WHERE id=%s', (legacy,)).fetchone()[0]
#             self.assertNotIn('corpus', retained)
#             self.assertEqual((retained['root'], retained['path'], retained['auditTag']),
#                              ('artifact', 'generated.md', 'retained'))
#             (self.base.artifact / 'generated.py').write_bytes(b'def generated():\n    return 2\n')
#             changed = next(file for file in capture_repository(self.base.settings, 'fixture').disk.files
#                             if file.primary.path == 'generated.py')
#             inserted = bind_disk_file(connection, self.base.settings, 'fixture', changed)
#             self.assertEqual(inserted.identifier, binding.identifier)
#             self.assertNotEqual(inserted.version, binding.version)
#             self.assertNotEqual(inserted.location, binding.location)
#             self.assertEqual(connection.execute('SELECT metadata->>\'corpus\' FROM public.mycel_file_locations WHERE id=%s',
#                 (inserted.location,)).fetchone(), ('code',))
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusStoreTests.test_checked_source_binding_writes_corpus_on_update_and_insert_without_inventing_legacy_git_ownership

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusStoreTests.test_dirty_code_head_document_retains_exact_location_corpus_through_full_producer_repeat_and_rollback
#     def test_dirty_code_head_document_retains_exact_location_corpus_through_full_producer_repeat_and_rollback(self):
#         from mycel._derive import DeriveStore
#         with self.base.connect() as connection:
#             with MutationActivity(connection, build=1).session() as activity:
#                 initial = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): initial.counts})
#             old = next(file for file in initial.files if file.location.kind == 'disk'
#                        and file.binding.primary.path == 'generated.md')
#             self.generated.rename(self.base.artifact / 'generated.py')
#             with MutationActivity(connection, build=1).session() as activity:
#                 changed = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): changed.counts})
#             disk = next(file for file in changed.files if file.location.kind == 'disk'
#                         and file.binding.primary.path == 'generated.py')
#             branch = next(file for file in changed.files if file.location.kind == 'branch'
#                           and file.binding.primary.path == 'generated.md')
#             self.assertEqual((disk.binding.identifier, branch.binding.identifier), (old.binding.identifier,) * 2)
#             self.assertEqual((disk.binding.version, branch.binding.version), (old.binding.version,) * 2)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_file_versions WHERE file_id=%s',
#                 (old.binding.identifier,)).fetchone(), (1,))
#             stored = connection.execute('SELECT l.kind,l.metadata,v.source_bytes FROM public.mycel_file_locations l '
#                 'JOIN public.mycel_file_versions v ON v.id=l.file_version WHERE v.file_id=%s ORDER BY l.kind',
#                 (old.binding.identifier,)).fetchall()
#             self.assertEqual([(kind, data['path'], data['corpus'], bytes(raw)) for kind, data, raw in stored],
#                 [('branch', 'generated.md', 'documents', self.raw), ('disk', 'generated.py', 'code', self.raw)])
#             self.assertTrue(next(data for kind, data, _ in stored if kind == 'disk')
#                             ['documentDeclarations']['metadata']['generated'])
#             resolver = SourceResolver.from_store(connection, self.base.settings)
#             current = next(file for file in resolver.files if file.primary.path == 'generated.py')
#             self.assertEqual(current.chunks[0].kind, 'file')
#             self.assertEqual(current.chunks[0].source, self.raw)
#             historical = SourceResolver.from_store(connection, self.base.settings, kind='branch',
#                 location=location_key(LocationId('branch', 'code', 'refs/heads/fixture-main')))
#             retained = next(file for file in historical.files if file.primary.path == 'generated.md')
#             self.assertEqual(retained.chunks[0].kind, 'document')
#             self.assertEqual(retained.chunks[0].source, b'# Historical\nOriginal generated text.\n')
#             contexts, _ = retained_contexts(connection, 'fixture')
#             self.assertEqual(contexts[current.chunks[0].version].kind, 'code')
#             self.assertIn('generated.py', contexts[current.chunks[0].version].place_line)
#             self.assertEqual(contexts[retained.chunks[0].version].kind, 'document')
#             self.assertIn('generated.md', contexts[retained.chunks[0].version].place_line)
#             dependant = resolver._members(current, current.chunks)[0].place.address
#             DeriveStore(connection).apply(self.base.settings, dependant, 'fixture:@artifact/source.md#Source',
#                 captured_at='2026-10-11T12:01:00Z')
#             pins = connection.execute('SELECT id,baseline_owner,source_place FROM public.mycel_dependencies '
#                 "WHERE kind='asserted' ORDER BY id").fetchall()
#             evidence = connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_evidence_references r '
#                 'ORDER BY to_jsonb(r)::text').fetchall()
#             self.source.write_bytes(b'# Source\nChanged source of current code.\n')
#             with MutationActivity(connection, build=1).session() as activity:
#                 staled = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): staled.counts})
#             self.assertEqual(connection.execute('SELECT id,baseline_owner,source_place FROM public.mycel_dependencies '
#                 "WHERE kind='asserted' ORDER BY id").fetchall(), pins)
#             self.assertEqual(connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_evidence_references r '
#                 'ORDER BY to_jsonb(r)::text').fetchall(), evidence)
#             self.assertEqual(connection.execute('SELECT reason->>\'kind\' FROM public.mycel_stale_reasons '
#                 'WHERE chunk_version=%s', (current.chunks[0].version,)).fetchall(), [('source_changed',)])
#             before = self.state(connection)
#             with MutationActivity(connection, build=1).session() as activity:
#                 repeated = self.publish(connection, activity=activity)
#                 activity.finish('done', counts={('fixture', 'ingest'): repeated.counts})
#             self.assertFalse(repeated.changed)
#             self.assertEqual(self.state(connection), before)
#             self.source.write_bytes(b'# Source\nLate prospective source change.\n')
#             def fail_reply(repository, counts):
#                 raise RuntimeError('late reply failure')
#             with MutationActivity(connection, build=1).session() as activity:
#                 with self.assertRaisesRegex(RuntimeError, 'late reply failure'):
#                     self.publish(connection, activity=activity, reply_counts=fail_reply)
#                 # A failed public operation's finish is caller-owned. Inspect
#                 # publication atomicity before creating a separate failure entry.
#                 self.assertEqual(self.state(connection), before)
#             self.assertEqual(self.base.git('rev-parse', 'HEAD'), self.commit)
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusStoreTests.test_dirty_code_head_document_retains_exact_location_corpus_through_full_producer_repeat_and_rollback

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusStoreTests.test_legacy_fields_recapture_atomically_and_malformed_or_contradictory_corpus_refuses
#     def test_legacy_fields_recapture_atomically_and_malformed_or_contradictory_corpus_refuses(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=metadata-'corpus'")
#             before = self.state(connection)
#             captured = LocatedCaptureStore(connection).capture(self.base.settings, 'fixture')
#             self.assertFalse(any(file.reused_parse for location in captured.locations for file in location.files))
#             self.assertFalse(any(location.reused for location in captured.locations[1:]))
#             with self.assertRaisesRegex(RuntimeError, 'late corpus upgrade failure'):
#                 self.publish(connection, reply_counts=lambda *_: (_ for _ in ()).throw(RuntimeError('late corpus upgrade failure')))
#             self.assertEqual(self.state(connection), before)
#             self.assertTrue(self.publish(connection).changed)
#             self.assertTrue(all('corpus' in row[0] for row in connection.execute(
#                 'SELECT metadata FROM public.mycel_file_locations').fetchall()))
#             before = self.state(connection)
#             self.assertFalse(self.publish(connection).changed)
#             self.assertEqual(self.state(connection), before)
#             target, original = connection.execute("SELECT id,metadata FROM public.mycel_file_locations "
#                 "WHERE kind='disk' AND metadata->>'path'='generated.md'").fetchone()
#             for value in (None, True, 'unknown', 'code'):
#                 with self.subTest(value=value):
#                     connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
#                         (Jsonb({**original, 'corpus': value}), target))
#                     damaged = self.state(connection)
#                     with self.assertRaises(MycelError):
#                         self.publish(connection, confirm_empty=True)
#                     self.assertEqual(self.state(connection), damaged)
#             connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s', (Jsonb(original), target))
#             # An older writer can preserve a stale key while changing exact
#             # bytes/parser metadata. Field presence alone must not authorize
#             # reuse or publication: independently valid code history conflicts
#             # with the stale document corpus even with empty confirmation.
#             target, code_metadata = connection.execute("SELECT id,metadata FROM public.mycel_file_locations "
#                 "WHERE kind='disk' AND metadata->>'path'='keeper.py'").fetchone()
#             connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
#                 (Jsonb({**code_metadata, 'corpus': 'documents'}), target))
#             damaged = self.state(connection)
#             for confirmed in (False, True):
#                 with self.assertRaisesRegex(MycelError, 'contradicts its exact parser evidence'):
#                     self.publish(connection, confirm_empty=confirmed)
#                 self.assertEqual(self.state(connection), damaged)
#             connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
#                 (Jsonb(code_metadata), target))
#             # Exercise the concrete older-writer transition too: the dirty
#             # rename updates raw-code parser history/location path while the
#             # previous document key survives its metadata merge.
#             self.generated.rename(self.base.artifact / 'generated.py')
#             self.publish(connection)
#             target, current = connection.execute("SELECT id,metadata FROM public.mycel_file_locations "
#                 "WHERE kind='disk' AND metadata->>'path'='generated.py'").fetchone()
#             connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
#                 (Jsonb({**current, 'corpus': original['corpus']}), target))
#             damaged = self.state(connection)
#             with self.assertRaisesRegex(MycelError, 'contradicts its exact parser evidence'):
#                 LocatedCaptureStore(connection).capture(self.base.settings, 'fixture')
#             with self.assertRaisesRegex(MycelError, 'contradicts its exact parser evidence'):
#                 self.publish(connection, confirm_empty=True)
#             self.assertEqual(self.state(connection), damaged)
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusStoreTests.test_legacy_fields_recapture_atomically_and_malformed_or_contradictory_corpus_refuses

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusStoreTests.test_unknown_legacy_disk_guard_needs_explicit_confirmation_and_retained_git_is_not_a_prior_disk_corpus
#     def test_unknown_legacy_disk_guard_needs_explicit_confirmation_and_retained_git_is_not_a_prior_disk_corpus(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=metadata-'corpus'-'parseHistory' "
#                 "WHERE kind='disk' AND metadata->>'path'='generated.md'")
#             before = self.state(connection)
#             with self.assertRaisesRegex(MycelError, 'previous on-disk corpus is unknown'):
#                 self.publish(connection)
#             self.assertEqual(self.state(connection), before)
#             self.assertTrue(self.publish(connection, confirm_empty=True).changed)
#             # Both prior disk corpora still have independent keepers after the
#             # mixed rename. Removing a disk source while local HEAD retains it
#             # must preserve the exact version/location and searchable chunk.
#             self.generated.rename(self.base.artifact / 'generated.py')
#             mixed = self.publish(connection)
#             branch = next(file for file in mixed.files if file.location.kind == 'branch'
#                           and file.binding.primary.path == 'generated.md')
#             (self.base.artifact / 'generated.py').unlink()
#             self.publish(connection)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_file_locations WHERE id=%s',
#                 (branch.binding.location,)).fetchone(), (1,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_file_versions WHERE id=%s',
#                 (branch.binding.version,)).fetchone(), (1,))
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_locations WHERE chunk_version=%s',
#                 (branch.chunk_versions[0][1],)).fetchone(), (1,))
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusStoreTests.test_unknown_legacy_disk_guard_needs_explicit_confirmation_and_retained_git_is_not_a_prior_disk_corpus

# TEST-TIER-DISABLED-BEGIN tests/test_location_corpus.py::LocationCorpusStoreTests.test_evaluation_uses_selected_disk_owner_and_fingerprints_its_corpus
#     def test_evaluation_uses_selected_disk_owner_and_fingerprints_its_corpus(self):
#         with self.base.connect() as connection:
#             self.publish(connection)
#             self.generated.rename(self.base.artifact / 'generated.py')
#             self.publish(connection)
#             def observe():
#                 with StoreRetrieval(connection, self.base.settings).snapshot('fixture') as snapshot:
#                     member = snapshot.resolver.resolve('fixture:@artifact/generated.py').selection.members[0]
#                     self.assertTrue(snapshot.eligible(RetrievalQuery('generated', (), 'code'), member))
#                     self.assertFalse(snapshot.eligible(RetrievalQuery('generated', (), 'docs'), member))
#                     return snapshot.index_fingerprint
#             fingerprint = observe()
#             file_id = connection.execute("SELECT id FROM public.mycel_files WHERE path='generated.py'").fetchone()[0]
#             connection.execute("UPDATE public.mycel_files SET corpus='documents' WHERE id=%s", (file_id,))
#             self.assertEqual(observe(), fingerprint)
#             # Retained HEAD metadata cannot redefine the selected disk origin.
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=jsonb_set(metadata,'{corpus}',%s) "
#                 "WHERE kind='branch' AND metadata->>'path'='generated.md'", (Jsonb('code'),))
#             self.assertEqual(observe(), fingerprint)
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=jsonb_set(metadata,'{corpus}',%s) "
#                 "WHERE kind='disk' AND metadata->>'path'='generated.py'", (Jsonb('documents'),))
#             damaged = self.state(connection)
#             with self.assertRaises(MycelError):
#                 observe()
#             self.assertEqual(self.state(connection), damaged)
# TEST-TIER-DISABLED-END tests/test_location_corpus.py::LocationCorpusStoreTests.test_evaluation_uses_selected_disk_owner_and_fingerprints_its_corpus

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:2
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:6
# from psycopg.types.json import Jsonb
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:8
# from mycel._activity import MutationActivity
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:11
# from mycel._disk_reconciliation import _guard_disk_corpora, _location_rows, _parse_history
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:12
# from mycel._embed import retained_contexts
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:13
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:14
# from mycel._evaluation import RetrievalQuery
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:15
# from mycel._evaluation_store import StoreRetrieval
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:16
# from mycel._location_corpus import location_corpus, require_captured_corpus
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:18
# from mycel._located_reconciliation import LocatedCaptureStore, location_key
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:18
# TEST-TIER-IMPORTS-BEGIN tests/test_location_corpus.py:20
# from mycel._resolver import SourceResolver
# TEST-TIER-IMPORTS-END tests/test_location_corpus.py:20
