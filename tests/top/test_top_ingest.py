"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_ingest as _support


class IngestStepStoreTests(_support.IngestStepStoreTests):
    def test_a_series_completes_while_a_file_changes_before_every_step(self):
        # SYL-289 run 3: other agents edited the corpus between all steps, and
        # each step that wrote their file started the refresh again (SYL-315).
        busy = self.base.artifact / 'busy.md'
        busy.write_bytes(b'# Busy\nEdit 0.\n')
        for number in range(6):
            (self.base.artifact / f'note{number}.md').write_bytes(b'# Note\nFirst.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        replies = []
        while not replies or not replies[-1]['complete']:
            busy.write_bytes(f'# Busy\nEdit {len(replies) + 1}.\n'.encode())
            status, reply = self.invoke('--repo', 'fixture', '--files', '3')
            self.assertEqual(status, 0, reply)
            fixture = reply['repositories']['fixture']
            self.assertEqual(fixture['files']['changed'], 1)
            replies.append(fixture)
            # One written file leaves a share of two unchanged files a step.
            self.assertLessEqual(len(replies), replies[0]['remaining']['refresh'] // 2 + 2,
                                 [reply['remaining'] for reply in replies])

    def test_a_refreshed_file_resting_on_a_written_file_is_refreshed_again(self):
        # The refresh has passed a.md when target.md gains the section a.md
        # names; the step that writes target.md refreshes a.md again (SYL-315).
        (self.base.artifact / 'a.md').write_bytes(
            b'# A\nRests on target.\n\n<!-- sources:\nfixture:@artifact/target.md#Added\n-->\n')
        target = self.base.artifact / 'target.md'
        target.write_bytes(b'# Target\nText.\n')
        for number in range(3):
            (self.base.artifact / f'note{number}.md').write_bytes(b'# Note\nFirst.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)

        def resolved():
            with self.base.connect() as connection:
                return connection.execute("""SELECT count(*) FROM public.mycel_dependencies d
                    JOIN public.mycel_edges e ON e.dependency=d.id
                    JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version
                    JOIN public.mycel_file_locations fl ON fl.id=l.file_location AND fl.kind='disk'
                    WHERE fl.metadata->>'path'='a.md'""").fetchone()[0]
        self.assertEqual(resolved(), 0)
        (self.base.artifact / 'note0.md').write_bytes(b'# Note\nSecond.\n')
        status, reply = self.invoke('--repo', 'fixture', '--files', '3')
        self.assertEqual(status, 0, reply)
        through = self.progress()[0]['refreshedThrough']
        self.assertEqual(through[0], 'disk')
        self.assertGreater(through[2], 'a.md')
        target.write_bytes(b'# Target\nText.\n\n## Added\nNow named.\n')
        status, reply = self.invoke('--repo', 'fixture', '--files', '3')
        self.assertEqual((status, reply['repositories']['fixture']['files']['changed']), (0, 1), reply)
        self.assertEqual(resolved(), 1)
        self.assertGreater(self.progress()[0]['refreshedThrough'], through)
        while not reply['repositories']['fixture']['complete']:
            status, reply = self.invoke('--repo', 'fixture', '--files', '3')
            self.assertEqual(status, 0, reply)

        # A whole pass over the same files finds nothing left to apply.
        def rows():
            with self.base.connect() as connection:
                return {table: connection.execute(
                            f'SELECT to_jsonb(t)::text FROM public.{table} t ORDER BY 1').fetchall()
                        for table in ('mycel_dependencies', 'mycel_edges', 'mycel_relations', 'mycel_stale_reasons')}
        series = rows()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        self.assertEqual(rows(), series)
