# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Real OS lock handoff, explicit maintenance and interrupted pruning proofs."""

import subprocess
import sys
import unittest
from contextlib import contextmanager

try:
    from .test_launcher_selection import ROOT, ready_line
except ImportError:
    from test_launcher_selection import ROOT, ready_line


@contextmanager
def peer_lock(path, operation):
    code = ('import fcntl,os,sys\n'
        'fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW)\n'
        'fcntl.flock(fd,int(sys.argv[2])|fcntl.LOCK_NB)\n'
        'print("locked",flush=True)\n'
        'sys.stdin.buffer.read()\n')
    process = subprocess.Popen([sys.executable, '-I', '-B', '-c', code, str(path), str(operation)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert ready_line(process) == b'locked\n'
        yield process
    finally:
        process.communicate(timeout=10)
        if process.returncode:
            raise AssertionError('fixture lock peer failed')


def peer_prune(fixture, number):
    code = ('import json,sys\nfrom pathlib import Path\n'
        f'sys.path.insert(0,{str(ROOT / "src")!r})\n'
        'from mycel_build._maintenance import prune\n'
        'from mycel_build._core import BuildError\n'
        'try:\n'
        '    result=prune(Path(sys.argv[1]),sys.argv[2])\n'
        '    print(json.dumps({"result":result}))\n'
        'except BuildError as error:\n'
        '    print(json.dumps({"error":{"code":error.code}}))\n'
        '    raise SystemExit(1)\n')
    return subprocess.run([sys.executable, '-I', '-B', '-c', code, str(fixture.registry), number],
        env=fixture.environment(), capture_output=True, timeout=5)


class LauncherMaintenanceTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
