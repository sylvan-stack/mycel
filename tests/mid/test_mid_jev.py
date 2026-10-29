"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_jev as _support
from test_jev import (JevFailure ,KEY ,Secret ,_https_request ,patch ,threading ,time)


class JevTests(_support.JevTests):


# TEST-TIER-BEGIN tests/test_jev.py::JevTests.test_cancelled_delayed_connect_cannot_send_late_paid_request
    def test_cancelled_delayed_connect_cannot_send_late_paid_request(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        requests, closed = [], []
        class Connection:
            sock = None
            def __init__(self, *a, **k):
                pass
            def connect(self):
                entered.set()
                release.wait(2)
            def request(self, *a, **k):
                requests.append(1)
            def close(self):
                closed.append(1)
                if release.is_set():
                    finished.set()
        with patch('http.client.HTTPSConnection', Connection), patch('mycel._jev._tls_context', return_value=object()):
            try:
                with self.assertRaises(JevFailure) as caught:
                    _https_request(b'{}', Secret(KEY), deadline=time.monotonic() + 1,
                                   cancelled=entered.is_set)
                self.assertEqual(caught.exception.code, 'cancelled')
            finally:
                release.set()
                self.assertTrue(finished.wait(1))
        self.assertEqual(requests, [])
        self.assertTrue(closed)
# TEST-TIER-END tests/test_jev.py::JevTests.test_cancelled_delayed_connect_cannot_send_late_paid_request
