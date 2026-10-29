"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_capture_history as _support
from test_capture_history import (DiskCaptureStore ,Jsonb ,MycelError ,_capture ,os ,patch ,replace ,sha256)


class CaptureHistoryStoreTests(_support.CaptureHistoryStoreTests):


# TEST-TIER-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored
    def test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored(self):
        self.populate(git=False)
        with self.connect() as connection:
            store = DiskCaptureStore(connection)
            first = store.apply(self.settings, 'fixture')
            original = next(file for file in first.files if file.binding.primary.path == 'module.py')
            before = self.state(connection)
            preliminary = store.capture(self.settings, 'fixture')
            self.assertEqual(self.state(connection), before)
            info = self.source.stat()
            self.source.write_bytes(b'def value():\n    return 9\n')
            os.utime(self.source, ns=(info.st_atime_ns, info.st_mtime_ns))
            with self.assertRaises(MycelError):
                store.apply(self.settings, preliminary)
            self.assertEqual(self.state(connection), before)
            with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
                    patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
                changed = store.apply(self.settings, 'fixture')
            current = next(file for file in changed.files if file.binding.primary.path == 'module.py')
            self.assertTrue(changed.changed)
            self.assertEqual(markdown.call_count, 0)
            self.assertGreater(code.call_count, 0)
            self.assertEqual(current.binding.identifier, original.binding.identifier)
            self.assertEqual(current.chunk_versions[0][0], original.chunk_versions[0][0])
            self.assertNotEqual(current.chunk_versions[0][1], original.chunk_versions[0][1])
            self.assertEqual(bytes(connection.execute('SELECT source_bytes FROM public.mycel_file_versions '
                'WHERE id=%s', (current.binding.version,)).fetchone()[0]), self.source.read_bytes())
# TEST-TIER-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_changed_code_after_preliminary_scan_is_not_hidden_or_preemptively_stored


# TEST-TIER-BEGIN tests/test_capture_history.py::CaptureHistoryStoreTests.test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses
    def test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses(self):
        self.populate(git=False)
        with self.connect() as connection:
            store = DiskCaptureStore(connection)
            store.apply(self.settings, 'fixture')
            before = self.state(connection)
            manifest = store.capture(self.settings, 'fixture')
            document = next(file for file in manifest.disk.files if file.corpus == 'documents')
            forged = replace(document, parsed=replace(document.parsed, chunks=(
                replace(document.parsed.chunks[0], name='Forged', title='Forged'),)))
            manifest = replace(manifest, locations=(replace(manifest.disk, files=tuple(
                forged if file is document else file for file in manifest.disk.files)),))
            with self.assertRaises(MycelError):
                store.apply(self.settings, manifest)
            self.assertEqual(self.state(connection), before)
            connection.execute("UPDATE public.mycel_file_locations SET metadata=jsonb_set(metadata,"
                "'{parseHistory,parsedHash}',%s) WHERE kind='disk'", (Jsonb('0' * 64),))
            with patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
                    patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
                captured = store.capture(self.settings, 'fixture')
            self.assertTrue(captured.deletion_safe)
            self.assertGreater(markdown.call_count, 0)
            self.assertGreater(code.call_count, 0)
            store.apply(self.settings, 'fixture')
            location, metadata = connection.execute('SELECT l.id,l.metadata FROM public.mycel_file_locations l '
                'JOIN public.mycel_file_versions v ON v.id=l.file_version '
                "JOIN public.mycel_files f ON f.id=v.file_id WHERE f.corpus='code' AND l.kind='disk'").fetchone()
            metadata['parseHistory']['parsed']['value'] = []
            metadata['parseHistory']['parsedHash'] = sha256(
                _capture._json(metadata['parseHistory']['parsed'])).hexdigest()
            connection.execute('UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s',
                               (Jsonb(metadata), location))
            with patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
                captured = store.capture(self.settings, 'fixture')
            self.assertTrue(captured.deletion_safe)
            self.assertGreater(code.call_count, 0)
            store.apply(self.settings, 'fixture')
            with patch.object(_capture, '_parser_revision', return_value='changed-parser'), \
                    patch.object(_capture, 'split_markdown', wraps=_capture.split_markdown) as markdown, \
                    patch.object(_capture, 'chunk_code', wraps=_capture.chunk_code) as code:
                captured = store.capture(self.settings, 'fixture')
            self.assertTrue(captured.deletion_safe)
            self.assertGreater(markdown.call_count, 0)
            self.assertGreater(code.call_count, 0)
# TEST-TIER-END tests/test_capture_history.py::CaptureHistoryStoreTests.test_forged_incoming_parse_is_refused_and_corrupt_or_changed_parser_cache_reparses
