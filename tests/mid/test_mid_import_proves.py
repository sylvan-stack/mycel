"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_import_proves as _support
from test_import_proves import (MycelError ,migration ,patch)


class ProvenImportStoreTests(_support.ProvenImportStoreTests):

# TEST-TIER-BEGIN tests/test_import_proves.py::ProvenImportStoreTests.test_late_input_edit_rolls_back_all_links_verifications_and_evidence
    def test_late_input_edit_rolls_back_all_links_verifications_and_evidence(self):
        original = migration.validate_plan
        calls = []
        def changed(plan):
            calls.append(True)
            if len(calls) == 3:
                self.source.write_text(self.source.read_text() + '\n# late edit\n')
            return original(plan)
        with self.base.connect() as connection:
            before = connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone()
            with patch.object(migration, 'validate_plan', side_effect=changed), self.assertRaises(MycelError):
                migration.apply_disposable(connection, self.settings, self.plan)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE kind='asserted'").fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone(), (0,))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_evidence_owners').fetchone(), before)
# TEST-TIER-END tests/test_import_proves.py::ProvenImportStoreTests.test_late_input_edit_rolls_back_all_links_verifications_and_evidence
