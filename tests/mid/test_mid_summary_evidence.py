"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_evidence as _support
from test_summary_evidence import (GenerationEvidenceStore ,Path ,SummarySection ,blob ,document ,invocation_guard ,json ,load_settings ,selections ,sys ,tempfile)


class SummaryEvidenceStoreTests(_support.SummaryEvidenceStoreTests):


# TEST-TIER-BEGIN tests/test_summary_evidence.py::SummaryEvidenceStoreTests.test_real_generation_caller_retains_exact_stdin_cut_source_and_stdout_with_live_private_lease
    def test_real_generation_caller_retains_exact_stdin_cut_source_and_stdout_with_live_private_lease(self):
        from mycel._summaries import generate_summary_requests

        with self.store_fixture.backend.connection(self.store_fixture.database) as connection, tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observed = root / 'stdin.bin'
            executable = root / 'fictional-summary-command.py'
            answer = ' Exact fictional answer 雪🙂\r\n\0ending '.encode()
            executable.write_text('import pathlib, sys\n'
                'pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n'
                'sys.stdout.buffer.write(bytes.fromhex(sys.argv[2]))\n', encoding='utf-8')
            command = (sys.executable, str(executable), str(observed), answer.hex())
            config = root / 'config.toml'
            config.write_text('[summaries]\ncommand=' + json.dumps(command) + '\nat_once=1\n', encoding='utf-8')
            settings = load_settings(path=config)
            file = self.seed(connection, document('# Source\n' + '🙂雪' * 30_000, repository='owner'))
            sections = tuple(SummarySection(member, member.chunk.span[0]) for member in selections(file))
            store = GenerationEvidenceStore(connection)
            counts = self.searchable_counts(connection)
            with invocation_guard(connection) as invocation:
                result, = generate_summary_requests(settings, sections, operation='build', invocation=invocation,
                                                   evidence_store=store)
                self.assertEqual(result.result.response, answer)
                retained = store.read('owner', result.evidence.manifest_hash)
                self.assertEqual(blob(retained, retained.manifest.payload['request']), observed.read_bytes())
                self.assertEqual(observed.read_bytes(), result.request.request)
                self.assertEqual(blob(retained, retained.manifest.payload['response']), answer)
                member, = retained.manifest.payload['members']
                self.assertTrue(member['cut'])
                self.assertEqual(blob(retained, member['source']), file.chunks[0].source)
                self.assertEqual(blob(retained, member['sent']), result.request.sent_texts[0])
                self.assertEqual(retained.manifest.payload['command'], command)
                self.assertEqual(self.searchable_counts(connection), counts)
                self.assertEqual(connection.execute('SELECT invocation FROM public.mycel_evidence_owners WHERE id=%s',
                    (result.evidence.owner_id,)).fetchone(), (invocation.id,))
# TEST-TIER-END tests/test_summary_evidence.py::SummaryEvidenceStoreTests.test_real_generation_caller_retains_exact_stdin_cut_source_and_stdout_with_live_private_lease
