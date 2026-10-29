"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_clone_locations as _support
from test_clone_locations import (patch)


class CloneStoreTests(_support.CloneStoreTests):

# TEST-TIER-BEGIN tests/test_clone_locations.py::CloneStoreTests.test_two_public_passes_capture_concurrently_and_publish_both_clones
    def test_two_public_passes_capture_concurrently_and_publish_both_clones(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier,Event
        from mycel._located_reconciliation import LocatedCaptureStore
        from mycel._cli import Invocation
        from mycel._ingest import ingest
        self.ingest(self.primary);self.ingest(self.secondary)
        self.source.write_text('def value():\n    return 10\n')
        (self.clone/'value.py').write_text('def value():\n    return 20\n')
        simultaneous=Barrier(2);primary_captured=Event();primary_done=Event()
        original=LocatedCaptureStore.capture
        def capture(store,settings,repository):
            manifest=original(store,settings,repository)
            if settings._cwd==self.base.code:
                primary_captured.set()
            simultaneous.wait(timeout=20)
            if settings._cwd==self.clone:
                self.assertTrue(primary_done.wait(timeout=20))
            return manifest
        def run(settings):
            try:
                return ingest(Invocation('ingest',repositories=('fixture',),settings=settings))
            finally:
                if settings._cwd==self.base.code:primary_done.set()
        with patch('mycel._build_identity.current_build',return_value=1), \
                patch.object(LocatedCaptureStore,'capture',capture), ThreadPoolExecutor(2) as pool:
            first=pool.submit(run,self.primary)
            # The allocator deliberately refuses peers without waiting. Start
            # the second invocation after those short guards are released;
            # both captures must still finish before either can publish.
            self.assertTrue(primary_captured.wait(timeout=20))
            second=pool.submit(run,self.secondary)
            results=(first.result(timeout=30),second.result(timeout=30))
        self.assertTrue(all(result.status==0 for result in results),[r.value for r in results])
        with self.base.connect() as connection:
            self.assertIn(b'return 10',self.member(connection,self.primary).source)
            self.assertIn(b'return 20',self.member(connection,self.secondary).source)
# TEST-TIER-END tests/test_clone_locations.py::CloneStoreTests.test_two_public_passes_capture_concurrently_and_publish_both_clones
