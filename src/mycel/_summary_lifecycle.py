"""Guarded per-summary publication, withdrawal and complete set removal."""
from __future__ import annotations

from contextlib import ExitStack
import json
import math
from types import SimpleNamespace
from uuid import UUID

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation, MutationActivity
from ._build_identity import current_build
from ._collection import CollectionStore, _RELEASE_OWNER_SQL
from ._embedding_plan import EmbeddingPlan, document_place_line
from ._errors import MycelError
from ._evidence import EvidenceError, exact_bytes
from ._generated import GeneratedPublicationStore
from ._locks import atomic_transaction, invocation_guard, operation_guard, require_transaction_guards
from ._safeguards import _defer_cleanup_signals
from ._store import checked_store
from ._summary_evidence import GenerationEvidenceStore, GenerationLease, _KIND, _OWNER_SQL, _REFERENCES_SQL
from ._summary_publication import SummaryPublicationStore
from ._summary_store import _Summary, _set_metadata, summary_removal_reply, summary_repository, summary_set_identifier


def _fail(reason='snapshot_corrupt'):
    raise EvidenceError(reason)


class SummaryLifecycleStore:
    """A caller owns the summary lock and each publication's atomic transaction.

    Prospective versions reserve sequence identities only. A produced response,
    its embedding and its exact member evidence become visible together.
    """
    def __init__(self, connection, settings, invocation, repository):
        self.connection, self.settings = connection, settings
        self.invocation, self.repository = invocation, repository
        self._reserved = {}
        self._checks = []

    def _bound(self, repositories):
        require_transaction_guards(self.connection, repositories)
        if self.repository not in repositories:
            _fail('invalid_input')
        row = self.connection.execute("SELECT EXISTS (SELECT 1 FROM public.mycel_lock_keys k "
            "JOIN pg_catalog.pg_locks l ON l.classid::bigint=(k.key >> 32) "
            "AND l.objid::bigint=(k.key & 4294967295) WHERE k.namespace='repository.summaries' "
            "AND k.identity=%s AND l.locktype='advisory' AND l.objsubid=1 AND l.granted "
            "AND l.mode='ExclusiveLock' AND l.pid=pg_catalog.pg_backend_pid() "
            "AND l.database=(SELECT oid FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database()))",
            (self.repository,)).fetchone()
        if row != (True,):
            _fail('invalid_input')
        self.settings.require_current()
        GenerationEvidenceStore(self.connection)._invocation(self.invocation)

    def _target(self, summary):
        if (not isinstance(summary, _Summary) or summary.member.place.repository != self.repository
                or summary.member.place.root != 'index' or summary.member.place.path != 'summaries'
                or summary.member.chunk.kind != 'summary'):
            _fail('invalid_input')
        member, chunk = summary.member, summary.member.chunk
        row = self.connection.execute('SELECT c.repository,c.kind,c.file_id,g.kind,g.state FROM public.mycel_chunks c '
            'LEFT JOIN public.mycel_generated_state g ON g.chunk_id=c.id WHERE c.id=%s FOR UPDATE OF c NOWAIT',
            (chunk.identifier,)).fetchone()
        if row != (self.repository, 'summary', None, 'summary', summary.state.to_dict()):
            _fail('inputs_changed')
        locations = self.connection.execute('SELECT l.chunk_version,l.location,l.metadata,v.snapshot_hash,v.source_bytes '
            'FROM public.mycel_locations l JOIN public.mycel_chunk_versions v ON v.id=l.chunk_version '
            "WHERE v.chunk_id=%s AND l.kind='index' ORDER BY l.id FOR SHARE OF l,v NOWAIT",
            (chunk.identifier,)).fetchall()
        expected = (chunk.version, member.place.address,
            {'name': member.place.name, 'path': 'summaries', 'level': summary.state.level},
            chunk.snapshot_hash, chunk.source)
        if len(locations) != 1 or (*locations[0][:4], exact_bytes(locations[0][4])) != expected:
            _fail('inputs_changed')

    def _capture(self, lease):
        if not isinstance(lease, GenerationLease) or lease.invocation != self.invocation or lease.repository != self.repository:
            _fail('invalid_input')
        evidence = GenerationEvidenceStore(self.connection)
        evidence._invocation(self.invocation)
        if self.connection.execute(_OWNER_SQL, (self.repository, _KIND, lease.identity)).fetchone() != (
                lease.owner_id, self.repository, _KIND, lease.identity, self.invocation.id):
            _fail('invalid_input')
        capture = evidence._read(self.repository, lease.manifest_hash)
        if 'response' not in capture.manifest.payload:
            _fail('invalid_input')
        refs = self.connection.execute(_REFERENCES_SQL, (lease.owner_id, self.repository)).fetchall()
        expected = {(None, lease.request_manifest), *evidence._refs(capture)}
        if (len(refs) != len(expected) or [row[0] for row in refs] != list(range(len(refs)))
                or {(snap, manifest) for _, snap, manifest in refs} != expected):
            _fail()
        digest = capture.manifest.payload['response']['hash']
        return capture, next(blob.source for blob in capture.snapshots if blob.evidence.hash == digest)

    def reserve_response(self, summary, lease):
        """Reserve the exact future version without a chunk, location or vector write."""
        with checked_store(self.connection), operation_guard(self.connection, self.repository, 'pass'), \
                atomic_transaction(self.connection):
            self._bound((self.repository,))
            self._target(summary)
            capture, _ = self._capture(lease)
            digest = capture.manifest.payload['response']['hash']
            key = (summary.member.chunk.identifier, lease.owner_id, lease.manifest_hash)
            if key in self._reserved:
                return self._reserved[key]
            row = self.connection.execute('SELECT id FROM public.mycel_chunk_versions WHERE chunk_id=%s AND snapshot_hash=%s',
                (summary.member.chunk.identifier, digest)).fetchone()
            version = row[0] if row is not None else self.connection.execute("SELECT nextval(pg_get_serial_sequence("
                "'public.mycel_chunk_versions','id'))").fetchone()[0]
            self._reserved[key] = version
            return version

    def _embedding(self, summary, lease, plan, vectors):
        capture, response = self._capture(lease)
        version = self._reserved.get((summary.member.chunk.identifier, lease.owner_id, lease.manifest_hash))
        embedding = self.settings.values['embedding']
        if (not isinstance(plan, EmbeddingPlan) or version is None or plan.repository != self.repository
                or plan.chunk_id != summary.member.chunk.identifier or plan.chunk_version != str(version)
                or plan.text_sha256 != capture.manifest.payload['response']['hash']
                or plan.text.encode('utf-8') != response or plan.kind != 'document'
                or plan.place_line != document_place_line('summaries', summary.member.place.name)
                or (plan.model, plan.dimensions) != (embedding['model'], embedding['dimensions'])
                or not plan.parts or type(vectors) is not tuple or len(vectors) != len(plan.parts)):
            _fail('invalid_input')
        offset = 0
        for number, (part, vector) in enumerate(zip(plan.parts, vectors)):
            if (part.order != number or part.start_byte != offset or part.end_byte < offset
                    or part.text.encode('utf-8') != response[part.start_byte:part.end_byte]
                    or part.input_text != plan.place_line + '\n' + part.text
                    or type(vector) is not tuple or len(vector) != plan.dimensions
                    or any(type(value) not in {int, float} or not math.isfinite(value) for value in vector)):
                _fail('invalid_input')
            offset = part.end_byte
        if offset != len(response):
            _fail('invalid_input')
        return version, response

    def _owners(self, identifiers):
        return self.connection.execute('SELECT DISTINCT o.id,o.repository FROM public.mycel_evidence_owners o WHERE o.id IN ('
            'SELECT d.baseline_owner FROM public.mycel_dependencies d JOIN public.mycel_chunk_versions v ON v.id=d.dependant_version '
            'WHERE v.chunk_id=ANY(%s::uuid[]) UNION SELECT w.evidence_owner FROM public.mycel_classification_work w '
            'JOIN public.mycel_dependencies d ON d.id=w.dependency JOIN public.mycel_chunk_versions v ON v.id=d.dependant_version '
            'WHERE v.chunk_id=ANY(%s::uuid[]) UNION SELECT v.evidence_owner FROM public.mycel_verifications v '
            'WHERE v.chunk_id=ANY(%s::uuid[]) UNION SELECT r.baseline_owner FROM public.mycel_relations r '
            'JOIN public.mycel_chunk_versions v ON v.id=r.left_version WHERE v.chunk_id=ANY(%s::uuid[])) ORDER BY o.repository,o.id',
            (identifiers, identifiers, identifiers, identifiers)).fetchall()

    def _release(self, owners, repositories):
        require_transaction_guards(self.connection, tuple(sorted({self.repository, *(owner for _, owner in owners)})))
        for identifier, repository in owners:
            self.connection.execute(_RELEASE_OWNER_SQL, (identifier, repository))
        for repository in sorted({self.repository, *(owner for _, owner in owners)}):
            CollectionStore(self.connection).collect_evidence_in_transaction(repository)

    def publish_in_transaction(self, summary, lease, plan, vectors, *, guarded_repositories, guard=None):
        self._bound(guarded_repositories)
        self._target(summary)
        if guard is not None:
            guard()
        version, response = self._embedding(summary, lease, plan, vectors)
        chunk_id = UUID(summary.member.chunk.identifier)
        owners = self._owners([chunk_id])
        # The reserved row is created only inside this final transaction. The
        # existing publisher's content upsert then chooses this same identity.
        row = self.connection.execute('SELECT id,source_bytes FROM public.mycel_chunk_versions '
            'WHERE chunk_id=%s AND snapshot_hash=%s', (chunk_id, plan.text_sha256)).fetchone()
        if row is None:
            self.connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(id,chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) OVERRIDING SYSTEM VALUE '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)', (version, chunk_id, plan.text_sha256, response,
                response.decode('utf-8').replace('\0', '\ufffd'), Jsonb({}),
                Jsonb({'kind': 'summary', 'name': summary.member.place.name, 'path': 'summaries', 'level': summary.state.level})))
        elif row[0] != version or exact_bytes(row[1]) != response:
            _fail('inputs_changed')
        publisher = GeneratedPublicationStore(self.connection)
        result = publisher.publish_in_transaction(self.settings, self.invocation, lease,
            chunk_id=chunk_id, place=summary.member.place, level=summary.state.level,
            metadata=summary.state.metadata, guarded_repositories=guarded_repositories)
        if result.chunk_version != version:
            _fail()
        self.connection.execute('DELETE FROM public.mycel_dependencies d USING public.mycel_chunk_versions v '
            "WHERE d.dependant_version=v.id AND v.chunk_id=%s AND v.id<>%s AND d.kind='generated'", (chunk_id, version))
        self.connection.execute('DELETE FROM public.mycel_embedding_plans p USING public.mycel_chunk_versions v '
            'WHERE p.chunk_version=v.id AND v.chunk_id=%s', (chunk_id,))
        value = SimpleNamespace(plan=plan, vectors=vectors)
        identifier = SummaryPublicationStore._write_embedding(self, result, value)
        self._release(owners, guarded_repositories)
        self._checks.append(('publish', publisher, result, identifier, plan, vectors, guarded_repositories, guard))
        self.verify_in_transaction()
        return result

    def _detect(self, repositories):
        from ._staleness import DetectionGuards, MechanicalStalenessStore
        detector, guards = MechanicalStalenessStore(self.connection), DetectionGuards(repositories, {})
        _, _, pending = detector.apply_in_transaction(self.settings, self.repository, guards)
        if pending:
            _fail('inputs_changed')
        return detector, guards

    def delete_in_transaction(self, summary, *, guarded_repositories, guard=None):
        """Withdraw a now-memberless node and recompute its surviving parents."""
        self._bound(guarded_repositories)
        self._target(summary)
        if guard is not None:
            guard()
        identifier = UUID(summary.member.chunk.identifier)
        owners = self._owners([identifier])
        self.connection.execute('DELETE FROM public.mycel_chunks WHERE id=%s AND repository=%s', (identifier, self.repository))
        self._release(owners, guarded_repositories)
        detector, guards = self._detect(guarded_repositories)
        self._checks.append(('delete', identifier, detector, guards, guarded_repositories, guard))
        self.verify_in_transaction()
        return 1

    def remove_in_transaction(self, *, guarded_repositories, guard=None):
        """Remove the complete set, its metadata, and only released evidence."""
        self._bound(guarded_repositories)
        if guard is not None:
            guard()
        rows = self.connection.execute("SELECT id FROM public.mycel_chunks WHERE repository=%s "
            "AND kind='summary' ORDER BY id FOR UPDATE NOWAIT", (self.repository,)).fetchall()
        owners = self._owners([identifier for identifier, in rows])
        sentinel = summary_set_identifier(self.repository)
        # The deterministic identity is reserved for an unlocated, typed set
        # owner. Never let a corrupted sentinel delete an ordinary chunk.
        _set_metadata(self.connection, self.repository, ())
        metadata = self.connection.execute('SELECT EXISTS(SELECT 1 FROM public.mycel_chunks WHERE id=%s AND repository=%s)',
            (sentinel, self.repository)).fetchone()[0]
        self.connection.execute("DELETE FROM public.mycel_chunks WHERE repository=%s AND (kind='summary' OR id=%s)",
            (self.repository, sentinel))
        if rows or metadata:
            self._release(owners, guarded_repositories)
        self._checks.append(('remove', sentinel, guarded_repositories, guard))
        self.verify_in_transaction()
        return len(rows), bool(rows or metadata)

    def verify_in_transaction(self):
        for check in self._checks:
            kind = check[0]
            if kind == 'publish':
                _, publisher, result, identifier, plan, vectors, repositories, guard = check
                self._bound(repositories)
                publisher.verify_in_transaction()
                row = self.connection.execute('SELECT chunk_version,model,dimensions,plan_hash,place_line,provenance,failure '
                    'FROM public.mycel_embedding_plans WHERE id=%s', (identifier,)).fetchone()
                if row != (result.chunk_version, plan.model, plan.dimensions, plan.plan_sha256,
                        plan.place_line, plan.to_dict(), None):
                    _fail()
                parts = self.connection.execute('SELECT p.part_order,p.byte_start,p.byte_end,p.input_bytes,p.submitted_tokens,'
                    'p.planning_tokens,p.failure,v.model,v.dimensions,v.embedding::text FROM public.mycel_embedding_parts p '
                    'LEFT JOIN public.mycel_vectors v ON v.plan_id=p.plan_id AND v.part_order=p.part_order '
                    'WHERE p.plan_id=%s ORDER BY p.part_order', (identifier,)).fetchall()
                if len(parts) != len(plan.parts):
                    _fail()
                for row, part, vector in zip(parts, plan.parts, vectors):
                    if (row[:9] != (part.order, part.start_byte, part.end_byte, part.input_text.encode('utf-8'),
                            part.submitted_tokens, part.planning_tokens, None, plan.model, plan.dimensions)
                            or row[9] is None or len(json.loads(row[9])) != len(vector)
                            or any(not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-7)
                                   for actual, expected in zip(json.loads(row[9]), vector))):
                        _fail()
            elif kind == 'delete':
                _, identifier, detector, guards, repositories, guard = check
                self._bound(repositories)
                detector.verify_in_transaction(self.settings, guards)
                if self.connection.execute('SELECT EXISTS(SELECT 1 FROM public.mycel_chunks WHERE id=%s)',
                        (identifier,)).fetchone() != (False,):
                    _fail()
            else:
                _, sentinel, repositories, guard = check
                self._bound(repositories)
                if self.connection.execute("SELECT EXISTS(SELECT 1 FROM public.mycel_chunks WHERE repository=%s "
                        "AND (kind='summary' OR id=%s))", (self.repository, sentinel)).fetchone() != (False,):
                    _fail()
            if guard is not None:
                guard()


