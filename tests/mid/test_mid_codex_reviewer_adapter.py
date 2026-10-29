"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_codex_reviewer_adapter as _support
from test_codex_reviewer_adapter import (CATALOG ,Path ,adapter ,patch ,subprocess ,sys ,tempfile ,time)


class CodexReviewerAdapterTests(_support.CodexReviewerAdapterTests):


# TEST-TIER-BEGIN tests/test_codex_reviewer_adapter.py::CodexReviewerAdapterTests.test_local_pipe_overflow_is_bounded_and_child_is_reaped
    def test_local_pipe_overflow_is_bounded_and_child_is_reaped(self):
        real_popen = subprocess.Popen
        def standin(*unused, **kwargs):
            return real_popen([sys.executable, "-c", "import os,time;os.write(1,b'x'*4194305);time.sleep(10)"], **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / ".codex").mkdir()
            (home / ".codex/config.toml").write_text("")
            with patch.object(Path, "home", return_value=home), patch.object(adapter.subprocess, "Popen", side_effect=standin):
                server = adapter.AppServer("/fictional/codex", home, time.monotonic() + 5, lambda: False, catalog=CATALOG)
            try:
                with self.assertRaises(adapter.Refused):
                    while True:
                        server.pump()
            finally:
                server.close()
            self.assertIsNotNone(server.child.returncode)
            self.assertLessEqual(server.sizes["stdout"], adapter.MAX_RPC_OUTPUT + 65536)
# TEST-TIER-END tests/test_codex_reviewer_adapter.py::CodexReviewerAdapterTests.test_local_pipe_overflow_is_bounded_and_child_is_reaped
