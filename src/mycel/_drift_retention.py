"""Closed exact-input bundles and writer-only, owner-scoped retention.

Superseded inputs receive their own closed record before the live work releases
any references. The count applies to closed records, never to live evidence.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._locks import require_transaction_guards


HISTORY_LIMIT = 1000
_HASH = re.compile(r'[0-9a-f]{64}\Z')


def _hashes(value):
    result = set()
    def visit(item):
        if isinstance(item, str):
            candidate = item.removeprefix('snapshot:')
            if _HASH.fullmatch(candidate):
                result.add(candidate)
        elif isinstance(item, dict):
            for member in item.values():
                visit(member)
        elif isinstance(item, list):
            for member in item:
                visit(member)
    visit(value)
    return result


class DriftHistoryStore:
    def __init__(self, connection):
        self.connection = connection

    def _references(self, owner, state, *, live=False):
        # Historical metadata in open work points to an independent bundle;
        # it does not keep that bundle's bytes alive through the live owner.
        sources = state['sources']
        if live:
            sources = [source for source in sources if not source.get('historyBundle')]
        needed = _hashes({'sources': sources, 'requests': state.get('classificationRequests', {}),
                          'observations': state.get('classificationRequestObservations', {})})
        references = self.connection.execute('SELECT snapshot_hash,manifest_hash,ordinal '
            'FROM public.mycel_evidence_references WHERE owner=%s ORDER BY ordinal FOR UPDATE NOWAIT',
            (owner,)).fetchall()
        # Baseline manifests contain complete before/dependant selections that
        # are deliberately absent from the mechanical pair descriptor.
        for _, manifest, _ in references:
            if manifest in needed:
                raw = self.connection.execute('SELECT bytes FROM public.mycel_manifests '
                    'WHERE repository=%s AND hash=%s', (state['chunk']['repository'], manifest)).fetchone()
                try:
                    if raw is None or sha256(bytes(raw[0])).hexdigest() != manifest:
                        raise ValueError()
                    needed.update(_hashes(json.loads(bytes(raw[0]))))
                except (ValueError, TypeError, UnicodeError):
                    # A corrupt/missing baseline stays a visible input fault.
                    # Retention cannot infer which old refs are safe to drop.
                    return references
        return [(snapshot, manifest, ordinal) for snapshot, manifest, ordinal in references
                if snapshot in needed or manifest in needed]

    def archive_source_in_transaction(self, row, source, state, *, at, input_hash=None):
        """Transfer one superseded pair/request before releasing live refs."""
        from ._drift_store import SCHEMA, _closed_source, _copy
        repository = row[1]
        require_transaction_guards(self.connection, (repository,))
        requests = {key: value for key, value in state.get('classificationRequests', {}).items()
                    if value['source'] == source['id'] and value['pairHash'] == source['pairHash']
                    and (input_hash is None or key == input_hash)}
        history = [item for item in state['history'] if item.get('source') == source['id']
                   and item.get('pairHash') == source['pairHash']
                   and (input_hash is None or item.get('inputHash') == input_hash)]
        identifier, owner = uuid4(), uuid4()
        archived_source = _closed_source(source, at, 'version_removed')
        archived_source.pop('historyBundle', None)
        archived = {'schema': SCHEMA, **{key: _copy(state[key]) for key in
            ('chunkId', 'versionId', 'version', 'chunk')},
            'sources': [archived_source],
            'history': [{**_copy(item), 'obsolete': True} for item in history],
            'classificationRequests': _copy(requests),
            'closureProvenance': {'source': _copy(source.get('closed')),
                                  'drift': _copy(state.get('closed')),
                                  'supersededAt': at},
            'closed': {'at': at, 'because': 'version_removed', 'disposition': 'obsolete',
                       'supersedes': str(row[0])}}
        refs = self._references(row[6], archived)
        existing = self.connection.execute("SELECT id,state,evidence_owner FROM public.mycel_drifts "
            "WHERE repository=%s AND dependant_version IS NULL AND closed_at IS NOT NULL "
            "AND state->>'versionId'=%s AND COALESCE(state->'classificationRequests','{}'::jsonb) ?& %s "
            "AND (SELECT count(*) FROM jsonb_object_keys(COALESCE(state->'classificationRequests','{}'::jsonb)))=%s "
            "AND EXISTS(SELECT 1 FROM jsonb_array_elements(state->'sources') member "
            "WHERE member->>'id'=%s AND member->>'pairHash'=%s) "
            'ORDER BY closed_at DESC,id DESC FOR UPDATE NOWAIT',
            (repository, str(state['versionId']), list(requests), len(requests), source['id'], source['pairHash'])).fetchall()
        for prior_id, prior, prior_owner in existing:
            if (prior.get('closed', {}).get('disposition') == 'obsolete'
                    and prior.get('versionId') == state['versionId']
                    and any(member['id'] == source['id'] and member['pairHash'] == source['pairHash']
                            for member in prior.get('sources', ()))
                    and set(prior.get('classificationRequests', {})) == set(requests)):
                # Identical decision inputs have one owning bundle. Preserve
                # every full guard/bundle observation without duplicating text.
                merged = _copy(prior)
                for key, request in requests.items():
                    if merged['classificationRequests'][key] != request:
                        observations = merged.setdefault('classificationRequestObservations', {})
                        observations[request['bundleSnapshot']] = _copy(request)
                merged['history'].extend(item for item in archived['history'] if item not in merged['history'])
                if merged.get('closureProvenance') != archived['closureProvenance']:
                    events = merged.setdefault('closureObservations', [])
                    if archived['closureProvenance'] not in events:
                        events.append(archived['closureProvenance'])
                if at > merged['closed']['at']:
                    merged['closed']['at'] = at
                    for member in merged['sources']:
                        member['closed']['at'] = at
                self.connection.execute('UPDATE public.mycel_drifts SET state=%s,closed_at=%s WHERE id=%s',
                    (Jsonb(merged), merged['closed']['at'], prior_id))
                retained = self.connection.execute('SELECT snapshot_hash,manifest_hash,ordinal FROM '
                    'public.mycel_evidence_references WHERE owner=%s ORDER BY ordinal', (prior_owner,)).fetchall()
                known = {(snapshot, manifest) for snapshot, manifest, _ in retained}
                ordinal = max((ordinal for _, _, ordinal in retained), default=-1) + 1
                for snapshot, manifest, _ in refs:
                    if (snapshot, manifest) not in known:
                        self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                            (prior_owner, repository, snapshot, manifest, ordinal))
                        ordinal += 1
                for item in history:
                    item['bundle'] = str(prior_id)
                for key in requests:
                    state['classificationRequests'].pop(key, None)
                return str(prior_id)
        self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
            (owner, repository, 'drift', str(identifier)))
        self.connection.execute('INSERT INTO public.mycel_drifts VALUES (%s,%s,NULL,%s,%s,%s,%s)',
            (identifier, repository, row[3], at, Jsonb(archived), owner))
        for ordinal, (snapshot, manifest, _) in enumerate(refs):
            self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                (owner, repository, snapshot, manifest, ordinal))
        for item in history:
            item['bundle'] = str(identifier)
        for key in requests:
            state['classificationRequests'].pop(key, None)
        return str(identifier)

    def attach_obsolete_attempt_in_transaction(self, row, state, attempt):
        """Attach a late result to its exact archived input before lease exit."""
        from ._drift_store import _copy
        require_transaction_guards(self.connection, (row[1],))
        archived = self.connection.execute("SELECT id,state FROM public.mycel_drifts "
            "WHERE repository=%s AND dependant_version IS NULL AND closed_at IS NOT NULL "
            "AND (%s::text IS NULL OR state->'classificationRequests' ? %s) "
            "AND EXISTS(SELECT 1 FROM jsonb_array_elements(state->'sources') member "
            "WHERE member->>'id'=%s AND member->>'pairHash'=%s) "
            'ORDER BY closed_at DESC,id DESC FOR UPDATE NOWAIT',
            (row[1], attempt.get('inputHash'), attempt.get('inputHash'), attempt['source'], attempt['pairHash'])).fetchall()
        selected = None
        for identifier, saved in archived:
            if (any(source['id'] == attempt['source'] and source['pairHash'] == attempt['pairHash']
                    for source in saved.get('sources', ()))
                    and (attempt.get('inputHash') is None
                         or attempt['inputHash'] in saved.get('classificationRequests', {}))):
                selected = identifier, saved
                break
        if selected is None:
            source = next((source for source in state['sources']
                if source['id'] == attempt['source'] and source['pairHash'] == attempt['pairHash']), None)
            if source is None:
                return None  # A diagnostic with no retained request owns no new bytes.
            identifier = self.archive_source_in_transaction(row, source, state, at=attempt['at'],
                                                             input_hash=attempt.get('inputHash'))
            saved = self.connection.execute('SELECT state FROM public.mycel_drifts WHERE id=%s',
                                            (identifier,)).fetchone()[0]
        else:
            identifier, saved = selected
        updated = _copy(saved)
        value = {key: _copy(member) for key, member in attempt.items() if key != 'bundle'}
        value['obsolete'] = True
        if value not in updated['history']:
            updated['history'].append(value)
            self.connection.execute('UPDATE public.mycel_drifts SET state=%s WHERE id=%s',
                                    (Jsonb(updated), identifier))
        attempt['bundle'] = str(identifier)
        return str(identifier)

    def retain_live_references_in_transaction(self, row, state):
        require_transaction_guards(self.connection, (row[1],))
        keep = [ordinal for _, _, ordinal in self._references(row[6], state, live=True)]
        self.connection.execute('DELETE FROM public.mycel_evidence_references WHERE owner=%s '
            'AND NOT (ordinal=ANY(%s))', (row[6], keep))

    def prune_in_transaction(self, repository):
        """Newest 1,000 closure-time/full-ID records, plus protected records.

        Active current-version suppression, externally owned bundles and live
        leases can exceed the bound. Shared blobs remain owned independently.
        Reports and activity pruning never call this writing boundary.
        """
        from ._collection import CollectionStore, _RELEASE_OWNER_SQL
        require_transaction_guards(self.connection, (repository,))
        from ._locks import invocation_is_live
        ended = self.connection.execute("SELECT id,invocation FROM public.mycel_evidence_owners "
            "WHERE repository=%s AND kind='classification_lease' AND invocation IS NOT NULL "
            'ORDER BY id FOR UPDATE NOWAIT', (repository,)).fetchall()
        for lease, invocation in ended:
            if not invocation_is_live(self.connection, invocation):
                self.connection.execute("DELETE FROM public.mycel_evidence_owners WHERE id=%s "
                    "AND repository=%s AND kind='classification_lease' AND invocation=%s",
                    (lease, repository, invocation))
        rows = self.connection.execute('SELECT id,evidence_owner FROM public.mycel_drifts '
            'WHERE repository=%s AND closed_at IS NOT NULL ORDER BY closed_at DESC,id DESC '
            'OFFSET %s FOR UPDATE NOWAIT', (repository, HISTORY_LIMIT)).fetchall()
        removed = []
        for identifier, owner in rows:
            protected = self.connection.execute("""SELECT EXISTS (
                SELECT 1 FROM public.mycel_drifts d WHERE d.id=%s AND (
                  EXISTS (SELECT 1 FROM public.mycel_locations l
                    JOIN public.mycel_stale_reasons stale ON stale.chunk_version=l.chunk_version
                    JOIN LATERAL jsonb_array_elements(d.state->'sources') source ON true
                    WHERE l.chunk_version=d.dependant_version
                      AND source->'closed'->>'because'='still_supported'
                      AND source->'classification'->>'judgement'='still_supported'
                      AND stale.id::text=source->>'staleReason'
                      AND stale.reason->'classification'->>'pairHash'=source->>'pairHash'
                      AND stale.reason->'classification'->>'inputHash' IS NOT DISTINCT FROM
                          source->'classification'->>'inputHash')
                  OR EXISTS (SELECT 1 FROM public.mycel_dependencies x WHERE x.baseline_owner=d.evidence_owner)
                  OR EXISTS (SELECT 1 FROM public.mycel_relations x WHERE x.baseline_owner=d.evidence_owner)
                  OR EXISTS (SELECT 1 FROM public.mycel_verifications x WHERE x.evidence_owner=d.evidence_owner)
                  OR EXISTS (SELECT 1 FROM public.mycel_classification_work x WHERE x.evidence_owner=d.evidence_owner)
                  OR EXISTS (SELECT 1 FROM public.mycel_evidence_owners x WHERE x.id=d.evidence_owner AND x.invocation IS NOT NULL)
                  OR EXISTS (SELECT 1 FROM jsonb_each(COALESCE(d.state->'classificationRequests','{}'::jsonb)) request
                    JOIN public.mycel_evidence_references leased ON leased.repository=d.repository
                      AND ('snapshot:' || leased.snapshot_hash IN
                        (request.value->>'payloadSnapshot',request.value->>'bundleSnapshot'))
                    JOIN public.mycel_evidence_owners lease ON lease.id=leased.owner
                    WHERE lease.invocation IS NOT NULL)))""", (identifier,)).fetchone()[0]
            if protected:
                continue
            self.connection.execute('DELETE FROM public.mycel_drifts WHERE id=%s', (identifier,))
            self.connection.execute(_RELEASE_OWNER_SQL, (owner, repository))
            removed.append(str(identifier))
        if removed:
            # Remove only metadata whose complete owning bundle was collected.
            live = self.connection.execute("SELECT id,state,closed_at,evidence_owner FROM public.mycel_drifts WHERE repository=%s "
                "AND state->>'schema'='mycel-drift-work-v1' FOR UPDATE NOWAIT", (repository,)).fetchall()
            for identifier, state, closed_at, owner in live:
                updated = dict(state)
                updated['history'] = [item for item in state['history'] if item.get('bundle') not in removed]
                updated['sources'] = [source for source in state['sources'] if source.get('historyBundle') not in removed]
                if not updated['sources'] and closed_at is not None:
                    self.connection.execute('DELETE FROM public.mycel_drifts WHERE id=%s', (identifier,))
                    self.connection.execute(_RELEASE_OWNER_SQL, (owner, repository))
                    removed.append(str(identifier))
                elif updated != state:
                    self.connection.execute('UPDATE public.mycel_drifts SET state=%s WHERE id=%s',
                        (Jsonb(updated), identifier))
        snapshots, manifests = CollectionStore(self.connection).collect_evidence_in_transaction(repository)
        return {'records': len(removed), 'snapshots': snapshots, 'manifests': manifests}