def remove_summaries(invocation, *, _store=None, _before_publish=None):
    """Explicit removal needs neither a summary command nor model credentials."""
    from ._cli import Result, invocation_store
    settings = invocation.settings
    repository = summary_repository(settings, invocation.repositories)
    committed, reply = False, None
    try:
        with ExitStack() as stack:
            connection, _ = (_store if _store is not None else stack.enter_context(invocation_store(invocation)))
            stack.enter_context(checked_store(connection, dimensions=settings.values['embedding']['dimensions']))
            stack.enter_context(operation_guard(connection, repository, 'summaries'))
            build = current_build()
            activity = None if build is None else stack.enter_context(MutationActivity(connection, build=build).session())
            identity = activity.invocation if activity is not None else stack.enter_context(invocation_guard(connection))
            store = SummaryLifecycleStore(connection, settings, identity, repository)
            if _before_publish is not None:
                _before_publish()
            with _defer_cleanup_signals():
                with operation_guard(connection, repository, 'pass'), atomic_transaction(connection):
                    removed, changed = store.remove_in_transaction(guarded_repositories=(repository,))
                    reply = summary_removal_reply(repository, removed)
                    if activity is not None:
                        activity.record_in_transaction(repository, 'summaries_remove', AppliedMutation(changed, reply))
                    store.verify_in_transaction()
                committed = True
                if activity is not None:
                    activity.finish('done', counts={(repository, 'summaries_remove'): reply})
    except (MycelError, KeyboardInterrupt) as error:
        if not committed:
            raise
        # A final audit or connection-close fault must retain the acknowledged
        # mutation count, with the failure status still visible to the caller.
        interrupted = isinstance(error, KeyboardInterrupt)
        fault = ({'code': 'refused', 'message': 'Summary removal was stopped by the caller.'}
                 if interrupted else error.to_dict()['error'])
        return Result({**reply, 'stopped': 'interrupted' if interrupted else 'failed',
                       'error': fault, 'countsState': 'committed_prefix'}, 2 if interrupted else 1)
    return Result(reply)
