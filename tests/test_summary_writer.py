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

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_literal_arguments_complete_stdin_empty_cwd_and_exact_utf8_output
#     def test_literal_arguments_complete_stdin_empty_cwd_and_exact_utf8_output(self):
#         marker = self.root / "shell-expanded"
#         arguments = (f"$(touch {marker})", "a b", "*; $HOME", "")
#         command = self.command("""
#             import json, os, sys
#             request = sys.stdin.buffer.read()
#             result = {'argv': sys.argv[1:], 'request': list(request),
#                       'cwd': os.getcwd(), 'files': os.listdir('.')}
#             sys.stdout.buffer.write((' 雪\\n' + json.dumps(result)).encode('utf-8'))
#         """, *arguments)
#         request = ("complete request 😀 雪\\n".encode() + b"\0") * 4000
#         result = SummaryWriter(command, 1).write(request)
#         self.assertIsInstance(result, WriterResult)
#         self.assertIsNone(result.reason)
#         self.assertEqual(result.attempts, 1)
#         self.assertTrue(result.response.startswith(" 雪\n".encode()))
#         response = json.loads(result.response.decode().split("\n", 1)[1])
#         self.assertEqual(response["argv"], list(arguments))
#         self.assertEqual(bytes(response["request"]), request)
#         self.assertEqual(response["files"], [])
#         self.assertFalse(Path(response["cwd"]).exists())
#         self.assertFalse(marker.exists())
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_literal_arguments_complete_stdin_empty_cwd_and_exact_utf8_output

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_retry_uses_the_same_request_and_a_new_empty_directory
#     def test_retry_uses_the_same_request_and_a_new_empty_directory(self):
#         trace = self.root / "trace.jsonl"
#         command = self.command("""
#             import json, os, pathlib, sys
#             trace = pathlib.Path(sys.argv[1])
#             previous = trace.read_text().splitlines() if trace.exists() else []
#             request = sys.stdin.buffer.read()
#             with trace.open('a') as stream:
#                 stream.write(json.dumps({'cwd': os.getcwd(), 'files': os.listdir('.'),
#                                          'request': list(request)}) + '\\n')
#             pathlib.Path('attempt-local').write_text('fixture')
#             if not previous:
#                 sys.stderr.write('public-fixture-secret')
#                 sys.exit(9)
#             sys.stdout.buffer.write(b'  summary \\n')
#         """, str(trace))
#         request = b"full exact request\0with bytes\n"
#         result = SummaryWriter(command, 1).write(request)
#         self.assertEqual(result, WriterResult(b"  summary \n", None, 2))
#         attempts = [json.loads(line) for line in trace.read_text().splitlines()]
#         self.assertEqual(len(attempts), 2)
#         self.assertNotEqual(attempts[0]["cwd"], attempts[1]["cwd"])
#         for attempt in attempts:
#             self.assertEqual(attempt["files"], [])
#             self.assertEqual(bytes(attempt["request"]), request)
#             self.assertFalse(Path(attempt["cwd"]).exists())
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_retry_uses_the_same_request_and_a_new_empty_directory

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_user_path_resolves_executable_without_forwarding_private_environment
#     def test_user_path_resolves_executable_without_forwarding_private_environment(self):
#         bin_directory = self.root / "bin"
#         bin_directory.mkdir()
#         executable = bin_directory / "fixture-summary-command"
#         executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent("""
#             import json, os, sys
#             sys.stdin.buffer.read()
#             print(json.dumps({'environment': dict(os.environ), 'cwd': os.getcwd(),
#                               'executable': sys.argv[0], 'argv': sys.argv[1:]}))
#         """))
#         executable.chmod(0o700)
#         literal = ("fixture-summary-command", "literal $HOME")
#         writer = SummaryWriter(literal, 1)
#         with patch.dict(os.environ, {
#                 "PATH": str(bin_directory), "MYCEL_CONFIG": "public-fixture-private-setting",
#                 "VOYAGE_API_KEY": "public-fixture-private-key",
#                 "CUSTOM_PROVIDER_SECRET": "public-fixture-private-provider-key"}):
#             result = writer.write(b"request")
#         self.assertIsNone(result.reason)
#         response = json.loads(result.response)
#         environment = response["environment"]
#         self.assertEqual(environment["PATH"], SYSTEM_PATH)
#         self.assertEqual(environment["HOME"], str(Path.home().resolve()))
#         self.assertEqual(environment["TMPDIR"], response["cwd"])
#         # macOS itself supplies __CF_USER_TEXT_ENCODING to a new process.
#         self.assertTrue(set(environment).issubset({"HOME", "PATH", "LANG", "LC_ALL", "TMPDIR",
#                                                    "__CF_USER_TEXT_ENCODING"}))
#         self.assertEqual(response["executable"], str(executable.resolve()))
#         self.assertEqual(response["argv"], list(literal[1:]))
#         self.assertEqual(writer.command, literal)
#         self.assertNotIn("public-fixture-private", result.response.decode())
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_user_path_resolves_executable_without_forwarding_private_environment

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_failure_reasons_are_fixed_redacted_and_get_exactly_one_retry
#     def test_failure_reasons_are_fixed_redacted_and_get_exactly_one_retry(self):
#         cases = {
#             "nonzero_exit": "sys.stderr.write('public-fixture-secret'); sys.exit(5)",
#             "invalid_utf8": "sys.stdout.buffer.write(b'\\xff')",
#             "empty_response": "sys.stdout.buffer.write(' \\t\\n\\u2003'.encode())",
#             "stdout_limit": f"sys.stdout.buffer.write(b'x' * {MAX_STDOUT_BYTES + 1})",
#             "stderr_limit": f"sys.stderr.buffer.write(b'x' * {MAX_STDERR_BYTES + 1}); print('summary')",
#         }
#         for reason, behaviour in cases.items():
#             with self.subTest(reason=reason):
#                 trace = self.root / (reason + ".count")
#                 command = self.command(f"""
#                     import pathlib, sys
#                     sys.stdin.buffer.read()
#                     with pathlib.Path(sys.argv[1]).open('a') as stream:
#                         stream.write('attempt\\n')
#                     {behaviour}
#                 """, str(trace))
#                 result = SummaryWriter(command, 1).write(b"request")
#                 self.assertEqual(result, WriterResult(None, reason, 2))
#                 self.assertEqual(trace.read_text().splitlines(), ["attempt", "attempt"])
#                 self.assertNotIn("public-fixture-secret", repr(result))
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_failure_reasons_are_fixed_redacted_and_get_exactly_one_retry

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_exact_byte_limits_succeed_and_missing_executable_has_safe_reason
#     def test_exact_byte_limits_succeed_and_missing_executable_has_safe_reason(self):
#         command = self.command(f"""
#             import sys
#             sys.stdin.buffer.read()
#             sys.stderr.buffer.write(b'x' * {MAX_STDERR_BYTES})
#             sys.stdout.buffer.write(b'y' * {MAX_STDOUT_BYTES})
#         """)
#         self.assertEqual(SummaryWriter(command, 1).write(b"request"),
#                          WriterResult(b"y" * MAX_STDOUT_BYTES, None, 1))
#         missing = SummaryWriter((str(self.root / "missing-public-fixture-secret"),), 1)
#         self.assertEqual(missing.write(b"request"), WriterResult(None, "start_failed", 2))
#         self.assertNotIn("public-fixture-secret", repr(missing.write(b"request")))
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_exact_byte_limits_succeed_and_missing_executable_has_safe_reason

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_parallel_and_direct_calls_share_limit_and_preserve_request_order
#     def test_parallel_and_direct_calls_share_limit_and_preserve_request_order(self):
#         counts = self.root / "counts.json"
#         counts.write_text(json.dumps({"active": 0, "peak": 0, "calls": 0}))
#         command = self.command("""
#             import fcntl, json, pathlib, sys, time
#             path = pathlib.Path(sys.argv[1])
#             request = sys.stdin.buffer.read()
#             def update(delta):
#                 with path.open('r+') as stream:
#                     fcntl.flock(stream, fcntl.LOCK_EX)
#                     state = json.load(stream)
#                     state['active'] += delta
#                     state['peak'] = max(state['peak'], state['active'])
#                     state['calls'] += int(delta > 0)
#                     stream.seek(0)
#                     json.dump(state, stream)
#                     stream.truncate()
#             update(1)
#             time.sleep(0.08)
#             update(-1)
#             sys.stdout.buffer.write(b'summary ' + request)
#         """, str(counts))
#         writer = SummaryWriter(command, 2)
#         requests = tuple(str(index).encode() for index in range(7))
#         with ThreadPoolExecutor(max_workers=2) as caller:
#             batch = caller.submit(writer.write_many, requests)
#             direct = caller.submit(writer.write, b"direct")
#             results = batch.result()
#             direct_result = direct.result()
#         self.assertEqual(results, tuple(WriterResult(b"summary " + request, None, 1)
#                                         for request in requests))
#         self.assertEqual(direct_result, WriterResult(b"summary direct", None, 1))
#         self.assertEqual(json.loads(counts.read_text()), {"active": 0, "peak": 2, "calls": 8})
#         self.assertEqual(writer.write_many(()), ())
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_parallel_and_direct_calls_share_limit_and_preserve_request_order

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

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_deadline_and_overflow_kill_process_group_and_reap_each_attempt
#     def test_deadline_and_overflow_kill_process_group_and_reap_each_attempt(self):
#         self.assertEqual(WRITER_TIMEOUT_SECONDS, 300)
#         for reason, behaviour in (
#                 ("timeout", "pass"),
#                 ("stdout_limit", f"os.write(1, b'x' * {MAX_STDOUT_BYTES + 1})"),
#                 ("stderr_limit", f"os.write(2, b'x' * {MAX_STDERR_BYTES + 1})")):
#             with self.subTest(reason=reason):
#                 command, trace_directory = self.tree_command(behaviour)
#                 for path in trace_directory.glob("pid-*"):
#                     path.unlink()
#                 processes = []
#                 with self.record_processes(processes):
#                     result = SummaryWriter(command, 1, _timeout=0.2).write(b"request")
#                 self.assertEqual(result, WriterResult(None, reason, 2))
#                 self.assertEqual(len(processes), 2)
#                 self.assert_tree_terminated(trace_directory, processes)
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_deadline_and_overflow_kill_process_group_and_reap_each_attempt

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_direct_interruption_cleans_up_and_does_not_retry
#     def test_direct_interruption_cleans_up_and_does_not_retry(self):
#         command, trace_directory = self.tree_command("pass")
#         check = writer_module._check_stopped
#         def interrupt(stopped):
#             check(stopped)
#             if any(trace_directory.glob("pid-*")):
#                 raise KeyboardInterrupt()
#         processes = []
#         with self.record_processes(processes), patch.object(writer_module, "_check_stopped", interrupt):
#             with self.assertRaises(KeyboardInterrupt):
#                 SummaryWriter(command, 1).write(b"request")
#         self.assertEqual(len(processes), 1)
#         self.assert_tree_terminated(trace_directory, processes)
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_direct_interruption_cleans_up_and_does_not_retry

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_success_also_terminates_background_descendants
#     def test_success_also_terminates_background_descendants(self):
#         trace_directory = self.root / "processes"
#         trace_directory.mkdir()
#         command = self.command("""
#             import json, os, pathlib, subprocess, sys
#             sys.stdin.buffer.read()
#             child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
#                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
#                                      stderr=subprocess.DEVNULL)
#             path = pathlib.Path(sys.argv[1]) / ('pid-' + str(os.getpid()))
#             path.write_text(json.dumps({'leader': os.getpid(), 'child': child.pid,
#                                         'cwd': os.getcwd()}))
#             print('summary')
#         """, str(trace_directory))
#         processes = []
#         with self.record_processes(processes):
#             result = SummaryWriter(command, 1).write(b"request")
#         self.assertEqual(result, WriterResult(b"summary\n", None, 1))
#         self.assertEqual(len(processes), 1)
#         self.assertEqual(processes[0].returncode, 0)
#         self.assert_tree_terminated(trace_directory, processes)
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_success_also_terminates_background_descendants

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_selector_setup_failure_or_interruption_reaps_already_started_process
#     def test_selector_setup_failure_or_interruption_reaps_already_started_process(self):
#         command = self.command("import time; time.sleep(60)")
#         for error, attempts in ((OSError("public-fixture-secret"), 2), (KeyboardInterrupt(), 1)):
#             with self.subTest(error=type(error).__name__):
#                 processes = []
#                 with self.record_processes(processes), patch.object(
#                         writer_module.selectors, "DefaultSelector", side_effect=error):
#                     if isinstance(error, KeyboardInterrupt):
#                         with self.assertRaises(KeyboardInterrupt):
#                             SummaryWriter(command, 1).write(b"request")
#                     else:
#                         result = SummaryWriter(command, 1).write(b"request")
#                         self.assertEqual(result, WriterResult(None, "io_failure", 2))
#                         self.assertNotIn("public-fixture-secret", repr(result))
#                 self.assertEqual(len(processes), attempts)
#                 self.assertTrue(all(process.returncode is not None for process in processes))
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_selector_setup_failure_or_interruption_reaps_already_started_process

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_batch_interruption_terminates_all_running_requests_and_cancels_pending
#     def test_batch_interruption_terminates_all_running_requests_and_cancels_pending(self):
#         command, trace_directory = self.tree_command("pass")
#         def interrupt(future, *args, **kwargs):
#             deadline = time.monotonic() + 2
#             while len(tuple(trace_directory.glob("pid-*"))) < 2:
#                 if time.monotonic() >= deadline:
#                     self.fail("parallel summary fixtures did not start")
#                 time.sleep(0.01)
#             raise KeyboardInterrupt()
#         processes = []
#         with self.record_processes(processes), patch.object(Future, "result", interrupt):
#             with self.assertRaises(KeyboardInterrupt):
#                 SummaryWriter(command, 2).write_many((b"one", b"two", b"three"))
#         self.assertEqual(len(processes), 2)
#         self.assert_tree_terminated(trace_directory, processes)
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_batch_interruption_terminates_all_running_requests_and_cancels_pending

