"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_working_publication as _support
from test_working_publication import (BuildError ,PublicationFixture ,patch ,publication ,read_record ,selected ,tempfile)


class WorkingPublicationTests(_support.WorkingPublicationTests):


# TEST-TIER-BEGIN tests/test_working_publication.py::WorkingPublicationTests.test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade
    def test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade(self):
        for exception in (OSError,KeyboardInterrupt):
            with self.subTest(exception=exception),tempfile.TemporaryDirectory() as temporary:
                fixture=PublicationFixture(temporary); original=publication.atomic_json
                def write(path,value):
                    original(path,value)
                    if path.name=='build.json':raise exception('private postcommit sentinel')
                with patch.object(publication,'atomic_json',side_effect=write):
                    with self.assertRaises(KeyboardInterrupt if exception is KeyboardInterrupt else BuildError) as failure:fixture.publish()
                self.assertEqual(failure.exception.partialResult['status'],'working')
                self.assertEqual((read_record(fixture.root,fixture.number)['status'],selected(fixture.root)),('working',fixture.number))
                self.assertNotIn('private postcommit sentinel',str(failure.exception) if isinstance(failure.exception,BuildError) else '')
# TEST-TIER-END tests/test_working_publication.py::WorkingPublicationTests.test_postcommit_fsync_error_or_interrupt_reports_actual_working_state_without_downgrade
