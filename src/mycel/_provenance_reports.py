"""Finite reports of committed provenance, freshness and exact-pair work.

These readers do not scan files, retry references, reconcile work or execute a
model. Their counts and evidence describe one read-only repeatable-read view.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy

from ._drift_store import DriftStore, STATUSES, JUDGEMENTS
from ._errors import MycelError
from ._locks import snapshot_transaction
from ._resolver import require_read_transaction
from ._refs import _REFS_SQL, _RELATED_REFS_SQL, _reports, _related_reports, _place
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address
from ._store import checked_store


def _bad():
    raise MycelError('store_format', 'The provenance report has incompatible retained place or reason metadata.')


def _qualified_place(value):
    try:
        if not isinstance(value, dict):
            _bad()
        parsed = parse_source_address(value['address'])
        result = _place(parsed)
        if parsed.root is None or value != result:
            _bad()
        return result
    except (KeyError, TypeError, ValueError, SourceAddressError):
        _bad()


def source_pair_key(drift, source):
    """Match the classifier's exact dependency/version/input candidate key."""
    return (drift['version'], source['dependency'],
            source['classification'].get('inputHash') or source['pairHash'])


def report_counts(drifts, regeneration=()):
    """Count work bundles, exact source pairs and their retained stages apart.

    Counts cover all retained records, independently of the listing filters.
    Current and inactive stages include supported/closed pair evidence, but
    exclude obsolete attempts in history. Pair openness follows its own active
    reason, so one supported pair does not close another pair's work bundle.
    """
    buckets = ('currentOpen', 'currentClosed', 'inactiveOpen', 'inactiveClosed')
    work = dict.fromkeys(buckets, 0)
    pairs = dict.fromkeys(buckets, 0)
    stages = {name: 0 for name in sorted(STATUSES)}
    inactive_stages = dict(stages)
    judgements = {name: 0 for name in sorted(JUDGEMENTS)}
    inactive_judgements = dict(judgements)
    candidates = {}
    faults = set()
    inactive_versions = set()
    for drift in drifts:
        if drift.get('closed', {}).get('disposition') == 'obsolete':
            continue
        prefix = 'current' if drift['current'] else 'inactive'
        work[prefix + ('Open' if drift['state'] == 'open' else 'Closed')] += 1
        if not drift['current']:
            inactive_versions.add((drift['chunkId'], drift['version']))
        for source in drift['sources']:
            key = (prefix, *source_pair_key(drift, source))
            classification = source['classification']
            status = classification['status']
            judgement = classification.get('judgement')
            if status not in stages or judgement is not None and judgement not in judgements:
                _bad()
            value = (bool(source['active']), status, judgement)
            if key in candidates and candidates[key] != value:
                _bad()
            candidates[key] = value
            if (drift['current'] and source['active']
                    and (source['kind'] in {'ref_fault', 'baseline_missing'} or status == 'error')):
                faults.add(key)
    for (prefix, *_), (active, status, judgement) in candidates.items():
        pairs[prefix + ('Open' if active else 'Closed')] += 1
        (stages if prefix == 'current' else inactive_stages)[status] += 1
        if status == 'complete':
            (judgements if prefix == 'current' else inactive_judgements)[judgement] += 1
    return {'work': work, 'pairs': pairs, 'stages': stages,
            'inactiveStages': inactive_stages, 'judgements': judgements,
            'inactiveJudgements': inactive_judgements,
            'unresolvedFaults': len(faults), 'inactiveVersions': len(inactive_versions),
            'regeneration': len(regeneration)}


