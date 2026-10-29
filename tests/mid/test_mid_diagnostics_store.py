"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_diagnostics_store as _support
from test_diagnostics_store import (
    DiagnosticsStoreTests,
    STORE_FORMAT,
    StringIO,
    json,
    run,
    store_state,
    unittest,
)


class DiagnosticsStoreTests(_support.DiagnosticsStoreTests):
# TEST-TIER-BEGIN tests/test_diagnostics_store.py::DiagnosticsStoreTests.test_info_current_and_newer_store_diagnostics_never_repair_or_write_state
    def test_info_current_and_newer_store_diagnostics_never_repair_or_write_state(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            connection.execute("INSERT INTO public.mycel_repository_state "
                               "(repository,read_locations) VALUES ('retained','{}')")
            for number, expected in ((STORE_FORMAT, 'current'), (STORE_FORMAT + 1, 'newer')):
                connection.execute('UPDATE public.mycel_store SET format=%s', (number,))
                before = store_state(connection)
                output, errors = StringIO(), StringIO()
                self.assertEqual(run(['info'], stdout=output, stderr=errors), 0)
                self.assertEqual(errors.getvalue(), '')
                reply = json.loads(output.getvalue())
                self.assertEqual(reply['store']['state'], expected)
                self.assertEqual(reply['store']['format'], number)
                self.assertEqual(reply['models']['embedding']['model'], 'voyage-code-4')
                self.assertEqual(store_state(connection), before)
# TEST-TIER-END tests/test_diagnostics_store.py::DiagnosticsStoreTests.test_info_current_and_newer_store_diagnostics_never_repair_or_write_state
