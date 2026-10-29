"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_grep_tail as _support
from test_grep_tail import (Path ,SOURCE ,configured ,json ,os ,selectors ,signal ,subprocess ,sys ,tempfile)


class GrepTailUnitTests(_support.GrepTailUnitTests):


# TEST-TIER-BEGIN tests/test_grep_tail.py::GrepTailUnitTests.test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group
    def test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings, folders = configured(root)
            binary = root / 'waiting-bin'
            report = self.executable(binary, wait=True)
            script = ('from mycel._cli import main\nfrom mycel._coverage import no_network\n'
                      'with no_network():\n raise SystemExit(main())\n')
            env = {'PATH': str(binary), 'HOME': str(root), 'PYTHONPATH': str(SOURCE),
                   'PYTHONDONTWRITEBYTECODE': '1', 'MYCEL_CONFIG': str(settings.file)}
            process = subprocess.Popen([sys.executable, '-B', '-c', script, 'grep', 'needle'],
                cwd=folders['alpha'], env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                with selectors.DefaultSelector() as ready:
                    ready.register(process.stderr, selectors.EVENT_READ)
                    self.assertTrue(ready.select(10), 'Primary grep did not reach its ready marker.')
                self.assertEqual(process.stderr.readline(), b'fixture-ready\n')
                process.send_signal(signal.SIGINT)
                out, err = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 128 + signal.SIGINT)
                self.assertNotIn(b'"error"', out + err)
                observed = json.loads(report.read_text())
                self.assertEqual(observed['argv'], ['needle'])
                with self.assertRaises(ProcessLookupError):
                    os.killpg(observed['pgid'], 0)
            finally:
                if process.poll() is None:
                    process.kill()
                if report.exists():
                    try:
                        os.killpg(json.loads(report.read_text())['pgid'], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.communicate(timeout=5)
# TEST-TIER-END tests/test_grep_tail.py::GrepTailUnitTests.test_primary_cancellation_keeps_signal_status_and_reaps_its_real_child_group
