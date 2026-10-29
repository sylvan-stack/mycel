"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_classification_eligibility as _support
from test_classification_eligibility import (
    ClassificationEligibilityTests,
    ExitStack,
    FILE,
    MycelError,
    NOW,
    classification_eligibility,
    datetime,
    json,
    observe_input,
    patch,
    sha256,
    timedelta,
    timezone,
    unittest,
)


class ClassificationEligibilityTests(_support.ClassificationEligibilityTests):
# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_first_discovery_uses_old_modification_time_without_discovery_delay
    def test_first_discovery_uses_old_modification_time_without_discovery_delay(self):
        changed = NOW - timedelta(days=7)
        observation = self.file(modified=changed)
        result = classification_eligibility((observation,), at=NOW)
        self.assertEqual(observation['changedAt'], changed.isoformat(timespec='microseconds'))
        self.assertEqual(observation['timeSource'], 'modification')
        self.assertTrue(result.eligible)
        self.assertEqual(result.status, 'pending_jev')
        self.assertEqual(result.eligible_at, (changed + timedelta(seconds=300)).isoformat(timespec='microseconds'))
        self.assertEqual(result.faults, ())
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_first_discovery_uses_old_modification_time_without_discovery_delay

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_newest_source_dependant_context_and_generated_version_determine_time
    def test_newest_source_dependant_context_and_generated_version_determine_time(self):
        source = self.file(modified=NOW - timedelta(seconds=180))
        dependant = observe_input('fixture:@artifact/answer.md', 'dep', observed_at=NOW,
                                  modified_at=NOW - timedelta(seconds=100))
        context = observe_input('fixture:@artifact/context.md', 'ctx', observed_at=NOW,
                                modified_at=NOW - timedelta(seconds=50))
        generated = observe_input('fixture:@index/summary#Summary', 'summary-v2', kind='generated',
                                  observed_at=NOW, created_at=NOW - timedelta(seconds=20))
        result = classification_eligibility((source, dependant, context, generated), at=NOW)
        self.assertEqual(result.eligible_at, (NOW + timedelta(seconds=280)).isoformat(timespec='microseconds'))
        self.assertEqual(result.status, 'pending_debounce')
        self.assertFalse(result.eligible)
        self.assertEqual(generated['timeSource'], 'creation')
        self.assertFalse(classification_eligibility((source, dependant, context, generated),
                         at=NOW + timedelta(seconds=279, microseconds=999999)).eligible)
        self.assertTrue(classification_eligibility((source, dependant, context, generated),
                        at=NOW + timedelta(seconds=280)).eligible)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_newest_source_dependant_context_and_generated_version_determine_time

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_unchanged_hash_scan_mtime_touch_and_cache_reuse_do_not_restart
    def test_unchanged_hash_scan_mtime_touch_and_cache_reuse_do_not_restart(self):
        first = self.file(modified=NOW - timedelta(seconds=100))
        rescanned = self.file(observed=NOW + timedelta(seconds=200),
                              modified=NOW + timedelta(seconds=199), previous=first)
        repeated = self.file(observed=NOW + timedelta(seconds=500),
                             modified=NOW + timedelta(seconds=499), previous=rescanned)
        self.assertEqual(repeated['firstObservedAt'], first['firstObservedAt'])
        self.assertEqual(repeated['changedAt'], first['changedAt'])
        self.assertEqual(repeated['lastObservedAt'], (NOW + timedelta(seconds=500)).isoformat(timespec='microseconds'))
        self.assertEqual(self.eligible(first).eligible_at, self.eligible(repeated).eligible_at)
        self.assertTrue(self.eligible(repeated, at=NOW + timedelta(seconds=200)).eligible)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_unchanged_hash_scan_mtime_touch_and_cache_reuse_do_not_restart

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_preserved_backward_and_restored_timestamps_use_first_exact_read
    def test_preserved_backward_and_restored_timestamps_use_first_exact_read(self):
        first = self.file(modified=NOW - timedelta(seconds=100))
        last_read = NOW + timedelta(seconds=300)
        first = self.file(observed=last_read, modified=NOW + timedelta(seconds=200), previous=first)
        for modified in (NOW - timedelta(seconds=100), NOW - timedelta(days=2),
                         NOW + timedelta(seconds=200), last_read):
            with self.subTest(modified=modified):
                new_time = NOW + timedelta(seconds=400)
                delta = self.file('second', observed=new_time, modified=modified, previous=first)
                self.assertEqual(delta['changedAt'], new_time.isoformat(timespec='microseconds'))
                self.assertEqual(delta['timeSource'], 'observation')
                self.assertEqual(delta['faults'], ['timestamp_untrusted'])
                again = self.file('second', observed=new_time + timedelta(seconds=40),
                                  modified=modified, previous=json.loads(json.dumps(delta)))
                self.assertEqual(again['firstObservedAt'], delta['firstObservedAt'])
                self.assertEqual(self.eligible(again).eligible_at, self.eligible(delta).eligible_at)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_preserved_backward_and_restored_timestamps_use_first_exact_read

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_true_newer_modification_time_is_trusted_after_content_delta
    def test_true_newer_modification_time_is_trusted_after_content_delta(self):
        first = self.file(modified=NOW - timedelta(days=1))
        delta = self.file('second', observed=NOW + timedelta(seconds=30),
                          modified=NOW + timedelta(seconds=20), previous=first)
        self.assertEqual(delta['timeSource'], 'modification')
        self.assertEqual(delta['changedAt'], (NOW + timedelta(seconds=20)).isoformat(timespec='microseconds'))
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_true_newer_modification_time_is_trusted_after_content_delta

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_return_to_old_hash_after_another_version_establishes_new_timer
    def test_return_to_old_hash_after_another_version_establishes_new_timer(self):
        first = self.file(modified=NOW - timedelta(days=1))
        second = self.file('second', observed=NOW + timedelta(seconds=60),
                           modified=NOW + timedelta(seconds=40), previous=first)
        restored = self.file(observed=NOW + timedelta(seconds=100),
                             modified=NOW - timedelta(days=1), previous=second)
        self.assertEqual(restored['version'], first['version'])
        self.assertNotEqual(restored['firstObservedAt'], first['firstObservedAt'])
        self.assertEqual(restored['timeSource'], 'observation')
        self.assertFalse(self.eligible(restored, at=NOW + timedelta(seconds=399)).eligible)
        self.assertTrue(self.eligible(restored, at=NOW + timedelta(seconds=400)).eligible)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_return_to_old_hash_after_another_version_establishes_new_timer

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_whole_file_delta_outside_unchanged_cited_span_restarts_timer
    def test_whole_file_delta_outside_unchanged_cited_span_restarts_timer(self):
        selected = b'# Selected\nUnchanged claim.\n'
        before = sha256(selected + b'# Other\nOld context.\n').hexdigest()
        after = sha256(selected + b'# Other\nNew context.\n').hexdigest()
        old_mtime = NOW - timedelta(days=1)
        first = self.file(before, modified=old_mtime)
        changed = self.file(after, observed=NOW + timedelta(seconds=100),
                            modified=old_mtime, previous=first)
        self.assertNotEqual(changed['version'], first['version'])
        self.assertEqual(changed['changedAt'], (NOW + timedelta(seconds=100)).isoformat(timespec='microseconds'))
        self.assertEqual(changed['faults'], ['timestamp_untrusted'])
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_whole_file_delta_outside_unchanged_cited_span_restarts_timer

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_future_missing_naive_and_malformed_source_times_fall_back_visibly
    def test_future_missing_naive_and_malformed_source_times_fall_back_visibly(self):
        for modified in (NOW + timedelta(days=300), None, NOW.replace(tzinfo=None), 'malformed'):
            with self.subTest(modified=modified):
                observed = self.file(modified=modified)
                self.assertEqual(observed['changedAt'], NOW.isoformat(timespec='microseconds'))
                self.assertEqual(observed['timeSource'], 'observation')
                result = self.eligible(observed)
                self.assertFalse(result.eligible)
                self.assertEqual(result.as_dict()['faults'], [{'identity': FILE, 'reason': 'timestamp_untrusted'}])
                self.assertTrue(self.eligible(observed, at=NOW + timedelta(seconds=300)).eligible)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_future_missing_naive_and_malformed_source_times_fall_back_visibly

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_failed_initial_read_stays_pending_until_success_establishes_observation
    def test_failed_initial_read_stays_pending_until_success_establishes_observation(self):
        unavailable = self.file(observed=None, successful_read=False)
        self.assertIsNone(unavailable['firstObservedAt'])
        self.assertIsNone(self.eligible(unavailable).eligible_at)
        self.assertEqual(self.eligible(unavailable).status, 'pending_debounce')
        observed = self.file(observed=NOW + timedelta(seconds=20), previous=unavailable)
        self.assertEqual(observed['firstObservedAt'], (NOW + timedelta(seconds=20)).isoformat(timespec='microseconds'))
        self.assertFalse(self.eligible(observed, at=NOW + timedelta(seconds=319)).eligible)
        self.assertTrue(self.eligible(observed, at=NOW + timedelta(seconds=320)).eligible)
        failed_again = self.file(observed=None, successful_read=False, previous=observed)
        self.assertEqual(failed_again, observed)
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_failed_initial_read_stays_pending_until_success_establishes_observation

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_deletion_uses_first_tombstone_read_and_restoration_checks_that_time
    def test_deletion_uses_first_tombstone_read_and_restoration_checks_that_time(self):
        first = self.file(modified=NOW - timedelta(days=1))
        deleted = observe_input(FILE, 'tombstone', kind='deleted', observed_at=NOW, previous=first)
        repeated = observe_input(FILE, 'tombstone', kind='deleted', observed_at=NOW + timedelta(seconds=200),
                                 previous=deleted)
        self.assertEqual(repeated['changedAt'], deleted['changedAt'])
        self.assertEqual(repeated['faults'], [])
        self.assertFalse(self.eligible(repeated, at=NOW + timedelta(seconds=299)).eligible)
        self.assertTrue(self.eligible(repeated, at=NOW + timedelta(seconds=300)).eligible)
        restored = self.file(observed=NOW + timedelta(seconds=250),
                             modified=NOW - timedelta(days=1), previous=repeated)
        self.assertEqual(restored['timeSource'], 'observation')
        self.assertEqual(restored['changedAt'], (NOW + timedelta(seconds=250)).isoformat(timespec='microseconds'))
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_deletion_uses_first_tombstone_read_and_restoration_checks_that_time

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_generated_creation_time_is_not_discovery_time_and_future_creation_falls_back
    def test_generated_creation_time_is_not_discovery_time_and_future_creation_falls_back(self):
        identity = 'fixture:@index/summary#Summary'
        first = observe_input(identity, 'generated-v1', kind='generated', observed_at=NOW,
                              created_at=NOW - timedelta(days=2))
        self.assertTrue(self.eligible(first).eligible)
        second = observe_input(identity, 'generated-v2', kind='generated', observed_at=NOW,
                               created_at=NOW - timedelta(days=1), previous=first)
        self.assertEqual(second['timeSource'], 'creation')
        self.assertTrue(self.eligible(second).eligible)
        future = observe_input(identity, 'generated-v3', kind='generated', observed_at=NOW,
                               created_at=NOW + timedelta(days=3), previous=second)
        self.assertEqual(future['timeSource'], 'observation')
        self.assertEqual(future['faults'], ['timestamp_untrusted'])
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_generated_creation_time_is_not_discovery_time_and_future_creation_falls_back

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_all_serialized_times_are_utc_and_custom_zero_quiet_period_is_effective
    def test_all_serialized_times_are_utc_and_custom_zero_quiet_period_is_effective(self):
        madrid = timezone(timedelta(hours=2))
        observation = self.file(observed=NOW.astimezone(madrid),
                                modified=(NOW - timedelta(seconds=10)).astimezone(madrid))
        self.assertTrue(all(value.endswith('+00:00') for key, value in observation.items()
                            if key.endswith('At') and value is not None))
        result = self.eligible(observation, seconds=0)
        self.assertTrue(result.eligible)
        self.assertEqual(result.eligible_at, observation['changedAt'])
        self.assertEqual(self.eligible(observation, seconds=600).eligible_at,
                         (NOW + timedelta(seconds=590)).isoformat(timespec='microseconds'))
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_all_serialized_times_are_utc_and_custom_zero_quiet_period_is_effective

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_unavailable_required_context_prevents_eligibility_of_other_old_inputs
    def test_unavailable_required_context_prevents_eligibility_of_other_old_inputs(self):
        old = self.file(modified=NOW - timedelta(days=1))
        unavailable = observe_input('fixture:@artifact/context.md', 'context', successful_read=False)
        result = classification_eligibility((old, unavailable), at=NOW)
        self.assertEqual(result.as_dict(), {'eligibleAt': None, 'eligible': False,
                                          'status': 'pending_debounce', 'faults': []})
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_unavailable_required_context_prevents_eligibility_of_other_old_inputs

