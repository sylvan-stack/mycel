"""Real-store info reporting retains every feature row and sequence."""
import unittest


class DiagnosticsStoreTests(unittest.TestCase):
    check_kind = "store"

# TEST-TIER-DISABLED-BEGIN tests/test_diagnostics_store.py::DiagnosticsStoreTests.test_info_current_and_newer_store_diagnostics_never_repair_or_write_state
#     def test_info_current_and_newer_store_diagnostics_never_repair_or_write_state(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             connection.execute("INSERT INTO public.mycel_repository_state "
#                                "(repository,read_locations) VALUES ('retained','{}')")
#             for number, expected in ((STORE_FORMAT, 'current'), (STORE_FORMAT + 1, 'newer')):
#                 connection.execute('UPDATE public.mycel_store SET format=%s', (number,))
#                 before = store_state(connection)
#                 output, errors = StringIO(), StringIO()
#                 self.assertEqual(run(['info'], stdout=output, stderr=errors), 0)
#                 self.assertEqual(errors.getvalue(), '')
#                 reply = json.loads(output.getvalue())
#                 self.assertEqual(reply['store']['state'], expected)
#                 self.assertEqual(reply['store']['format'], number)
#                 self.assertEqual(reply['models']['embedding']['model'], 'voyage-code-4')
#                 self.assertEqual(store_state(connection), before)
# TEST-TIER-DISABLED-END tests/test_diagnostics_store.py::DiagnosticsStoreTests.test_info_current_and_newer_store_diagnostics_never_repair_or_write_state

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_diagnostics_store.py:2
# from io import StringIO
# TEST-TIER-IMPORTS-END tests/test_diagnostics_store.py:2
# TEST-TIER-IMPORTS-BEGIN tests/test_diagnostics_store.py:3
# import json
# TEST-TIER-IMPORTS-END tests/test_diagnostics_store.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_diagnostics_store.py:6
# from mycel._cli import run
# TEST-TIER-IMPORTS-END tests/test_diagnostics_store.py:6
# TEST-TIER-IMPORTS-BEGIN tests/test_diagnostics_store.py:7
# from mycel._store import STORE_FORMAT
# TEST-TIER-IMPORTS-END tests/test_diagnostics_store.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_diagnostics_store.py:8
# from test_refs import store_state
# TEST-TIER-IMPORTS-END tests/test_diagnostics_store.py:8
