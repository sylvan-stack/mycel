"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_pin_observation as _support
from test_pin_observation import (observation ,patch)


class PinObservationTests(_support.PinObservationTests):


# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_collision_after_scan_but_before_observation_finishes_is_detected
    def test_new_collision_after_scan_but_before_observation_finishes_is_detected(self):
        adapter = self.adapter()
        expected = adapter.observe()
        original = self.capture
        def create_collision_after_capture(snapshot, repository, **kwargs):
            result = original(snapshot,repository,**kwargs)
            if repository.name == 'source':
                (self.source_code/'source.md').write_text('# Source\nNew late collision\n')
            return result
        with patch.object(observation,'capture_repository',create_collision_after_capture):
            self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_collision_after_scan_but_before_observation_finishes_is_detected


# TEST-TIER-BEGIN tests/test_pin_observation.py::PinObservationTests.test_new_required_symlink_never_reads_outside_capture_roots
    def test_new_required_symlink_never_reads_outside_capture_roots(self):
        adapter = self.adapter()
        expected = adapter.observe()
        path = self.source_artifact/'source.md'
        outside = self.home/'outside.md'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        self.assert_refused_without_write(adapter,expected)
# TEST-TIER-END tests/test_pin_observation.py::PinObservationTests.test_new_required_symlink_never_reads_outside_capture_roots
