"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_classification_store as _support
from test_classification_store import (AT ,ClassificationStore ,DriftStore ,MycelError ,json ,patch ,sha256)


class ClassificationEvidenceStoreTests(_support.ClassificationEvidenceStoreTests):


# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_during_final_annotation_rolls_back_every_store_effect
    def test_context_race_during_final_annotation_rolls_back_every_store_effect(self):
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            before = self.fixture.state(connection)
            original = DriftStore._publish_classification
            def write(store, *args, **kwargs):
                original(store, *args, **kwargs)
                self.fixture.extra[0].write_bytes(b'# Source2\nContext edited during publication.\n')
            with patch.object(DriftStore, '_publish_classification', write), self.assertRaises(MycelError):
                ClassificationStore(connection).apply(self.base.settings, prepared,
                    judgement='still_supported', at=AT)
            self.assertEqual(self.fixture.state(connection), before)
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_context_race_during_final_annotation_rolls_back_every_store_effect

# TEST-TIER-BEGIN tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound
    def test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound(self):
        executable = self.write_reviewer()
        with self.base.connect() as connection:
            prepared = self.prepare(connection)
            self.assertIsNone(prepared.fault, prepared.as_dict())
            guards = json.loads(prepared.guards_bytes)
            identity = guards['command']
            self.assertEqual(identity['argv'], [str(executable.resolve()), '--literal', '$HOME/*.json'])
            self.assertEqual(identity['adapterRevision'], 'fixture-adapter-v1')
            self.assertEqual(identity['executableSha256'], sha256(executable.read_bytes()).hexdigest())
            self.assertEqual((identity['protocol'], identity['instructionVersion'], identity['environmentVersion']),
                             (1, 'mycel-review-v1', 'mycel-review-env-v1'))
            self.assertTrue(self.stage_check(connection, prepared, 'review')['allowed'])
            executable.write_bytes(b'#!/bin/sh\nexit 1\n')
            for stage in ('jev', 'review', 'application', 'reuse'):
                self.assertFalse(self.stage_check(connection, prepared, stage)['allowed'])
            result = ClassificationStore(connection).apply(self.base.settings, prepared,
                judgement='still_supported', at=AT)
            self.assertTrue(result['obsolete'])
# TEST-TIER-END tests/test_classification_store.py::ClassificationEvidenceStoreTests.test_reviewer_revision_literal_arguments_executable_digest_and_fixed_versions_are_bound
