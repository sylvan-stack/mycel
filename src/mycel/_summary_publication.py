"""Private invocation-owned staging and one complete summary-tree publication.

Only immutable request evidence is committed while commands run. Prospective
chunk identities are reserved from the native sequence; no chunk, location,
embedding plan or vector row exists until the final caller-owned transaction.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from types import SimpleNamespace
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._collection import CollectionStore, _RELEASE_OWNER_SQL
from ._embedding_plan import EmbeddingPlan, document_place_line
from ._errors import MycelError
from ._evidence import EvidenceError
from ._generated import GeneratedPublicationStore
from ._locks import atomic_transaction, operation_guard, require_transaction_guards
from ._resolver import ResolvedChunk, SelectionMember
from ._safeguards import _defer_cleanup_signals
from ._source_refs import SourceAddress
from ._store import checked_store
from ._summary_evidence import (GenerationCapture, GenerationEvidenceStore,
    GenerationLease, _KIND, _OWNER_SQL, _REFERENCES_SQL, _INSERT_OWNER_SQL, _INSERT_REFERENCE_SQL)
from ._summary_store import PublishedSummaryState, SummarySetMetadata, summary_set_identifier


def _fail(reason='invalid_input'):
    raise EvidenceError(reason)


@dataclass(frozen=True)
class StagedSummary:
    member: SelectionMember
    lease: GenerationLease
    level: int


@dataclass(frozen=True)
class StagedSummaryEmbedding:
    summary: StagedSummary
    plan: EmbeddingPlan
    vectors: tuple[tuple[float, ...], ...]


class _StagedEvidence(GenerationEvidenceStore):
    def __init__(self, publisher):
        super().__init__(publisher.connection)
        self.publisher = publisher

    def _retain_in_transaction(self, invocation, capture):
        self._invocation(invocation)
        self._inputs(capture)
        self._write(capture)
        repository, digest = self.publisher.repository, capture.manifest.identifier
        owner = uuid4()
        identity = f'{invocation.id}:{digest}:{owner}'
        self.connection.execute(_INSERT_OWNER_SQL, (owner, repository, _KIND, identity, invocation.id))
        for number, (snapshot_hash, manifest_hash) in enumerate(self._refs(capture)):
            self.connection.execute(_INSERT_REFERENCE_SQL,
                (owner, repository, snapshot_hash, manifest_hash, number))
        return GenerationLease(owner, repository, invocation, digest, digest, identity)

    def _inputs(self, capture):
        publisher = self.publisher
        documents = []
        self._invocation(publisher.invocation)
        for item in capture.manifest.payload['members']:
            if item['kind'] == 'document':
                documents.append(item)
                continue
            staged = publisher._staged.get(item['id'])
            if staged is None:
                _fail('inputs_changed')
            publisher._validate_stage(staged)
            member = staged.member
            if (item['version'] != member.chunk.version or item['source']['hash'] != member.chunk.snapshot_hash
                    or item['place']['address'] != member.place.address or item['comparison'] != {}
                    or item['title'] is not None):
                _fail('inputs_changed')
        # The exact disk-bound checks remain the existing evidence boundary's.
        restricted = SimpleNamespace(manifest=SimpleNamespace(payload={
            'ownerRepository': publisher.repository, 'members': tuple(documents)}), snapshots=capture.snapshots)
        super()._inputs(restricted)


class SummaryPublicationStore:
    def __init__(self, connection, settings, invocation, repository: str):
        self.connection, self.settings = connection, settings
        self.invocation, self.repository = invocation, repository
        self._leases: dict[UUID, GenerationLease] = {}
        self._staged: dict[str, StagedSummary] = {}
        self._evidence = _StagedEvidence(self)
        self._final = None
        self._release_pending = False

    def retain_request(self, capture: GenerationCapture) -> GenerationLease:
        """Retain every actual request before its command, including higher levels."""
        if (not isinstance(capture, GenerationCapture) or 'response' in capture.manifest.payload
                or capture.manifest.payload['ownerRepository'] != self.repository
                or any(item['place']['repository'] != self.repository for item in capture.manifest.payload['members'])):
            _fail()
        lease = self._evidence.retain(self.invocation, capture)
        self._leases[lease.owner_id] = lease
        return lease

    def stage_response(self, lease: GenerationLease, response: bytes, *, place: SourceAddress,
                       level: int) -> StagedSummary:
        """Retain a response and reserve its exact future version without index rows."""
        if (not isinstance(lease, GenerationLease) or not isinstance(place, SourceAddress)
                or self._leases.get(lease.owner_id) != lease or place.repository != self.repository
                or place.root != 'index' or place.path != 'summaries' or type(level) is not int
                or not 1 <= level <= 5 or place.name is None
                or place.name.split('/')[0] != str(level)
                or len(place.name.split('/')) != 2 or not place.name.split('/')[1].isdigit()
                or str(int(place.name.split('/')[1])) != place.name.split('/')[1]
                or int(place.name.split('/')[1]) < 1
                or any(item.member.place == place for item in self._staged.values())):
            _fail()
        with checked_store(self.connection), operation_guard(self.connection, self.repository, 'pass'), \
                atomic_transaction(self.connection):
            completed = self._evidence.retain_response_in_transaction(self.invocation, lease, response)
            version = self.connection.execute("SELECT nextval(pg_get_serial_sequence("
                "'public.mycel_chunk_versions','id'))").fetchone()[0]
        self._leases[completed.owner_id] = completed
        identifier = str(uuid4())
        member = SelectionMember(place, ResolvedChunk(identifier, version, place.name, 'summary',
            response, sha256(response).hexdigest()))
        staged = StagedSummary(member, completed, level)
        self._staged[identifier] = staged
        return staged

    def _validate_stage(self, staged):
        if (not isinstance(staged, StagedSummary) or self._staged.get(staged.member.chunk.identifier) != staged
                or self._leases.get(staged.lease.owner_id) != staged.lease):
            _fail()
        lease = staged.lease
        self._evidence._invocation(self.invocation)
        identity = lease.identity
        if self.connection.execute(_OWNER_SQL, (self.repository, _KIND, identity)).fetchone() != (
                lease.owner_id, self.repository, _KIND, identity, self.invocation.id):
            _fail()
        capture = self._evidence._read(self.repository, lease.manifest_hash)
        if ('response' not in capture.manifest.payload
                or capture.manifest.payload['response']['hash'] != staged.member.chunk.snapshot_hash):
            _fail()
        response = next(blob.source for blob in capture.snapshots
                        if blob.evidence.hash == capture.manifest.payload['response']['hash'])
        if response != staged.member.chunk.source:
            _fail()
        refs = self.connection.execute(_REFERENCES_SQL, (lease.owner_id, self.repository)).fetchall()
        expected = {(None, lease.request_manifest), *self._evidence._refs(capture)}
        if (len(refs) != len(expected) or [ordinal for ordinal, _, _ in refs] != list(range(len(refs)))
                or {(snap, manifest) for _, snap, manifest in refs} != expected):
            _fail('snapshot_corrupt')
        return capture

    def _embedding(self, value):
        if not isinstance(value, StagedSummaryEmbedding) or not isinstance(value.plan, EmbeddingPlan):
            _fail()
        staged, plan, vectors = value.summary, value.plan, value.vectors
        self._validate_stage(staged)
        chunk = staged.member.chunk
        settings = self.settings.values['embedding']
        if (plan.repository != self.repository or plan.chunk_id != chunk.identifier
                or plan.chunk_version != str(chunk.version) or plan.text_sha256 != chunk.snapshot_hash
                or plan.text.encode('utf-8') != chunk.source or plan.kind != 'document'
                or plan.place_line != document_place_line(staged.member.place.path, staged.member.place.name)
                or (plan.model, plan.dimensions) != (settings['model'], settings['dimensions'])
                or not plan.parts or type(vectors) is not tuple or len(vectors) != len(plan.parts)):
            _fail()
        offset = 0
        for number, (part, vector) in enumerate(zip(plan.parts, vectors)):
            if (part.order != number or part.start_byte != offset or part.end_byte < offset
                    or part.text.encode('utf-8') != chunk.source[part.start_byte:part.end_byte]
                    or part.input_text != plan.place_line + '\n' + part.text
                    or type(vector) is not tuple or len(vector) != plan.dimensions
                    or any(type(number) not in {int, float} or not math.isfinite(number) for number in vector)):
                _fail()
            offset = part.end_byte
        if offset != len(chunk.source):
            _fail()

    def _write_embedding(self, result, value):
        plan, vectors, identifier = value.plan, value.vectors, uuid4()
        self.connection.execute('INSERT INTO public.mycel_embedding_plans '
            '(id,chunk_version,model,dimensions,plan_hash,place_line,provenance,failure) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)', (identifier, result.chunk_version, plan.model,
                plan.dimensions, plan.plan_sha256, plan.place_line, Jsonb(plan.to_dict())))
        for part, vector in zip(plan.parts, vectors):
            self.connection.execute('INSERT INTO public.mycel_embedding_parts '
                '(plan_id,part_order,byte_start,byte_end,input_bytes,submitted_tokens,planning_tokens) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)', (identifier, part.order, part.start_byte, part.end_byte,
                    part.input_text.encode('utf-8'), part.submitted_tokens, part.planning_tokens))
            self.connection.execute('INSERT INTO public.mycel_vectors VALUES (%s,%s,%s,%s,%s::public.vector)',
                (identifier, part.order, plan.model, plan.dimensions,
                 json.dumps(vector, separators=(',', ':'), allow_nan=False)))
        return identifier

    def publish_in_transaction(self, values: Sequence[StagedSummaryEmbedding], metadata: SummarySetMetadata, *,
                               guarded_repositories: tuple[str, ...], guard=None):
        """Replace all current summaries, pins and vectors in the caller's transaction.

        The caller owns the summary lock, checked store, pass guards and atomic
        transaction. Its guard validates the retained full eligible input set.
        Call verify_in_transaction again after caller-owned audit writes.
        """
        require_transaction_guards(self.connection, guarded_repositories)
        self.settings.require_current()
        self._evidence._invocation(self.invocation)
        if (not isinstance(values, (list, tuple)) or not isinstance(metadata, SummarySetMetadata)
                or any(not isinstance(value, StagedSummaryEmbedding) for value in values)
                or self.repository not in guarded_repositories or self._final is not None):
            _fail()
        PublishedSummaryState.from_dict(PublishedSummaryState(1, 1, (), metadata).to_dict(),
                                       repository=self.repository)
        ordered = tuple(sorted(values, key=lambda value: (value.summary.level,
            int(value.summary.member.place.name.split('/')[1]))))
        if (len({value.summary.member.chunk.identifier for value in ordered}) != len(ordered)
                or {value.summary.member.chunk.identifier for value in ordered} != set(self._staged)):
            _fail()
        for value in ordered:
            self._embedding(value)
        if guard is not None:
            guard()
        old = self.connection.execute("SELECT c.id FROM public.mycel_chunks c "
            "WHERE c.repository=%s AND c.kind='summary' ORDER BY c.id FOR UPDATE NOWAIT", (self.repository,)).fetchall()
        owners = self.connection.execute('SELECT DISTINCT d.baseline_owner FROM public.mycel_dependencies d '
            'JOIN public.mycel_chunk_versions v ON v.id=d.dependant_version JOIN public.mycel_chunks c ON c.id=v.chunk_id '
            "WHERE c.repository=%s AND c.kind='summary' AND d.baseline_owner IS NOT NULL", (self.repository,)).fetchall()
        self.connection.execute("DELETE FROM public.mycel_chunks WHERE repository=%s AND kind='summary'", (self.repository,))
        publisher, results, plans = GeneratedPublicationStore(self.connection), [], []
        for value in ordered:
            staged = value.summary
            result = publisher.publish_in_transaction(self.settings, self.invocation, staged.lease,
                chunk_id=UUID(staged.member.chunk.identifier), place=staged.member.place, level=staged.level,
                metadata=metadata, guarded_repositories=guarded_repositories,
                reserved_version=staged.member.chunk.version)
            results.append(result)
            plans.append((self._write_embedding(result, value), value))
        sentinel = summary_set_identifier(self.repository)
        self.connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,%s) ON CONFLICT DO NOTHING',
            (sentinel, self.repository, 'summary_set', Jsonb({})))
        if self.connection.execute('SELECT repository,file_id,kind FROM public.mycel_chunks WHERE id=%s',
                (sentinel,)).fetchone() != (self.repository, None, 'summary_set'):
            _fail('snapshot_corrupt')
        state = {'schemaVersion': 1, 'set': metadata.to_dict()}
        self.connection.execute('INSERT INTO public.mycel_generated_state VALUES (%s,%s,%s,%s) '
            'ON CONFLICT (chunk_id) DO UPDATE SET kind=EXCLUDED.kind,state=EXCLUDED.state',
            (sentinel, self.repository, 'summary_set', Jsonb(state)))
        for owner, in owners:
            self.connection.execute(_RELEASE_OWNER_SQL, (owner, self.repository))
        self._final = (publisher, tuple(results), tuple(plans), state, guarded_repositories, guard)
        self.verify_in_transaction()
        return tuple(results), len(old)

    def verify_in_transaction(self):
        if self._final is None:
            _fail()
        publisher, results, plans, state, guarded, guard = self._final
        require_transaction_guards(self.connection, guarded)
        publisher.verify_in_transaction()
        catalog = self.connection.execute("SELECT c.id,g.kind,g.state FROM public.mycel_chunks c "
            "LEFT JOIN public.mycel_generated_state g ON g.chunk_id=c.id WHERE c.repository=%s "
            "AND c.kind='summary' ORDER BY c.id", (self.repository,)).fetchall()
        if {str(row[0]) for row in catalog} != {result.chunk_id for result in results} or len(catalog) != len(results):
            _fail('snapshot_corrupt')
        if self.connection.execute('SELECT kind,state FROM public.mycel_generated_state WHERE chunk_id=%s',
                (summary_set_identifier(self.repository),)).fetchone() != ('summary_set', state):
            _fail('snapshot_corrupt')
        for identifier, value in plans:
            plan = value.plan
            row = self.connection.execute('SELECT chunk_version,model,dimensions,plan_hash,place_line,provenance,failure '
                'FROM public.mycel_embedding_plans WHERE id=%s', (identifier,)).fetchone()
            if row != (value.summary.member.chunk.version, plan.model, plan.dimensions, plan.plan_sha256,
                    plan.place_line, plan.to_dict(), None):
                _fail('snapshot_corrupt')
            rows = self.connection.execute('SELECT p.part_order,p.byte_start,p.byte_end,p.input_bytes,'
                'p.submitted_tokens,p.planning_tokens,p.failure,v.model,v.dimensions,v.embedding::text '
                'FROM public.mycel_embedding_parts p LEFT JOIN public.mycel_vectors v '
                'ON v.plan_id=p.plan_id AND v.part_order=p.part_order WHERE p.plan_id=%s ORDER BY p.part_order',
                (identifier,)).fetchall()
            if len(rows) != len(plan.parts):
                _fail('snapshot_corrupt')
            for row, part, vector in zip(rows, plan.parts, value.vectors):
                if (row[:9] != (part.order, part.start_byte, part.end_byte, part.input_text.encode('utf-8'),
                        part.submitted_tokens, part.planning_tokens, None, plan.model, plan.dimensions)
                        or any(not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-7)
                               for actual, expected in zip(json.loads(row[9]), vector))):
                    _fail('snapshot_corrupt')
        self.settings.require_current()
        self._evidence._invocation(self.invocation)
        if guard is not None:
            guard()

    def discard(self):
        """Release only this publisher's exact invocation-owned private leases."""
        if not self._leases:
            return
        with _defer_cleanup_signals(), checked_store(self.connection), atomic_transaction(self.connection):
            self._delete_private()
        self._leases.clear()
        self._staged.clear()
        # Collection can yield to ingest. Private owner release already ended
        # atomically and cannot turn a committed tree into a failed build reply.
        try:
            with checked_store(self.connection), operation_guard(self.connection, self.repository, 'pass'), \
                    atomic_transaction(self.connection):
                CollectionStore(self.connection).collect_evidence_in_transaction(self.repository)
        except MycelError as error:
            if error.code != 'busy':
                raise

    def _delete_private(self):
        for owner in self._leases:
            self.connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s AND repository=%s '
                'AND kind=%s AND invocation=%s', (owner, self.repository, _KIND, self.invocation.id))

    def release_in_transaction(self):
        """Transfer/release private evidence last, before publication commit.

        Final verification must precede this call. The later release remains
        safe even if the caller's transaction rolls back after this deletion.
        """
        require_transaction_guards(self.connection, (self.repository,))
        self._delete_private()
        CollectionStore(self.connection).collect_evidence_in_transaction(self.repository)
        self._release_pending = True

    def confirm_release(self):
        """Forget released leases only after the caller confirms its outer commit."""
        if not self._release_pending:
            _fail()
        self._leases.clear()
        self._staged.clear()
        self._release_pending = False

    release = discard
