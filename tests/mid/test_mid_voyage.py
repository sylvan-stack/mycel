"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_voyage as _support
from test_voyage import (KEY ,ProviderFailure ,Secret ,_https_request ,patch ,threading ,time)


class VoyageTests(_support.VoyageTests):


# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends
    def test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends(self):
        for cancellation in (False, True):
            setup_started = threading.Event()
            release_setup = threading.Event()
            worker_done = threading.Event()
            calls = []
            def delayed_context():
                setup_started.set()
                release_setup.wait(1)
                return object()
            class Connection:
                sock = None
                def __init__(self, *args, **kwargs): calls.append("create")
                def connect(self): calls.append("connect")
                def request(self, *args, **kwargs): calls.append("POST")
                def close(self): calls.append("close")
            actual_thread = threading.Thread
            def thread_factory(*args, **kwargs):
                target = kwargs["target"]
                def work():
                    try:
                        target()
                    finally:
                        worker_done.set()
                return actual_thread(*args, **dict(kwargs, target=work))
            started = time.monotonic()
            with self.subTest(cancellation=cancellation), \
                    patch("mycel._voyage._tls_context", side_effect=delayed_context), \
                    patch("mycel._voyage.http.client.HTTPSConnection", Connection), \
                    patch("mycel._voyage.threading.Thread", side_effect=thread_factory):
                try:
                    with self.assertRaises(ProviderFailure) as failure:
                        _https_request(b"{}", Secret(KEY), deadline=started + 0.08,
                                       cancelled=lambda: cancellation and setup_started.is_set())
                    self.assertEqual(failure.exception.kind, "cancelled" if cancellation else "deadline")
                    self.assertTrue(setup_started.is_set())
                    self.assertLess(time.monotonic() - started, 0.3)
                    self.assertFalse(calls)
                finally:
                    release_setup.set()
                    self.assertTrue(worker_done.wait(0.5))
                self.assertFalse(calls)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends
