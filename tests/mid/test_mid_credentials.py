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

# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_store_address_is_only_the_password_free_setting_not_parent_environment
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Store address is only the password free setting not parent environment.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_store_address_is_only_the_password_free_setting_not_parent_environment(self):
#         snapshot = self.settings()
#         with patch.dict(os.environ, {
#             "MYCEL_PG_DSN": "postgresql://other:secret@other/other",
#             "MYCEL_STORE_ADDRESS": "postgresql://other:secret@other/other",
#             "DATABASE_URL": SENTINEL, "PGHOST": SENTINEL, "PGPASSWORD": SENTINEL,
#         }), patch("mycel._credentials.run_child") as child:
#             self.assertEqual(configured_store_address(snapshot), ADDRESS)
#             target = Credentials(snapshot, InvocationPolicy("init")).store_target()
#             self.assertEqual(target.location, ADDRESS)
#             self.assertIsNone(target.password)
#             child.assert_not_called()
#         self.config.write_text("[embedding]\nmodel='voyage-code-4'\n")
#         with patch.dict(os.environ, {"DATABASE_URL": ADDRESS, "MYCEL_PG_DSN": ADDRESS}), \
#                 self.assertRaises(MycelError) as error:
#             configured_store_address(load_settings(path=self.config))
#         self.assertEqual(error.exception.code, "settings")
#         self.assertNotIn(ADDRESS, error.exception.message)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_password_bearing_addresses_are_refused_before_any_acquisition
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Password bearing addresses are refused before any acquisition.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_password_bearing_addresses_are_refused_before_any_acquisition(self):
#         bad_addresses = (
#             "postgresql://fixture:" + SENTINEL + "@localhost/fixture",
#             "postgresql://fixture:@localhost/fixture",
#             "postgresql://fixture@localhost/fixture?password=" + SENTINEL,
#             "postgresql://fixture@localhost/fixture?%70assword=" + SENTINEL,
#             "host=localhost user=fixture password=" + SENTINEL,
#             "postgresql://fixture@localhost/fixture?passfile=/" + SENTINEL,
#             "postgresql://fixture@localhost/fixture?service=" + SENTINEL,
#         )
#         with patch("mycel._credentials.run_child") as child:
#             for address in bad_addresses:
#                 with self.subTest(address_kind=bad_addresses.index(address)):
#                     snapshot = self.settings(address=address)
#                     with self.assertRaises(MycelError) as error:
#                         Credentials(snapshot, InvocationPolicy("init")).store_target(password_requested=True)
#                     self.assertEqual(error.exception.code, "settings")
#                     self.assertNotIn(SENTINEL, json.dumps(error.exception.to_dict()))
#                     self.assertNotIn(SENTINEL, json.dumps(snapshot.report()))
#             child.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_keychain_reads_use_fixed_program_service_accounts_and_login_keychain
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Keychain reads use fixed program service accounts and login keychain.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_keychain_reads_use_fixed_program_service_accounts_and_login_keychain(self):
#         calls = []
#         def child(argv, **kwargs):
#             calls.append((argv, kwargs))
#             return completed()
#         snapshot = self.settings()
#         embedding = Credentials(snapshot, InvocationPolicy("embed"), home=self.root, _runner=child)
#         store = Credentials(snapshot, InvocationPolicy("init"), home=self.root, _runner=child)
#         jev = Credentials(snapshot, InvocationPolicy("classify"), home=self.root, _runner=child)
#         self.assertEqual(calls, [])
#         self.assertEqual(embedding.require_embedding_key().reveal(), "public-key")
#         self.assertEqual(store.store_target(password_requested=True).password.reveal(), "public-key")
#         self.assertEqual(jev.require_jev_key().reveal(), "public-key")
#         login = str(self.root.resolve() / "Library" / "Keychains" / "login.keychain-db")
#         for (argv, kwargs), account in zip(calls, ("voyage-api-key", "store-password", "jev-api-key")):
#             self.assertEqual(argv, (SECURITY, "find-generic-password", "-s", "mycel", "-a", account, "-w", login))
#             self.assertEqual(kwargs["home"], self.root.resolve())
#             self.assertEqual(kwargs["timeout_seconds"], 10.0)
#             self.assertEqual(kwargs["stdout_limit"], CREDENTIAL_STDOUT_LIMIT)
#             self.assertEqual(kwargs["stderr_limit"], CREDENTIAL_STDERR_LIMIT)
#         # No create/update/delete command or ACL rewrite belongs to this reader.
#         self.assertTrue(all("find-generic-password" in argv for argv, _ in calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_output_removes_one_final_line_break_without_trimming_any_other_text
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Output removes one final line break without trimming any other text.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_output_removes_one_final_line_break_without_trimming_any_other_text(self):
#         snapshot = self.settings()
#         for output, expected in (
#             (b"public", "public"), (b" public \n", " public "),
#             (b"public\r\n", "public"), (b"public\r", "public"),
#             (b"public\n\n", "public\n"), (b"\npublic\n", "\npublic"),
#             ("public-\u03bb\n".encode(), "public-\u03bb"),
#         ):
#             with self.subTest(output=output):
#                 credential = Credentials(snapshot, InvocationPolicy("embed"),
#                                          _runner=lambda *args, **kwargs: completed(output))
#                 self.assertEqual(credential.require_embedding_key().reveal(), expected)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_failed_access_has_no_secret_or_fallback_and_has_only_sanitized_faults
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Failed access has no secret or fallback and has only sanitized faults.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_failed_access_has_no_secret_or_fallback_and_has_only_sanitized_faults(self):
#         for result in (
#             completed(SENTINEL.encode(), returncode=1, stderr=SENTINEL.encode()),
#             completed(b"", stderr=SENTINEL.encode()), completed(b"\n"),
#             completed(b"invalid-\xff"), completed(b"private\0value"),
#         ):
#             with self.subTest(result_kind=(result.returncode, len(result.stdout))):
#                 snapshot = self.settings()
#                 credential = Credentials(snapshot, InvocationPolicy("embed"), _runner=lambda *args, **kwargs: result)
#                 with self.assertRaises(MycelError) as error:
#                     credential.require_embedding_key()
#                 self.assertEqual(error.exception.code, "refused")
#                 self.assertNotIn(SENTINEL, str(error.exception))
#                 jev = Credentials(snapshot, InvocationPolicy("classify"), _runner=lambda *args, **kwargs: result)
#                 with self.assertRaises(CredentialUnavailable) as error:
#                     jev.require_jev_key()
#                 self.assertEqual(error.exception.to_dict()["code"], "authentication")
#                 self.assertNotIn(SENTINEL, json.dumps(error.exception.to_dict()))
#                 store = Credentials(snapshot, InvocationPolicy("init"), _runner=lambda *args, **kwargs: result)
#                 self.assertIsNone(store.store_target(password_requested=True).password)
#         executable = self.script("import sys\nprint('" + SENTINEL + "')\nsys.exit(3)\n")
#         snapshot = self.settings("[embedding]\nkey_command = " + json.dumps([str(executable)]) + "\n")
#         with patch("mycel._credentials.Credentials._keychain") as keychain:
#             self.assertIsNone(Credentials(snapshot, InvocationPolicy("embed")).embedding_key())
#             keychain.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_unavailable_programs_do_not_expose_paths_outputs_or_environment_fallbacks
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Unavailable programs do not expose paths outputs or environment fallbacks.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_unavailable_programs_do_not_expose_paths_outputs_or_environment_fallbacks(self):
#         snapshot = self.settings("[embedding]\nkey_command = " + json.dumps([str(self.root / SENTINEL)]) + "\n")
#         with patch.dict(os.environ, {"VOYAGE_API_KEY": SENTINEL}), \
#                 patch("mycel._credentials.Credentials._keychain") as keychain:
#             self.assertIsNone(Credentials(snapshot, InvocationPolicy("embed")).embedding_key())
#             keychain.assert_not_called()
#         snapshot = self.settings()
#         for reason in ("unavailable", "timeout", "stdout_limit", "stderr_limit", "transport"):
#             def fail(*args, **kwargs):
#                 raise ChildProcessFailure(reason)
#             credential = Credentials(snapshot, InvocationPolicy("embed"), _runner=fail)
#             self.assertIsNone(credential.embedding_key())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_reporting_ordinary_commands_and_all_dry_runs_acquire_no_model_credentials
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Reporting ordinary commands and all dry runs acquire no model credentials.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_reporting_ordinary_commands_and_all_dry_runs_acquire_no_model_credentials(self):
#         snapshot = self.settings()
#         commands = ("ingest", "read", "status", "repos", "stale", "refs", "drifts",
#                     "verifications", "overview", "activity", "info", "init", "relate", "confirm")
#         policies = [InvocationPolicy(name) for name in commands]
#         policies += [InvocationPolicy("evaluate", kind="drift"),
#                      InvocationPolicy("evaluate", kind="retrieval", live=True)]
#         with patch("mycel._credentials.run_child") as child, \
#                 patch("mycel._credentials.resolve_command") as resolve:
#             for policy in policies:
#                 credential = Credentials(snapshot, policy)
#                 with self.subTest(policy=policy), self.assertRaises(MycelError):
#                     credential.jev_key()
#             for policy in (
#                 InvocationPolicy("embed", dry_run=True), InvocationPolicy("search", dry_run=True),
#                 InvocationPolicy("ingest", embed=True, dry_run=True),
#                 InvocationPolicy("classify", dry_run=True),
#                 InvocationPolicy("evaluate", kind="drift", live=True, dry_run=True),
#                 InvocationPolicy("summaries", action="build", dry_run=True),
#             ):
#                 credential = Credentials(snapshot, policy)
#                 for method in (credential.embedding_key, credential.jev_key):
#                     with self.subTest(policy=policy, method=method.__name__), self.assertRaises(MycelError):
#                         method()
#             child.assert_not_called()
#             resolve.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_jev_key_requires_explicit_classification_or_live_drift_qualification
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Jev key requires explicit classification or live drift qualification.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_jev_key_requires_explicit_classification_or_live_drift_qualification(self):
#         snapshot = self.settings()
#         with patch("mycel._credentials.run_child", return_value=completed()) as child:
#             for policy in (InvocationPolicy("classify"), InvocationPolicy("evaluate", kind="drift", live=True)):
#                 self.assertEqual(Credentials(snapshot, policy).require_jev_key().reveal(), "public-key")
#             self.assertEqual(child.call_count, 2)
#             for policy in (InvocationPolicy("search"), InvocationPolicy("grep"), InvocationPolicy("ingest", embed=True)):
#                 with self.assertRaises(MycelError):
#                     Credentials(snapshot, policy).require_jev_key()
#             self.assertEqual(child.call_count, 2)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_each_invocation_reads_each_needed_credential_only_once_even_when_access_fails
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Each invocation reads each needed credential only once even when access fails.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_each_invocation_reads_each_needed_credential_only_once_even_when_access_fails(self):
#         snapshot = self.settings()
#         for result in (completed(), completed(returncode=1, stderr=SENTINEL.encode())):
#             with self.subTest(access_succeeded=result.returncode == 0), \
#                     patch("mycel._credentials.run_child", return_value=result) as child:
#                 embedding = Credentials(snapshot, InvocationPolicy("embed"))
#                 first = embedding.embedding_key()
#                 self.assertIs(embedding.embedding_key(), first)
#                 store = Credentials(snapshot, InvocationPolicy("init"))
#                 first = store.store_target(password_requested=True).password
#                 self.assertIs(store.store_target(password_requested=True).password, first)
#                 jev = Credentials(snapshot, InvocationPolicy("classify"))
#                 first = jev.jev_key()
#                 self.assertIs(jev.jev_key(), first)
#                 self.assertEqual(child.call_count, 3)
#                 # The next invocation starts fresh and can see an owner's edit.
#                 Credentials(snapshot, InvocationPolicy("embed")).embedding_key()
#                 self.assertEqual(child.call_count, 4)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_store_challenge_acquisition_shares_the_callers_remaining_deadline
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Store challenge acquisition shares the callers remaining deadline.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_store_challenge_acquisition_shares_the_callers_remaining_deadline(self):
#         calls = []
#         def child(argv, **kwargs):
#             calls.append(kwargs["timeout_seconds"])
#             return completed()
#         for configured, remaining, expected in ((10.0, 0.25, 0.25), (0.3, 2.0, 0.3)):
#             credentials = Credentials(self.settings(), InvocationPolicy("init"),
#                                       timeout_seconds=configured, _runner=child)
#             self.assertIsNone(credentials.store_target(timeout_seconds=remaining).password)
#             self.assertEqual(credentials.store_target(password_requested=True,
#                              timeout_seconds=remaining).password.reveal(), "public-key")
#             self.assertEqual(calls[-1], expected)
#             self.assertEqual(credentials.store_target(password_requested=True,
#                              timeout_seconds=remaining / 2).password.reveal(), "public-key")
#         self.assertEqual(len(calls), 2)
#
#         for remaining in (0.0, -1.0, float("nan"), float("inf")):
#             credentials = Credentials(self.settings(), InvocationPolicy("init"), _runner=child)
#             self.assertIsNone(credentials.store_target(password_requested=True,
#                              timeout_seconds=remaining).password)
#         self.assertEqual(len(calls), 2)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_store_challenge_acquisition_interrupts_and_reaps_its_private_child
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Store challenge acquisition interrupts and reaps its private child.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_store_challenge_acquisition_interrupts_and_reaps_its_private_child(self):
#         stopped = threading.Event()
#         executable = self.script("import time\ntime.sleep(10)\n")
#         def child(argv, **kwargs):
#             self.assertIs(kwargs["cancelled"].__self__, stopped)
#             from mycel._safeguards import run_child
#             return run_child((str(executable),), **kwargs)
#         credentials = Credentials(self.settings(), InvocationPolicy("init"), _runner=child)
#         timer = threading.Timer(0.05, stopped.set)
#         timer.start()
#         self.addCleanup(timer.cancel)
#         start = time.monotonic()
#         with self.assertRaises(KeyboardInterrupt):
#             credentials.store_target(password_requested=True,
#                                      timeout_seconds=2, cancelled=stopped.is_set)
#         self.assertLess(time.monotonic() - start, 0.75)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_secret_and_store_target_formatting_is_redacted_and_children_receive_neither
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Secret and store target formatting is redacted and children receive neither.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_secret_and_store_target_formatting_is_redacted_and_children_receive_neither(self):
#         secret = Secret(SENTINEL)
#         target = StoreTarget(ADDRESS, secret)
#         for value in (secret, target):
#             self.assertNotIn(SENTINEL, repr(value) + str(value))
#             self.assertNotIn(ADDRESS, repr(value) + str(value))
#             with self.assertRaises(TypeError):
#                 json.dumps(value)
#         self.assertEqual(target.location, ADDRESS)
#         self.assertEqual(secret.reveal(), SENTINEL)
#         executable = self.script("import json,os\nprint(json.dumps(dict(os.environ)))\n")
#         parent = {"MYCEL_PG_DSN": ADDRESS, "DATABASE_URL": ADDRESS,
#                   "MYCEL_STORE_PASSWORD": SENTINEL, "PGPASSWORD": SENTINEL,
#                   "VOYAGE_API_KEY": SENTINEL, "JEV_API_KEY": SENTINEL}
#         with patch.dict(os.environ, parent):
#             for policy, purpose in ((InvocationPolicy("classify"), "reviewer"),
#                                     (InvocationPolicy("summaries", action="build"), "summary")):
#                 result = run_model_child(policy, purpose, [str(executable)], b"{}", timeout_seconds=5)
#                 self.assertEqual(result.returncode, 0)
#                 self.assertNotIn(SENTINEL.encode(), result.stdout + result.stderr)
#                 self.assertNotIn(ADDRESS.encode(), result.stdout + result.stderr)
#                 self.assertFalse(set(parent).intersection(json.loads(result.stdout)))
#             # Git's actual complete environment is inspected at its existing
#             # private transport boundary, without invoking a configured hook.
#             with patch("mycel._safeguards._run_process", return_value=completed()) as transport:
#                 run_git(["rev-parse", "--show-toplevel"], cwd=self.root)
#                 self.assertNotIn(SENTINEL, json.dumps(transport.call_args.kwargs["environment"]))
#                 self.assertNotIn(ADDRESS, json.dumps(transport.call_args.kwargs["environment"]))
#                 self.assertFalse(set(parent).intersection(transport.call_args.kwargs["environment"]))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::CredentialsTests.test_cli_fault_conversion_does_not_disclose_credential_command_output
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Cli fault conversion does not disclose credential command output.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cli_fault_conversion_does_not_disclose_credential_command_output(self):
#         executable = self.script("import sys\nprint('" + SENTINEL + "')\nsys.stderr.write('" + SENTINEL + "')\nsys.exit(4)\n")
#         snapshot = self.settings("[embedding]\nkey_command = " + json.dumps([str(executable)]) + "\n")
#         def embed(invocation):
#             Credentials(invocation.settings, InvocationPolicy("embed")).require_embedding_key()
#             self.fail("missing credential started an operation")
#         out, err = io.StringIO(), io.StringIO()
#         before = self.config.read_bytes()
#         with patch("mycel._cli.load_settings", return_value=snapshot):
#             self.assertEqual(run(["embed"], handlers={"embed": embed}, stdout=out, stderr=err), 1)
#         self.assertEqual(json.loads(out.getvalue())["error"]["code"], "refused")
#         self.assertNotIn(SENTINEL, out.getvalue() + err.getvalue())
#         self.assertEqual(self.config.read_bytes(), before)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_both_api_keys_use_private_pipe_and_explicit_trusted_reader
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Both api keys use private pipe and explicit trusted reader.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_both_api_keys_use_private_pipe_and_explicit_trusted_reader(self):
#         from mycel._credentials import store_api_key
#         secret = Secret(' public "key" \\ ascii ')
#         for provider, account in (("voyage", "voyage-api-key"), ("jev", "jev-api-key")):
#             calls = []
#             def child(argv, request, **limits):
#                 calls.append((argv, request, limits))
#                 return completed()
#             result = store_api_key(provider, secret, home=self.root, _runner=child)
#             self.assertEqual(result, {"stored": provider, "item": {"service": "mycel", "account": account}, "replaced": False})
#             argv, request, limits = calls[0]
#             self.assertEqual(argv, (SECURITY, "-q", "-i"))
#             self.assertNotIn(secret.reveal(), repr(argv) + repr(limits))
#             self.assertEqual(request.count(b"\n"), 1)
#             self.assertIn(b'-T "/usr/bin/security"', request)
#             self.assertNotIn(b" -A", request)
#             self.assertIn(b" -X " + secret.reveal().encode().hex().encode() + b" ", request)
#             self.assertIn(account.encode(), request)
#             self.assertIn(str(self.root / "Library/Keychains/login.keychain-db").encode(), request)
#             self.assertEqual(limits["home"], self.root.resolve())
#             self.assertGreater(limits["timeout_seconds"], 0)
#             self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["config.toml"])
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_replacement_only_follows_duplicate_without_reading_old_secret
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Replacement only follows duplicate without reading old secret.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_replacement_only_follows_duplicate_without_reading_old_secret(self):
#         from mycel._credentials import store_api_key
#         calls = []
#         def child(argv, request, **kwargs):
#             calls.append(request)
#             return completed(returncode=45 if len(calls) == 1 else 0)
#         result = store_api_key("voyage", Secret(SENTINEL), home=self.root, _runner=child)
#         self.assertTrue(result["replaced"])
#         self.assertEqual(len(calls), 2)
#         self.assertTrue(calls[0].startswith(b"add-generic-password -s "))
#         self.assertTrue(calls[1].startswith(b"add-generic-password -U -s "))
#         self.assertTrue(all(b"find-generic-password" not in request for request in calls))
#         self.assertTrue(all(request.count(b"\n") == 1 for request in calls))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_write_refusals_are_sanitized_and_do_not_retry_other_faults
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Write refusals are sanitized and do not retry other faults.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_write_refusals_are_sanitized_and_do_not_retry_other_faults(self):
#         from mycel._credentials import store_api_key
#         for codes in ((1,), (36,), (45, 1), (45, 36)):
#             calls = []
#             def child(*args, **kwargs):
#                 code = codes[len(calls)]
#                 calls.append(args)
#                 return completed(SENTINEL.encode(), returncode=code, stderr=SENTINEL.encode())
#             with self.assertRaises(MycelError) as error:
#                 store_api_key("jev", Secret(SENTINEL), home=self.root, _runner=child)
#             self.assertEqual(error.exception.code, "refused")
#             self.assertNotIn(SENTINEL, str(error.exception.to_dict()))
#             self.assertEqual(len(calls), len(codes))
#         def fail(*args, **kwargs):
#             raise ChildProcessFailure("timeout")
#         with self.assertRaises(MycelError) as error:
#             store_api_key("jev", Secret(SENTINEL), home=self.root, _runner=fail)
#         self.assertEqual(error.exception.code, "refused")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_invalid_or_overlong_keys_and_metadata_never_start_security
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Invalid or overlong keys and metadata never start security.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_invalid_or_overlong_keys_and_metadata_never_start_security(self):
#         from mycel._credentials import store_api_key
#         with patch("mycel._credentials.run_child") as child:
#             for value in ("", "a\0b", "a\nb", "a\rb", "a\tb", "λ", "x" * 3000, "\ud800"):
#                 with self.subTest(size=len(value)), self.assertRaises(MycelError) as error:
#                     store_api_key("voyage", Secret(value), home=self.root)
#                 self.assertEqual(error.exception.code, "invalid_input")
#             with self.assertRaises(MycelError):
#                 store_api_key("unknown", Secret(SENTINEL), home=self.root)
#             with self.assertRaises(MycelError):
#                 store_api_key("jev", Secret(SENTINEL), home=self.root / "bad\npath")
#             child.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_native_parser_path_quoting_is_not_shell_quoting
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Native parser path quoting is not shell quoting.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_native_parser_path_quoting_is_not_shell_quoting(self):
#         from mycel._credentials import store_api_key
#         home = self.root / "space ' quote\" back\\slash"
#         calls = []
#         def child(argv, request, **kwargs):
#             calls.append(request)
#             return completed()
#         store_api_key("jev", Secret(SENTINEL), home=home, _runner=child)
#         expected = str(home.resolve() / "Library/Keychains/login.keychain-db")
#         expected = '"' + expected.replace('\\', '\\\\').replace('"', '\\"') + '"'
#         self.assertTrue(calls[0].endswith((expected + "\n").encode()))
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_prompt_requires_hidden_terminal_and_nonempty_complete_line
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Prompt requires hidden terminal and nonempty complete line.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_prompt_requires_hidden_terminal_and_nonempty_complete_line(self):
#         from mycel._credentials import prompt_api_key
#         import getpass
#         with patch("mycel._credentials.open", side_effect=OSError), self.assertRaises(MycelError) as error:
#             prompt_api_key("voyage")
#         self.assertEqual(error.exception.code, "invalid_input")
#         from unittest.mock import MagicMock
#         terminal = MagicMock()
#         terminal.__enter__.return_value.isatty.return_value = True
#         for value in ("", "a\0b", "a\nb"):
#             with patch("mycel._credentials.open", return_value=terminal), \
#                     patch("mycel._credentials.getpass.getpass", return_value=value), self.assertRaises(MycelError):
#                 prompt_api_key("jev")
#         for fault in (EOFError(), getpass.GetPassWarning("private")):
#             with patch("mycel._credentials.open", return_value=terminal), \
#                     patch("mycel._credentials.getpass.getpass", side_effect=fault), self.assertRaises(MycelError) as error:
#                 prompt_api_key("jev")
#             self.assertEqual(error.exception.code, "invalid_input")
#             self.assertNotIn("private", str(error.exception.to_dict()))
#         with patch("mycel._credentials.open", return_value=terminal), \
#                 patch("mycel._credentials.getpass.getpass", return_value=" exact "):
#             self.assertEqual(prompt_api_key("voyage").reveal(), " exact ")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_cli_returns_only_item_identity_and_replacement_result
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Cli returns only item identity and replacement result.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cli_returns_only_item_identity_and_replacement_result(self):
#         for provider in ("voyage", "jev"):
#             expected = {"stored": provider, "item": {"service": "mycel", "account": provider + "-api-key"}, "replaced": True}
#             out, err = io.StringIO(), io.StringIO()
#             with patch.dict(os.environ, {"MYCEL_CONFIG": str(self.config)}), \
#                     patch("mycel._credentials.prompt_api_key", return_value=Secret(SENTINEL)) as prompt, \
#                     patch("mycel._credentials.store_api_key", return_value=expected) as writer, \
#                     patch("mycel._cli.invocation_store") as store:
#                 self.assertEqual(run(["api-key", provider], stdout=out, stderr=err), 0)
#             self.assertEqual(json.loads(out.getvalue()), expected)
#             self.assertEqual(out.getvalue().count("\n"), 1)
#             self.assertNotIn(SENTINEL, out.getvalue() + err.getvalue())
#             self.assertEqual(err.getvalue(), "")
#             prompt.assert_called_once_with(provider)
#             self.assertEqual(writer.call_args.args[1].reveal(), SENTINEL)
#             store.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_cli_invalid_syntax_stops_before_prompt_or_write
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Cli invalid syntax stops before prompt or write.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_cli_invalid_syntax_stops_before_prompt_or_write(self):
#         for arguments in ([], ["other"], ["voyage", SENTINEL], ["--repo", "x", "jev"], ["--all", "jev"]):
#             out = io.StringIO()
#             with patch("mycel._credentials.prompt_api_key") as prompt, patch("mycel._credentials.store_api_key") as writer:
#                 self.assertEqual(run(["api-key", *arguments], stdout=out, stderr=io.StringIO()), 1)
#                 self.assertEqual(json.loads(out.getvalue())["error"]["code"], "invalid_input")
#                 prompt.assert_not_called()
#                 writer.assert_not_called()
#             self.assertNotIn(SENTINEL, out.getvalue())
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_real_cli_without_controlling_terminal_refuses_before_keychain
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Real cli without controlling terminal refuses before keychain.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_real_cli_without_controlling_terminal_refuses_before_keychain(self):
#         environment = {"PATH": os.defpath, "HOME": str(self.root), "MYCEL_CONFIG": str(self.config),
#                        "PYTHONPATH": str(Path(_support.__file__).resolve().parents[1] / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
#         script = "from mycel._cli import main\nraise SystemExit(main())\n"
#         result = subprocess.run([sys.executable, "-c", script, "api-key", "voyage"],
#             start_new_session=True, input=b"ignored-pipe-input\n", capture_output=True, env=environment, timeout=5)
#         self.assertEqual(result.returncode, 1)
#         self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_input")
#         self.assertNotIn(b"ignored-pipe-input", result.stdout + result.stderr)
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_credentials.py::ApiKeyTests.test_help_and_info_name_api_key_and_invalid_settings_prevent_prompt
# Reason: Narrower case removed from this family after retaining test_configured_credential_command_is_literal_argv_with_empty_stdin_and_no_shell, test_credential_command_deadline_and_output_limits_are_private_failures, test_plain_grep_receives_neither_store_target_nor_parent_credentials, test_hidden_input_in_real_pseudoterminal_and_echo_restoration, test_real_pipe_child_never_receives_key_in_argv_environment_or_files. Its extra expected-state/branch permutation is not admitted as a separate consequential integration or independent invariant under the raised bar; this is a deliberate reduction of qualification breadth, not equivalent coverage. Case reviewed: Help and info name api key and invalid settings prevent prompt.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_credentials.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_help_and_info_name_api_key_and_invalid_settings_prevent_prompt(self):
#         out = io.StringIO()
#         self.assertEqual(run(["api-key", "--help"], stdout=out), 0)
#         entry, = json.loads(out.getvalue())["commands"]
#         self.assertEqual(entry["name"], "api-key")
#         self.assertTrue(entry["available"])
#         self.assertNotIn("--repo <name>", entry["options"])
#         self.config.write_text("[unknown]\nvalue = true\n")
#         with patch.dict(os.environ, {"MYCEL_CONFIG": str(self.config)}), patch("mycel._credentials.prompt_api_key") as prompt:
#             out = io.StringIO()
#             self.assertEqual(run(["api-key", "jev"], stdout=out), 1)
#             self.assertEqual(json.loads(out.getvalue())["error"]["code"], "settings")
#             prompt.assert_not_called()
#             out = io.StringIO()
#             self.assertEqual(run(["info"], stdout=out), 0)
#             self.assertIn("api-key", json.loads(out.getvalue())["commands"])
# LOW-TIER-SOURCE-END
# LOW-TIER-END
