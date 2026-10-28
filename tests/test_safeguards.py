"""Executable boundary proofs; all programs and repositories are local fixtures."""

import sys
import unittest

from mycel._safeguards import (
    run_child,
)


class ModelPolicyTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ModelPolicyTests.test_embedding_is_separate_from_classification_and_requires_explicit_ingest_embed
#     def test_embedding_is_separate_from_classification_and_requires_explicit_ingest_embed(self):
#         for policy in (
#             InvocationPolicy("embed"), InvocationPolicy("ingest", embed=True),
#             InvocationPolicy("search"), InvocationPolicy("grep"),
#             InvocationPolicy("evaluate"), InvocationPolicy("evaluate", kind="retrieval"),
#             InvocationPolicy("summaries", action="build"),
#             InvocationPolicy("summaries", action="regenerate"),
#         ):
#             with self.subTest(policy=policy):
#                 self.assertTrue(model_call_allowed(policy, "embedding"))
#                 self.assertFalse(model_call_allowed(policy, "jev"))
#                 self.assertFalse(model_call_allowed(policy, "reviewer"))
#         self.assertFalse(model_call_allowed(InvocationPolicy("ingest"), "embedding"))
#         self.assertFalse(model_call_allowed(InvocationPolicy("evaluate", kind="drift", live=True), "embedding"))
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ModelPolicyTests.test_embedding_is_separate_from_classification_and_requires_explicit_ingest_embed

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ModelPolicyTests.test_classifier_and_reviewer_only_allow_explicit_classify_or_live_drift_evaluation
#     def test_classifier_and_reviewer_only_allow_explicit_classify_or_live_drift_evaluation(self):
#         allowed = (InvocationPolicy("classify"), InvocationPolicy("evaluate", kind="drift", live=True))
#         denied = (
#             InvocationPolicy("ingest", embed=True), InvocationPolicy("search"), InvocationPolicy("read"),
#             InvocationPolicy("evaluate", kind="drift"), InvocationPolicy("evaluate", live=True),
#             InvocationPolicy("evaluate", kind="retrieval", live=True),
#             *(InvocationPolicy(name) for name in (
#                 "status", "repos", "stale", "refs", "drifts", "verifications", "overview", "activity", "info",
#             )),
#         )
#         for purpose in ("jev", "reviewer"):
#             for policy in allowed:
#                 with self.subTest(purpose=purpose, policy=policy):
#                     require_model_call(policy, purpose)
#             for policy in denied:
#                 with self.subTest(purpose=purpose, policy=policy), self.assertRaises(MycelError) as error:
#                     require_model_call(policy, purpose)
#                 self.assertEqual(error.exception.code, "refused")
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ModelPolicyTests.test_classifier_and_reviewer_only_allow_explicit_classify_or_live_drift_evaluation

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ModelPolicyTests.test_summaries_only_allow_explicit_build_and_regenerate
#     def test_summaries_only_allow_explicit_build_and_regenerate(self):
#         for action in ("build", "regenerate"):
#             require_model_call(InvocationPolicy("summaries", action=action), "summary")
#         for action in (None, "status", "remove", "unknown"):
#             self.assertFalse(model_call_allowed(InvocationPolicy("summaries", action=action), "summary"))
#         for command in ("ingest", "search", "read", "classify", "evaluate"):
#             self.assertFalse(model_call_allowed(InvocationPolicy(command, action="build", live=True), "summary"))
#         self.assertFalse(model_call_allowed(InvocationPolicy("classify"), "unknown"))
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ModelPolicyTests.test_summaries_only_allow_explicit_build_and_regenerate

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ModelPolicyTests.test_all_dry_runs_refuse_model_calls_before_command_resolution_or_spawn
#     def test_all_dry_runs_refuse_model_calls_before_command_resolution_or_spawn(self):
#         policies = (
#             InvocationPolicy("ingest", embed=True, dry_run=True),
#             InvocationPolicy("embed", dry_run=True), InvocationPolicy("search", dry_run=True),
#             InvocationPolicy("classify", dry_run=True),
#             InvocationPolicy("evaluate", kind="drift", live=True, dry_run=True),
#             InvocationPolicy("summaries", action="build", dry_run=True),
#             InvocationPolicy("summaries", action="regenerate", dry_run=True),
#         )
#         with patch("mycel._safeguards.resolve_command") as resolve, patch("mycel._safeguards.subprocess.Popen") as spawn:
#             for policy in policies:
#                 for purpose in ("embedding", "jev", "reviewer", "summary"):
#                     with self.subTest(policy=policy, purpose=purpose), self.assertRaises(MycelError):
#                         run_model_child(policy, purpose, ["/nonexistent"], b"", timeout_seconds=1)
#             resolve.assert_not_called()
#             spawn.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ModelPolicyTests.test_all_dry_runs_refuse_model_calls_before_command_resolution_or_spawn

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ModelPolicyTests.test_report_and_search_cannot_launch_configured_model_children
#     def test_report_and_search_cannot_launch_configured_model_children(self):
#         with patch("mycel._safeguards.subprocess.Popen") as spawn:
#             for command in ("ingest", "search", "read", "status", "drifts", "activity", "info"):
#                 for purpose in ("summary", "reviewer"):
#                     with self.subTest(command=command, purpose=purpose), self.assertRaises(MycelError):
#                         run_model_child(InvocationPolicy(command), purpose, [sys.executable], b"", timeout_seconds=1)
#             spawn.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ModelPolicyTests.test_report_and_search_cannot_launch_configured_model_children


