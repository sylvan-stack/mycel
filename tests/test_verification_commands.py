"""Actual confirmation and history dispatch over configured disposable stores."""
from io import StringIO
import json
import unittest
from unittest.mock import patch

from mycel._cli import run
from mycel._coverage import proves

try:
    from . import test_dependency_source_refresh as fixtures
except ImportError:
    import test_dependency_source_refresh as fixtures


class VerificationCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DependencySourceRefreshStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def invoke(self, *arguments):
        output, diagnostic = StringIO(), StringIO()
        with patch('mycel._cli.load_settings', return_value=self.base.settings), \
                patch('mycel._build_identity.current_build', return_value=None):
            status = run(arguments, stdout=output, stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(), '')
        return status, json.loads(output.getvalue())

    @proves('MYC-7.18', 'MYC-7.20', 'MYC-7.30', kind='store')
    def test_real_confirm_dispatch_and_history_reply_with_explicit_and_default_voucher(self):
        self.fixture.answer.write_bytes(b'# Answer\nIndependent statement.\n')
        with self.base.connect() as connection:
            self.fixture.prepare(connection)
            with patch('mycel._verification.getpass.getuser', return_value='owner-login'):
                status, first = self.invoke('confirm', 'downstream:@artifact/answer.md#Answer')
            self.assertEqual((status, first['by'], first['how'], first['current']),
                             (0, 'owner-login', 'read', True))
            expected = {'id', 'chunk', 'chunkId', 'version', 'textHash', 'dependantSnapshot',
                        'baselineManifests', 'sources', 'by', 'how', 'at', 'current'}
            self.assertEqual(set(first), expected)
            status, second = self.invoke('confirm', 'downstream:@artifact/answer.md#Answer',
                                        '--by', 'ana', '--how', 'check')
            self.assertEqual((status, second['by'], second['how']), (0, 'ana', 'check'))
            self.assertNotEqual(first['id'], second['id'])
            before = self.fixture.state(connection)
            records = connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_verifications r ORDER BY id').fetchall()
            status, current = self.invoke('verifications', '--repo', 'downstream')
            self.assertEqual(status, 0)
            self.assertEqual(current, {'repository': 'downstream', 'verifications': [second]})
            status, history = self.invoke('verifications', '--repo', 'downstream', '--history')
            self.assertEqual(status, 0)
            self.assertEqual([r['id'] for r in history['verifications']], [second['id'], first['id']])
            self.assertEqual([r['current'] for r in history['verifications']], [True, False])
            self.assertEqual(self.fixture.state(connection), before)
            self.assertEqual(connection.execute('SELECT to_jsonb(r),xmin::text FROM public.mycel_verifications r ORDER BY id').fetchall(), records)
