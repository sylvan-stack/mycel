"""Offline quiet-period observations, separate from semantic decision identity.

Callers retain one observation per required live input in their guarded store
transaction. A file version means its complete bytes, including uncited spans.
Neither immutable pinned snapshots nor a cache-use timestamp belongs here.
This module does not sleep, schedule work, read disk or invoke a model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ._errors import MycelError


OBSERVATION_SCHEMA = 'mycel-classification-observation-v1'
DEFAULT_DEBOUNCE_SECONDS = 300
_KINDS = {'file', 'deleted', 'generated'}
_SOURCES = {'modification', 'creation', 'observation', 'unavailable'}


def _invalid(message):
    raise MycelError('invalid_input', message)


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('A UTC observation requires a timezone-aware time.')
    return value.astimezone(timezone.utc)


def _utc(value):
    return value.isoformat(timespec='microseconds')


def _text(value):
    if not isinstance(value, str) or not value or '\0' in value:
        return False
    try:
        value.encode('utf-8', errors='strict')
        return True
    except UnicodeError:
        return False


def _read_observation(value):
    """Reject incompatible retained observations instead of resetting a timer."""
    def bad():
        raise MycelError('store_format', 'The classification time observation is incompatible.')

    fields = {'schema', 'identity', 'version', 'kind', 'firstObservedAt', 'lastObservedAt',
              'changedAt', 'timeSource', 'faults'}
    if (not isinstance(value, Mapping) or not isinstance(value.get('kind'), str)
            or value['kind'] not in _KINDS):
        bad()
    fields.update({'modifiedAt'} if value['kind'] == 'file' else
                  {'createdAt'} if value['kind'] == 'generated' else set())
    if (set(value) != fields or value.get('schema') != OBSERVATION_SCHEMA
            or not _text(value.get('identity')) or not _text(value.get('version'))
            or not isinstance(value.get('timeSource'), str) or value['timeSource'] not in _SOURCES
            or not isinstance(value.get('faults'), list)
            or value['faults'] not in ([], ['timestamp_untrusted'])):
        bad()
    times = {}
    for key in fields & {'firstObservedAt', 'lastObservedAt', 'modifiedAt', 'createdAt', 'changedAt'}:
        raw = value[key]
        try:
            times[key] = None if raw is None else _time(raw)
            if raw is not None and (not isinstance(raw, str) or raw != _utc(times[key])):
                bad()
        except (TypeError, ValueError, OverflowError):
            bad()
    first, last, changed = (times[key] for key in ('firstObservedAt', 'lastObservedAt', 'changedAt'))
    if ((first is None) != (last is None) or first is not None and first > last
            or (changed is None) != (value['timeSource'] == 'unavailable')
            or (first is None) != (changed is None) or changed is not None and changed > first):
        bad()
    if value['timeSource'] == 'modification' and (value['kind'] != 'file'
            or times['modifiedAt'] is None or changed != times['modifiedAt']):
        bad()
    if value['timeSource'] == 'creation' and (value['kind'] != 'generated'
            or times['createdAt'] is None or changed != times['createdAt']):
        bad()
    if value['timeSource'] == 'observation' and changed != first:
        bad()
    expected_faults = (['timestamp_untrusted'] if value['timeSource'] == 'observation'
                       and value['kind'] != 'deleted' else [])
    if value['faults'] != expected_faults:
        bad()
    if value['kind'] == 'deleted' and (value['timeSource'] not in {'observation', 'unavailable'}
            or value['faults']):
        bad()
    return dict(value), times


def observe_input(identity: str, version: str, *, kind: str = 'file', observed_at=None,
                  modified_at=None, created_at=None, previous=None,
                  successful_read: bool = True) -> dict:
    """Record the first successful observation of the current complete version.

    ``previous`` is the last observation for this input identity, even if its
    bytes/state differ. A returned earlier hash after an intervening version is
    newly observed; it cannot borrow that older version's expired quiet period.
    Unchanged consecutive versions retain their original change time. The last
    successful read is retained only to detect later restored/preserved mtimes.

    Initial old mtimes are trustworthy. For a changed file, an mtime no newer
    than the previous successful read cannot prove when the new bytes appeared.
    Missing, malformed or future timestamps also use the first successful read
    and expose ``timestamp_untrusted``. A failed first read establishes no time.
    """
    if (not _text(identity) or not _text(version) or not isinstance(kind, str) or kind not in _KINDS
            or type(successful_read) is not bool
            or kind != 'file' and modified_at is not None
            or kind != 'generated' and created_at is not None):
        _invalid('Classification observations require an exact live input identity and version.')
    try:
        observed = None if observed_at is None else _time(observed_at)
    except (TypeError, ValueError, OverflowError):
        _invalid('Classification observations require a timezone-aware recording time.')
    if successful_read and observed is None:
        _invalid('A successful classification input read requires an observation time.')
    prior, prior_times = (None, {}) if previous is None else _read_observation(previous)
    if prior is not None and prior['identity'] != identity:
        _invalid('A prior classification observation must belong to the same input identity.')
    if (prior is not None and successful_read and prior_times['lastObservedAt'] is not None
            and observed < prior_times['lastObservedAt']):
        _invalid('Classification observation times must not precede the last successful read.')
    same = prior is not None and (prior['version'], prior['kind']) == (version, kind)
    if same and prior_times['firstObservedAt'] is not None:
        # Saving unchanged bytes, scanning or using a completed cache result is
        # not a new input version. In particular, an mtime-only touch cannot
        # postpone eligibility, nor can a repaired mtime erase its fallback.
        result = {**prior, 'faults': list(prior['faults'])}
        if successful_read:
            result['lastObservedAt'] = _utc(observed)
        return result

    timestamp = None
    raw_time = modified_at if kind == 'file' else created_at if kind == 'generated' else None
    if raw_time is not None:
        try:
            timestamp = _time(raw_time)
        except (TypeError, ValueError, OverflowError):
            pass  # A source timestamp is evidence to assess, not a clock to trust.
    result = {'schema': OBSERVATION_SCHEMA, 'identity': identity, 'version': version, 'kind': kind,
              'firstObservedAt': _utc(observed) if successful_read else None,
              'lastObservedAt': _utc(observed) if successful_read else None,
              'changedAt': None, 'timeSource': 'unavailable', 'faults': []}
    if kind != 'deleted':
        result['modifiedAt' if kind == 'file' else 'createdAt'] = _utc(timestamp) if timestamp is not None else None
    if not successful_read:
        return result
    trusted = (timestamp is not None and timestamp <= observed
               and (kind != 'file' or prior is None or prior_times['lastObservedAt'] is None
                    or timestamp > prior_times['lastObservedAt']))
    if kind == 'deleted':
        changed, source = observed, 'observation'
    elif trusted:
        changed, source = timestamp, 'modification' if kind == 'file' else 'creation'
    else:
        changed, source = observed, 'observation'
        result['faults'] = ['timestamp_untrusted']
    result['changedAt'], result['timeSource'] = _utc(changed), source
    return result


@dataclass(frozen=True)
class ClassificationEligibility:
    eligible_at: str | None
    eligible: bool
    status: str
    faults: tuple[dict[str, str], ...] = ()

    def as_dict(self) -> dict:
        return {'eligibleAt': self.eligible_at, 'eligible': self.eligible, 'status': self.status,
                'faults': [dict(fault) for fault in self.faults]}


def classification_eligibility(observations: Sequence[Mapping], *, at,
                               debounce_seconds: int = DEFAULT_DEBOUNCE_SECONDS) -> ClassificationEligibility:
    """Use the newest required live input time, independently of cache identity."""
    if (not isinstance(observations, Sequence) or isinstance(observations, (str, bytes))
            or not observations or type(debounce_seconds) is not int or debounce_seconds < 0):
        _invalid('Classification eligibility requires live observations and a nonnegative quiet period.')
    try:
        now = _time(at)
    except (TypeError, ValueError, OverflowError):
        _invalid('Classification eligibility requires a timezone-aware recording time.')
    seen, changed, faults = set(), [], []
    unavailable = False
    for value in observations:
        record, times = _read_observation(value)
        if record['identity'] in seen:
            _invalid('A classification guard set must contain each live input identity once.')
        seen.add(record['identity'])
        faults.extend({'identity': record['identity'], 'reason': fault} for fault in record['faults'])
        if times['changedAt'] is None:
            unavailable = True
        else:
            changed.append(times['changedAt'])
    faults.sort(key=lambda fault: (fault['identity'], fault['reason']))
    if unavailable:
        return ClassificationEligibility(None, False, 'pending_debounce', tuple(faults))
    try:
        eligible_at = max(changed) + timedelta(seconds=debounce_seconds)
    except OverflowError:
        _invalid('The classification quiet period exceeds the supported time range.')
    eligible = now >= eligible_at
    return ClassificationEligibility(_utc(eligible_at), eligible,
                                     'pending_jev' if eligible else 'pending_debounce', tuple(faults))
