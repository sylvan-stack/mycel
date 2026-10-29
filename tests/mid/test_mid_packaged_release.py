"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_packaged_release as _support
from test_packaged_release import (BuildError ,Path ,os ,packaged ,sys ,tempfile)


class PackagedReleaseTests(_support.PackagedReleaseTests):


# TEST-TIER-BEGIN tests/test_packaged_release.py::PackagedReleaseTests.test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution
    def test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'unexpected-write'
            with self.assertRaises(BuildError) as error:
                packaged._case('fixture_write', [sys.executable, '-I', '-B', '-c',
                    'import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("actual write")', str(target)],
                    cwd=root, env=os.environ.copy(), before_root=root, timeout=10)
            self.assertEqual(error.exception.code, 'refused')
            self.assertEqual(target.read_text(), 'actual write')
# TEST-TIER-END tests/test_packaged_release.py::PackagedReleaseTests.test_actual_case_detects_a_real_write_instead_of_reporting_immutable_execution
