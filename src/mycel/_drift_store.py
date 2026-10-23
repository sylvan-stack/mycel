"""Offline exact-pair semantic work, independent of mechanical freshness.

Detection owns stale marks; this projection owns work and retained attempts.
The result sink is a private boundary for scripted/validated classifier stages,
not a provider adapter. Its pair hash guards the local evidence bundle; MYC-14's
versioned model request/hash assembly is a separate boundary.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from ._errors import MycelError
from ._declared_refs import _raw as _raw_hex, _stored
from ._evidence import (CaptureLocation, EvidenceError, EvidenceStore, SnapshotEvidence, _chunk_snapshot,
                       canonical_json, capture_baseline, snapshot)
from ._locks import atomic_transaction, operation_guard, read_snapshot, require_transaction_guards
from ._reconciliation import _place_payload
from ._resolver import SourceResolver
from ._source_refs import SourceAddressError, parse_source_address
from ._staleness import _NODES, _eligible, _links, _raw, _resolve, _stored_link, inactive_policy_links
from ._store import checked_store


SCHEMA = 'mycel-drift-work-v1'
STATUSES = {'pending_debounce', 'pending_jev', 'needs_llm_review', 'complete', 'error'}
JUDGEMENTS = {'still_supported', 'needs_review', 'insufficient_evidence'}
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_CLOSURES = {'still_supported', 'edited', 'confirmed', 'source_restored', 'ref_removed',
             'heartwood', 'generated', 'version_removed'}


def _invalid(message):
    raise MycelError('invalid_input', message)


def _copy(value):
    try:
        result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
        def validate(item):
            if isinstance(item, str):
                item.encode('utf-8', errors='strict')
                if '\0' in item:
                    raise ValueError()
            elif isinstance(item, dict):
                for key, member in item.items():
                    validate(key)
                    validate(member)
            elif isinstance(item, list):
                for member in item:
                    validate(member)
        validate(result)
        return result
    except (TypeError, ValueError, OverflowError, UnicodeError):
        _invalid('Classification evidence must be finite JSON data.')


def _time(at):
    if at is None:
        return datetime.now(timezone.utc).isoformat(timespec='microseconds')
    try:
        parsed = datetime.fromisoformat(at.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (AttributeError, TypeError, ValueError):
        _invalid('Drift work requires a timezone-aware recording time.')


def _uuid(identifier):
    try:
        return str(UUID(str(identifier)))
    except (TypeError, ValueError, AttributeError):
        _invalid('Drift work requires an exact record UUID.')


def _base_reason(reason):
    return {key: value for key, value in reason.items() if key != 'classification'}


def _key(dependency, reason):
    return str(uuid5(NAMESPACE_URL, 'mycel:drift-reason:' + str(dependency) + ':' +
                     canonical_json(_base_reason(reason)).decode()))


def _closed_source(source, at, because):
    result = _copy(source)
    result['active'] = False
    result['closed'] = {'at': at, 'because': because}
    return result


class DriftStore:
    """Maintain one guarded work bundle for each exact dependant version.

    JSON state uses the format-2 reserved Drift table and independent evidence
    ownership. Source/ref/related reasons never require a dependency FK, so a
    removal or malformed ref cannot make the record impossible to retain.
    """
    def __init__(self, connection):
        self.connection = connection

    def reconcile(self, settings, repository, *, at=None):
        """Explicit offline reconciliation; neither ingest nor model execution."""
        settings.require_valid(require_store=False)
        if not settings.values['repos'].get(repository, {}).get('enabled'):
            _invalid('Drift reconciliation requires an enabled registered repository.')
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            for owner in _eligible(settings):
                stack.enter_context(operation_guard(self.connection, owner, 'pass'))
            with atomic_transaction(self.connection):
                self.sync_in_transaction(settings, (repository,), at=at)
        return self.list(repository)

    def _rows(self, repositories, *, lock=False):
        # Format 2 reserved this table before its lifecycle producer existed.
        # Closed pre-feature evidence/history bundles retain their ownership
        # and FK behavior. Unknown open work must be rejected, never hidden
        # while a second open bundle is created for its dependant version.
        return self.connection.execute('SELECT id,repository,dependant_version,opened_at,closed_at,state,evidence_owner '
            "FROM public.mycel_drifts WHERE repository=ANY(%s) AND (state->>'schema'=%s OR closed_at IS NULL) ORDER BY opened_at,id" +
            (' FOR UPDATE NOWAIT' if lock else ''), (list(repositories), SCHEMA)).fetchall()

    def _validate(self, row):
        identifier, repository, version, _, closed_at, state, owner = row
        def bad():
            raise MycelError('store_format', 'The Drift work record has incompatible retained state.')
        def digest(value):
            return isinstance(value, str) and _HASH.fullmatch(value) is not None
        def known(value, choices):
            return isinstance(value, str) and value in choices
        def identifier_value(value):
            try:
                return isinstance(value, str) and str(UUID(value)) == value
            except (ValueError, AttributeError, TypeError):
                return False
        def place(value, *, dependant=False):
            if not isinstance(value, dict) or not isinstance(value.get('address'), str):
                bad()
            try:
                parsed = parse_source_address(value['address'])
            except (SourceAddressError, TypeError):
                if dependant or set(value) != {'address', 'repository'} or not isinstance(value['repository'], str):
                    bad()
                return
            if value != _place_payload(parsed) or dependant and (parsed.repository != repository
                    or parsed.root not in {'code', 'artifact'} or parsed.name is None):
                bad()
        def closure(value):
            if not isinstance(value, dict) or not known(value.get('because'), _CLOSURES) or not isinstance(value.get('at'), str):
                bad()
            try:
                parsed = datetime.fromisoformat(value['at'].replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    bad()
            except (TypeError, ValueError):
                bad()
            return parsed
        if (not isinstance(state, dict) or state.get('schema') != SCHEMA
                or not isinstance(state.get('sources'), list) or not state['sources'] or not isinstance(state.get('history'), list)
                or not identifier_value(state.get('chunkId')) or not digest(state.get('version'))
                or type(state.get('versionId')) is not int or state['versionId'] < 1
                or version is not None and state['versionId'] != version
                or version is None and closed_at is None):
            bad()
        place(state.get('chunk'), dependant=True)
        observations = state.get('classificationObservations', {})
        requests = state.get('classificationRequests', {})
        if not isinstance(observations, dict) or not isinstance(requests, dict):
            bad()
        from ._classification_eligibility import _read_observation
        for identity, observation in observations.items():
            checked, _ = _read_observation(observation)
            if identity != checked['identity']:
                bad()
        request_fields = {'schema', 'source', 'pairHash', 'payloadSnapshot', 'bundle', 'guards',
                          'bundleSnapshot', 'fullManifests', 'recordedAt'}
        for input_hash, request in requests.items():
            if (not digest(input_hash) or not isinstance(request, dict) or set(request) != request_fields
                    or request['schema'] != 'mycel-classification-request-v1'
                    or not identifier_value(request['source']) or not digest(request['pairHash'])
                    or request['payloadSnapshot'] != 'snapshot:' + input_hash
                    or not isinstance(request['bundle'], dict) or not isinstance(request['guards'], dict)
                    or not isinstance(request['bundleSnapshot'], str)
                    or not request['bundleSnapshot'].startswith('snapshot:')
                    or not digest(request['bundleSnapshot'].removeprefix('snapshot:'))
                    or not isinstance(request['fullManifests'], list)
                    or any(not digest(value) for value in request['fullManifests'])
                    or not isinstance(request['recordedAt'], str)):
                bad()
            try:
                recorded = datetime.fromisoformat(request['recordedAt'].replace('Z', '+00:00'))
                if recorded.tzinfo is None:
                    bad()
            except (TypeError, ValueError):
                bad()
        if version is not None:
            binding = self.connection.execute('SELECT c.id,v.snapshot_hash FROM public.mycel_chunk_versions v '
                'JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE v.id=%s AND c.repository=%s', (version, repository)).fetchone()
            if binding is None or (str(binding[0]), binding[1]) != (state['chunkId'], state['version']):
                bad()
        seen = set()
        for source in state['sources']:
            if (not isinstance(source, dict) or not identifier_value(source.get('id')) or source['id'] in seen
                    or not identifier_value(source.get('dependency')) or type(source.get('active')) is not bool
                    or not digest(source.get('pairHash')) or not known(source.get('kind'),
                    {'source_changed', 'source_removed', 'related_changed', 'upstream_stale', 'ref_fault', 'baseline_missing'})
                    or not known(source.get('link'), {'declared', 'asserted', 'related', 'generated'})):
                bad()
            seen.add(source['id'])
            place(source.get('source'))
            payload, classification = source.get('input'), source.get('classification')
            if (not isinstance(payload, dict) or payload.get('schema') != 'mycel-drift-pair-v1'
                    or payload.get('dependency') != source['dependency'] or payload.get('link') != source['link']
                    or not isinstance(payload.get('reason'), dict) or payload['reason'].get('kind') != source['kind']
                    or payload['reason'].get('source') != source['source'] or payload['reason'].get('edge') != source['link']
                    or not isinstance(payload.get('ref'), str) or not digest(payload.get('dependantFileHash'))
                    or payload.get('baselineManifest') is not None and not digest(payload['baselineManifest'])
                    or not isinstance(classification, dict) or not known(classification.get('status'), STATUSES)
                    or classification.get('pairHash') != source['pairHash']
                    or classification.get('inputHash') is not None and not digest(classification['inputHash'])
                    or classification.get('judgement') is not None and not known(classification['judgement'], JUDGEMENTS)
                    or classification.get('status') == 'complete' and not known(classification.get('judgement'), JUDGEMENTS)
                    or classification.get('status') in {'error', 'pending_jev', 'pending_debounce'} and 'judgement' in classification
                    or classification.get('status') == 'error' and (not isinstance(classification.get('reason'), str)
                        or not classification['reason'])
                    or 'evidence' in classification and not isinstance(classification['evidence'], dict)):
                bad()
            try:
                if source['id'] != _key(source['dependency'], payload['reason']):
                    bad()
            except (EvidenceError, TypeError, ValueError):
                bad()
            if source.get('staleReason') is not None and not identifier_value(source['staleReason']):
                bad()
            current = payload.get('current')
            if (not isinstance(current, dict) or not known(current.get('state'), {'present', 'deleted', 'away', 'unresolved'})
                    or not isinstance(current.get('members'), list)
                    or current.get('manifest') is not None and not digest(current['manifest'])):
                bad()
            try:
                descriptor = SnapshotEvidence.from_record(payload['dependant'])
                if descriptor.hash != state['version']:
                    bad()
                if current['state'] == 'present':
                    place(current.get('place'))
                    if (not known(current.get('selection'), {'file', 'chunk', 'family'})
                            or not digest(current.get('fileHash')) or not digest(current.get('manifest'))
                            or not current['members']):
                        bad()
                    for member in current['members']:
                        if not isinstance(member, dict) or not identifier_value(member.get('id')):
                            bad()
                        place(member.get('place'))
                        SnapshotEvidence.from_record(member['evidence'])
                fingerprint = json.loads(canonical_json(payload))
                fingerprint['current'].pop('manifest', None)
                if sha256(canonical_json(fingerprint)).hexdigest() != source['pairHash']:
                    bad()
            except (EvidenceError, KeyError, TypeError, ValueError):
                bad()
            if source['active']:
                if 'closed' in source or (classification['status'] == 'complete'
                        and classification.get('judgement') == 'still_supported'):
                    bad()
            else:
                closure(source.get('closed'))
        active = any(source['active'] for source in state['sources'])
        if closed_at is None:
            if 'closed' in state or not active:
                bad()
        else:
            if active:
                bad()
            recorded = closure(state.get('closed'))
            expected = (datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
                        if isinstance(closed_at, str) else closed_at)
            if recorded != expected:
                bad()
        owning = self.connection.execute('SELECT repository,kind,identity FROM public.mycel_evidence_owners '
            'WHERE id=%s', (owner,)).fetchone()
        if owning != (repository, 'drift', str(identifier)):
            bad()
        return state

    def _retain(self, repository, owner, blobs=(), captures=()):
        """Append verified references; closed/obsolete attempts keep their bytes."""
        require_transaction_guards(self.connection, (repository,))
        snapshots = {blob.evidence.hash: blob for blob in blobs}
        manifests = {}
        for capture in captures:
            manifests[capture.manifest.identifier] = capture.manifest
            snapshots.update((blob.evidence.hash, blob) for blob in capture.snapshots)
        for digest, blob in sorted(snapshots.items()):
            metadata = {'schema': 1, 'bytes': len(blob.source), 'encoding': blob.evidence.encoding}
            self.connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (repository, digest, blob.source, Jsonb(metadata)))
            row = self.connection.execute('SELECT bytes,metadata FROM public.mycel_snapshots '
                'WHERE repository=%s AND hash=%s', (repository, digest)).fetchone()
            if row is None or bytes(row[0]) != blob.source or row[1] != metadata:
                raise EvidenceError('snapshot_corrupt')
        for digest, manifest in sorted(manifests.items()):
            self.connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (repository, digest, 'baseline', manifest.canonical_bytes, Jsonb({'schema': 1})))
            row = self.connection.execute('SELECT kind,bytes,metadata FROM public.mycel_manifests '
                'WHERE repository=%s AND hash=%s', (repository, digest)).fetchone()
            if row is None or (row[0], bytes(row[1]), row[2]) != ('baseline', manifest.canonical_bytes, {'schema': 1}):
                raise EvidenceError('snapshot_corrupt')
        existing = self.connection.execute('SELECT snapshot_hash,manifest_hash,ordinal FROM public.mycel_evidence_references '
            'WHERE owner=%s ORDER BY ordinal', (owner,)).fetchall()
        known = {(item[0], item[1]) for item in existing}
        ordinal = max((item[2] for item in existing), default=-1) + 1
        refs = [(None, digest) for digest in sorted(manifests)] + [(digest, None) for digest in sorted(snapshots)]
        for ref in refs:
            if ref not in known:
                self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                    (owner, repository, *ref, ordinal))
                ordinal += 1

    def _physical(self, settings, files, declarations, captures, catalog):
        # Reuse the complete no-substitution observation that Detection uses.
        from ._staleness import MechanicalStalenessStore
        try:
            values = MechanicalStalenessStore(self.connection)._physical_inputs(settings, files, declarations, captures)
            if any((len(value) == 5 and (value[3] != (value[2],) or not value[4]))
                   or (len(value) == 4 and not value[3]) for value in values):
                return 'changed_since_ingest'
            for address in declarations:
                expected = tuple(sorted((tuple(sorted((alias.root, alias.path) for alias in file.aliases)), file.source)
                    for file in catalog.files if file.repository == address.repository and any(
                        alias.path == address.path and address.root in {None, alias.root} for alias in file.aliases)))
                observed = next(value[2] for value in values if len(value) == 4 and value[1] == address.address)
                if observed != expected:
                    return 'changed_since_ingest'
        except (MycelError, OSError):
            return 'read_failed'
        return None

    def _retention_conflicts(self, repository, blobs, captures):
        """Observe corrupt durable slots without repairing or claiming them.

        Live indexed bytes can diagnose a conflict, but cannot silently repair
        the private store's evidence metadata or validate a corrupt old pin.
        """
        snapshots = {blob.evidence.hash: blob for blob in blobs}
        for capture in captures:
            snapshots.update((blob.evidence.hash, blob) for blob in capture.snapshots)
        corrupt = set()
        for digest, blob in snapshots.items():
            row = self.connection.execute('SELECT bytes,metadata FROM public.mycel_snapshots '
                'WHERE repository=%s AND hash=%s', (repository, digest)).fetchone()
            expected = {'schema': 1, 'bytes': len(blob.source), 'encoding': blob.evidence.encoding}
            if row is not None and (bytes(row[0]) != blob.source or row[1] != expected):
                corrupt.add(digest)
        invalid_manifests = set()
        for capture in captures:
            manifest = capture.manifest
            row = self.connection.execute('SELECT kind,bytes,metadata FROM public.mycel_manifests '
                'WHERE repository=%s AND hash=%s', (repository, manifest.identifier)).fetchone()
            if (any(blob.evidence.hash in corrupt for blob in capture.snapshots) or row is not None
                    and (row[0], bytes(row[1]), row[2]) != ('baseline', manifest.canonical_bytes, {'schema': 1})):
                invalid_manifests.add(manifest.identifier)
        return corrupt, invalid_manifests

    def _pair(self, settings, catalog, member, file, row, captures):
        """Exact retained pair descriptor; no model request is constructed here."""
        identifier, owner, version, _, natural, kind, state, _, manifest_hash = row
        resolution = _resolve(catalog, row)
        raw = _raw(row)
        required = [file]
        if resolution.selection is not None and resolution.selection.file is not None:
            required.append(resolution.selection.file)
        addresses = ()
        try:
            address = parse_source_address(raw)
            if address.root != 'index' and address.repository in _eligible(settings):
                addresses = (address,)
        except SourceAddressError:
            pass
        fault = self._physical(settings, required, addresses, captures, catalog)
        blobs, retained = [], []
        try:
            dep = _chunk_snapshot(member, file)
        except EvidenceError as error:
            dep = snapshot(member.chunk.source)
            fault = error.status
        blobs.append(dep)
        baseline = None
        if manifest_hash is not None:
            try:
                baseline = EvidenceStore(self.connection)._read_baseline(owner, manifest_hash)
                if (baseline.manifest.payload['dependantId'] != member.chunk.identifier
                        or baseline.manifest.payload['dependantVersion'] != str(version)):
                    raise EvidenceError('baseline_missing')
                retained.append(baseline)
            except EvidenceError as error:
                fault = error.status
        elif state.get('everResolved') or resolution.state == 'resolved':
            fault = 'baseline_missing'
        current = {'state': 'unresolved', 'members': []}
        if resolution.selection is not None:
            selected = resolution.selection
            if selected.file is not None:
                try:
                    capture = capture_baseline(owner, member, file, selected, kind=kind,
                        declaration=raw, captured_at=_time(None), location=CaptureLocation('disk'))
                    blobs.extend(capture.snapshots)
                    retained.append(capture)
                    current = {'state': 'present', 'place': _place_payload(selected.place),
                        'selection': selected.kind, 'fileHash': selected.file.snapshot_hash,
                        'manifest': capture.manifest.identifier,
                        'members': _copy(json.loads(capture.manifest.canonical_bytes)['members'])}
                except EvidenceError as error:
                    fault = error.status
            else:
                fault = 'insufficient_evidence'
        else:
            absence = state.get('sourceAbsence', {}).get('state')
            if resolution.fault in {'missing_file', 'missing_name'} and absence in {'away', 'deleted'}:
                current['state'] = absence
                if absence == 'away':
                    fault = 'source_away'
            else:
                fault = fault or resolution.fault or 'ref_fault'
        corrupt, invalid_manifests = self._retention_conflicts(owner, blobs, retained)
        if corrupt or invalid_manifests:
            fault = fault or 'snapshot_corrupt'
            blobs = [blob for blob in blobs if blob.evidence.hash not in corrupt]
            retained = [capture for capture in retained if capture.manifest.identifier not in invalid_manifests]
            if current.get('manifest') in invalid_manifests:
                current = {**current, 'state': 'unresolved', 'indexedState': current['state'],
                    'evidenceStatus': 'snapshot_corrupt'}
                current.pop('manifest', None)
        descriptor = {'schema': 'mycel-drift-pair-v1', 'dependency': str(identifier), 'link': kind,
            'ref': _stored(raw), 'refHex': _raw_hex(raw), 'baselineManifest': manifest_hash, 'dependant': dep.evidence.as_dict(),
            'dependantFileHash': file.snapshot_hash, 'current': current}
        if any(blob.evidence.encoding != 'utf-8' for blob in blobs) or any(
                blob.evidence.encoding != 'utf-8' for capture in retained for blob in capture.snapshots):
            fault = fault or 'insufficient_evidence'
        if fault is not None:
            descriptor['fault'] = fault
        return descriptor, blobs, retained, fault

    def sync_in_transaction(self, settings, repositories, *, at=None, versions=None,
                            pending=(), closure=None, verification=None, _candidate_pairs=None,
                            captures=None, catalogs=None):
        """Project guarded current reasons, joining the producer's transaction.

        ``versions`` limits Detection's affected closure. Pending faults supply
        unresolved work even when mechanical detection cannot create a mark.
        ``closure`` may map exact version IDs to an owner-authorized event.
        A guarded justification batch passes its ``captures`` and ``catalogs``
        so that each repository is captured and catalogued once per batch.
        """
        settings.require_valid(require_store=False)
        repositories = tuple(sorted(set(repositories)))
        require_transaction_guards(self.connection, repositories)
        at = _time(at)
        catalog = (SourceResolver.from_observation_transaction(self.connection, settings,
            guarded_repositories=repositories) if catalogs is None else
            SourceResolver.from_transaction(self.connection, settings, guarded_repositories=repositories,
                                            catalogs=catalogs))
        files = {chunk.version: (file, member) for file in catalog.files
                 for member in catalog._members(file, file.chunks) for chunk in (member.chunk,)}
        eligible = _eligible(settings)
        # Located file metadata is index data: a batch's guards keep it fixed.
        nodes_key = ('drift-nodes', tuple(eligible))
        located = None if catalogs is None else catalogs.get(nodes_key)
        if located is None:
            located = self.connection.execute(_NODES, (eligible, eligible)).fetchall()
            if catalogs is not None:
                catalogs[nodes_key] = located
        metadata = {version: file_meta for _, _, version, _, _, file_meta in located}
        generated = {str(row[0]) for row in self.connection.execute('SELECT chunk_id FROM public.mycel_generated_state').fetchall()}
        inactive = inactive_policy_links(self.connection, settings)
        rows = [row for row in _links(self.connection, _eligible(settings)) if row[1] in repositories and row[5] != 'generated'
                and str(row[0]) not in inactive and row[2] in files and (versions is None or row[2] in versions)]
        reasons = defaultdict(list)
        stale = self.connection.execute('SELECT id,repository,chunk_version,dependency,reason FROM public.mycel_stale_reasons '
            'WHERE repository=ANY(%s) ORDER BY id', (list(repositories),)).fetchall()
        for stale_id, _, version, dependency, reason in stale:
            reasons[version].append((str(stale_id), _stored_link(dependency, reason), _base_reason(reason)))
        fault_rows = self.connection.execute(
            'SELECT id,repository,chunk_version,declaration,fault FROM public.mycel_ref_faults '
            'WHERE repository=ANY(%s)', (list(repositories),)).fetchall()
        faults = {str(identifier): fault for identifier, _, _, _, fault in fault_rows}
        pending_links = {item.get('dependency'): item.get('reason') for item in pending if item.get('dependency')}
        pending_places = {item.get('chunk', {}).get('address'): item.get('reason') for item in pending
                          if not item.get('dependency')}
        candidates, bundles = defaultdict(dict), defaultdict(lambda: ([], []))
        captures = {} if captures is None else captures
        exemptions = {}
        for version, (file, member) in files.items():
            declarations = metadata.get(version, {}).get('documentDeclarations', {}).get('metadata', {})
            if member.chunk.identifier in generated or declarations.get('generated') is True:
                exemptions[version] = 'generated'
            elif declarations.get('heartwood') is True:
                exemptions[version] = 'heartwood'
        for row in rows:
            identifier, owner, version, _, natural, kind, state, _, _ = row
            if version in exemptions:
                continue
            file, member = files[version]
            descriptor, blobs, baselines, fault = self._pair(settings, catalog, member, file, row, captures)
            bundles[version][0].extend(blobs)
            bundles[version][1].extend(baselines)
            selected = [(stale_id, reason) for stale_id, dependency, reason in reasons[version] if dependency == str(identifier)]
            # A previously resolved explicit absence is classification work;
            # never turn its ordinary missing-path ref report into a second fault.
            ref_fault = faults.get(str(identifier))
            absence = descriptor['current']['state']
            if ref_fault is not None and not (state.get('everResolved') and absence in {'away', 'deleted'}):
                selected.append((None, {'kind': 'ref_fault', 'source': self._source(natural, _raw(row), member), 'edge': kind}))
            for occurrence in state.get('occurrences', ()):
                if occurrence.get('syntaxFault'):
                    selected.append((None, {'kind': 'ref_fault', 'source': self._source(natural, _raw(row), member),
                        'edge': kind, 'fault': occurrence['syntaxFault'], 'occurrence': _copy(occurrence)}))
            if fault is not None and not selected:
                selected.append((None, {'kind': 'baseline_missing' if fault == 'baseline_missing' else 'ref_fault',
                    'source': self._source(natural, _raw(row), member), 'edge': kind}))
            fault = pending_links.get(str(identifier), fault)
            upstream_unchecked = pending_places.get(member.place.address)
            if upstream_unchecked and not selected and kind != 'related':
                selected.append((None, {'kind': 'upstream_stale',
                    'source': self._source(natural, _raw(row), member), 'edge': kind}))
                fault = fault or upstream_unchecked
            if fault is not None:
                descriptor['fault'] = fault
            for stale_id, reason in selected:
                key = _key(identifier, reason)
                pair = {**descriptor, 'reason': reason}
                fingerprint = _copy(pair)
                fingerprint['current'].pop('manifest', None)  # observation time is outside exact pair identity
                pair_hash = sha256(canonical_json(fingerprint)).hexdigest()
                unresolved = fault or ('upstream_stale' if reason['kind'] == 'upstream_stale' else
                    reason.get('fault') or (ref_fault.get('fault') if ref_fault else None) or 'ref_fault'
                    if reason['kind'] == 'ref_fault' else None)
                classification = {'status': 'error' if unresolved else 'pending_jev', 'pairHash': pair_hash}
                if unresolved:
                    classification['reason'] = unresolved
                source = {'id': key, 'dependency': str(identifier), 'source': reason['source'], 'kind': reason['kind'],
                    'link': kind, 'active': True, 'pairHash': pair_hash, 'input': pair, 'classification': classification}
                if reason.get('via'):
                    source['via'] = reason['via']
                if reason.get('occurrence'):
                    source['occurrence'] = reason['occurrence']
                if stale_id:
                    source['staleReason'] = stale_id
                candidates[version][key] = source
        # Fault occurrences without an eligible link still own visible work.
        # An off-disk link's fault cannot be borrowed by the current branch.
        represented = {str(row[0]) for row in rows}
        for identifier, owner, version, declaration, fault in fault_rows:
            if (str(identifier) in represented or version not in files or version in exemptions
                    or versions is not None and version not in versions):
                continue
            linked = self.connection.execute('SELECT state FROM public.mycel_dependencies WHERE id=%s '
                'UNION ALL SELECT state FROM public.mycel_relations WHERE id=%s', (identifier, identifier)).fetchall()
            if linked:  # exact location owners that _links did not select are inactive
                continue
            file, member = files[version]
            dep = snapshot(member.chunk.source)
            corrupt, _ = self._retention_conflicts(owner, (dep,), ())
            reason = {'kind': 'ref_fault', 'source': self._source('', declaration, member), 'edge': 'declared'}
            descriptor = {'schema': 'mycel-drift-pair-v1', 'dependency': str(identifier), 'link': 'declared',
                'ref': declaration, 'baselineManifest': None, 'dependant': dep.evidence.as_dict(),
                'dependantFileHash': file.snapshot_hash, 'current': {'state': 'unresolved', 'members': []},
                'fault': 'snapshot_corrupt' if corrupt else fault.get('fault') or 'ref_fault', 'reason': reason}
            key = _key(identifier, reason)
            pair_hash = sha256(canonical_json(descriptor)).hexdigest()
            candidates[version][key] = {'id': key, 'dependency': str(identifier), 'source': reason['source'],
                'kind': 'ref_fault', 'link': 'declared', 'active': True, 'pairHash': pair_hash, 'input': descriptor,
                'classification': {'status': 'error', 'pairHash': pair_hash, 'reason': descriptor['fault']}}
            if not corrupt:
                bundles[version][0].append(dep)
        if _candidate_pairs is not None:
            _candidate_pairs.update(((version, identifier), source['pairHash'])
                for version, sources in candidates.items() for identifier, source in sources.items())
        old = self._rows(repositories, lock=True)
        by_version = {}
        for row in old:
            state = self._validate(row)
            if row[2] is not None:
                if row[2] in by_version:
                    raise MycelError('store_format', 'A dependant version has duplicate Drift work bundles.')
                by_version[row[2]] = row
        changed = set()
        selected_versions = {version for version, (file, _) in files.items() if file.repository in repositories
                             and (versions is None or version in versions)}
        for version in sorted(selected_versions):
            file, member = files[version]
            desired = candidates[version]
            previous = by_version.get(version)
            if previous is None and not desired:
                continue
            if previous is None:
                identifier, owner = uuid4(), uuid4()
                self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
                    (owner, file.repository, 'drift', str(identifier)))
                state = {'schema': SCHEMA, 'chunkId': member.chunk.identifier, 'versionId': version,
                    'version': member.chunk.snapshot_hash, 'chunk': _place_payload(member.place), 'sources': [], 'history': []}
                self.connection.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,%s,%s,NULL,%s,%s)',
                    (identifier, file.repository, version, at, Jsonb(state), owner))
                previous = (identifier, file.repository, version, datetime.fromisoformat(at), None, state, owner)
            state = _copy(previous[5])
            state['chunk'] = _place_payload(member.place)
            prior = {source['id']: source for source in state['sources']}
            composed = []
            for key, source in desired.items():
                saved = prior.pop(key, None)
                if (saved is not None and saved['pairHash'] == source['pairHash']
                        and (saved['active'] or saved.get('closed', {}).get('because') == 'still_supported')):
                    source = saved  # exact suppression/stage/evidence survives repeated detection
                elif saved is not None:
                    from ._drift_retention import DriftHistoryStore
                    bundle = (saved.get('historyBundle') or
                        DriftHistoryStore(self.connection).archive_source_in_transaction(
                            previous, saved, state, at=at))
                    state['history'].append({'at': at, 'because': 'input_changed', 'source': saved,
                                             'bundle': bundle})
                composed.append(source)
            ended = []
            for source in prior.values():
                if source['dependency'] in inactive:
                    composed.append(source)
                    continue
                if (not source['active'] and source.get('closed', {}).get('because') == 'still_supported'
                        and not source.get('historyBundle')):
                    # This suppressed exact input is no longer a current
                    # candidate. Retire its support before a withdrawal or
                    # restoration can accumulate unbounded closed pairs in
                    # otherwise open work; the archive keeps its old closure.
                    because = exemptions.get(version) or (closure or {}).get(version)
                    if because is None:
                        present = any(str(row[0]) == source.get('dependency') for row in rows)
                        because = 'source_restored' if present else 'ref_removed'
                    from ._drift_retention import DriftHistoryStore
                    bundle = DriftHistoryStore(self.connection).archive_source_in_transaction(
                        previous, source, state, at=at)
                    source = _closed_source(source, at, because)
                    source['historyBundle'] = bundle
                    ended.append(because)
                if source['active']:
                    because = exemptions.get(version) or (closure or {}).get(version)
                    if because is None:
                        present = any(str(row[0]) == source.get('dependency') for row in rows)
                        because = 'source_restored' if present else 'ref_removed'
                    source = _closed_source(source, at, because)
                    ended.append(because)
                composed.append(source)
            state['sources'] = sorted(composed, key=lambda source: (source['source'].get('address', ''), source['kind'], source['link'], source['id']))
            active = any(source['active'] for source in state['sources'])
            if active:
                from ._drift_retention import DriftHistoryStore
                history_store = DriftHistoryStore(self.connection)
                for source in state['sources']:
                    if (not source['active'] and not source.get('historyBundle')
                            and source.get('closed', {}).get('because') != 'still_supported'):
                        source['historyBundle'] = history_store.archive_source_in_transaction(
                            previous, source, state, at=source['closed']['at'])
                # Format-2 work may predate independent bounded bundles.
                # Transfer retained historical inputs before releasing any refs.
                for event in list(state['history']):
                    if (event.get('because') == 'input_changed' and not event.get('bundle')
                            and isinstance(event.get('source'), dict)):
                        event['bundle'] = history_store.archive_source_in_transaction(
                            previous, event['source'], state, at=event['at'])
            if active:
                state.pop('closed', None)
                closed_at = None
            else:
                because = exemptions.get(version) or (closure or {}).get(version) or (ended[-1] if ended else
                    state.get('closed', {}).get('because', 'still_supported'))
                if ended:
                    state['closed'] = {'at': at, 'because': because}
                else:
                    state.setdefault('closed', {'at': at, 'because': because})
                if verification is not None and because == 'confirmed':
                    state['closed']['verification'] = _copy(verification)
                closed_at = state['closed']['at']
            if state != previous[5] or (previous[4] is None) != (closed_at is None):
                self._write(previous[0], state, closed_at)
                changed.add(file.repository)
            retained_hashes = {source['input'].get('baselineManifest') for source in state['sources']}
            retained_hashes.update(source['input']['current'].get('manifest') for source in state['sources'])
            self._retain(file.repository, previous[6], bundles[version][0],
                tuple(capture for capture in bundles[version][1] if capture.manifest.identifier in retained_hashes))
            from ._drift_retention import DriftHistoryStore
            DriftHistoryStore(self.connection).retain_live_references_in_transaction(previous, state)
            # Reconciliation publishes work stages in this bundle only. A
            # stale reason's classification remains retained answer evidence;
            # mechanical/no-op/error observation must not overwrite it.
        from ._drift_retention import DriftHistoryStore
        for repository in repositories:
            DriftHistoryStore(self.connection).prune_in_transaction(repository)
        return changed

    @staticmethod
    def _source(natural, raw, dependant):
        try:
            return _place_payload(parse_source_address(natural or raw))
        except (SourceAddressError, TypeError):
            # The malformed spelling is preserved as data, never guessed into an edge.
            return {'address': _stored(raw), 'repository': dependant.place.repository}

    def _write(self, identifier, state, closed_at):
        self.connection.execute('UPDATE public.mycel_drifts SET state=%s,closed_at=%s WHERE id=%s',
            (Jsonb(state), closed_at, identifier))

    def _publish_classification(self, state, *, source_ids=None):
        for source in state['sources']:
            if source_ids is not None and source['id'] not in source_ids:
                continue
            if source.get('staleReason'):
                self.connection.execute("UPDATE public.mycel_stale_reasons SET reason=jsonb_set(reason,'{classification}',%s) "
                    'WHERE id=%s AND chunk_version=%s AND reason->\'classification\' IS DISTINCT FROM %s',
                    (Jsonb(source['classification']), source['staleReason'], state['versionId'], Jsonb(source['classification'])))

    def _classification_publication_inputs(self, settings, row, source):
        """Read the checked inputs around the final annotation write.

        The expected selected annotation is the only excluded output. Exact
        indexed/physical bytes, pins, mechanical reasons and retained ownership
        must remain unchanged, including when a publication callback edits disk.
        """
        from ._staleness import DetectionGuards, MechanicalStalenessStore
        detector = MechanicalStalenessStore(self.connection)
        selected = frozenset((row[5]['chunkId'],))
        detector._scope = (selected, selected, row[1])
        indexed = detector._signature_of(detector._read(settings, DetectionGuards(tuple(_eligible(settings)), {})))
        declarations = []
        for link in indexed[1]:
            try:
                address = parse_source_address(_raw(link))
                if address.root != 'index' and address.repository in _eligible(settings):
                    declarations.append(address)
            except SourceAddressError:
                pass
        owner = self.connection.execute('SELECT * FROM public.mycel_evidence_owners WHERE id=%s', (row[6],)).fetchone()
        references = self.connection.execute('SELECT * FROM public.mycel_evidence_references WHERE owner=%s '
            'ORDER BY ordinal', (row[6],)).fetchall()
        snapshots = self.connection.execute('SELECT s.* FROM public.mycel_snapshots s WHERE (s.repository,s.hash) '
            'IN (SELECT repository,snapshot_hash FROM public.mycel_evidence_references WHERE owner=%s) '
            'ORDER BY s.repository,s.hash', (row[6],)).fetchall()
        manifests = self.connection.execute('SELECT m.* FROM public.mycel_manifests m WHERE (m.repository,m.hash) '
            'IN (SELECT repository,manifest_hash FROM public.mycel_evidence_references WHERE owner=%s) '
            'ORDER BY m.repository,m.hash', (row[6],)).fetchall()
        reasons = tuple((str(identifier), dependency,
            _base_reason(reason) if str(identifier) == source.get('staleReason') else reason)
            for identifier, dependency, reason in self.connection.execute(
                'SELECT id,dependency,reason FROM public.mycel_stale_reasons WHERE chunk_version=%s ORDER BY id',
                (row[2],)).fetchall())
        bundle = self.connection.execute('SELECT repository,dependant_version,state,evidence_owner '
            'FROM public.mycel_drifts WHERE id=%s', (row[0],)).fetchone()
        if bundle != (row[1], row[2], row[5], row[6]):
            _invalid('The Drift work binding changed during classification publication.')
        # Read physical inputs last, after every possible publication callback.
        # Uncheckable inputs are already blocked; a stable failure can retain an
        # error stage. Observe owners independently so an unrelated read fault
        # cannot mask changed bytes in a successfully checked selected pair.
        physical = []
        for repository in sorted({file.repository for file in indexed[0]} |
                                 {address.repository for address in declarations}):
            files = tuple(file for file in indexed[0] if file.repository == repository)
            addresses = tuple(address for address in declarations if address.repository == repository)
            try:
                observed = detector._physical_inputs(settings, files, addresses)
            except (MycelError, OSError) as error:
                observed = ('read_failed', type(error).__name__, getattr(error, 'code', None), getattr(error, 'errno', None))
            physical.append((repository, observed))
        return indexed, owner, references, snapshots, manifests, reasons, tuple(physical)

    def close_versions_in_transaction(self, repository, versions, *, because='version_removed', at=None):
        require_transaction_guards(self.connection, (repository,))
        if because not in _CLOSURES:
            _invalid('The Drift closure event is unsupported.')
        at = _time(at)
        changed = False
        for row in self._rows((repository,), lock=True):
            if row[2] not in versions or row[4] is not None:
                continue
            state = _copy(self._validate(row))
            state['sources'] = [_closed_source(source, at, because) if source['active'] else source for source in state['sources']]
            state['closed'] = {'at': at, 'because': because}
            self._write(row[0], state, at)
            changed = True
        from ._drift_retention import DriftHistoryStore
        DriftHistoryStore(self.connection).prune_in_transaction(repository)
        return changed

    def record_classification(self, settings, drift_id, reason_id, pair_hash, *, status='complete',
                              judgement=None, evidence=None, at=None, canonical_input_hash=None,
                              _canonical_guard=None, _audit=None):
        """Apply one validated stage to one current exact pair, preserving pins.

        An obsolete effect is retained as an attempt. Supplied stage evidence is
        metadata, never replacement bytes for the checked durable local bundle.
        """
        drift_id, reason_id = _uuid(drift_id), _uuid(reason_id)
        if _audit is not None and not callable(_audit):
            _invalid('Classification audit must be a transaction callback.')
        if (not isinstance(status, str) or status not in STATUSES
                or judgement is not None and (not isinstance(judgement, str) or judgement not in JUDGEMENTS)
                or not isinstance(pair_hash, str) or not _HASH.fullmatch(pair_hash)
                or status == 'complete' and judgement is None
                or status in {'pending_jev', 'pending_debounce', 'error'} and judgement is not None):
            _invalid('Classification requires one categorical exact-input stage.')
        if evidence is not None and not isinstance(evidence, dict):
            _invalid('Classification stage evidence must be a JSON object.')
        if status == 'error' and evidence is not None and 'reason' in evidence and (
                not isinstance(evidence['reason'], str) or not evidence['reason']):
            _invalid('Classification errors require a nonempty categorical reason.')
        if canonical_input_hash is not None and (not isinstance(canonical_input_hash, str) or not _HASH.fullmatch(canonical_input_hash)):
            _invalid('The canonical classification input hash must be exact SHA-256.')
        evidence = _copy(evidence or {})
        at = _time(at)
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            settings.require_valid(require_store=False)
            for owner in _eligible(settings):
                stack.enter_context(operation_guard(self.connection, owner, 'pass'))
            with atomic_transaction(self.connection):
                row = self.connection.execute('SELECT id,repository,dependant_version,opened_at,closed_at,state,evidence_owner '
                    'FROM public.mycel_drifts WHERE id=%s FOR UPDATE NOWAIT', (drift_id,)).fetchone()
                if row is None:
                    _invalid('The selected Drift record is absent.')
                self._validate(row)
                self.sync_in_transaction(settings, (row[1],), versions=(row[2],), at=at)
                row = next(item for item in self._rows((row[1],), lock=True) if str(item[0]) == drift_id)
                state = _copy(row[5])
                selected = next((source for source in state['sources'] if source['id'] == reason_id), None)
                current = self.connection.execute("SELECT 1 FROM public.mycel_locations WHERE chunk_version=%s AND kind='disk'",
                    (row[2],)).fetchone() is not None
                obsolete = (selected is None or not selected['active'] or selected['pairHash'] != pair_hash or not current
                    or not settings.values['repos'].get(row[1], {}).get('enabled'))
                if _canonical_guard is not None and not _canonical_guard():
                    obsolete = True
                application_inputs = (None if obsolete else
                    self._classification_publication_inputs(settings, row, selected))
                committed_source = None if obsolete else _copy(selected)
                prior_history_length = len(state['history'])
                attempt = {'at': at, 'source': reason_id, 'pairHash': pair_hash,
                           'status': status, 'judgement': judgement, 'evidence': evidence, 'obsolete': obsolete}
                if canonical_input_hash is not None:
                    attempt['inputHash'] = canonical_input_hash
                state['history'].append(attempt)
                if not obsolete:
                    classification = {**selected['classification'], 'status': status, 'pairHash': pair_hash,
                        'evidence': {**selected['classification'].get('evidence', {}), **evidence}}
                    classification.pop('judgement', None)
                    if canonical_input_hash is not None:
                        classification['inputHash'] = canonical_input_hash
                    if judgement is not None:
                        classification['judgement'] = judgement
                    blocked = selected['kind'] in {'upstream_stale', 'ref_fault', 'baseline_missing'} or selected['input'].get('fault')
                    if blocked and status == 'complete':
                        classification['status'] = 'error'
                        classification['reason'] = selected['input'].get('fault') or selected['kind']
                        classification.pop('judgement', None)
                    elif status != 'error':
                        classification.pop('reason', None)
                    else:
                        classification['reason'] = evidence.get('reason', 'provider_error')
                    selected['classification'] = classification
                    support = classification['status'] == 'complete' and judgement == 'still_supported'
                    selected['active'] = not support
                    if support:
                        selected['closed'] = {'at': at, 'because': 'still_supported'}
                    else:
                        selected.pop('closed', None)
                    if any(source['active'] for source in state['sources']):
                        state.pop('closed', None)
                    else:
                        state['closed'] = {'at': at, 'because': 'still_supported'}
                self._write(row[0], state, state.get('closed', {}).get('at'))
                # Producer/audit callbacks can edit disk input after the first
                # observation. Recompose before commit; the answered old bytes
                # then survive only as obsolete history, never active support.
                current_pairs = {}
                self.sync_in_transaction(settings, (row[1],), versions=(row[2],), at=at,
                    _candidate_pairs=current_pairs)
                latest = next(item for item in self._rows((row[1],), lock=True) if str(item[0]) == drift_id)
                state = _copy(latest[5])
                current_source = next((source for source in state['sources'] if source['id'] == reason_id), None)
                if not obsolete and (current_source is None or current_source['pairHash'] != pair_hash
                        or current_pairs.get((row[2], reason_id)) != pair_hash
                        or _canonical_guard is not None and not _canonical_guard()):
                    obsolete = True
                    for item in reversed(state['history']):
                        if item.get('source') == reason_id and item.get('pairHash') == pair_hash:
                            item['obsolete'] = True
                            break
                    # A rejected tentative stage is attempt evidence only.
                    # Restore the committed source before recomposing an ended
                    # reason, so withdrawal/restoration gets its actual closure
                    # instead of inheriting the rejected support suppression.
                    for item in state['history'][prior_history_length:]:
                        archived = item.get('source')
                        if (isinstance(archived, dict) and archived.get('id') == reason_id
                                and archived.get('pairHash') == pair_hash):
                            item['source'] = _copy(committed_source)
                    if current_source is not None and current_source['pairHash'] == pair_hash:
                        state['sources'] = [_copy(committed_source) if source['id'] == reason_id else source
                                            for source in state['sources']]
                        state.pop('closed', None)
                    if latest[2] is None:
                        state['sources'] = [_closed_source(source, at, 'version_removed') if source['active'] else source
                                            for source in state['sources']]
                        state['closed'] = {'at': at, 'because': 'version_removed'}
                    self._write(latest[0], state, state.get('closed', {}).get('at'))
                    self.sync_in_transaction(settings, (row[1],), versions=(row[2],), at=at)
                    latest = next(item for item in self._rows((row[1],), lock=True) if str(item[0]) == drift_id)
                    state = _copy(latest[5])
                if obsolete:
                    from ._drift_retention import DriftHistoryStore
                    returned = next((item for item in reversed(state['history'])
                        if item.get('source') == reason_id and item.get('pairHash') == pair_hash
                        and item.get('at') == at and item.get('evidence') == evidence), None)
                    if returned is not None:
                        DriftHistoryStore(self.connection).attach_obsolete_attempt_in_transaction(latest, state, returned)
                        self._write(latest[0], state, state.get('closed', {}).get('at'))
                wire = self._wire((*latest[:4], state.get('closed', {}).get('at'), state, latest[6]))
                if not obsolete:
                    if _canonical_guard is not None and not _canonical_guard():
                        _invalid('Canonical classification inputs changed before publication.')
                    before_publication = self._classification_publication_inputs(settings, latest, current_source)
                    if before_publication != application_inputs:
                        _invalid('Exact Drift inputs changed before classification publication.')
                    self._publish_classification(state, source_ids=(reason_id,))
                    if _canonical_guard is not None and not _canonical_guard():
                        _invalid('Canonical classification inputs changed during publication.')
                    if self._classification_publication_inputs(settings, latest, current_source) != before_publication:
                        _invalid('Exact Drift inputs changed during classification publication.')
                settings.require_current()
                result = {'applied': not obsolete, 'obsolete': obsolete, 'drift': wire}
                if _audit is not None:
                    _audit(result)
                    if not obsolete:
                        if _canonical_guard is not None and not _canonical_guard():
                            _invalid('Canonical classification inputs changed during audit publication.')
                        if self._classification_publication_inputs(settings, latest, current_source) != before_publication:
                            _invalid('Exact Drift inputs changed during audit publication.')
                    settings.require_current()
                from ._drift_retention import DriftHistoryStore
                DriftHistoryStore(self.connection).prune_in_transaction(row[1])
                return result

    def _wire(self, row):
        state = self._validate(row)
        locations = self.connection.execute('SELECT kind,location,metadata FROM public.mycel_locations '
            'WHERE chunk_version=%s ORDER BY kind,location,id', (row[2],)).fetchall() if row[2] is not None else ()
        wire = {'id': str(row[0]), 'chunk': _copy(state['chunk']), 'chunkId': state['chunkId'], 'version': state['version'],
            'current': any(location[0] == 'disk' for location in locations), 'state': 'open' if row[4] is None else 'closed',
            'openedAt': row[3].isoformat(), 'sources': _copy(state['sources']), 'history': _copy(state['history']),
            'locations': [{'kind': kind, 'location': location, 'place': metadata} for kind, location, metadata in locations]}
        if state.get('closed'):
            wire['closed'] = _copy(state['closed'])
        return wire

    def list(self, repository, *, closed=False, all_versions=False):
        """Read committed work only; no reconciliation, providers or writes."""
        if type(closed) is not bool or type(all_versions) is not bool:
            _invalid('Drift listing options must be explicit booleans.')
        with checked_store(self.connection), read_snapshot(self.connection):
            drifts = [self._wire(row) for row in self._rows((repository,))]
            drifts = [drift for drift in drifts if (closed or drift['state'] == 'open')
                      and (all_versions or drift['current'])]
            drifts.sort(key=lambda drift: (drift['chunk'].get('address', ''), drift['version'], drift['openedAt'], drift['id']))
            regeneration = self.connection.execute("""SELECT DISTINCT c.id,v.id,v.snapshot_hash,l.metadata
                FROM public.mycel_generated_state g JOIN public.mycel_chunks c ON c.id=g.chunk_id
                JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
                JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index'
                JOIN public.mycel_stale_reasons s ON s.chunk_version=v.id WHERE c.repository=%s ORDER BY v.id""",
                (repository,)).fetchall()
            return {'repository': repository, 'drifts': drifts, 'regeneration': [
                {'chunkId': str(identifier), 'version': digest, 'state': 'regeneration', 'place': metadata}
                for identifier, _, digest, metadata in regeneration]}
