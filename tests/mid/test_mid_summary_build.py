"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_build as _support
from test_summary_build import (LocalEmbedding ,LocalWriter ,SimpleNamespace ,patch)


class SummaryBuildStoreTests(_support.SummaryBuildStoreTests):


# TEST-TIER-BEGIN tests/test_summary_build.py::SummaryBuildStoreTests.test_generation_embedding_and_interruption_preserve_old_tree_and_release_private_leases
    def test_generation_embedding_and_interruption_preserve_old_tree_and_release_private_leases(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.state(connection)
            for writer, client, expected in ((LocalWriter(failure='nonzero_exit'), LocalEmbedding(), 'failed'),
                    (LocalWriter(), LocalEmbedding(fail=True), 'failed'),
                    (LocalWriter(), LocalEmbedding(cancelled=True), 'interrupted')):
                with self.subTest(expected=expected, embedding=client.fail):
                    result = self.build(connection, writer=writer, client=client)
                    self.assertEqual(result.value['stopped'], expected)
                    self.assertFalse(result.value['replaced'])
                    self.assertEqual(self.state(connection), old)
                    self.no_leases(connection)
# TEST-TIER-END tests/test_summary_build.py::SummaryBuildStoreTests.test_generation_embedding_and_interruption_preserve_old_tree_and_release_private_leases


# TEST-TIER-BEGIN tests/test_summary_build.py::SummaryBuildStoreTests.test_configuration_changed_at_actual_writer_launch_stops_without_child_retry_or_replacement
    def test_configuration_changed_at_actual_writer_launch_stops_without_child_retry_or_replacement(self):
        from mycel._summary_writer import SummaryWriter
        with self.base.connect() as connection:
            self.prepare(connection)
            self.build(connection)
            old = self.state(connection)
            config = self.base.config.read_bytes()
            launches = []

            def writer(command, at_once, *, before_launch):
                def changed_guard():
                    launches.append('guard')
                    self.base.config.write_bytes(config.replace(b'at_once=3', b'at_once=2'))
                    before_launch()
                return SummaryWriter(command, at_once, before_launch=changed_guard)

            with patch('mycel._summary_build.SummaryWriter', side_effect=writer), \
                    patch('mycel._summary_writer.subprocess', SimpleNamespace(
                        PIPE=-1, Popen=lambda *a, **kw: self.fail('obsolete request launched a child'))):
                result = self.build(connection, writer=False)
            self.assertEqual(result.value['stopped'], 'inputs_changed')
            self.assertFalse(result.value['replaced'])
            self.assertEqual(result.value['written'], 0)
            self.assertEqual(launches, ['guard'])
            self.assertEqual(self.state(connection), old)
            self.no_leases(connection)
# TEST-TIER-END tests/test_summary_build.py::SummaryBuildStoreTests.test_configuration_changed_at_actual_writer_launch_stops_without_child_retry_or_replacement