def stale_chunks(rows):
    """Project complete current reasons with canonical root-aware places."""
    chunks = {}
    for row in rows:
        (reason_id, chunk_id, version_id, version, kind, chunk_metadata,
         located, file_repository, root, path, file_metadata, dependency, reason) = row
        try:
            if kind == 'index':
                address = SourceAddress(file_repository, 'index', located['path'], located['name'])
            elif kind == 'disk':
                if 'root' in file_metadata or 'path' in file_metadata:
                    root, path = file_metadata['root'], file_metadata['path']
                address = SourceAddress(file_repository, root, path,
                    located.get('name', chunk_metadata.get('name')))
                if address.root not in {'code', 'artifact'} or address.name is None:
                    _bad()
            else:
                _bad()
            place = _place(address)
            copied = deepcopy(reason)
            if copied['kind'] not in {'source_changed', 'source_removed', 'related_changed', 'upstream_stale'}:
                _bad()
            if copied['edge'] not in {'declared', 'asserted', 'related', 'generated'}:
                _bad()
            copied['source'] = _qualified_place(copied['source'])
            if 'via' in copied:
                if not isinstance(copied['via'], list):
                    _bad()
                copied['via'] = [_qualified_place(value) for value in copied['via']]
            if 'classification' in copied and not isinstance(copied['classification'], dict):
                _bad()
            copied['id'] = str(reason_id)
            copied['dependency'] = str(dependency) if dependency is not None else copied.get('relation')
            key = (str(chunk_id), version_id)
            if key not in chunks:
                chunks[key] = {'id': str(chunk_id), 'version': version, 'chunk': place, 'reasons': {}}
            elif chunks[key]['chunk'] != place:
                _bad()
            chunks[key]['reasons'][str(reason_id)] = copied
        except (KeyError, TypeError, ValueError, SourceAddressError):
            _bad()
    result = []
    for chunk in chunks.values():
        reasons = sorted(chunk['reasons'].values(), key=lambda value:
            (value['kind'] == 'upstream_stale', value['source']['address'],
             tuple(place['address'] for place in value.get('via', ())),
             value['kind'], value['edge'], value['id']))
        sources = {value['source']['address']: value['source'] for value in reasons}
        result.append({**chunk, 'reasons': reasons,
                       'sources': [sources[address] for address in sorted(sources)]})
    return sorted(result, key=lambda chunk: (chunk['chunk']['address'], chunk['version'], chunk['id']))


def reference_counts(references):
    """Count current physical declaration occurrences, including related refs."""
    current = [ref for ref in references if ref['location']['kind'] == 'disk'
               and ref['ownerLocationAvailable']]
    return {'refs': len(current),
            'unresolvedRefs': sum(ref['state'] == 'unresolved' for ref in current),
            'invalidRefs': sum(ref['fault'] in {'unknown_repository', 'disabled_repository'} for ref in current),
            'refFaults': sum(ref['fault'] is not None for ref in current)}


class ProvenanceReports:
    def __init__(self, connection, settings=None):
        self.connection, self.settings = connection, settings

    def _drifts(self, repository):
        require_read_transaction(self.connection)
        store = DriftStore(self.connection)
        records = [store._wire(row) for row in store._rows((repository,))]
        records.sort(key=lambda drift: (drift['chunk']['address'], drift['version'], drift['openedAt'], drift['id']))
        rows = self.connection.execute(_REGENERATION_SQL, (repository,)).fetchall()
        regeneration = []
        for identifier, version, metadata in rows:
            try:
                place = _place(SourceAddress(repository, 'index', metadata['path'], metadata['name']))
            except (KeyError, TypeError, ValueError, SourceAddressError):
                _bad()
            regeneration.append({'chunkId': str(identifier), 'version': version,
                                 'state': 'regeneration', 'place': place})
        return records, regeneration

    def drifts_in_snapshot(self, repository, *, closed=False, all_versions=False):
        if type(closed) is not bool or type(all_versions) is not bool:
            raise MycelError('invalid_input', 'Drift reporting options must be explicit booleans.')
        records, regeneration = self._drifts(repository)
        selected = [record for record in records if (closed or record['state'] == 'open')
                    and (all_versions or record['current'])]
        return {'repository': repository, 'drifts': selected, 'regeneration': regeneration,
                'counts': report_counts(records, regeneration)}

    def stale_in_snapshot(self, repository):
        require_read_transaction(self.connection)
        rows = self.connection.execute(_STALE_SQL, (repository,)).fetchall()
        if self.settings is not None and self.settings.values['repos'][repository].get('code_clones'):
            from ._scope import RepositoryLocations
            from ._staleness import inactive_policy_links, _stored_link
            selected = RepositoryLocations(self.settings).named(repository)[0]
            inactive = inactive_policy_links(self.connection, self.settings)
            rows = [row for row in rows if _stored_link(row[11], row[12]) not in inactive
                and (row[4] == 'index' or row[10].get('captureLocation', {}).get('clone') == selected.location)]
        chunks = stale_chunks(rows)
        return {'repository': repository, 'stale': chunks, 'count': len(chunks)}

    def status_in_snapshot(self, repository):
        require_read_transaction(self.connection)
        references = [ref for row in self.connection.execute(_REFS_SQL, (repository,)).fetchall()
                      for ref in _reports(row)]
        references.extend(ref for row in self.connection.execute(_RELATED_REFS_SQL, (repository,)).fetchall()
                          for ref in _related_reports(row))
        chunks, stale = self.connection.execute(_CURRENT_COUNTS_SQL, (repository,)).fetchone()
        records, regeneration = self._drifts(repository)
        return {'repository': repository, 'chunks': chunks, 'stale': stale,
                **reference_counts(references), 'drifts': report_counts(records, regeneration)}

    def drifts(self, repository, *, closed=False, all_versions=False):
        with checked_store(self.connection), snapshot_transaction(self.connection):
            return self.drifts_in_snapshot(repository, closed=closed, all_versions=all_versions)

    def stale(self, repository):
        with checked_store(self.connection), snapshot_transaction(self.connection):
            return self.stale_in_snapshot(repository)

    def status(self, repository):
        with checked_store(self.connection), snapshot_transaction(self.connection):
            return self.status_in_snapshot(repository)