class ChildBoundaryTests(unittest.TestCase):
    def child(self, code, request=b"", **kwargs):
        return run_child([sys.executable, "-c", code], request, timeout_seconds=kwargs.pop("timeout_seconds", 5), **kwargs)

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_child_environment_is_exact_and_contains_no_parent_credentials
#     def test_child_environment_is_exact_and_contains_no_parent_credentials(self):
#         fake_parent = {
#             "MYCEL_STORE_PASSWORD": "fixture-store-secret", "VOYAGE_API_KEY": "fixture-voyage-secret",
#             "JEV_API_KEY": "fixture-jev-secret", "AWS_SESSION_TOKEN": "fixture-token", "PYTHONPATH": "/fixture",
#             "LD_PRELOAD": "/fixture", "GIT_EXTERNAL_DIFF": "/fixture", "PATH": "/untrusted",
#         }
#         with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, fake_parent):
#             result = run_child(["/usr/bin/env"], timeout_seconds=5, home=Path(directory))
#         environment = dict(line.split("=", 1) for line in result.stdout.decode().splitlines())
#         self.assertEqual(set(environment), {"HOME", "PATH", "LANG", "LC_ALL", "TMPDIR"})
#         self.assertEqual(environment["HOME"], str(Path(directory).resolve()))
#         self.assertEqual(environment["PATH"], SYSTEM_PATH)
#         self.assertEqual(environment["LANG"], "en_US.UTF-8")
#         self.assertEqual(environment["LC_ALL"], "en_US.UTF-8")
#         for secret in fake_parent.values():
#             self.assertNotIn(secret, environment.values())
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_child_environment_is_exact_and_contains_no_parent_credentials

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_child_has_empty_private_directory_pipes_and_own_process_group
#     def test_child_has_empty_private_directory_pipes_and_own_process_group(self):
#         code = """import json,os,stat,sys
# print(json.dumps({'cwd':os.getcwd(), 'entries':os.listdir('.'),
#  'mode':stat.S_IMODE(os.stat('.').st_mode), 'group':os.getpgrp(), 'pid':os.getpid(),
#  'tty':[os.isatty(fd) for fd in (0,1,2)], 'tmp':os.environ['TMPDIR']}))
# """
#         result = self.child(code)
#         data = json.loads(result.stdout)
#         self.assertEqual(result.returncode, 0)
#         self.assertEqual(data["entries"], [])
#         self.assertEqual(data["mode"], 0o700)
#         self.assertEqual(data["group"], data["pid"])
#         self.assertNotEqual(data["group"], os.getpgrp())
#         self.assertEqual(data["tty"], [False, False, False])
#         self.assertEqual(data["cwd"], data["tmp"])
#         self.assertFalse(Path(data["cwd"]).exists())
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_child_has_empty_private_directory_pipes_and_own_process_group

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_inheritable_credentials_and_lock_descriptors_are_closed
#     def test_inheritable_credentials_and_lock_descriptors_are_closed(self):
#         read_fd, write_fd = os.pipe()
#         os.set_inheritable(write_fd, True)
#         try:
#             code = f"""import os
# try: os.fstat({write_fd})
# except OSError: print('closed')
# else: print('inherited')
# """
#             result = self.child(code)
#             self.assertEqual(result.stdout, b"closed\n")
#         finally:
#             os.close(read_fd)
#             os.close(write_fd)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_inheritable_credentials_and_lock_descriptors_are_closed

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_arguments_and_input_are_literal_and_request_is_not_an_argument
#     def test_arguments_and_input_are_literal_and_request_is_not_an_argument(self):
#         arguments = ["$HOME", "$(touch /fixture)", "*.md", "; exit 1", ""]
#         request = "complete request · α\n".encode()
#         result = run_child(
#             [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:])); sys.stdout.flush(); sys.stdout.buffer.write(sys.stdin.buffer.read())", *arguments],
#             request, timeout_seconds=5,
#         )
#         first, remaining = result.stdout.split(b"\n", 1)
#         self.assertEqual(json.loads(first), arguments)
#         self.assertEqual(remaining, request)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_arguments_and_input_are_literal_and_request_is_not_an_argument

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_stdin_and_both_outputs_are_drained_concurrently
#     def test_stdin_and_both_outputs_are_drained_concurrently(self):
#         import errno
#
#         code = """import sys
# sys.stdout.buffer.write(b'x'*300000); sys.stdout.buffer.flush()
# sys.stderr.buffer.write(b'e'*30000); sys.stderr.buffer.flush()
# data = sys.stdin.buffer.read()
# sys.stdout.buffer.write(str(len(data)).encode())
# """
#         def drained(result):
#             self.assertEqual(result.returncode, 0)
#             self.assertEqual(result.stdout, b"x" * 300000 + b"2000000")
#             self.assertEqual(result.stderr, b"e" * 30000)
#
#         drained(self.child(code, b"i" * 2000000))
#         real_spawn = subprocess.Popen
#         operations = {"read": os.read, "write": os.write}
#         for operation in operations:
#             for transient in (True, False):
#                 with self.subTest(operation=operation, transient=transient):
#                     transport_fds, children = set(), []
#                     injected = False
#
#                     def spawn(*args, **kwargs):
#                         child = real_spawn(*args, **kwargs)
#                         children.append(child)
#                         streams = (child.stdout, child.stderr) if operation == "read" else (child.stdin,)
#                         transport_fds.update(stream.fileno() for stream in streams)
#                         return child
#
#                     def perform(fd, value):
#                         nonlocal injected
#                         if fd in transport_fds and not injected:
#                             injected = True
#                             if transient:
#                                 raise BlockingIOError(errno.EAGAIN, "fixture readiness race")
#                             raise OSError(errno.EIO, "fixture transport fault")
#                         return operations[operation](fd, value)
#
#                     with patch("mycel._safeguards.subprocess.Popen", side_effect=spawn), \
#                             patch("mycel._safeguards.os." + operation, side_effect=perform):
#                         if transient:
#                             drained(self.child(code, b"i" * 2000000))
#                         else:
#                             with self.assertRaises(ChildProcessFailure) as error:
#                                 self.child(code, b"i" * 2000000)
#                             self.assertEqual(error.exception.reason, "transport")
#                             self.assertNotIn("fixture transport fault", str(error.exception))
#                     self.assertTrue(injected)
#                     self.assertEqual(len(children), 1)
#                     self.assertIsNotNone(children[0].returncode)
#                     self.assertTrue(all(stream.closed for stream in
#                                         (children[0].stdin, children[0].stdout, children[0].stderr)))
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_stdin_and_both_outputs_are_drained_concurrently

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_output_caps_fail_with_safe_diagnostics_and_reap_the_child
#     def test_output_caps_fail_with_safe_diagnostics_and_reap_the_child(self):
#         for channel in ("stdout", "stderr"):
#             code = f"import sys,time; sys.{channel}.buffer.write(b'fixture-secret'*10000); sys.{channel}.flush(); time.sleep(20)"
#             started = time.monotonic()
#             with self.subTest(channel=channel), self.assertRaises(ChildProcessFailure) as error:
#                 self.child(code, stdout_limit=1000, stderr_limit=1000)
#             self.assertEqual(error.exception.reason, channel + "_limit")
#             self.assertNotIn("fixture-secret", str(error.exception))
#             self.assertLess(time.monotonic() - started, 3)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_output_caps_fail_with_safe_diagnostics_and_reap_the_child

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_exact_output_caps_are_allowed
#     def test_exact_output_caps_are_allowed(self):
#         result = self.child(
#             "import sys;sys.stdout.buffer.write(b'o'*1000);sys.stderr.buffer.write(b'e'*1000)",
#             stdout_limit=1000, stderr_limit=1000,
#         )
#         self.assertEqual(result.stdout, b"o" * 1000)
#         self.assertEqual(result.stderr, b"e" * 1000)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_exact_output_caps_are_allowed

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_timeout_kills_term_ignoring_process_and_does_not_expose_stderr
#     def test_timeout_kills_term_ignoring_process_and_does_not_expose_stderr(self):
#         with tempfile.TemporaryDirectory() as directory:
#             pid_file = Path(directory) / "pid"
#             code = f"""import os,pathlib,signal,sys,time
# signal.signal(signal.SIGTERM, signal.SIG_IGN)
# pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))
# sys.stderr.write('fixture-provider-secret');sys.stderr.flush()
# time.sleep(20)
# """
#             started = time.monotonic()
#             with self.assertRaises(ChildProcessFailure) as error:
#                 self.child(code, timeout_seconds=0.3)
#             self.assertEqual(error.exception.reason, "timeout")
#             self.assertNotIn("fixture-provider-secret", str(error.exception))
#             self.assertLess(time.monotonic() - started, 3)
#             with self.assertRaises(ProcessLookupError):
#                 os.kill(int(pid_file.read_text()), 0)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_timeout_kills_term_ignoring_process_and_does_not_expose_stderr

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_cancellation_terminates_the_entire_process_group
#     def test_cancellation_terminates_the_entire_process_group(self):
#         with tempfile.TemporaryDirectory() as directory:
#             marker = Path(directory) / "survived"
#             ready = Path(directory) / "ready"
#             grandchild = f"import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(2);pathlib.Path({str(marker)!r}).write_text('survived')"
#             code = f"""import pathlib,signal,subprocess,sys,time
# signal.signal(signal.SIGTERM,signal.SIG_IGN)
# subprocess.Popen([sys.executable,'-c',{grandchild!r}])
# pathlib.Path({str(ready)!r}).write_text('ready')
# time.sleep(20)
# """
#             started = time.monotonic()
#             with self.assertRaises(KeyboardInterrupt):
#                 self.child(code, cancelled=ready.exists)
#             self.assertLess(time.monotonic() - started, 3)
#             time.sleep(max(0, 2.2 - (time.monotonic() - started)))
#             self.assertFalse(marker.exists())
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_cancellation_terminates_the_entire_process_group

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_keyboard_interrupt_reaps_the_spawned_child
#     def test_keyboard_interrupt_reaps_the_spawned_child(self):
#         real_spawn = subprocess.Popen
#         children = []
#
#         def capture(*args, **kwargs):
#             child = real_spawn(*args, **kwargs)
#             children.append(child)
#             return child
#
#         with patch("mycel._safeguards.subprocess.Popen", side_effect=capture), \
#                 patch("mycel._safeguards.selectors.DefaultSelector.select", side_effect=KeyboardInterrupt):
#             with self.assertRaises(KeyboardInterrupt):
#                 self.child("import time; time.sleep(20)")
#         self.assertEqual(len(children), 1)
#         self.assertIsNotNone(children[0].returncode)
#         self.assertTrue(all(stream.closed for stream in (children[0].stdin, children[0].stdout, children[0].stderr)))
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_keyboard_interrupt_reaps_the_spawned_child

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_repeated_real_signals_cannot_interrupt_process_group_cleanup
#     def test_repeated_real_signals_cannot_interrupt_process_group_cleanup(self):
#         source = Path(__file__).resolve().parents[1] / "src"
#         for repeated_signal in (signal.SIGINT, signal.SIGTERM):
#             with self.subTest(repeated_signal=repeated_signal), tempfile.TemporaryDirectory() as directory:
#                 pid_file = Path(directory) / "pid"
#                 child_code = f"""import os,pathlib,signal,time
# signal.signal(signal.SIGTERM,signal.SIG_IGN)
# pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))
# time.sleep(20)
# """
#                 fixture = f"""import json,os,pathlib,signal,sys,threading,time
# sys.path.insert(0,{str(source)!r})
# from mycel._safeguards import run_child
# pid_file=pathlib.Path({str(pid_file)!r})
# original={{number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}}
# def interrupt():
#     while not pid_file.exists(): time.sleep(.005)
#     os.kill(os.getpid(),signal.SIGINT)
#     time.sleep(.05)
#     os.kill(os.getpid(),{int(repeated_signal)})
# sender=threading.Thread(target=interrupt)
# sender.start()
# interrupted=False
# try: run_child([sys.executable,'-c',{child_code!r}],timeout_seconds=5)
# except KeyboardInterrupt: interrupted=True
# sender.join()
# pid=int(pid_file.read_text())
# try: os.kill(pid,0); alive=True
# except ProcessLookupError: alive=False
# if alive:
#     os.killpg(pid,signal.SIGKILL)
#     os.waitpid(pid,0)
# print(json.dumps({{'interrupted':interrupted,'reaped':not alive,
#  'handlers_restored':all(signal.getsignal(number)==handler for number,handler in original.items())}}))
# """
#                 result = subprocess.run(
#                     [sys.executable, "-c", fixture], cwd=directory,
#                     env={"HOME": directory, "PATH": SYSTEM_PATH, "LC_ALL": "C"},
#                     capture_output=True, timeout=8, start_new_session=True,
#                 )
#                 self.assertEqual(result.returncode, 0, result.stderr)
#                 self.assertEqual(json.loads(result.stdout), {
#                     "interrupted": True, "reaped": True, "handlers_restored": True,
#                 })
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_repeated_real_signals_cannot_interrupt_process_group_cleanup

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_invalid_transport_limits_are_refused_before_spawn
#     def test_invalid_transport_limits_are_refused_before_spawn(self):
#         with patch("mycel._safeguards.subprocess.Popen") as spawn:
#             for limit in (0, -1, float("inf"), float("nan"), True):
#                 with self.subTest(timeout=limit), self.assertRaises(MycelError):
#                     self.child("pass", timeout_seconds=limit)
#             for limit in (0, -1, True, 1.5):
#                 with self.subTest(output_limit=limit), self.assertRaises(MycelError):
#                     self.child("pass", stdout_limit=limit)
#             spawn.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_invalid_transport_limits_are_refused_before_spawn

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_reviewer_resolution_never_searches_path_or_expands_arguments
#     def test_reviewer_resolution_never_searches_path_or_expands_arguments(self):
#         with patch("mycel._safeguards.shutil.which") as search:
#             with self.assertRaises(MycelError) as error:
#                 resolve_command(["python3", "--config", "$HOME/adapter.toml"])
#             self.assertEqual(error.exception.code, "settings")
#             search.assert_not_called()
#         arguments = [sys.executable, "--config", "$HOME/adapter.toml", "~/prompt", "*.json"]
#         resolved = resolve_command(arguments)
#         self.assertEqual(resolved[0], str(Path(sys.executable).resolve()))
#         self.assertEqual(resolved[1:], tuple(arguments[1:]))
# TEST-TIER-DISABLED-END tests/test_safeguards.py::ChildBoundaryTests.test_reviewer_resolution_never_searches_path_or_expands_arguments


class GitBoundaryTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::GitBoundaryTests.test_git_accepts_required_local_object_and_ref_reads
#     def test_git_accepts_required_local_object_and_ref_reads(self):
#         commands = (
#             ("rev-parse", "--show-toplevel"), ("rev-parse", "--verify", "--end-of-options", "HEAD"),
#             ("for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads/"),
#             ("ls-tree", "-r", "-z", "--name-only", "HEAD"), ("cat-file", "-p", "HEAD:file.md"),
#             ("cat-file", "--batch"), ("stash", "list", "--format=%H"),
#             ("show", "HEAD:file.md"), ("diff", "--name-status", "HEAD", "--", "-literal-file"),
#             ("status", "--porcelain=v2", "--untracked-files=no"),
#             ("config", "--bool", "--get", "core.ignorecase"),
#         )
#         for command in commands:
#             with self.subTest(command=command):
#                 self.assertEqual(validate_read_only_git_args(command), command)
# TEST-TIER-DISABLED-END tests/test_safeguards.py::GitBoundaryTests.test_git_accepts_required_local_object_and_ref_reads

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::GitBoundaryTests.test_git_mutations_and_executable_or_output_options_are_refused_before_spawn
#     def test_git_mutations_and_executable_or_output_options_are_refused_before_spawn(self):
#         denied = (
#             ("fetch",), ("reset", "--hard"), ("pull",), ("checkout", "main"), ("worktree", "add", "/fixture"),
#             ("branch", "created"), ("stash",), ("stash", "push"), ("stash", "drop"),
#             ("update-ref", "refs/heads/main", "HEAD"), ("config", "user.name", "changed"),
#             ("config", "--get", "credential.helper"), ("config", "--bool", "--get", "core.ignorecase", "true"),
#             ("-c", "alias.read=!touch /fixture", "read"), ("--exec-path=/fixture", "show", "HEAD"),
#             ("diff", "--output=/fixture"), ("log", "--output=/fixture"),
#             ("diff", "--ext-diff"), ("show", "--textconv", "HEAD:file.md"),
#             ("cat-file", "--filters", "HEAD:file.md"), ("log", "--show-signature"),
#             ("log", "--format=%G?"), ("for-each-ref", "--format=%(signature:grade)"),
#             ("rev-parse", "--parseopt"), ("ls-tree", "--unknown-option", "HEAD"),
#         )
#         with patch("mycel._safeguards.subprocess.Popen") as spawn:
#             for command in denied:
#                 with self.subTest(command=command), self.assertRaises(MycelError) as error:
#                     run_git(command, cwd=Path("/fixture"))
#                 self.assertEqual(error.exception.code, "refused")
#             spawn.assert_not_called()
# TEST-TIER-DISABLED-END tests/test_safeguards.py::GitBoundaryTests.test_git_mutations_and_executable_or_output_options_are_refused_before_spawn

