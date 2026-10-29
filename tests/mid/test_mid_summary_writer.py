"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_summary_writer as _support
from test_summary_writer import (Future ,SummaryWriter ,patch ,time)


class SummaryWriterTests(_support.SummaryWriterTests):


# TEST-TIER-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_batch_interruption_terminates_all_running_requests_and_cancels_pending
    def test_batch_interruption_terminates_all_running_requests_and_cancels_pending(self):
        command, trace_directory = self.tree_command("pass")
        def interrupt(future, *args, **kwargs):
            deadline = time.monotonic() + 2
            while len(tuple(trace_directory.glob("pid-*"))) < 2:
                if time.monotonic() >= deadline:
                    self.fail("parallel summary fixtures did not start")
                time.sleep(0.01)
            raise KeyboardInterrupt()
        processes = []
        with self.record_processes(processes), patch.object(Future, "result", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                SummaryWriter(command, 2).write_many((b"one", b"two", b"three"))
        self.assertEqual(len(processes), 2)
        self.assert_tree_terminated(trace_directory, processes)
# TEST-TIER-END tests/test_summary_writer.py::SummaryWriterTests.test_batch_interruption_terminates_all_running_requests_and_cancels_pending
