"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_capture_history as _support
# from test_capture_history import (
#     CaptureHistoryStoreTests,
#     _fixture_module,
#     unittest,
# )


# class CaptureHistoryStoreTests(_support.CaptureHistoryStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_branch_and_stash_blobs_are_read_in_one_batch_and_a_failed_batch_reads_each_alone
#     def test_branch_and_stash_blobs_are_read_in_one_batch_and_a_failed_batch_reads_each_alone(self):
#         self.populate()
#         calls = []
#
#         def counting(args, **kwargs):
#             calls.append(tuple(args[:2]))
#             return _capture.run_git(args, **kwargs)
#
#         first = _capture.capture_repository(self.settings, 'fixture', _git=counting)
#         self.assertTrue(first.deletion_safe)
#         self.assertIn(('cat-file', '--batch'), calls)
#         # Only the stash's own commit header is read alone.
#         self.assertEqual(calls.count(('cat-file', '-p')), 1)
#
#         def no_batch(args, **kwargs):
#             calls.append(tuple(args[:2]))
#             if tuple(args[:2]) == ('cat-file', '--batch'):
#                 return _capture.CompletedChild(1, b'', b'', 0.0)
#             return _capture.run_git(args, **kwargs)
#
#         calls.clear()
#         second = _capture.capture_repository(self.settings, 'fixture', _git=no_batch)
#         self.assertGreater(calls.count(('cat-file', '-p')), 1)
#         self.assertEqual([[file.source for file in location.files] for location in second.locations],
#                          [[file.source for file in location.files] for location in first.locations])
# TEST-TIER-DISABLED-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_branch_and_stash_blobs_are_read_in_one_batch_and_a_failed_batch_reads_each_alone

# TEST-TIER-DISABLED-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_unchanged_disk_and_located_repeat_from_persisted_history_never_splits
#     def test_unchanged_disk_and_located_repeat_from_persisted_history_never_splits(self):
#         self.populate()
#         with self.connect() as connection:
#             first = LocatedCaptureStore(connection).apply(self.settings, 'fixture')
#             before = self.state(connection)
#             identities = tuple((file.binding, file.chunk_versions) for file in first.files)
#         # A new store object and connection must use persisted parser history,
#         # rather than process-local previous-manifest state.
#         with self.connect() as connection:
#             with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
#                     patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 store = LocatedCaptureStore(connection)
#                 captured = store.capture(self.settings, 'fixture')
#                 self.assertTrue(all(file.reused_parse for file in captured.disk.files))
#                 self.assertTrue(all(location.reused for location in captured.locations[1:]))
#                 frontmatter = next(file.parsed.frontmatter for file in captured.disk.files
#                                    if file.corpus == 'documents')
#                 self.assertEqual(frontmatter['unknown_nul'], 'malformed\0ref')
#                 self.assertEqual(frontmatter['unknown_surrogate'], '\ud800')
#                 self.assertEqual(frontmatter['unknown\0key'], '\udfff')
#                 repeat = store.apply(self.settings, 'fixture')
#             self.assertEqual((markdown.call_count, code.call_count), (0, 0))
#             self.assertFalse(repeat.changed)
#             self.assertEqual(tuple((file.binding, file.chunk_versions) for file in repeat.files), identities)
#             self.assertEqual(self.state(connection), before)
#         # The disk-only API also retains unchanged parse history without a Git
#         # publication catalog, while reading every selected disk file again.
#         self.git('update-ref', '-d', 'refs/stash')
#         self.git('update-ref', '-d', 'refs/heads/feature')
#         self.git('update-ref', '-d', 'refs/heads/fixture-main')
#         with self.connect() as connection:
#             disk = DiskCaptureStore(connection)
#             disk.apply(self.settings, 'fixture')
#             before = self.state(connection)
#             with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
#                     patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 repeat = disk.apply(self.settings, 'fixture')
#             self.assertEqual((markdown.call_count, code.call_count), (0, 0))
#             self.assertFalse(repeat.changed)
#             self.assertEqual(self.state(connection), before)
# TEST-TIER-DISABLED-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_unchanged_disk_and_located_repeat_from_persisted_history_never_splits

# TEST-TIER-DISABLED-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored
#     def test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored(self):
#         self.populate(git=False)
#         with self.connect() as connection:
#             store = DiskCaptureStore(connection)
#             first = store.apply(self.settings, 'fixture')
#             original = next(file for file in first.files if file.binding.primary.path == 'module.py')
#             before = self.state(connection)
#             preliminary = store.capture(self.settings, 'fixture')
#             self.assertEqual(self.state(connection), before)
#             info = self.source.stat()
#             self.source.write_bytes(b'def value():\n    return 9\n')
#             os.utime(self.source, ns=(info.st_atime_ns, info.st_mtime_ns))
#             with self.assertRaises(MycelError):
#                 store.apply(self.settings, preliminary)
#             self.assertEqual(self.state(connection), before)
#             with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
#                     patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 changed = store.apply(self.settings, 'fixture')
#             current = next(file for file in changed.files if file.binding.primary.path == 'module.py')
#             self.assertTrue(changed.changed)
#             self.assertEqual(markdown.call_count, 0)
#             self.assertGreater(code.call_count, 0)
#             self.assertEqual(current.binding.identifier, original.binding.identifier)
#             self.assertEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
#             self.assertNotEqual(current.chunk_versions[0][1], original.chunk_versions[0][1])
#             self.assertEqual(bytes(connection.execute('SELECT source_bytes FROM public.mycel_file_versions '
#                 'WHERE id=%s', (current.binding.version,)).fetchone()[0]), self.source.read_bytes())
# TEST-TIER-DISABLED-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored

