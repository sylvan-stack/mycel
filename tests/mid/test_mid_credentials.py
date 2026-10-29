"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_credentials as _support
from test_credentials import (ADDRESS ,Credentials ,InvocationPolicy ,MycelError ,Path ,SENTINEL ,Secret ,io ,json ,os ,patch ,subprocess ,sys ,time)


class CredentialsTests(_support.CredentialsTests):


# TEST-TIER-BEGIN tests/test_credentials.py::CredentialsTests.test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell
    def test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell(self):
        marker = self.root / "shell-was-started"
        body = ("import json,os,sys\n"
                "print(json.dumps({'argv':sys.argv[1:],'input':sys.stdin.read(),"
                "'leaked':[k for k in ['MYCEL_PG_DSN','MYCEL_STORE_PASSWORD','PGPASSWORD',"
                "'VOYAGE_API_KEY','JEV_API_KEY','AWS_SESSION_TOKEN','MYCEL_CONFIG'] if k in os.environ]}))\n"
                "sys.stderr.write('" + SENTINEL + "')\n")
        executable = self.script(body)
        args = ["$(touch " + str(marker) + ")", "~literal", "value\nline", "", "; exit 5"]
        snapshot = self.settings("[embedding]\nkey_command = " + json.dumps([str(executable), *args]) + "\n")
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {
            "MYCEL_PG_DSN": ADDRESS, "MYCEL_STORE_PASSWORD": SENTINEL,
            "PGPASSWORD": SENTINEL, "VOYAGE_API_KEY": SENTINEL,
            "JEV_API_KEY": SENTINEL, "AWS_SESSION_TOKEN": SENTINEL,
        }), patch("sys.stdout", out), patch("sys.stderr", err), \
                patch("mycel._safeguards.subprocess.Popen", wraps=subprocess.Popen) as spawn:
            value = Credentials(snapshot, InvocationPolicy("embed"), home=self.root).require_embedding_key()
        self.assertEqual(json.loads(value.reveal()), {"argv": args, "input": "", "leaked": []})
        self.assertFalse(marker.exists())
        self.assertEqual(out.getvalue() + err.getvalue(), "")
        self.assertFalse(spawn.call_args.kwargs["shell"])
        self.assertTrue(spawn.call_args.kwargs["close_fds"])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertNotIn(ADDRESS, json.dumps(spawn.call_args.kwargs["env"]))
        self.assertNotIn(SENTINEL, json.dumps(spawn.call_args.kwargs["env"]))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["config.toml", "credential-command"])
# TEST-TIER-END tests/test_credentials.py::CredentialsTests.test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell


# TEST-TIER-BEGIN tests/test_credentials.py::CredentialsTests.test_credential_command_deadline_and_output_limits_are_private_failures
    def test_credential_command_deadline_and_output_limits_are_private_failures(self):
        programs = (
            "import time\ntime.sleep(10)\n",
            "import sys\nsys.stdout.write('" + SENTINEL + "' * 10000)\n",
            "import sys\nsys.stderr.write('" + SENTINEL + "' * 1000)\n",
        )
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            for body in programs:
                executable = self.script(body)
                snapshot = self.settings("[embedding]\nkey_command = " + json.dumps([str(executable)]) + "\n")
                with self.subTest(program=programs.index(body)), self.assertRaises(MycelError) as error:
                    Credentials(snapshot, InvocationPolicy("embed"), timeout_seconds=0.3).require_embedding_key()
                self.assertEqual(error.exception.code, "refused")
                self.assertNotIn(SENTINEL, error.exception.message)
        self.assertEqual(out.getvalue() + err.getvalue(), "")
# TEST-TIER-END tests/test_credentials.py::CredentialsTests.test_credential_command_deadline_and_output_limits_are_private_failures


