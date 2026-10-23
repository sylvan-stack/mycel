"""Real-store info reporting retains every feature row and sequence."""
from io import StringIO
import json
import unittest

from mycel._cli import run
from mycel._coverage import proves
from mycel._store import STORE_FORMAT
from test_refs import store_state


class DiagnosticsStoreTests(unittest.TestCase):
    check_kind = "store"

    @proves('MYC-1.28', kind='store')
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