def _handle(invocation, report, **options):
    from ._cli import for_repositories, invocation_store
    with ExitStack() as stack:
        reports = None

        def prepare():
            nonlocal reports
            connection, _ = stack.enter_context(invocation_store(invocation))
            stack.enter_context(snapshot_transaction(connection))
            reports = ProvenanceReports(connection, invocation.settings)

        return for_repositories(invocation,
            lambda repository: getattr(reports, report)(repository.name, **options),
            needs_folders=False, prepare=prepare)


def handle_drifts(invocation):
    arguments = invocation.arguments
    if (any(argument not in {'--closed', '--all-versions'} for argument in arguments)
            or len(set(arguments)) != len(arguments)):
        raise MycelError('invalid_input', 'Use drifts with repository selectors, --closed and --all-versions only.')
    return _handle(invocation, 'drifts_in_snapshot', closed='--closed' in arguments,
                   all_versions='--all-versions' in arguments)


def handle_stale(invocation):
    if invocation.arguments:
        raise MycelError('invalid_input', 'Use stale with repository selectors only.')
    return _handle(invocation, 'stale_in_snapshot')


def handle_status(invocation):
    if invocation.arguments:
        raise MycelError('invalid_input', 'Use status with repository selectors only.')
    from ._repository_status import report_status
    return report_status(invocation)


_STALE_SQL = """SELECT r.id,c.id,v.id,v.snapshot_hash,l.kind,v.metadata,l.metadata,
       c.repository,f.root,f.path,fl.metadata,r.dependency,r.reason
FROM public.mycel_stale_reasons r
JOIN public.mycel_chunk_versions v ON v.id=r.chunk_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id AND c.repository=r.repository
JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind IN ('disk','index')
LEFT JOIN public.mycel_file_locations fl ON fl.id=l.file_location AND fl.kind='disk'
LEFT JOIN public.mycel_file_versions fv ON fv.id=fl.file_version
LEFT JOIN public.mycel_files f ON f.id=fv.file_id AND f.repository=c.repository
WHERE r.repository=%s ORDER BY c.id,v.id,r.id,l.id"""

_CURRENT_COUNTS_SQL = """SELECT count(DISTINCT v.id),
       count(DISTINCT v.id) FILTER (WHERE EXISTS (
         SELECT 1 FROM public.mycel_stale_reasons r
         WHERE r.chunk_version=v.id AND r.repository=c.repository))
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind IN ('disk','index')
WHERE c.repository=%s"""

_REGENERATION_SQL = """SELECT DISTINCT c.id,v.snapshot_hash,l.metadata
FROM public.mycel_generated_state g JOIN public.mycel_chunks c ON c.id=g.chunk_id
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index'
JOIN public.mycel_stale_reasons s ON s.chunk_version=v.id
WHERE c.repository=%s ORDER BY c.id,v.snapshot_hash"""