# TEST-TIER-DISABLED-BEGIN tests/test_summary_writer.py::SummaryWriterTests.test_settings_and_request_validation_happen_before_any_process_starts
#     def test_settings_and_request_validation_happen_before_any_process_starts(self):
#         bad_commands = ((), [], ("",), ("   ",), ("python", 2), ("python\0bad",))
#         with patch.object(writer_module.subprocess, "Popen") as start:
#             for command in bad_commands:
#                 with self.subTest(command=command), self.assertRaises(MycelError) as raised:
#                     SummaryWriter(command, 1)
#                 self.assertEqual(raised.exception.code, "settings")
#             for count in (0, -1, True, 1.5, "1"):
#                 with self.subTest(count=count), self.assertRaises(MycelError) as raised:
#                     SummaryWriter(("fixture",), count)
#                 self.assertEqual(raised.exception.code, "settings")
#             writer = SummaryWriter(("fixture",), 1)
#             for operation in (lambda: writer.write("request"),
#                               lambda: writer.write_many([b"request"]),
#                               lambda: writer.write_many((b"valid", "invalid"))):
#                 with self.assertRaises(MycelError) as raised:
#                     operation()
#                 self.assertEqual(raised.exception.code, "invalid_input")
#             start.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_summary_writer.py::SummaryWriterTests.test_settings_and_request_validation_happen_before_any_process_starts


if __name__ == "__main__":
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_writer.py:3
# from concurrent.futures import Future, ThreadPoolExecutor
# TEST-TIER-IMPORTS-END tests/test_summary_writer.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_writer.py:15
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_summary_writer.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_writer.py:16
# from mycel._safeguards import SYSTEM_PATH
# TEST-TIER-IMPORTS-END tests/test_summary_writer.py:16
# TEST-TIER-IMPORTS-BEGIN tests/test_summary_writer.py:18
# from mycel._summary_writer import (
#     MAX_STDERR_BYTES, MAX_STDOUT_BYTES, SummaryWriter, WRITER_TIMEOUT_SECONDS, WriterResult,
# )
# TEST-TIER-IMPORTS-END tests/test_summary_writer.py:18