# TEST-TIER-DISABLED-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_reused_parses_preserve_late_disk_git_and_effective_settings_rollback_guards
#     def test_reused_parses_preserve_late_disk_git_and_effective_settings_rollback_guards(self):
#         self.populate()
#         with self.connect() as connection:
#             store = LocatedCaptureStore(connection)
#             store.apply(self.settings, 'fixture')
#             initial_settings = self.config.read_bytes()
#             initial_source = self.source.read_bytes()
#             for stage in ('disk', 'git', 'settings'):
#                 with self.subTest(stage=stage):
#                     before = self.state(connection)
#                     def late_change(repository, counts):
#                         if stage == 'disk':
#                             self.source.write_bytes(b'def value():\n    return 7\n')
#                         elif stage == 'git':
#                             self.git('branch', 'late-ref')
#                         else:
#                             self.config.write_bytes(initial_settings.replace(b'enabled=true', b'enabled=false'))
#                         return counts
#                     try:
#                         with self.assertRaises(MycelError):
#                             store.apply(self.settings, 'fixture', reply_counts=late_change)
#                         self.assertEqual(self.state(connection), before)
#                     finally:
#                         self.source.write_bytes(initial_source)
#                         self.config.write_bytes(initial_settings)
#                         if stage == 'git':
#                             self.git('branch', '--delete', 'late-ref')
# TEST-TIER-DISABLED-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_reused_parses_preserve_late_disk_git_and_effective_settings_rollback_guards

# TEST-TIER-DISABLED-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses
#     def test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses(self):
#         self.populate(git=False)
#         with self.connect() as connection:
#             store = DiskCaptureStore(connection)
#             store.apply(self.settings, 'fixture')
#             before = self.state(connection)
#             manifest = store.capture(self.settings, 'fixture')
#             document = next(file for file in manifest.disk.files if file.corpus == 'documents')
#             forged = replace(document, parsed=replace(document.parsed, chunks=(
#                 replace(document.parsed.chunks[0], name='Forged', title='Forged'),)))
#             manifest = replace(manifest, locations=(replace(manifest.disk, files=tuple(
#                 forged if file is document else file for file in manifest.disk.files)),))
#             with self.assertRaises(MycelError):
#                 store.apply(self.settings, manifest)
#             self.assertEqual(self.state(connection), before)
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=jsonb_set(metadata,"
#                 "'{parseHistory,parsedHash}',%s) WHERE kind='disk'", (Jsonb('0' * 64),))
#             with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
#                     patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 captured = store.capture(self.settings, 'fixture')
#             self.assertTrue(captured.deletion_safe)
#             self.assertGreater(markdown.call_count, 0)
#             self.assertGreater(code.call_count, 0)
#             store.apply(self.settings, 'fixture')
#             location, metadata = connection.execute('SELECT l.id,l.metadata FROM public.mycel_file_locations l '
#                 'JOIN public.mycel_file_versions v ON v.id=l.file_version '
#                 "JOIN public.mycel_files f ON f.id=v.file_id WHERE f.corpus='code' AND l.kind='disk'").fetchone()
#             metadata['parseHistory']['parsed']['value'] = []
#             metadata['parseHistory']['parsedHash'] = sha256(
#                 _capture._json(metadata['parseHistory']['parsed'])).hexdigest()
#             connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
#                                (Jsonb(metadata), location))
#             with patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 captured = store.capture(self.settings, 'fixture')
#             self.assertTrue(captured.deletion_safe)
#             self.assertGreater(code.call_count, 0)
#             store.apply(self.settings, 'fixture')
#             with patch.object(_capture, '_parser_revision', return_value='changed-parser'), \
#                     patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
#                     patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
#                 captured = store.capture(self.settings, 'fixture')
#             self.assertTrue(captured.deletion_safe)
#             self.assertGreater(markdown.call_count, 0)
#             self.assertGreater(code.call_count, 0)
# TEST-TIER-DISABLED-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:2
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:2

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:3
# from hashlib import sha256
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:3

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:4
# import os
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:4

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:5
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:8
# from psycopg.types.json import Jsonb
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:8

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:10
# from mycel import _capture
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:10

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:11
# from mycel._disk_reconciliation import DiskCaptureStore
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:11

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:12
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:12

# TEST-TIER-IMPORTS-BEGIN tests/test_capture_history.py:13
# from mycel._located_reconciliation import LocatedCaptureStore
# TEST-TIER-IMPORTS-END tests/test_capture_history.py:13

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
