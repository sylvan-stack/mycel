"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_replacement as _support
from test_replacement import (Fixture ,Path ,tempfile)


class ReplacementTests(_support.ReplacementTests):


# TEST-TIER-BEGIN tests/test_replacement.py::ReplacementTests.test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog
    def test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory).resolve()); fixture.compile()
            for step in fixture.plan['steps']:
                if not step['required']: continue
                fixture.observe(step['id'], 'completed', fixture.action(step['id']))
            report = fixture.validate()
            self.assertTrue(report['complete']); self.assertFalse(report['partial'])
            self.assertFalse(fixture.old.exists()); self.assertFalse(fixture.link.is_symlink())
            self.assertEqual(fixture.corpus.read_bytes(), b'Keep exact source evidence.\n')
            self.assertEqual(fixture.unrelated.read_bytes(), b'Keep unrelated bytes.\n')
            self.assertEqual(fixture.shell.read_text(), 'export KEEP=one\n# retained tail\n')
            self.assertEqual(report['commandAvailability'], 'mycel2_verified')
            self.assertFalse(report['ownerReplacementPerformedByValidator']); self.assertEqual(report['databaseConnections'], 0)
# TEST-TIER-END tests/test_replacement.py::ReplacementTests.test_disposable_rehearsal_removes_only_approved_objects_and_preserves_sources_shell_tail_and_catalog
