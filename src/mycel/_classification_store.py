"""Complete canonical classification inputs and short, fresh guarded boundaries.

This internal producer launches no provider. The future finite classifier owns
transport, routing and budgets; it consumes these immutable inputs and checks
them at both calls and application. Evidence belongs to the dependant's Drift.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._classification_eligibility import observe_input, classification_eligibility
from ._classification_payload import (DecisionPayload, DecisionText, CurrentSelection,
    EvidenceBundle, ReviewCommandIdentity, semantic_baseline, ROUTING_REVISION)
from ._drift_store import DriftStore, JUDGEMENTS, _copy, _time, _uuid
from ._errors import MycelError
from ._evidence import (EvidenceError, EvidenceStore, SnapshotEvidence, CaptureLocation,
    _chunk_snapshot, canonical_json, capture_baseline, snapshot)
from ._locks import (atomic_transaction, operation_guard, invocation_guard,
    invocation_is_live, require_transaction_guards)
from ._markdown import split_markdown
from ._reconciliation import _place_payload
from ._resolver import SourceResolver, require_read_transaction
from ._source_refs import parse_source_address
from ._staleness import _eligible, _links, _resolve, _raw
from ._store import checked_store


REQUEST_SCHEMA = 'mycel-classification-request-v1'


def _plain(value):
    if hasattr(value, 'items'):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ClassificationPreparation:
    drift_id: str
    reason_id: str
    repository: str
    pair_hash: str
    recorded_at: str
    decision: DecisionPayload | None = field(repr=False)
    bundle: EvidenceBundle | None = field(repr=False)
    guards_bytes: bytes = field(repr=False)
    observations_bytes: bytes = field(repr=False)
    status: str
    eligible_at: str | None
    fault: str | None = None

    @property
    def input_hash(self):
        return None if self.decision is None else self.decision.input_hash

    def as_dict(self):
        result = {'drift': self.drift_id, 'source': self.reason_id, 'repository': self.repository,
            'pairHash': self.pair_hash, 'inputHash': self.input_hash, 'status': self.status,
            'eligibleAt': self.eligible_at}
        if self.fault:
            result['reason'] = self.fault
        return result


class ClassificationStore:
    def __init__(self, connection):
        self.connection = connection
        self.drifts = DriftStore(connection)

    @contextmanager
    def _guarded(self, settings):
        settings.require_valid(require_store=False)
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            for repository in _eligible(settings):
                stack.enter_context(operation_guard(self.connection, repository, 'pass'))
            with atomic_transaction(self.connection):
                settings.require_current()
                yield
                settings.require_current()

    def _row(self, drift_id):
        row = self.connection.execute('SELECT id,repository,dependant_version,opened_at,closed_at,state,evidence_owner '
            'FROM public.mycel_drifts WHERE id=%s FOR UPDATE NOWAIT', (drift_id,)).fetchone()
        if row is None:
            raise EvidenceError('version_removed')
        self.drifts._validate(row)
        return row

    @staticmethod
    def _texts(capture):
        blobs = {blob.evidence.hash: blob.source for blob in capture.snapshots}
        return tuple(DecisionText.create(SnapshotEvidence.from_record(_plain(member['evidence'])),
            blobs[member['evidence']['hash']]) for member in capture.manifest.payload['members'])

    def _selection(self, settings, catalog, dependant, dep_file, link, *, at, required, declarations,
                   captures, baselines, blobs):
        identifier, owner, version, _, natural, kind, state, _, manifest_hash = link
        if manifest_hash is None:
            raise EvidenceError('baseline_missing')
        pinned = EvidenceStore(self.connection)._read_baseline(owner, manifest_hash)
        if (pinned.manifest.payload['dependantId'] != dependant.chunk.identifier
                or pinned.manifest.payload['dependantVersion'] != str(version)):
            raise EvidenceError('baseline_missing')
        baselines.append(pinned)
        blobs.extend(pinned.snapshots)
        address = parse_source_address(_raw(link))
        if address.repository not in _eligible(settings):
            raise EvidenceError('disabled_repository')
        if address.root != 'index':
            declarations.append(address)
        resolution = _resolve(catalog, link)
        selected = resolution.selection
        if selected is not None and selected.file is not None:
            required[selected.file.identifier] = selected.file
            current = capture_baseline(owner, dependant, dep_file, selected, kind=kind,
                declaration=_raw(link), captured_at=at, location=CaptureLocation('disk'))
            baselines.append(current)
            blobs.extend(current.snapshots)
            selection = CurrentSelection.create('present', selected.place, selected.kind, self._texts(current))
        elif selected is not None:
            # Direct dependency refs cannot supply an index-only source. Index
            # context is handled separately through its exact generated row.
            raise EvidenceError('insufficient_evidence')
        else:
            absence = state.get('sourceAbsence', {})
            if (resolution.fault not in {'missing_file', 'missing_name'}
                    or absence.get('state') not in {'away', 'deleted'}):
                raise EvidenceError(resolution.fault or 'ref_fault')
            for file in catalog.files:
                if file.repository == address.repository and any(alias.path == address.path
                        and address.root in {None, alias.root} for alias in file.aliases):
                    required[file.identifier] = file
            selection = CurrentSelection.create(absence['state'],
                parse_source_address(pinned.manifest.payload['source']['address']),
                pinned.manifest.payload['selection'], ())
        return pinned, selection, state.get('sourceAbsence')

    @staticmethod
    def _stat_file(settings, file):
        values = []
        for alias in file.aliases:
            root = settings.values['repos'][file.repository].get(alias.root + '_root')
            if root is None:
                raise EvidenceError('read_failed')
            try:
                root_path = Path(root).resolve(strict=True)
                path = (root_path / alias.path).resolve(strict=True)
                path.relative_to(root_path)
                info = path.stat()
                # MechanicalStalenessStore already captured safely. This
                # additional observation binds the complete file's timer and
                # location, including modifications outside the selected span.
                values.append({'place': _place_payload(alias), 'hash': file.snapshot_hash,
                    'signature': [info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                  info.st_mtime_ns, info.st_ctime_ns]})
            except (OSError, ValueError):
                raise EvidenceError('read_failed') from None
        return values

    def _assemble(self, settings, row, reason_id, *, at, capture_at=None, previous=None,
                  _guarded_repositories=None):
        if _guarded_repositories is not None:
            require_read_transaction(self.connection)
        guarded_repositories = (tuple(_eligible(settings)) if _guarded_repositories is None
                                else tuple(_guarded_repositories))
        require_transaction_guards(self.connection, guarded_repositories)
        source = next((item for item in row[5]['sources'] if item['id'] == reason_id), None)
        if source is None:
            raise EvidenceError('reason_removed')
        from ._staleness import inactive_policy_links
        inactive = inactive_policy_links(self.connection, settings)
        if source['dependency'] in inactive:
            raise MycelError('invalid_input', 'Classification requires work owned by the invoking clone.')
        catalog = SourceResolver.from_observation_transaction(self.connection, settings,
            guarded_repositories=guarded_repositories)
        located = [(file, member) for file in catalog.files for member in catalog._members(file, file.chunks)
                   if member.chunk.version == row[2] and member.chunk.identifier == row[5]['chunkId']]
        if len(located) != 1:
            raise EvidenceError('source_away')
        dep_file, dependant = located[0]
        if not settings.values['repos'].get(row[1], {}).get('enabled'):
            raise EvidenceError('disabled_repository')
        if source['kind'] in {'upstream_stale', 'ref_fault', 'baseline_missing'}:
            raise EvidenceError(source['input'].get('fault') or source['kind'])
        links = [link for link in _links(self.connection, _eligible(settings))
                 if link[1] == row[1] and link[2] == row[2] and str(link[0]) not in inactive]
        faults = self.connection.execute('SELECT id FROM public.mycel_ref_faults '
            'WHERE repository=%s AND chunk_version=%s', (row[1], row[2])).fetchall()
        if any(str(fault[0]) not in inactive and str(fault[0]) not in {str(link[0]) for link in links} for fault in faults):
            raise EvidenceError('context_missing')
        selected_link = next((link for link in links if str(link[0]) == source['dependency']), None)
        if selected_link is None:
            raise EvidenceError('reason_removed')
        capture_at = at if capture_at is None else capture_at
        required, declarations, captures = {dep_file.identifier: dep_file}, [], {}
        baselines, blobs, context, absent = [], [], [], []
        pinned, current, absence = self._selection(settings, catalog, dependant, dep_file, selected_link,
            at=capture_at, required=required, declarations=declarations, captures=captures,
            baselines=baselines, blobs=blobs)
        if absence is not None and current.payload['state'] != 'present':
            absent.append((current.payload, absence))
        for link in sorted(links, key=lambda item: (item[4] or _raw(item), str(item[0]))):
            if str(link[0]) == source['dependency'] or link[5] not in {'declared', 'asserted'}:
                continue
            try:
                baseline, selection, tombstone = self._selection(settings, catalog, dependant, dep_file, link,
                    at=capture_at, required=required, declarations=declarations, captures=captures,
                    baselines=baselines, blobs=blobs)
            except EvidenceError as error:
                raise EvidenceError('context_missing', error.addresses) from None
            stale = self.connection.execute('SELECT 1 FROM public.mycel_stale_reasons s '
                'JOIN public.mycel_edges e ON e.source_version=s.chunk_version WHERE e.dependency=%s LIMIT 1',
                (link[0],)).fetchone() is not None
            if link[6].get('reasons'):
                stale = True
            context.append({'role': 'governor', 'baseline': semantic_baseline(baseline.manifest),
                'before': [text.payload for text in self._texts(baseline)],
                'current': selection.payload, 'freshness': 'stale' if stale else 'fresh'})
            if tombstone is not None and selection.payload['state'] != 'present':
                absent.append((selection.payload, tombstone))
        if dependant.chunk.kind == 'document':
            parsed = split_markdown(dep_file.source)
            selected_sections = [section for section in parsed.chunks
                if (section.span.byte_start, section.span.byte_end) == dependant.chunk.span]
            if len(selected_sections) != 1:
                raise EvidenceError('context_missing')
            selected_section = selected_sections[0]
            for depth in range(1, len(selected_section.heading_path)):
                candidates = [section for section in parsed.chunks
                    if section.heading_path == selected_section.heading_path[:depth]
                    and section.span.byte_start < selected_section.span.byte_start]
                if not candidates:
                    raise EvidenceError('context_missing')
                ancestor = max(candidates, key=lambda section: section.span.byte_start)
                matches = [member for member in catalog._members(dep_file, dep_file.chunks)
                           if member.chunk.span == (ancestor.span.byte_start, ancestor.span.byte_end)]
                if len(matches) != 1:
                    raise EvidenceError('context_missing')
                blob = _chunk_snapshot(matches[0], dep_file)
                blobs.append(blob)
                context.append({'role': 'ancestor', 'evidence': DecisionText.create(blob.evidence, blob.source).payload})
        fault = self.drifts._physical(settings, tuple(required.values()), declarations, captures, catalog)
        if fault:
            raise EvidenceError(fault)
        # Detect durable collisions instead of repairing a retained old slot.
        corrupt, invalid_manifests = self.drifts._retention_conflicts(row[1], blobs, baselines)
        if corrupt or invalid_manifests:
            raise EvidenceError('snapshot_corrupt')
        live = [record for file in sorted(required.values(), key=lambda file: file.primary.address)
                for record in self._stat_file(settings, file)]
        previous = previous or {}
        observations = {}
        for record in live:
            place = record['place']['address']
            mtime = datetime.fromtimestamp(record['signature'][4] / 1_000_000_000, timezone.utc)
            observations[place] = observe_input(place, record['hash'], observed_at=at,
                modified_at=mtime, previous=previous.get(place))
        absent_identities = {}
        for selection, tombstone in absent:
            source_place = parse_source_address(selection['place']['address'])
            place = type(source_place)(source_place.repository, source_place.root, source_place.path).address
            # Removing a selected section/method is a tombstone while its
            # whole source file remains live. Keep both clocks; a governor of
            # another section cannot replace either one.
            if place in observations:
                place = source_place.address + '|tombstone'
            absent_identities[source_place.address] = place
            # A successfully checked absence binds its first producer tombstone
            # even when canonical preparation happens in a later invocation.
            observed = tombstone.get('observedAt') or at
            observations[place] = observe_input(place, 'absent:' + observed, kind='deleted',
                observed_at=observed, previous=previous.get(place))
        eligibility = classification_eligibility(tuple(observations.values()), at=at,
            debounce_seconds=settings.values['drifts']['debounce_seconds'])
        options = settings.values['drifts']
        command = None
        reviewer = None
        if options.get('review_command'):
            command = ReviewCommandIdentity.inspect(options['review_command'],
                adapter_revision=options['review_revision'], resolved_home=settings._home or Path.home())
            reviewer = {'provider': options['review_provider'], 'model': options['review_model'],
                'adapterRevision': options['review_revision'], 'commandHash': command.command_hash,
                'instructionVersion': 'mycel-review-v1'}
        dep = _chunk_snapshot(dependant, dep_file)
        blobs.append(dep)
        context.sort(key=lambda item: (item['current']['place']['address'] if item['role'] == 'governor'
            else item['evidence']['snapshot']['place']['address']))
        decision = DecisionPayload.create(baseline=pinned.manifest, before=self._texts(pinned), current=current,
            dependant=DecisionText.create(dep.evidence, dep.source), context=context, jev_model=options['model'],
            review=reviewer, routing_revision=ROUTING_REVISION,
            confidence_floor=str(options['confidence_floor']))
        file_guards = [{'place': record['place'], 'hash': record['hash'],
            'changedAt': observations[record['place']['address']]['changedAt'], 'event': 'file_changed'} for record in live]
        for selection, _ in absent:
            identity = absent_identities[selection['place']['address']]
            file_guards.append({'place': selection['place'],
                'changedAt': observations[identity]['changedAt'], 'event': 'deleted'})
        bundle = EvidenceBundle.create(owner_repository=row[1], baseline_id=pinned.manifest.identifier,
            decision=decision, evidence=[blob.evidence for blob in blobs], guards=file_guards, disposition='active')
        guards = {'live': live, 'absence': [{'selection': selection, 'tombstone': tombstone} for selection, tombstone in absent],
            'baseline': sorted({link[8] for link in links if link[8] is not None}),
            'dependantId': dependant.chunk.identifier, 'dependantVersion': dependant.chunk.version,
            'declarationRows': [[str(link[0]), link[4], link[5], _plain(link[6]), link[8]] for link in links],
            'command': None if command is None else _plain(command.payload),
            'settings': sha256(json.dumps(_plain(settings.values), sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'branches': {owner: [{'kind': location.id.kind, 'identity': location.id.identity, 'commit': location.commit,
                                'trees': list(location.trees)} for location in capture.locations]
                for owner, capture in captures.items()}}
        prepared = ClassificationPreparation(str(row[0]), reason_id, row[1], source['pairHash'], capture_at,
            decision, bundle, canonical_json(guards), canonical_json(observations),
            eligibility.status, eligibility.eligible_at)
        return prepared, tuple(blobs), tuple(baselines)

    def prepare(self, settings, drift_id, reason_id, *, at=None, reconcile=False):
        if type(reconcile) is not bool:
            raise MycelError('invalid_input', 'Local classification reconciliation requires a boolean.')
        drift_id, reason_id, at = _uuid(drift_id), _uuid(reason_id), _time(at)
        with self._guarded(settings):
            row = self._row(drift_id)
            state = _copy(row[5])
            try:
                prepared, blobs, captures = self._assemble(settings, row, reason_id, at=at,
                    previous=state.get('classificationObservations', {}))
                prior = state.get('classificationRequests', {}).get(prepared.input_hash)
                if (prior is not None and prior.get('source') == reason_id and prior.get('pairHash') == prepared.pair_hash
                        and canonical_json(prior.get('guards')) == prepared.guards_bytes):
                    prepared, blobs, captures = self._assemble(settings, row, reason_id, at=at,
                        capture_at=prior['recordedAt'], previous=state.get('classificationObservations', {}))
                self.drifts._retain(row[1], row[6], (*blobs, snapshot(prepared.decision.canonical_bytes),
                    snapshot(prepared.bundle.canonical_bytes)), captures)
                # Retention is followed by a complete fresh input check before
                # committing any request claim, including callback races.
                checked, _, _ = self._assemble(settings, row, reason_id, at=at, capture_at=prepared.recorded_at,
                    previous=json.loads(prepared.observations_bytes))
                if checked.guards_bytes != prepared.guards_bytes or checked.input_hash != prepared.input_hash:
                    raise EvidenceError('changed_since_ingest')
                from ._drift_retention import DriftHistoryStore
                old_source = next(item for item in state['sources'] if item['id'] == reason_id)
                older = [key for key, request in state.get('classificationRequests', {}).items()
                         if request['source'] == reason_id and key != prepared.input_hash]
                for key in older:
                    bundle = DriftHistoryStore(self.connection).archive_source_in_transaction(
                        row, old_source, state, at=at, input_hash=key)
                    state['history'].append({'at': at, 'because': 'request_changed',
                                             'source': reason_id, 'inputHash': key, 'bundle': bundle})
                state.setdefault('classificationObservations', {}).update(json.loads(prepared.observations_bytes))
                requests = state.setdefault('classificationRequests', {})
                requests[prepared.input_hash] = {'schema': REQUEST_SCHEMA, 'source': reason_id,
                    'pairHash': prepared.pair_hash, 'payloadSnapshot': 'snapshot:' + prepared.input_hash,
                    'bundle': _plain(prepared.bundle.payload), 'guards': json.loads(prepared.guards_bytes),
                    'bundleSnapshot': 'snapshot:' + prepared.bundle.evidence_hash,
                    'fullManifests': sorted({capture.manifest.identifier for capture in captures}),
                    'recordedAt': prepared.recorded_at}
            except EvidenceError as error:
                source = next((item for item in state['sources'] if item['id'] == reason_id), None)
                pair_hash = '' if source is None else source['pairHash']
                prepared = ClassificationPreparation(drift_id, reason_id, row[1], pair_hash, at, None, None,
                    b'{}', b'{}', 'error', None, error.status)
            source = next((item for item in state['sources'] if item['id'] == reason_id), None)
            keep_stage = (source is not None and prepared.decision is not None
                and source['classification'].get('inputHash') == prepared.input_hash
                and (source['classification']['status'] == 'complete' or
                     reconcile and prepared.status == 'pending_jev'
                     and source['classification']['status'] in {'needs_llm_review', 'error'}))
            if keep_stage and reconcile and prepared.status == 'pending_jev':
                prepared = replace(prepared, status=source['classification']['status'],
                    fault=source['classification'].get('reason'))
            if (reconcile and source is not None and source.get('closed', {}).get('because') == 'still_supported'
                    and (prepared.decision is None or source['classification'].get('inputHash') != prepared.input_hash)):
                source['active'] = True
                source.pop('closed', None)
                state.pop('closed', None)
            if source is not None and source['active'] and not keep_stage:
                if (prepared.decision is not None
                        and source['classification'].get('inputHash') != prepared.input_hash):
                    source['classification'].pop('evidence', None)
                source['classification'] = {**source['classification'], 'status': prepared.status,
                    'pairHash': source['pairHash'], 'eligibleAt': prepared.eligible_at}
                source['classification'].pop('judgement', None)
                if prepared.input_hash:
                    source['classification']['inputHash'] = prepared.input_hash
                if prepared.fault:
                    source['classification']['reason'] = prepared.fault
                else:
                    source['classification'].pop('reason', None)
            if state != row[5]:
                self.drifts._write(row[0], state, state.get('closed', {}).get('at'))
            from ._drift_retention import DriftHistoryStore
            DriftHistoryStore(self.connection).retain_live_references_in_transaction(row, state)
            DriftHistoryStore(self.connection).prune_in_transaction(row[1])
            if reconcile and source is not None:
                self.drifts._publish_classification(state, source_ids=(reason_id,))
                if prepared.decision is not None:
                    final, _, _ = self._assemble(settings, row, reason_id, at=at,
                        capture_at=prepared.recorded_at, previous=json.loads(prepared.observations_bytes))
                    if final.input_hash != prepared.input_hash or final.guards_bytes != prepared.guards_bytes:
                        raise EvidenceError('changed_since_ingest')
            return prepared

    def check_in_transaction(self, settings, prepared, *, stage, at=None):
        """Recheck complete inputs in a caller's guarded transaction."""
        if not isinstance(prepared, ClassificationPreparation) or stage not in {'jev', 'review', 'application', 'reuse'}:
            raise MycelError('invalid_input', 'Classification requires a prepared exact stage boundary.')
        if prepared.decision is None:
            return {'allowed': False, 'reason': prepared.fault or 'baseline_missing'}
        try:
            settings.require_current()
            row = self._row(prepared.drift_id)
            current, _, captures = self._assemble(settings, row, prepared.reason_id, at=_time(at),
                capture_at=prepared.recorded_at, previous=json.loads(prepared.observations_bytes))
            if current.input_hash != prepared.input_hash or current.guards_bytes != prepared.guards_bytes:
                return {'allowed': False, 'reason': 'obsolete'}
            if current.status != 'pending_jev':
                return {'allowed': False, 'reason': 'pending_debounce', 'eligibleAt': current.eligible_at}
            if stage == 'review' and (current.decision.payload['models']['review'] is None
                    or json.loads(current.guards_bytes)['command']['executableSha256'] is None):
                return {'allowed': False, 'reason': 'review_command_unavailable'}
            request = row[5].get('classificationRequests', {}).get(prepared.input_hash)
            if request is None or request.get('schema') != REQUEST_SCHEMA:
                return {'allowed': False, 'reason': 'baseline_missing'}
            if (request.get('source') != prepared.reason_id or request.get('pairHash') != prepared.pair_hash
                    or request.get('fullManifests') != sorted({capture.manifest.identifier for capture in captures})):
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            if request.get('bundle') != _plain(prepared.bundle.payload):
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            for digest in request.get('fullManifests', ()):
                if self.connection.execute('SELECT 1 FROM public.mycel_evidence_references '
                        'WHERE owner=%s AND repository=%s AND manifest_hash=%s',
                        (row[6], prepared.repository, digest)).fetchone() is None:
                    return {'allowed': False, 'reason': 'baseline_missing'}
                EvidenceStore(self.connection)._read_baseline(prepared.repository, digest)
            if request.get('bundleSnapshot') != 'snapshot:' + prepared.bundle.evidence_hash:
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            bundle_descriptor = snapshot(prepared.bundle.canonical_bytes).evidence
            retained_bundle = self.connection.execute('SELECT s.bytes,s.metadata FROM public.mycel_snapshots s '
                'JOIN public.mycel_evidence_references r ON r.repository=s.repository AND r.snapshot_hash=s.hash '
                'WHERE r.owner=%s AND s.repository=%s AND s.hash=%s',
                (row[6], prepared.repository, bundle_descriptor.hash)).fetchone()
            if retained_bundle is None:
                return {'allowed': False, 'reason': 'baseline_missing'}
            if retained_bundle[1] != {'schema': 1, 'bytes': bundle_descriptor.byte_count, 'encoding': 'utf-8'}:
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            bundle_descriptor.verify(bytes(retained_bundle[0]), textual=True)
            for descriptor in prepared.bundle.payload['evidence']:
                full = SnapshotEvidence.from_record(_plain(descriptor))
                retained = self.connection.execute('SELECT s.bytes,s.metadata FROM public.mycel_snapshots s '
                    'JOIN public.mycel_evidence_references r ON r.repository=s.repository AND r.snapshot_hash=s.hash '
                    'WHERE r.owner=%s AND s.repository=%s AND s.hash=%s',
                    (row[6], prepared.repository, full.hash)).fetchone()
                if retained is None:
                    return {'allowed': False, 'reason': 'baseline_missing'}
                if retained[1] != {'schema': 1, 'bytes': full.byte_count, 'encoding': full.encoding}:
                    return {'allowed': False, 'reason': 'snapshot_corrupt'}
                full.verify(bytes(retained[0]), textual=True)
            payload = snapshot(prepared.decision.canonical_bytes).evidence
            retained = self.connection.execute('SELECT s.bytes,s.metadata FROM public.mycel_snapshots s '
                'JOIN public.mycel_evidence_references r ON r.repository=s.repository AND r.snapshot_hash=s.hash '
                'WHERE r.owner=%s AND s.repository=%s AND s.hash=%s',
                (row[6], prepared.repository, prepared.input_hash)).fetchone()
            if retained is None:
                return {'allowed': False, 'reason': 'baseline_missing'}
            if retained[1] != {'schema': 1, 'bytes': payload.byte_count, 'encoding': 'utf-8'}:
                return {'allowed': False, 'reason': 'snapshot_corrupt'}
            payload.verify(bytes(retained[0]), textual=True)
            settings.require_current()
            return {'allowed': True, 'inputHash': prepared.input_hash, 'eligibleAt': current.eligible_at}
        except EvidenceError as error:
            return {'allowed': False, 'reason': error.status}
        except MycelError as error:
            if error.code == 'invalid_input':
                return {'allowed': False, 'reason': 'obsolete'}
            raise

    def check(self, settings, prepared, *, stage, at=None):
        try:
            with self._guarded(settings):
                return self.check_in_transaction(settings, prepared, stage=stage, at=at)
        except MycelError as error:
            if error.code == 'invalid_input':
                return {'allowed': False, 'reason': 'obsolete'}
            raise

    def _obsolete(self, prepared, *, judgement, evidence, at, _audit=None):
        """Retain a finished attempt when frozen settings became obsolete.

        The old settings authorize no current effect. Only immutable diagnostic
        history is appended under the existing owner/removal/pass guard.
        """
        if not isinstance(judgement, str) or judgement not in JUDGEMENTS:
            raise MycelError('invalid_input', 'Classification requires one categorical judgement.')
        evidence = _copy(evidence or {})
        with checked_store(self.connection), operation_guard(self.connection, prepared.repository, 'pass'), \
                atomic_transaction(self.connection):
            row = self._row(prepared.drift_id)
            state = _copy(row[5])
            attempt = {'at': at, 'source': prepared.reason_id, 'pairHash': prepared.pair_hash,
                'inputHash': prepared.input_hash, 'status': 'complete', 'judgement': judgement,
                'evidence': evidence, 'obsolete': True}
            from ._drift_retention import DriftHistoryStore
            DriftHistoryStore(self.connection).attach_obsolete_attempt_in_transaction(row, state, attempt)
            state['history'].append(attempt)
            self.drifts._write(row[0], state, state.get('closed', {}).get('at'))
            result = {'applied': False, 'obsolete': True, 'drift': self.drifts._wire(
                (*row[:5], state, row[6]))}
            if _audit is not None:
                _audit(result)
            DriftHistoryStore(self.connection).prune_in_transaction(row[1])
            return result

    def apply(self, settings, prepared, *, judgement, evidence=None, at=None, _audit=None):
        """Apply a validated adapter result only through the canonical guard.

        Provider/protocol validation belongs to the stage adapter. This sink
        binds its categorical output to the retained exact request, never to
        an unchecked caller-supplied input hash.
        """
        at = _time(at)
        if _audit is not None and not callable(_audit):
            raise MycelError('invalid_input', 'Classification audit must be a transaction callback.')
        try:
            settings.require_current()
        except MycelError as error:
            if error.code != 'invalid_input':
                raise
            return self._obsolete(prepared, judgement=judgement, evidence=evidence, at=at, _audit=_audit)
        def canonical_guard():
            return self.check_in_transaction(settings, prepared, stage='application', at=at)['allowed']
        try:
            return self.drifts.record_classification(settings, prepared.drift_id, prepared.reason_id,
                prepared.pair_hash, judgement=judgement, evidence=evidence, at=at,
                canonical_input_hash=prepared.input_hash, _canonical_guard=canonical_guard, _audit=_audit)
        except MycelError as error:
            if error.code == 'invalid_input':
                try:
                    settings.require_current()
                except MycelError as changed:
                    if changed.code == 'invalid_input':
                        return self._obsolete(prepared, judgement=judgement, evidence=evidence, at=at, _audit=_audit)
            raise

    def reuse(self, settings, prepared, *, at=None):
        """Return only a complete guarded matching result, with no provider call."""
        with self._guarded(settings):
            checked = self.check_in_transaction(settings, prepared, stage='reuse', at=at)
            if not checked['allowed']:
                return None
            row = self._row(prepared.drift_id)
            source = next((item for item in row[5]['sources'] if item['id'] == prepared.reason_id), None)
            result = None if source is None else source['classification']
            if result is not None and result.get('inputHash') == prepared.input_hash and result.get('status') == 'complete':
                return _copy(result)
            for attempt in reversed(row[5]['history']):
                if (attempt.get('inputHash') == prepared.input_hash and attempt.get('status') == 'complete'
                        and attempt.get('judgement') in JUDGEMENTS and attempt.get('obsolete') is False):
                    return _copy({'status': 'complete', 'inputHash': prepared.input_hash,
                        'judgement': attempt['judgement'], 'evidence': attempt.get('evidence', {})})
            return None

    @contextmanager
    def stage(self, settings, prepared, *, stage, at=None):
        """Hold exact invocation/evidence liveness, releasing pass locks for I/O.

        The consumer must check immediately before launching and use apply for
        the result. The request remains protected until the consumer's process
        or HTTP attempt is known to have ended and this context exits.
        """
        if stage not in {'jev', 'review'}:
            raise MycelError('invalid_input', 'Only Jev and review have a call boundary.')
        with checked_store(self.connection), operation_guard(self.connection, prepared.repository, 'classify'), \
                invocation_guard(self.connection) as invocation:
            checked = self.check(settings, prepared, stage=stage, at=at)
            if not checked['allowed']:
                yield checked
                return
            lease = uuid4()
            with operation_guard(self.connection, prepared.repository, 'pass'), atomic_transaction(self.connection):
                if not invocation_is_live(self.connection, invocation):
                    raise EvidenceError('obsolete')
                row = self._row(prepared.drift_id)
                self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s)',
                    (lease, prepared.repository, 'classification_lease', str(lease), invocation.id))
                references = self.connection.execute('SELECT snapshot_hash,manifest_hash,ordinal '
                    'FROM public.mycel_evidence_references WHERE owner=%s ORDER BY ordinal', (row[6],)).fetchall()
                for digest, manifest, ordinal in references:
                    self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                        (lease, prepared.repository, digest, manifest, ordinal))
            try:
                # Final launch check follows lease publication. No pass guard
                # or transaction survives into the adapter's I/O scope.
                yield self.check(settings, prepared, stage=stage, at=at)
            finally:
                with operation_guard(self.connection, prepared.repository, 'pass'), atomic_transaction(self.connection):
                    self.connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s '
                        "AND repository=%s AND kind='classification_lease' AND invocation=%s",
                        (lease, prepared.repository, invocation.id))
                    from ._drift_retention import DriftHistoryStore
                    DriftHistoryStore(self.connection).prune_in_transaction(prepared.repository)
