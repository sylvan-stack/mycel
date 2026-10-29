"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_cli as _support
from test_cli import (
    CliTests,
    ErrorCode,
    Invocation,
    MycelError,
    Path,
    Result,
    SOURCE,
    StreamedResult,
    io,
    json,
    os,
    parse,
    run,
    signal,
    subprocess,
    sys,
    tempfile,
    unittest,
)


class CliTests(_support.CliTests):
# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_clean_environment_finite_help_and_refusal
    def test_clean_environment_finite_help_and_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"HOME": folder, "PATH": os.defpath, "PYTHONPATH": str(SOURCE),
                   "PYTHONDONTWRITEBYTECODE": "1", "MYCEL_CONFIG": str(Path(folder) / "absent.toml")}
            for args, expected in ((["--help"], 0), (["search", "--repo", "fictional", "question"], 1)):
                result = subprocess.run([sys.executable, "-m", "mycel", *args], env=env,
                                        cwd=folder, capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, expected)
                reply = json.loads(result.stdout)
                self.assertIsInstance(reply, dict)
                if expected:
                    self.assertEqual(reply["error"]["code"], "settings")
            self.assertEqual(list(Path(folder).iterdir()), [])
# TEST-TIER-END tests/test_cli.py::CliTests.test_clean_environment_finite_help_and_refusal

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_invalid_arguments_have_one_closed_error
    def test_invalid_arguments_have_one_closed_error(self):
        for args in (["unknown"], ["search", "--repo"], ["search", "--api-key", "secret-sentinel"],
                     ["search", "--rep", "demo"], ["ingest", "--repo", "demo", "--all"],
                     ["search", "--repo", ""], ["search", "-v", "a1"], ["-v"]):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(run(args, stdout=out, stderr=err), 1)
            reply = json.loads(out.getvalue())
            self.assertEqual(set(reply), {"error"})
            self.assertEqual(reply["error"]["code"], "invalid_input")
            self.assertNotIn("secret-sentinel", out.getvalue() + err.getvalue())
# TEST-TIER-END tests/test_cli.py::CliTests.test_invalid_arguments_have_one_closed_error

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_errors_are_closed_and_internal_details_are_private
    def test_errors_are_closed_and_internal_details_are_private(self):
        with self.assertRaises(ValueError):
            MycelError("not_found", "unknown")
        for code in ErrorCode:
            def fail(invocation):
                raise MycelError(code, "A safe failure.")
            out = io.StringIO()
            self.assertEqual(run(["info"], handlers={"info": fail}, stdout=out), 1)
            self.assertEqual(json.loads(out.getvalue())["error"]["code"], code.value)
        def broken(invocation):
            raise RuntimeError("credential-sentinel")
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(run(["info"], handlers={"info": broken}, stdout=out, stderr=err), 1)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "internal")
        self.assertNotIn("credential-sentinel", out.getvalue() + err.getvalue())
# TEST-TIER-END tests/test_cli.py::CliTests.test_errors_are_closed_and_internal_details_are_private

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_caller_signals_produce_status_two
    def test_caller_signals_produce_status_two(self):
        script = """import sys,time\nfrom mycel._cli import run\ndef wait(invocation):\n print('ready',file=sys.stderr,flush=True)\n time.sleep(100)\nfrom mycel._cli import _stop\nimport signal\nsignal.signal(signal.SIGTERM,_stop)\nsys.exit(run(['info'],handlers={'info':wait}))\n"""
        for sig in (signal.SIGINT, signal.SIGTERM):
            env = {"PATH": os.defpath, "PYTHONPATH": str(SOURCE), "PYTHONDONTWRITEBYTECODE": "1"}
            process = subprocess.Popen([sys.executable, "-c", script], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stderr.readline().strip(), "ready")
                process.send_signal(sig)
                out, err = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(json.loads(out)["error"]["code"], "refused")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
# TEST-TIER-END tests/test_cli.py::CliTests.test_caller_signals_produce_status_two

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_invalid_reply_cannot_emit_partial_json
    def test_invalid_reply_cannot_emit_partial_json(self):
        out, err = io.StringIO(), io.StringIO()
        status = run(["info"], handlers={"info": lambda _: Result({"invalid": float("nan")})},
                     stdout=out, stderr=err)
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "internal")
# TEST-TIER-END tests/test_cli.py::CliTests.test_invalid_reply_cannot_emit_partial_json

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_json_is_portable_to_ascii_output_and_closed_receiver
    def test_json_is_portable_to_ascii_output_and_closed_receiver(self):
        buffer = io.BytesIO()
        out = io.TextIOWrapper(buffer, encoding="ascii")
        self.assertEqual(run(["info"], handlers={"info": lambda _: Result({"text": "é葉"})},
                             stdout=out), 0)
        self.assertEqual(json.loads(buffer.getvalue()), {"text": "é葉"})
        class ClosedReceiver:
            def write(self, value):
                raise BrokenPipeError
        diagnostics = io.StringIO()
        self.assertEqual(run(["--help"], stdout=ClosedReceiver(), stderr=diagnostics), 1)
        self.assertIn("could not be written", diagnostics.getvalue())
# TEST-TIER-END tests/test_cli.py::CliTests.test_json_is_portable_to_ascii_output_and_closed_receiver

# TEST-TIER-BEGIN tests/test_cli.py::CliTests.test_grep_boundary_preserves_arguments_and_stream_status
    def test_grep_boundary_preserves_arguments_and_stream_status(self):
        args = ("--help", "--repo", "literal", "-v", "a2", "--", "pattern")
        self.assertEqual(parse(["grep", *args]), Invocation("grep", arguments=args, raw=True))
        def grep(invocation):
            self.assertEqual(invocation.arguments, args)
            return StreamedResult(7)
        out = io.StringIO()
        self.assertEqual(run(["grep", *args], handlers={"grep": grep}, stdout=out), 7)
        self.assertEqual(out.getvalue(), "")
        out = io.StringIO()
        self.assertEqual(run(["info"], handlers={"info": lambda _: StreamedResult(0)}, stdout=out), 1)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "internal")
# TEST-TIER-END tests/test_cli.py::CliTests.test_grep_boundary_preserves_arguments_and_stream_status
