"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_safeguards as _support
from test_safeguards import (Path ,SYSTEM_PATH ,json ,os ,patch ,run_git ,shutil ,signal ,subprocess ,sys ,tempfile)


class ChildBoundaryTests(_support.ChildBoundaryTests):


# TEST-TIER-BEGIN tests/test_safeguards.py::ChildBoundaryTests.test_repeated_real_signals_cannot_interrupt_process_group_cleanup
    def test_repeated_real_signals_cannot_interrupt_process_group_cleanup(self):
        source = Path(_support.__file__).resolve().parents[1] / "src"
        for repeated_signal in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(repeated_signal=repeated_signal), tempfile.TemporaryDirectory() as directory:
                pid_file = Path(directory) / "pid"
                child_code = f"""import os,pathlib,signal,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))
time.sleep(20)
"""
                fixture = f"""import json,os,pathlib,signal,sys,threading,time
sys.path.insert(0,{str(source)!r})
from mycel._safeguards import run_child
pid_file=pathlib.Path({str(pid_file)!r})
original={{number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}}
def interrupt():
    while not pid_file.exists(): time.sleep(.005)
    os.kill(os.getpid(),signal.SIGINT)
    time.sleep(.05)
    os.kill(os.getpid(),{int(repeated_signal)})
sender=threading.Thread(target=interrupt)
sender.start()
interrupted=False
try: run_child([sys.executable,'-c',{child_code!r}],timeout_seconds=5)
except KeyboardInterrupt: interrupted=True
sender.join()
pid=int(pid_file.read_text())
try: os.kill(pid,0); alive=True
except ProcessLookupError: alive=False
if alive:
    os.killpg(pid,signal.SIGKILL)
    os.waitpid(pid,0)
print(json.dumps({{'interrupted':interrupted,'reaped':not alive,
 'handlers_restored':all(signal.getsignal(number)==handler for number,handler in original.items())}}))
"""
                result = subprocess.run(
                    [sys.executable, "-c", fixture], cwd=directory,
                    env={"HOME": directory, "PATH": SYSTEM_PATH, "LC_ALL": "C"},
                    capture_output=True, timeout=8, start_new_session=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {
                    "interrupted": True, "reaped": True, "handlers_restored": True,
                })
# TEST-TIER-END tests/test_safeguards.py::ChildBoundaryTests.test_repeated_real_signals_cannot_interrupt_process_group_cleanup


class GitBoundaryTests(_support.GitBoundaryTests):


# TEST-TIER-BEGIN tests/test_safeguards.py::GitBoundaryTests.test_git_reads_preserve_repository_and_disable_repository_executables
    def test_git_reads_preserve_repository_and_disable_repository_executables(self):
        git = shutil.which("git", path=SYSTEM_PATH)
        self.assertIsNotNone(git)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repository"
            repo.mkdir()
            environment = {**os.environ, "PATH": SYSTEM_PATH, "LC_ALL": "C"}

            def fixture_git(*args):
                result = subprocess.run(
                    [git, *args],
                    cwd=repo, env=environment, capture_output=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            fixture_git("init", "--quiet")
            (repo / "file.txt").write_text("before\n")
            (repo / ".gitattributes").write_text("*.txt diff=fixture\n")
            fixture_git("add", ".")
            fixture_git("commit", "--quiet", "-m", "fixture")
            marker = root / "executed"
            executable = root / "untrusted"
            executable.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            executable.chmod(0o700)
            fixture_git("config", "core.fsmonitor", str(executable))
            fixture_git("config", "diff.external", str(executable))
            fixture_git("config", "diff.fixture.textconv", str(executable))
            (repo / "file.txt").write_text("after\n")
            before = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
            with patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": str(executable), "GIT_PAGER": str(executable)}):
                for args in (
                    ["rev-parse", "--show-toplevel"], ["for-each-ref", "--format=%(objectname)", "refs/heads/"],
                    ["ls-tree", "-r", "--name-only", "HEAD"], ["cat-file", "-p", "HEAD:file.txt"],
                    ["status", "--porcelain=v1"], ["diff", "HEAD"], ["show", "HEAD"], ["log", "--format=%H"],
                ):
                    with self.subTest(args=args):
                        self.assertEqual(run_git(args, cwd=repo).returncode, 0)
            after = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(marker.exists())
# TEST-TIER-END tests/test_safeguards.py::GitBoundaryTests.test_git_reads_preserve_repository_and_disable_repository_executables