# TEST-TIER-DISABLED-BEGIN tests/test_safeguards.py::GitBoundaryTests.test_git_reads_preserve_repository_and_disable_repository_executables
#     def test_git_reads_preserve_repository_and_disable_repository_executables(self):
#         git = shutil.which("git", path=SYSTEM_PATH)
#         self.assertIsNotNone(git)
#         with tempfile.TemporaryDirectory() as directory:
#             root = Path(directory)
#             repo = root / "repository"
#             repo.mkdir()
#             environment = {**os.environ, "PATH": SYSTEM_PATH, "LC_ALL": "C"}
#
#             def fixture_git(*args):
#                 result = subprocess.run(
#                     [git, *args],
#                     cwd=repo, env=environment, capture_output=True, timeout=5,
#                 )
#                 self.assertEqual(result.returncode, 0, result.stderr)
#
#             fixture_git("init", "--quiet")
#             (repo / "file.txt").write_text("before\n")
#             (repo / ".gitattributes").write_text("*.txt diff=fixture\n")
#             fixture_git("add", ".")
#             fixture_git("commit", "--quiet", "-m", "fixture")
#             marker = root / "executed"
#             executable = root / "untrusted"
#             executable.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
#             executable.chmod(0o700)
#             fixture_git("config", "core.fsmonitor", str(executable))
#             fixture_git("config", "diff.external", str(executable))
#             fixture_git("config", "diff.fixture.textconv", str(executable))
#             (repo / "file.txt").write_text("after\n")
#             before = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
#             with patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": str(executable), "GIT_PAGER": str(executable)}):
#                 for args in (
#                     ["rev-parse", "--show-toplevel"], ["for-each-ref", "--format=%(objectname)", "refs/heads/"],
#                     ["ls-tree", "-r", "--name-only", "HEAD"], ["cat-file", "-p", "HEAD:file.txt"],
#                     ["status", "--porcelain=v1"], ["diff", "HEAD"], ["show", "HEAD"], ["log", "--format=%H"],
#                 ):
#                     with self.subTest(args=args):
#                         self.assertEqual(run_git(args, cwd=repo).returncode, 0)
#             after = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
#             self.assertEqual(before, after)
#             self.assertFalse(marker.exists())
# TEST-TIER-DISABLED-END tests/test_safeguards.py::GitBoundaryTests.test_git_reads_preserve_repository_and_disable_repository_executables


if __name__ == "__main__":
    unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:3
# import json
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:4
# import os
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:4
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:5
# from pathlib import Path
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:5
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:6
# import shutil
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:7
# import signal
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:8
# import subprocess
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:8
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:10
# import tempfile
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:10
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:11
# import time
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:11
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:13
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:15
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:15
# TEST-TIER-IMPORTS-BEGIN tests/test_safeguards.py:16
# from mycel._safeguards import (
#     ChildProcessFailure, InvocationPolicy, SYSTEM_PATH, model_call_allowed,
#     require_model_call, resolve_command, run_child, run_git, run_model_child,
#     validate_read_only_git_args,
# )
# TEST-TIER-IMPORTS-END tests/test_safeguards.py:16