# TEST-TIER-BEGIN tests/test_credentials.py::CredentialsTests.test_plain_grep_receives_neither_store_target_nor_parent_credentials
    def test_plain_grep_receives_neither_store_target_nor_parent_credentials(self):
        grep = self.root / "grep"
        grep.write_text("#!" + sys.executable + "\nimport json,os\nprint(json.dumps(dict(os.environ)))\n")
        grep.chmod(0o700)
        self.settings()
        source = Path(_support.__file__).resolve().parents[1] / "src"
        parent = {"PATH": str(self.root), "HOME": str(self.root), "MYCEL_CONFIG": str(self.config),
                  "MYCEL_GREP_PLAIN": "1", "PYTHONPATH": str(source), "LC_ALL": "C",
                  "MYCEL_PG_DSN": ADDRESS, "DATABASE_URL": ADDRESS,
                  "MYCEL_STORE_PASSWORD": SENTINEL, "PGPASSWORD": SENTINEL,
                  "VOYAGE_API_KEY": SENTINEL, "JEV_API_KEY": SENTINEL}
        result = subprocess.run([sys.executable, "-m", "mycel", "grep", "literal"],
                                env=parent, cwd=self.root, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(SENTINEL.encode(), result.stdout + result.stderr)
        self.assertNotIn(ADDRESS.encode(), result.stdout + result.stderr)
        self.assertFalse(set(parent).difference({"PATH", "HOME", "LC_ALL"}).intersection(json.loads(result.stdout)))
# TEST-TIER-END tests/test_credentials.py::CredentialsTests.test_plain_grep_receives_neither_store_target_nor_parent_credentials


class ApiKeyTests(_support.ApiKeyTests):


# TEST-TIER-BEGIN tests/test_credentials.py::ApiKeyTests.test_hidden_input_in_real_pseudoterminal_and_echo_restoration
    def test_hidden_input_in_real_pseudoterminal_and_echo_restoration(self):
        import errno
        import hashlib
        import pty
        import select
        import signal
        import termios
        import uuid
        script = ("import hashlib,json,termios\n"
                  "from mycel._credentials import prompt_api_key\n"
                  "try:\n"
                  " value=prompt_api_key('voyage')\n"
                  " print(json.dumps({'hash':hashlib.sha256(value.reveal().encode()).hexdigest()}),flush=True)\n"
                  "except KeyboardInterrupt:\n"
                  " print('interrupted',flush=True)\n"
                  "with open('/dev/tty') as tty:\n"
                  " print('echo-restored='+str(bool(termios.tcgetattr(tty)[3]&termios.ECHO)),flush=True)\n")
        for interrupt in (False, True):
            master, slave = pty.openpty()
            def controlling_terminal():
                import fcntl
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            env = {"PATH": os.defpath, "PYTHONPATH": str(Path(_support.__file__).resolve().parents[1] / "src"),
                   "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(self.root)}
            process = subprocess.Popen([sys.executable, "-c", script], stdin=slave, stdout=slave, stderr=slave,
                preexec_fn=controlling_terminal, env=env)
            os.close(slave)
            output = bytearray()
            def collect_until(needle):
                deadline = time.monotonic() + 10
                while needle not in output:
                    if time.monotonic() >= deadline:
                        self.fail("API key terminal probe timed out")
                    ready, _, _ = select.select([master], [], [], .1)
                    if ready:
                        try:
                            block = os.read(master, 65536)
                        except OSError as error:
                            if error.errno == errno.EIO:
                                break
                            raise
                        if not block:
                            break
                        output.extend(block)
            try:
                collect_until(b"API key: ")
                self.assertIn(b"API key: ", output)
                self.assertFalse(termios.tcgetattr(master)[3] & termios.ECHO)
                value = ("public-probe-" + uuid.uuid4().hex).encode()
                if interrupt:
                    process.send_signal(signal.SIGINT)
                else:
                    os.write(master, value + b"\n")
                collect_until(b"echo-restored=True")
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertIn(b"echo-restored=True", output)
                self.assertNotIn(value, output)
                if interrupt:
                    self.assertIn(b"interrupted", output)
                else:
                    self.assertIn(hashlib.sha256(value).hexdigest().encode(), output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
# TEST-TIER-END tests/test_credentials.py::ApiKeyTests.test_hidden_input_in_real_pseudoterminal_and_echo_restoration

# TEST-TIER-BEGIN tests/test_credentials.py::ApiKeyTests.test_real_pipe_child_never_receives_key_in_argv_environment_or_files
    def test_real_pipe_child_never_receives_key_in_argv_environment_or_files(self):
        import uuid
        from mycel._credentials import store_api_key
        value = "public-pipe-" + uuid.uuid4().hex
        executable = self.root / "security-stand-in"
        executable.write_text("#!" + sys.executable + "\nimport sys\nrequest=sys.stdin.buffer.read()\n"
                              "sys.stdout.buffer.write(request)\nsys.stderr.buffer.write(request)\n")
        executable.chmod(0o700)
        out, err = io.StringIO(), io.StringIO()
        before = set(self.root.rglob("*"))
        with patch("mycel._credentials.SECURITY", str(executable)), \
                patch("mycel._safeguards.subprocess.Popen", wraps=subprocess.Popen) as spawn, \
                patch("sys.stdout", out), patch("sys.stderr", err):
            result = store_api_key("jev", Secret(value), home=self.root)
        self.assertFalse(result["replaced"])
        self.assertEqual(spawn.call_count, 1)
        argv = spawn.call_args.args[0]
        options = spawn.call_args.kwargs
        for representation in (repr(argv), repr(options["env"]), out.getvalue() + err.getvalue()):
            self.assertNotIn(value, representation)
            self.assertNotIn(value.encode().hex(), representation)
        self.assertFalse(options["shell"])
        self.assertTrue(options["close_fds"])
        self.assertTrue(options["start_new_session"])
        self.assertFalse(Path(options["cwd"]).exists())
        self.assertEqual(set(self.root.rglob("*")), before)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(value.encode(), path.read_bytes())
                self.assertNotIn(value.encode().hex().encode(), path.read_bytes())
# TEST-TIER-END tests/test_credentials.py::ApiKeyTests.test_real_pipe_child_never_receives_key_in_argv_environment_or_files
