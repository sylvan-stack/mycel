# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Summary command acceptance using real local executable fixtures."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mycel import _summary_writer as writer_module


def _process_running(identifier):
    """Observe a PID without macOS's setuid ps executable."""
    try:
        os.kill(identifier, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Denied observation never supplies evidence of termination.
        return True
    try:
        state = (Path("/proc") / str(identifier) / "stat").read_text()
    except (FileNotFoundError, PermissionError):
        # macOS has no /proc; launchd reaps its orphan children. Poll kill(0)
        # until the PID disappears rather than guessing from a denied read.
        return True
    # A Linux zombie cannot continue a request. The direct child must still
    # have been reaped by the writer, checked separately below.
    fields = state.rsplit(")", 1)[-1].split()
    return not fields or fields[0] != "Z"


class SummaryWriterTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sequence = 0

    def command(self, source, *arguments):
        self.sequence += 1
        executable = self.root / f"writer-{self.sequence}.py"
        executable.write_text(textwrap.dedent(source), encoding="utf-8")
        return (sys.executable, str(executable), *arguments)


    def tree_command(self, behaviour):
        trace_directory = self.root / "processes"
        trace_directory.mkdir(exist_ok=True)
        command = self.command(f"""
            import json, os, pathlib, signal, subprocess, sys, time
            sys.stdin.buffer.read()
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            path = pathlib.Path(sys.argv[1]) / ('pid-' + str(os.getpid()))
            path.write_text(json.dumps({{'leader': os.getpid(), 'child': child.pid,
                                        'cwd': os.getcwd()}}))
            {behaviour}
            time.sleep(60)
        """, str(trace_directory))
        return command, trace_directory

    def assert_tree_terminated(self, trace_directory, processes):
        # A real live negative control prevents the observer from granting a
        # false cleanup proof by reporting every PID as already terminated.
        control = subprocess.Popen((sys.executable, "-I", "-B", "-c", "import time; time.sleep(60)"),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(_process_running(control.pid))
        finally:
            control.kill()
            control.wait()
        self.assertFalse(_process_running(control.pid))
        traces = [json.loads(path.read_text()) for path in trace_directory.glob("pid-*")]
        self.assertEqual(len(traces), len(processes))
        for process, trace in zip(sorted(processes, key=lambda item: item.pid),
                                  sorted(traces, key=lambda item: item["leader"])):
            self.assertEqual(trace["leader"], process.pid)
            self.assertIsNotNone(process.returncode)
            self.assertFalse(Path(trace["cwd"]).exists())
            deadline = time.monotonic() + 2
            while _process_running(trace["child"]):
                if time.monotonic() >= deadline:
                    self.fail("summary command descendant survived termination")
                time.sleep(0.01)

    def record_processes(self, processes):
        start = subprocess.Popen
        def record(*args, **kwargs):
            process = start(*args, **kwargs)
            processes.append(process)
            return process
        return patch.object(writer_module.subprocess, "Popen", side_effect=record)



# Archived complete imports; restore needed names in their original scope, not at this file tail.