# TEST-TIER-BEGIN tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_invalid_clocks_periods_duplicate_inputs_and_corrupt_retained_state_are_refused
    def test_invalid_clocks_periods_duplicate_inputs_and_corrupt_retained_state_are_refused(self):
        observation = self.file(modified=NOW)
        for kwargs in ({'observed_at': NOW.replace(tzinfo=None)}, {'observed_at': None},
                       {'observed_at': NOW, 'successful_read': 1}, {'kind': 'pinned', 'observed_at': NOW},
                       {'kind': [], 'observed_at': NOW}):
            with self.subTest(kwargs=kwargs), self.assertRaises(MycelError) as caught:
                observe_input(FILE, 'version', **kwargs)
            self.assertEqual(caught.exception.code, 'invalid_input')
        for seconds in (-1, True, 3.5, 10**20):
            with self.subTest(seconds=seconds), self.assertRaises(MycelError) as caught:
                self.eligible(observation, seconds=seconds)
            self.assertEqual(caught.exception.code, 'invalid_input')
        with self.assertRaises(MycelError):
            classification_eligibility((observation, observation), at=NOW)
        with self.assertRaises(MycelError):
            self.file(observed=NOW - timedelta(seconds=1), previous=observation)
        for mutation in ({'schema': 'unknown'}, {'changedAt': '2026-10-13T10:00:00'},
                         {'firstObservedAt': None}, {'timeSource': 'creation'}, {'faults': ['hidden']},
                         {'kind': []}, {'timeSource': []}, {'faults': ['timestamp_untrusted']},
                         {'changedAt': None, 'timeSource': 'unavailable'}):
            with self.subTest(mutation=mutation), self.assertRaises(MycelError) as caught:
                self.file(previous={**observation, **mutation})
            self.assertEqual(caught.exception.code, 'store_format')
# TEST-TIER-END tests/test_classification_eligibility.py::ClassificationEligibilityTests.test_invalid_clocks_periods_duplicate_inputs_and_corrupt_retained_state_are_refused
