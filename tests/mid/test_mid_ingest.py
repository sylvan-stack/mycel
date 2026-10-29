"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_ingest as _support
from test_ingest import (patch)


class IngestStepStoreTests(_support.IngestStepStoreTests):


# TEST-TIER-BEGIN tests/test_ingest.py::IngestStepStoreTests.test_an_interrupted_step_loses_only_itself
    def test_an_interrupted_step_loses_only_itself(self):
        self.edited_notes()
        self.assertEqual(self.invoke('--repo', 'fixture', '--files', '1')[0], 0)
        from mycel import _ingest
        with patch.object(_ingest._CompleteProducer, '__call__', side_effect=KeyboardInterrupt):
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 2, reply)
        with self.base.connect() as connection:
            self.assertEqual(len(self.second(connection)), 1)
        status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 0, reply)
        self.assertEqual(reply['repositories']['fixture']['remaining'], {'files': 1, 'refresh': 0})
        with self.base.connect() as connection:
            self.assertEqual(len(self.second(connection)), 2)
# TEST-TIER-END tests/test_ingest.py::IngestStepStoreTests.test_an_interrupted_step_loses_only_itself
