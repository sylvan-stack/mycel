"""Saved exact-version embedding plans, coverage and atomic SQL callbacks.

Settings remain invocation-owned. This module never initializes a database or
contacts a provider. Callers supply current place metadata from ingest; a valid
saved plan retains its original input context through later metadata moves.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ._embedding_plan import (BatchInput, EmbeddingBatch, EmbeddingPart, EmbeddingPlan,
                             ModelTokenizer, PlanProvenance, PlanningError, load_tokenizer,
                             plan_batches, plan_chunk, validate_plan, _provenance)
from ._errors import MycelError
from ._activity import AppliedMutation, MutationActivity
from ._locks import atomic_transaction, operation_guard, snapshot_transaction
from ._settings import SettingsSnapshot
from ._resolver import require_read_transaction
from ._store import checked_store, exact_bytes, exact_text
from ._voyage import CommitReceipt, PartFailure, PartIdentity, ProviderFailure, VectorWrite


_VERSION_ID = re.compile(r"[1-9][0-9]*\Z", re.ASCII)
_COUNT_CONTEXT = ("tokenizer_repository", "tokenizer_revision", "tokenizer_file", "tokenizer_sha256",
                  "tokenizers_version", "tokenizers_library_sha256", "planner_version", "counting_rule",
                  "document_prompt", "query_prompt", "padding", "truncation")
_VERSIONS_SQL = """SELECT c.repository, c.id, c.kind, c.metadata,
v.id, v.snapshot_hash, v.source_bytes, v.metadata
FROM public.mycel_chunks c JOIN public.mycel_chunk_versions v ON v.chunk_id = c.id
WHERE c.repository = %s AND EXISTS
(SELECT 1 FROM public.mycel_locations l WHERE l.chunk_version = v.id)
ORDER BY c.id, v.id"""
_PLANS_SQL = """SELECT p.id, p.chunk_version, p.plan_hash, p.place_line, p.provenance, p.failure
FROM public.mycel_embedding_plans p JOIN public.mycel_chunk_versions v ON v.id=p.chunk_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id
WHERE c.repository=%s AND p.model=%s AND p.dimensions=%s ORDER BY p.chunk_version"""
_PARTS_SQL = """SELECT p.plan_id,p.part_order,p.byte_start,p.byte_end,p.input_bytes,
p.submitted_tokens,p.planning_tokens,p.failure,v.embedding::text
FROM public.mycel_embedding_parts p LEFT JOIN public.mycel_vectors v
ON v.plan_id=p.plan_id AND v.part_order=p.part_order AND v.model=%s AND v.dimensions=%s
WHERE p.plan_id=ANY(%s) ORDER BY p.plan_id,p.part_order"""
_RETAINED_SQL = """SELECT v.id,c.id,v.snapshot_hash,v.source_bytes
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
WHERE c.repository=%s AND v.id=ANY(%s) FOR KEY SHARE OF v NOWAIT"""
_RECEIPTS_SQL = """SELECT id,repository,model,dimensions,payload
FROM public.mycel_embedding_receipts WHERE repository=%s AND model=%s AND dimensions=%s
ORDER BY created_at,id"""
_PUBLISHED_PLAN_SQL = """SELECT id,plan_hash,provenance,failure
FROM public.mycel_embedding_plans WHERE chunk_version=%s AND model=%s AND dimensions=%s
FOR UPDATE NOWAIT"""
_PUBLISHED_PART_SQL = """SELECT byte_start,byte_end,input_bytes,submitted_tokens,planning_tokens
FROM public.mycel_embedding_parts WHERE plan_id=%s AND part_order=%s FOR UPDATE NOWAIT"""
_RECEIPT_VERSIONS_SQL = """SELECT v.id,c.id,v.snapshot_hash,v.source_bytes,c.repository
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
WHERE v.id=ANY(%s) FOR KEY SHARE OF v NOWAIT"""
_RECEIPT_SQL = """SELECT id,repository,model,dimensions,payload
FROM public.mycel_embedding_receipts WHERE id=%s FOR UPDATE NOWAIT"""


def _frozen(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(member) for key, member in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_frozen(member) for member in value)
    return value


def _payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _receipt_payload(value) -> dict:
    try:
        payload = json.loads(exact_text(value))
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (ValueError, TypeError, MycelError):
        raise MycelError("invalid_input", "A deferred embedding receipt has invalid exact payload bytes.") from None


def _receipt_row(row):
    return None if row is None else (*row[:4], _receipt_payload(row[4]))


def _version_id(value: str) -> int:
    if not isinstance(value, str) or not _VERSION_ID.fullmatch(value) or int(value) > 2**63 - 1:
        raise MycelError("invalid_input", "An embedding version must be its exact positive store identifier.")
    return int(value)


def _chunk_id(value: str) -> UUID:
    try:
        result = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise MycelError("invalid_input", "An embedding chunk must be its stable UUID.") from None
    if str(result) != value:
        raise MycelError("invalid_input", "An embedding chunk must use its canonical stable UUID.")
    return result


@dataclass(frozen=True)
class EmbeddingContext:
    place_line: str
    kind: str


@dataclass(frozen=True)
class RetainedVersion:
    repository: str
    chunk_id: str
    chunk_kind: str
    chunk_metadata: Mapping[str, Any]
    version: str
    snapshot_hash: str
    text: str = field(repr=False)
    metadata: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class PartState:
    part: EmbeddingPart
    vector: tuple[float, ...] | None = field(default=None, repr=False)
    failure: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class VersionEmbedding:
    version: RetainedVersion
    id: UUID | None
    plan: EmbeddingPlan | None
    parts: tuple[PartState, ...]
    failure: Mapping[str, Any] | None = None

    @property
    def complete(self) -> bool:
        return (self.plan is not None and self.failure is None and bool(self.parts)
                and len(self.parts) == len(self.plan.parts)
                and all(part.vector is not None for part in self.parts))


@dataclass(frozen=True)
class EmbeddingCounts:
    embedded_versions: int = 0
    pending_versions: int = 0
    failed_versions: int = 0
    embedded_parts: int = 0
    pending_parts: int = 0
    failed_parts: int = 0
    ineligible_versions: int = 0
    deferred_versions: int = 0
    deferred_parts: int = 0

    def to_dict(self) -> dict:
        return {"versions": {"embedded": self.embedded_versions, "pending": self.pending_versions,
                             "failed": self.failed_versions, "deferred": self.deferred_versions},
                "parts": {"embedded": self.embedded_parts, "pending": self.pending_parts,
                          "failed": self.failed_parts, "deferred": self.deferred_parts}}


def _counts(versions: Sequence[VersionEmbedding], *, eligible: bool,
            staged: frozenset[PartIdentity] = frozenset()) -> EmbeddingCounts:
    embedded_versions = pending_versions = failed_versions = 0
    embedded_parts = pending_parts = failed_parts = ineligible_versions = 0
    deferred_versions = deferred_parts = 0
    for version in versions:
        embedded = sum(part.vector is not None for part in version.parts)
        failed = sum(part.vector is None and part.failure is not None and PartIdentity(
                     version.version.repository, version.version.chunk_id, version.version.version,
                     part.part.order) not in staged for part in version.parts)
        deferred = sum(part.vector is None and PartIdentity(version.version.repository,
                       version.version.chunk_id, version.version.version, part.part.order) in staged
                       for part in version.parts)
        missing = sum(part.vector is None and part.failure is None and PartIdentity(
                      version.version.repository, version.version.chunk_id, version.version.version,
                      part.part.order) not in staged for part in version.parts)
        embedded_parts += embedded
        failed_parts += failed
        pending_parts += missing if eligible else 0
        deferred_parts += deferred
        if version.complete:
            embedded_versions += 1
        elif version.failure is not None or (failed and not missing and not deferred):
            failed_versions += 1
        elif missing and eligible:
            pending_versions += 1
        elif deferred and eligible:
            deferred_versions += 1
        elif not eligible:
            ineligible_versions += 1
    return EmbeddingCounts(embedded_versions, pending_versions, failed_versions,
                           embedded_parts, pending_parts, failed_parts, ineligible_versions,
                           deferred_versions, deferred_parts)


@dataclass(frozen=True)
class PreparedRepository:
    repository: str
    eligible: bool
    versions: tuple[VersionEmbedding, ...]
    counts: EmbeddingCounts
    batches: tuple[EmbeddingBatch, ...]
    staged: tuple[PartIdentity, ...] = ()
    obsolete_receipts: int = 0
    obsolete_parts: int = 0

    @property
    def estimate(self) -> dict:
        identities = {(item.chunk_id, item.chunk_version) for batch in self.batches for item in batch.inputs}
        return {"versions": len(identities), "parts": sum(len(batch.inputs) for batch in self.batches),
                "tokens": sum(batch.planning_tokens for batch in self.batches),
                "deferredParts": len(self.staged),
                "obsoleteReceipts": self.obsolete_receipts, "obsoleteParts": self.obsolete_parts,
                "planningFailed": sum(version.failure is not None for version in self.versions)}


def _vector(value: Any, dimensions: int) -> tuple[float, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise MycelError("internal", "A stored embedding vector is not valid finite float data.") from None
    try:
        valid = (isinstance(value, (tuple, list)) and len(value) == dimensions
                 and all(type(member) in {int, float} and math.isfinite(member) for member in value))
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise MycelError("invalid_input", "Every embedding vector must contain the selected number of finite float values.")
    return tuple(float(member) for member in value)


@dataclass(frozen=True)
class _Binding:
    id: UUID
    plan: EmbeddingPlan


@dataclass(frozen=True)
class _Result:
    binding: _Binding
    part: PartIdentity
    vector: tuple[float, ...] | None = field(default=None, repr=False)
    failure: Mapping[str, str] | None = None


def _identity(plan: EmbeddingPlan, order: int) -> PartIdentity:
    return PartIdentity(plan.repository, plan.chunk_id, plan.chunk_version, order)


class _CatalogIncompatible(MycelError):
    def __init__(self):
        super().__init__("invalid_input", "The paid embedding inputs are incompatible with this Build's catalog.")


def _structural_provenance(value) -> PlanProvenance:
    provenance = PlanProvenance(**value)
    positive = ("provider_context_tokens", "input_token_cap", "batch_token_cap", "batch_input_cap",
                "provider_input_cap", "repository_in_flight_cap", "planner_version")
    if (any(type(getattr(provenance, name)) is not int or getattr(provenance, name) < 1 for name in positive)
            or provenance.padding is not False or provenance.truncation is not False
            or provenance.repository_in_flight_cap != 1
            or provenance.input_token_cap > provenance.provider_context_tokens
            or provenance.input_token_cap > provenance.batch_token_cap
            or provenance.batch_input_cap > provenance.provider_input_cap
            or any(not isinstance(getattr(provenance, name), str) or not re.fullmatch("[0-9a-f]{64}", getattr(provenance, name))
                   for name in ("catalog_sha256", "tokenizer_sha256", "tokenizers_library_sha256"))
            or not isinstance(provenance.tokenizer_revision, str)
            or not re.fullmatch("[0-9a-f]{40}", provenance.tokenizer_revision)
            or any(not isinstance(getattr(provenance, name), str) or not getattr(provenance, name)
                   for name in ("tokenizer_repository", "tokenizer_file", "tokenizers_version", "counting_rule",
                                "document_prompt", "query_prompt"))):
        raise ValueError("invalid recorded counting context")
    return provenance


def _recorded_provenance(value, tokenizer: ModelTokenizer) -> PlanProvenance:
    """Verify retained counting context and internally valid historical caps."""
    provenance = _structural_provenance(value)
    current = _provenance(tokenizer)
    if any(getattr(provenance, name) != getattr(current, name) for name in _COUNT_CONTEXT):
        raise ValueError("incompatible recorded counting context")
    return provenance


def _compatible_plan(plan: EmbeddingPlan, tokenizer: ModelTokenizer) -> None:
    current = _provenance(tokenizer)
    if any(getattr(plan.provenance, name) != getattr(current, name) for name in _COUNT_CONTEXT):
        raise _CatalogIncompatible()
    for part in plan.parts:
        # With an identical verified encoding context, different recorded
        # counts are corruption, rather than a reason to quarantine data.
        if tokenizer.counts(part.input_text, "document") != (part.submitted_tokens, part.planning_tokens):
            raise MycelError("invalid_input", "A deferred embedding input has inconsistent recorded token counts.")
        if max(part.submitted_tokens, part.planning_tokens) > tokenizer.catalog.input_token_cap:
            raise _CatalogIncompatible()
    validate_plan(plan, tokenizer)


def _restore_plan(metadata, text, tokenizer: ModelTokenizer, *, compatible: bool = True) -> EmbeddingPlan:
    """Reconstruct and validate a complete saved plan, without trusting JSON."""
    try:
        raw = text.encode("utf-8")
        parts = []
        for data in metadata["parts"]:
            body = raw[data["start_byte"]:data["end_byte"]].decode("utf-8")
            parts.append(EmbeddingPart(text=body, input_text=metadata["place_line"] + "\n" + body, **data))
        plan = EmbeddingPlan(provenance=_structural_provenance(metadata["provenance"]), parts=tuple(parts), text=text,
                             **{key: value for key, value in metadata.items() if key not in {"parts", "provenance"}})
        _chunk_id(plan.chunk_id)
        _version_id(plan.chunk_version)
        if (plan.to_dict() != metadata or plan.text_sha256 != sha256(raw).hexdigest()
                or not plan.parts or (not raw and len(plan.parts) != 1)
                or plan.kind not in {"document", "code"} or type(plan.dimensions) is not int or plan.dimensions < 1
                or any(not isinstance(value, str) or not value or any(c in value for c in "\r\n\0")
                       for value in (plan.repository, plan.model, plan.place_line))):
            raise ValueError
        offset = 0
        for order, part in enumerate(parts):
            if (any(type(value) is not int or value < 0 for value in
                    (part.order, part.start_byte, part.end_byte, part.submitted_tokens, part.planning_tokens))
                    or part.order != order or part.start_byte != offset
                    or part.end_byte != offset + len(part.text.encode("utf-8")) or (raw and not part.text)
                    or part.end_byte > len(raw)
                    or max(part.submitted_tokens, part.planning_tokens) > plan.provenance.input_token_cap):
                raise ValueError
            offset = part.end_byte
        if offset != len(raw):
            raise ValueError
        if compatible:
            _compatible_plan(plan, tokenizer)
        return plan
    except _CatalogIncompatible:
        raise
    except (PlanningError, MycelError, ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        raise MycelError("invalid_input", "A deferred embedding receipt has invalid exact-plan provenance.") from None


def _integrity(payload: dict) -> str:
    normalized = {key: value for key, value in payload.items() if key != "integrity"}
    # Hash vector values as floats independently of transport JSON number
    # spelling. The complete canonical receipt itself is retained as BYTEA.
    normalized["results"] = [dict(result, vector=[0.0 if float(value) == 0 else float(value)
                            for value in result["vector"]]) if "vector" in result else result
                            for result in payload["results"]]
    return sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _validated_payload(payload, repository: str, model: str, dimensions: int,
                       tokenizer: ModelTokenizer, *, compatible: bool = True) -> tuple[_Result, ...]:
    """Validate every staged result before any publication statement runs."""
    try:
        if (not isinstance(payload, dict)
                or set(payload) != {"format", "kind", "repository", "model", "dimensions", "request_provenance", "plans", "results", "integrity"}
                or type(payload["format"]) is not int or payload["format"] != 1
                or payload["kind"] not in {"vectors", "failures"}
                or (payload["repository"], payload["model"], payload["dimensions"]) != (repository, model, dimensions)
                or type(payload["dimensions"]) is not int
                or not isinstance(payload["plans"], list) or not isinstance(payload["results"], list)
                or not payload["results"]):
            raise ValueError
        request = _structural_provenance(payload["request_provenance"])
        if len(payload["results"]) > request.batch_input_cap:
            raise ValueError
        bindings, versions = {}, set()
        for item in payload["plans"]:
            if not isinstance(item, dict) or set(item) != {"id", "metadata", "text"}:
                raise ValueError
            identifier = _chunk_id(item["id"])
            plan = _restore_plan(item["metadata"], item["text"], tokenizer, compatible=False)
            if ((plan.repository, plan.model, plan.dimensions) != (repository, model, dimensions)
                    or identifier in bindings or plan.chunk_version in versions):
                raise ValueError
            if any(getattr(plan.provenance, name) != getattr(request, name) for name in _COUNT_CONTEXT):
                raise ValueError
            versions.add(plan.chunk_version)
            bindings[identifier] = _Binding(identifier, plan)
        results, identities, used = [], set(), set()
        submitted = planning = 0
        field_name = "vector" if payload["kind"] == "vectors" else "failure"
        for item in payload["results"]:
            if not isinstance(item, dict) or set(item) != {"plan_id", "part_order", field_name}:
                raise ValueError
            binding = bindings[_chunk_id(item["plan_id"])]
            order = item["part_order"]
            if type(order) is not int or not 0 <= order < len(binding.plan.parts):
                raise ValueError
            identity = _identity(binding.plan, order)
            if identity in identities:
                raise ValueError
            identities.add(identity)
            used.add(binding.id)
            part = binding.plan.parts[order]
            if max(part.submitted_tokens, part.planning_tokens) > request.input_token_cap:
                raise ValueError
            submitted += part.submitted_tokens
            planning += part.planning_tokens
            if field_name == "vector":
                result = _Result(binding, identity, vector=_vector(item["vector"], dimensions))
            else:
                failure = item["failure"]
                if not isinstance(failure, dict) or failure != ProviderFailure("content").to_dict():
                    raise ValueError
                result = _Result(binding, identity, failure=_frozen(failure))
            results.append(result)
        if used != set(bindings) or max(submitted, planning) > request.batch_token_cap:
            raise ValueError
        if not isinstance(payload["integrity"], str) or payload["integrity"] != _integrity(payload):
            raise ValueError
        if compatible:
            for binding in bindings.values():
                _compatible_plan(binding.plan, tokenizer)
        return tuple(results)
    except _CatalogIncompatible:
        raise
    except (MycelError, ValueError, TypeError, KeyError, AttributeError):
        raise MycelError("invalid_input", "A deferred embedding receipt does not match a complete validated batch.") from None


def _quarantined_payload(payload, repository: str, model: str, dimensions: int,
                         tokenizer: ModelTokenizer) -> tuple[_Result, ...] | None:
    if not isinstance(payload, dict) or payload.get("format") != 2:
        return None
    if (set(payload) != {"format", "kind", "reason", "payload"} or type(payload["format"]) is not int
            or payload["kind"] != "quarantined" or payload["reason"] != "catalog_incompatible"):
        raise MycelError("invalid_input", "A quarantined embedding receipt has invalid metadata.")
    return _validated_payload(payload["payload"], repository, model, dimensions, tokenizer, compatible=False)


def _decode_plan(version: RetainedVersion, row, part_rows, *, tokenizer: ModelTokenizer,
                 model: str, dimensions: int) -> VersionEmbedding:
    identifier, _, plan_hash, place, metadata, failure = row
    try:
        if failure is not None:
            raise PlanningError("A failed plan must be retained or explicitly remade before it can send parts.")
        raw = version.text.encode("utf-8")
        parts, states = [], []
        for _, order, beginning, ending, input_text, submitted, planning, part_failure, vector in part_rows:
            text = raw[beginning:ending].decode("utf-8", errors="strict")
            part = EmbeddingPart(order, beginning, ending, submitted, planning, text, exact_text(input_text))
            parts.append(part)
            states.append(PartState(part, None if vector is None else _vector(vector, dimensions), _frozen(part_failure)))
        plan = EmbeddingPlan(version.repository, version.chunk_id, version.version, version.snapshot_hash,
                             model, dimensions, metadata["kind"], place,
                             _recorded_provenance(metadata["provenance"], tokenizer), tuple(parts), version.text)
        validate_plan(plan, tokenizer)
        if (plan.plan_sha256 != plan_hash or plan.to_dict() != metadata
                or any(max(p.submitted_tokens, p.planning_tokens) > plan.provenance.input_token_cap for p in plan.parts)):
            raise PlanningError("The saved plan metadata does not match its exact version and parts.")
        return VersionEmbedding(version, identifier, plan, tuple(states))
    except PlanningError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, MycelError):
        raise PlanningError("The saved embedding plan or its coverage is incompatible.") from None


def _pending_batches(versions: Sequence[VersionEmbedding], tokenizer: ModelTokenizer, *,
                     eligible: bool, retry_failed: bool,
                     staged: frozenset[PartIdentity] = frozenset()) -> tuple[EmbeddingBatch, ...]:
    if not eligible:
        return ()
    pending = {PartIdentity(version.version.repository, version.version.chunk_id,
                           version.version.version, part.part.order)
               for version in versions if version.failure is None for part in version.parts
               if part.vector is None and (part.failure is None or retry_failed)} - staged
    inputs: list[BatchInput] = []
    batches: list[EmbeddingBatch] = []
    key = None
    submitted = planning = 0

    def finish():
        if inputs:
            batches.append(EmbeddingBatch(*key, tuple(inputs), submitted, planning))

    plans = tuple(version.plan for version in versions if version.plan is not None and version.failure is None)
    for batch in plan_batches(plans, tokenizer=tokenizer):
        for item in batch.inputs:
            if PartIdentity(item.repository, item.chunk_id, item.chunk_version, item.part_order) not in pending:
                continue
            next_key = (batch.repository, batch.model, batch.dimensions)
            if inputs and (key != next_key or len(inputs) >= tokenizer.catalog.batch_input_cap
                           or submitted + item.submitted_tokens > tokenizer.catalog.batch_token_cap
                           or planning + item.planning_tokens > tokenizer.catalog.batch_token_cap):
                finish()
                inputs, submitted, planning = [], 0, 0
            key = next_key
            inputs.append(item)
            submitted += item.submitted_tokens
            planning += item.planning_tokens
    finish()
    return tuple(batches)


class EmbeddingStore:
    def __init__(self, connection, settings: SettingsSnapshot, *, tokenizer: ModelTokenizer | None = None,
                 activity: MutationActivity | None = None, input_guard: Callable[[], None] | None = None,
                 store_guard: Callable[[], None] | None = None):
        settings.require_valid()
        self.connection, self.settings = connection, settings
        self.model = settings.values["embedding"]["model"]
        self.dimensions = settings.values["embedding"]["dimensions"]
        self.tokenizer = tokenizer or load_tokenizer(self.model)
        if (self.tokenizer.catalog.model != self.model or type(self.dimensions) is not int
                or self.dimensions not in self.tokenizer.catalog.dimensions):
            raise MycelError("settings", "The selected embedding model, dimensions and tokenizer do not agree.")
        self._repository: str | None = None
        self._expected: dict[PartIdentity, _Binding] = {}
        if activity is not None and activity.connection is not connection:
            raise MycelError("invalid_input", "Embedding activity requires the exact writing connection.")
        self.activity, self.input_guard, self.store_guard = activity, input_guard, store_guard
        self.mutations: dict[str, dict[str, int]] = {}
        self.published: dict[PartIdentity, _Result] = {}
        self.discarded: set[PartIdentity] = set()
        self.staged_parts: set[PartIdentity] = set()

    def _guard(self, *, staging: bool = False) -> None:
        if self.store_guard is not None:
            self.store_guard()
        # Paid results must become durable even when settings change during
        # the request. They cannot publish until a current eligible session.
        if not staging and self.input_guard is not None:
            self.input_guard()

    def _audit(self, repository: str, *, staging: bool = False, **increments) -> dict[str, int]:
        """Attach each actual feature mutation before its transaction commits."""
        counts = dict(self.mutations.get(repository, {}))
        for name, count in increments.items():
            counts[name] = counts.get(name, 0) + count
        if self.activity is not None:
            self.activity.record_in_transaction(repository, "embed", AppliedMutation(True, counts))
        self._session(repository)
        self._guard(staging=staging)
        return counts

    def eligible(self, repository: str) -> bool:
        configured = self.settings.values["repos"].get(repository)
        return isinstance(configured, Mapping) and configured.get("enabled") is True

    @contextmanager
    def session(self, repository: str) -> Iterator[EmbeddingStore]:
        """Hold embed/removal guards through requests; hold no pass lock then."""
        if self._repository is not None:
            raise MycelError("internal", "An embedding store session cannot be nested.")
        if not self.eligible(repository):
            raise MycelError("refused", "The embedding repository is unknown or disabled in these settings.")
        self._guard()
        with checked_store(self.connection, dimensions=self.dimensions, operation="embed"), \
                operation_guard(self.connection, repository, "embed"):
            self._repository = repository
            self._expected = {}
            try:
                receipt = self.drain(repository)
                if receipt.deferred:
                    raise MycelError("busy", "Completed embedding parts remain durably staged while another pass is busy.")
                yield self
            finally:
                self._repository = None
                self._expected = {}

    def _session(self, repository: str) -> None:
        if self._repository != repository or not self.eligible(repository):
            raise MycelError("internal", "Embedding writes require this enabled repository's guarded embed session.")

    def _read(self, repository: str):
        versions = []
        for row in self.connection.execute(_VERSIONS_SQL, (repository,)).fetchall():
            source = exact_bytes(row[6])
            if sha256(source).hexdigest() != row[5]:
                raise MycelError("store_format", "An embedding version has incompatible exact bytes.")
            versions.append(RetainedVersion(row[0], str(row[1]), row[2], _frozen(row[3]),
                            str(row[4]), row[5], exact_text(source), _frozen(row[7])))
        versions = tuple(versions)
        plans = {str(row[1]): row for row in self.connection.execute(
            _PLANS_SQL, (repository, self.model, self.dimensions)).fetchall()}
        identifiers = [row[0] for row in plans.values()]
        parts: dict[UUID, list] = {identifier: [] for identifier in identifiers}
        if identifiers:
            for row in self.connection.execute(_PARTS_SQL, (self.model, self.dimensions, identifiers)).fetchall():
                parts[row[0]].append(row)
        return versions, plans, parts

    def prepare_in_snapshot(self, repository: str, *, contexts: Mapping[int, EmbeddingContext]) -> PreparedRepository:
        """Report complete coverage in the caller's checked read-only snapshot."""
        require_read_transaction(self.connection)
        return self.prepare(repository, contexts=contexts, _in_snapshot=True)

    def prepare(self, repository: str, *, contexts: Mapping[int, EmbeddingContext],
                persist: bool = False, retry_failed: bool = False,
                _captured: frozenset[str] | None = None,
                _in_snapshot: bool = False) -> PreparedRepository:
        """Compute/report complete coverage, saving plans only when requested.

        A provisional plan is pending work even before its first saved row.
        Stored metadata alone cannot enable a repository. Read-only status and
        dry-run calls create no plans, parts, vectors, failure or lock-key rows.
        """
        if _in_snapshot:
            require_read_transaction(self.connection)
            if persist:
                raise MycelError('internal', 'Snapshot embedding reports cannot persist plans.')
        if persist:
            self._session(repository)
        with (nullcontext() if _in_snapshot else checked_store(self.connection, dimensions=self.dimensions)), \
                (nullcontext() if _in_snapshot else snapshot_transaction(self.connection)):
            versions, saved, parts = self._read(repository)
            receipts = self.connection.execute(_RECEIPTS_SQL, (repository, self.model, self.dimensions)).fetchall()
        if _captured is not None:
            versions = tuple(version for version in versions if version.version in _captured)
        prepared, replacements = [], []
        for version in versions:
            row = saved.get(version.version)
            if (row is not None and row[5] is not None and not retry_failed
                    and self._valid_failed_plan(version, row)):
                # Failed plans are not silently retried on a later pass. The
                # model/dimension lookup already excludes old-model failures.
                prepared.append(VersionEmbedding(version, row[0], None, (), _frozen(row[5])))
                continue
            if row is not None and row[5] is None:
                try:
                    prepared.append(_decode_plan(version, row, parts[row[0]], tokenizer=self.tokenizer,
                                                  model=self.model, dimensions=self.dimensions))
                    continue
                except PlanningError:
                    pass
            context = contexts.get(_version_id(version.version))
            if not isinstance(context, EmbeddingContext):
                raise MycelError("invalid_input", "A new embedding plan requires its current place and logical kind from ingest.")
            try:
                plan = plan_chunk(repository, version.chunk_id, version.version, version.text,
                                  place_line=context.place_line, kind=context.kind, model=self.model,
                                  dimensions=self.dimensions, tokenizer=self.tokenizer)
                value = VersionEmbedding(version, None, plan, tuple(PartState(part) for part in plan.parts))
            except PlanningError:
                value = VersionEmbedding(version, None, None, (), _frozen({"kind": "planning",
                                         "message": "The complete chunk text could not be planned with this Build."}))
            prepared.append(value)
            replacements.append((value, context))
        if persist and replacements:
            self._save(repository, replacements)
            # Do not expand a paid pass to newly ingested, unsaved versions.
            # Its finite captured inventory can shrink through deletions.
            return self.prepare(repository, contexts=contexts, retry_failed=retry_failed,
                                _captured=frozenset(version.version for version in versions))
        eligible = self.eligible(repository)
        values = tuple(prepared)
        current = {value.id: value.plan for value in values if value.id is not None and value.plan is not None}
        staged = []
        obsolete_receipts = obsolete_parts = 0
        for _, repo, model, dimensions, payload in receipts:
            payload = _receipt_payload(payload)
            if (repo, model, dimensions) != (repository, self.model, self.dimensions):
                raise MycelError("invalid_input", "A staged embedding receipt has inconsistent repository or model metadata.")
            obsolete = _quarantined_payload(payload, repo, model, dimensions, self.tokenizer)
            if obsolete is None:
                try:
                    active = _validated_payload(payload, repo, model, dimensions, self.tokenizer)
                except _CatalogIncompatible:
                    obsolete = _validated_payload(payload, repo, model, dimensions, self.tokenizer, compatible=False)
            if obsolete is not None:
                obsolete_receipts += 1
                obsolete_parts += len(obsolete)
                continue
            for result in active:
                plan = current.get(result.binding.id)
                if plan is not None and plan.plan_sha256 == result.binding.plan.plan_sha256:
                    staged.append(result.part)
        deferred = frozenset(staged)
        batches = _pending_batches(values, self.tokenizer, eligible=eligible, retry_failed=retry_failed, staged=deferred)
        if self._repository == repository:
            bindings = {value.id: _Binding(value.id, value.plan) for value in values
                        if value.id is not None and value.plan is not None}
            selected = {PartIdentity(item.repository, item.chunk_id, item.chunk_version, item.part_order)
                        for batch in batches for item in batch.inputs}
            for binding in bindings.values():
                for part in binding.plan.parts:
                    identity = _identity(binding.plan, part.order)
                    if identity not in selected:
                        continue
                    previous = self._expected.get(identity)
                    if (previous is not None and (previous.id != binding.id
                            or previous.plan.plan_sha256 != binding.plan.plan_sha256)):
                        raise MycelError("invalid_input", "A prepared exact input changed during this embedding session.")
                    self._expected.setdefault(identity, binding)
        return PreparedRepository(repository, eligible, values, _counts(values, eligible=eligible, staged=deferred),
                                  batches, tuple(dict.fromkeys(staged)), obsolete_receipts, obsolete_parts)

    def _valid_failed_plan(self, version: RetainedVersion, row) -> bool:
        metadata = row[4]
        try:
            context = EmbeddingContext(metadata["place_line"], metadata["kind"])
            expected = self._failure_metadata(version, context)
            # A failure was made by this exact planner/catalog and input. A
            # changed Build may be able to plan it and must validate again.
            return (metadata == expected and row[2] == self._failure_digest(expected)
                    and row[3] == context.place_line and row[5] == self._planning_failure())
        except (TypeError, KeyError, ValueError):
            return False

    @staticmethod
    def _planning_failure() -> dict:
        return {"kind": "planning", "message": "The complete chunk text could not be planned with this Build."}

    def _failure_metadata(self, version: RetainedVersion, context: EmbeddingContext) -> dict:
        return {"kind": context.kind, "repository": version.repository, "chunk_id": version.chunk_id,
                "chunk_version": version.version, "text_sha256": version.snapshot_hash,
                "model": self.model, "dimensions": self.dimensions, "place_line": context.place_line,
                "provenance": asdict(_provenance(self.tokenizer))}

    @staticmethod
    def _failure_digest(metadata: dict) -> str:
        return sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def _save(self, repository: str, replacements) -> None:
        self._session(repository)
        identifiers = [_version_id(value.version.version) for value, _ in replacements]
        with operation_guard(self.connection, repository, "pass"), atomic_transaction(self.connection):
            self._guard()
            retained = {str(row[0]): row for row in self.connection.execute(_RETAINED_SQL, (repository, identifiers)).fetchall()}
            saved_count = 0
            for value, context in replacements:
                version, plan = value.version, value.plan
                row = retained.get(version.version)
                if row is None:
                    continue
                if str(row[1]) != version.chunk_id or (row[2], exact_bytes(row[3])) != (version.snapshot_hash, version.text.encode("utf-8")):
                    raise MycelError("internal", "An immutable embedding version changed during plan persistence.")
                self.connection.execute("DELETE FROM public.mycel_embedding_plans "
                                        "WHERE chunk_version=%s AND model=%s AND dimensions=%s",
                                        (_version_id(version.version), self.model, self.dimensions))
                metadata = plan.to_dict() if plan is not None else self._failure_metadata(version, context)
                digest = plan.plan_sha256 if plan is not None else self._failure_digest(metadata)
                identifier = uuid4()
                self.connection.execute("INSERT INTO public.mycel_embedding_plans "
                    "(id,chunk_version,model,dimensions,plan_hash,place_line,provenance,failure) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (identifier, _version_id(version.version), self.model, self.dimensions, digest,
                     plan.place_line if plan is not None else context.place_line, Jsonb(metadata),
                     None if value.failure is None else Jsonb(dict(value.failure))))
                saved_count += 1
                for part in value.parts:
                    item = part.part
                    self.connection.execute("INSERT INTO public.mycel_embedding_parts "
                        "(plan_id,part_order,byte_start,byte_end,input_bytes,submitted_tokens,planning_tokens) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (identifier, item.order, item.start_byte, item.end_byte, item.input_text.encode("utf-8"),
                         item.submitted_tokens, item.planning_tokens))
            counts = self._audit(repository, plans=saved_count) if saved_count else None
            self._guard()
        if counts is not None:
            self.mutations[repository] = counts

    def _payload(self, supplied: Sequence[VectorWrite] | Sequence[PartFailure], *, kind: str) -> dict:
        repository = self._repository
        if repository is None:
            raise MycelError("internal", "Embedding callbacks require a guarded enabled repository session.")
        self._session(repository)
        if not isinstance(supplied, (list, tuple)) or not supplied:
            raise MycelError("invalid_input", "An embedding callback requires a complete nonempty batch.")
        bindings, results, seen = {}, [], set()
        for value in supplied:
            expected_type = VectorWrite if kind == "vectors" else PartFailure
            if not isinstance(value, expected_type) or not isinstance(value.part, PartIdentity):
                raise MycelError("invalid_input", "An embedding callback has invalid part data.")
            part = value.part
            _chunk_id(part.chunk_id)
            _version_id(part.chunk_version)
            if (part.repository != repository or type(part.part_order) is not int or part.part_order < 0
                    or part in seen or part not in self._expected):
                raise MycelError("invalid_input", "An embedding result does not match a unique prepared input.")
            binding = self._expected[part]
            seen.add(part)
            bindings[binding.id] = {"id": str(binding.id), "metadata": binding.plan.to_dict(), "text": binding.plan.text}
            result = {"plan_id": str(binding.id), "part_order": part.part_order}
            if kind == "vectors":
                if (value.model != self.model or type(value.dimensions) is not int or value.dimensions != self.dimensions):
                    raise MycelError("invalid_input", "Embedding vectors must match the prepared model and dimensions.")
                result["vector"] = list(_vector(value.vector, self.dimensions))
            else:
                if value.kind != "content":
                    raise MycelError("invalid_input", "Only an isolated permanent content failure belongs to a part.")
                # Caller/provider strings never become saved diagnostic text.
                result["failure"] = ProviderFailure("content").to_dict()
            results.append(result)
        payload = {"format": 1, "kind": kind, "repository": repository, "model": self.model,
                   "dimensions": self.dimensions, "request_provenance": asdict(_provenance(self.tokenizer)),
                   "plans": list(bindings.values()), "results": results}
        payload["integrity"] = _integrity(payload)
        _validated_payload(payload, repository, self.model, self.dimensions, self.tokenizer)
        return payload

    def _stage(self, payload: dict) -> tuple:
        repository = payload["repository"]
        self._session(repository)
        identifier = uuid4()
        with atomic_transaction(self.connection):
            self._guard(staging=True)
            self.connection.execute("INSERT INTO public.mycel_embedding_receipts "
                "(id,repository,model,dimensions,payload) VALUES (%s,%s,%s,%s,%s)",
                (identifier, repository, self.model, self.dimensions, _payload_bytes(payload)))
            counts = self._audit(repository, staging=True, staged=len(payload["results"]))
        self.mutations[repository] = counts
        self.staged_parts.update(result.part for result in self._receipt_results(
            (identifier, repository, self.model, self.dimensions, payload)))
        return identifier, repository, self.model, self.dimensions, payload

    def commit(self, writes: Sequence[VectorWrite]) -> CommitReceipt:
        """Durably save a validated whole response before short publication."""
        payload = self._payload(writes, kind="vectors")
        row = self._stage(payload)
        for value in writes:
            self._expected.pop(value.part)
        return self._publish(row)

    def record_failures(self, failures: Sequence[PartFailure]) -> CommitReceipt:
        """Save isolated content failures without resetting successful parts."""
        payload = self._payload(failures, kind="failures")
        row = self._stage(payload)
        for value in failures:
            self._expected.pop(value.part)
        return self._publish(row)

    def _receipt_results(self, row) -> tuple[_Result, ...]:
        if len(row) != 5 or (row[1], row[2], row[3]) != (self._repository, self.model, self.dimensions):
            raise MycelError("invalid_input", "A deferred receipt has inconsistent repository or model metadata.")
        return _validated_payload(row[4], row[1], row[2], row[3], self.tokenizer)

    def _publish(self, row) -> CommitReceipt:
        """Keep a whole receipt durable on contention; discard only deletions."""
        repository = row[1]
        self._session(repository)
        results = self._receipt_results(row)
        identities = tuple(result.part for result in results)
        try:
            with operation_guard(self.connection, repository, "pass"), atomic_transaction(self.connection):
                self._guard()
                locked = _receipt_row(self.connection.execute(_RECEIPT_SQL, (row[0],)).fetchone())
                if locked is None:
                    raise MycelError("invalid_input", "The deferred embedding receipt no longer exists.")
                if locked != row:
                    raise MycelError("invalid_input", "The deferred embedding receipt changed before publication.")
                # Validate the locked payload too: a receipt is never a
                # trusted adapter bypass for vector or input validation.
                results = self._receipt_results(locked)
                retained = {str(value[0]): value for value in self.connection.execute(_RECEIPT_VERSIONS_SQL,
                            (list({_version_id(result.part.chunk_version) for result in results}),)).fetchall()}
                present, deleted = [], []
                plans = {}
                # Complete association validation precedes every vector or
                # failure write. A later statement fault rolls back all of it.
                for result in results:
                    binding, part = result.binding, result.part
                    version = retained.get(part.chunk_version)
                    if version is None:
                        deleted.append(part)
                        continue
                    if (str(version[1]), version[2], exact_bytes(version[3]), version[4]) != (
                            part.chunk_id, binding.plan.text_sha256, binding.plan.text.encode("utf-8"), repository):
                        raise MycelError("invalid_input", "A retained exact version does not match its deferred input.")
                    if binding.id not in plans:
                        saved = self.connection.execute(_PUBLISHED_PLAN_SQL,
                                  (_version_id(part.chunk_version), self.model, self.dimensions)).fetchone()
                        if (saved is None or saved[0] != binding.id or saved[1] != binding.plan.plan_sha256
                                or saved[2] != binding.plan.to_dict() or saved[3] is not None):
                            raise MycelError("invalid_input", "A retained version's embedding plan changed; its receipt remains staged.")
                        plans[binding.id] = saved
                    saved_part = self.connection.execute(_PUBLISHED_PART_SQL, (binding.id, part.part_order)).fetchone()
                    expected = binding.plan.parts[part.part_order]
                    if saved_part != (expected.start_byte, expected.end_byte, expected.input_text.encode("utf-8"),
                                      expected.submitted_tokens, expected.planning_tokens):
                        raise MycelError("invalid_input", "A deferred result does not match the saved exact part input.")
                    present.append(result)
                for result in present:
                    if result.vector is not None:
                        self.connection.execute("INSERT INTO public.mycel_vectors "
                            "(plan_id,part_order,model,dimensions,embedding) VALUES (%s,%s,%s,%s,%s::public.vector) "
                            "ON CONFLICT (plan_id,part_order) DO UPDATE SET model=EXCLUDED.model, "
                            "dimensions=EXCLUDED.dimensions,embedding=EXCLUDED.embedding",
                            (result.binding.id, result.part.part_order, self.model, self.dimensions,
                             json.dumps(result.vector, separators=(",", ":"), allow_nan=False)))
                        self.connection.execute("UPDATE public.mycel_embedding_parts SET failure=NULL "
                            "WHERE plan_id=%s AND part_order=%s", (result.binding.id, result.part.part_order))
                    else:
                        self.connection.execute("UPDATE public.mycel_embedding_parts SET failure=%s "
                            "WHERE plan_id=%s AND part_order=%s AND NOT EXISTS "
                            "(SELECT 1 FROM public.mycel_vectors WHERE plan_id=%s AND part_order=%s "
                            "AND model=%s AND dimensions=%s)",
                            (Jsonb(dict(result.failure)), result.binding.id, result.part.part_order,
                             result.binding.id, result.part.part_order, self.model, self.dimensions))
                self.connection.execute("DELETE FROM public.mycel_embedding_receipts WHERE id=%s", (row[0],))
                counts = self._audit(repository, sent=sum(result.vector is not None for result in present),
                    failed=sum(result.vector is None for result in present), discarded=len(deleted))
                self._guard()
            self.mutations[repository] = counts
            self.published.update((result.part, result) for result in present)
            self.discarded.update(deleted)
            self.staged_parts.difference_update(identities)
            return CommitReceipt(tuple(result.part for result in present), tuple(deleted))
        except MycelError as error:
            if error.code != "busy":
                raise
            return CommitReceipt((), (), identities)

    def drain(self, repository: str) -> CommitReceipt:
        """Publish staged current-model batches before any further sending.

        A mismatched model is left durable. Callers cannot publish anything
        through a session for an unknown or disabled repository.
        """
        self._session(repository)
        with snapshot_transaction(self.connection):
            rows = tuple(_receipt_row(row) for row in self.connection.execute(_RECEIPTS_SQL, (repository, self.model, self.dimensions)).fetchall())
        actions, all_parts, seen = [], [], set()
        for row in rows:
            if _quarantined_payload(row[4], repository, self.model, self.dimensions, self.tokenizer) is not None:
                continue
            incompatible = False
            try:
                results = self._receipt_results(row)
            except _CatalogIncompatible:
                incompatible = True
                results = _validated_payload(row[4], repository, self.model, self.dimensions, self.tokenizer, compatible=False)
            parts = tuple(result.part for result in results)
            if not incompatible:
                if seen.intersection(parts):
                    raise MycelError("invalid_input", "Deferred embedding receipts contain duplicate prepared inputs.")
                seen.update(parts)
            actions.append((row, incompatible, results))
            all_parts.append(parts)
        retained, deleted = [], []
        for index, (row, incompatible, results) in enumerate(actions):
            receipt = self._quarantine(row, results) if incompatible else self._publish(row)
            retained.extend(receipt.retained)
            deleted.extend(receipt.deleted)
            if receipt.deferred:
                deferred = tuple(part for parts in all_parts[index:] for part in parts)
                return CommitReceipt(tuple(retained), tuple(deleted), deferred)
        return CommitReceipt(tuple(retained), tuple(deleted))

    def _quarantine(self, row, results: tuple[_Result, ...]) -> CommitReceipt:
        """Keep incompatible paid inputs private without blocking new plans."""
        repository = row[1]
        self._session(repository)
        try:
            with operation_guard(self.connection, repository, "pass"), atomic_transaction(self.connection):
                self._guard()
                locked = _receipt_row(self.connection.execute(_RECEIPT_SQL, (row[0],)).fetchone())
                if locked != row:
                    raise MycelError("invalid_input", "The deferred embedding receipt changed before quarantine.")
                validated = _validated_payload(locked[4], repository, self.model, self.dimensions,
                                               self.tokenizer, compatible=False)
                retained = {str(value[0]): value for value in self.connection.execute(_RECEIPT_VERSIONS_SQL,
                            (list({_version_id(result.part.chunk_version) for result in validated}),)).fetchall()}
                checked = set()
                for result in validated:
                    binding, part = result.binding, result.part
                    version = retained.get(part.chunk_version)
                    if version is None:
                        continue
                    if (str(version[1]), version[2], exact_bytes(version[3]), version[4]) != (
                            part.chunk_id, binding.plan.text_sha256, binding.plan.text.encode("utf-8"), repository):
                        raise MycelError("invalid_input", "A retained exact version does not match its deferred input.")
                    if binding.id in checked:
                        continue
                    checked.add(binding.id)
                    saved = self.connection.execute(_PUBLISHED_PLAN_SQL,
                            (_version_id(part.chunk_version), self.model, self.dimensions)).fetchone()
                    # A replacement plan can already exist. The original
                    # receipt's checksum, complete source and historical
                    # ranges still prove what it contains. If its original
                    # saved plan remains, validate every association too.
                    if saved is not None and saved[0] == binding.id:
                        if (saved[1] != binding.plan.plan_sha256 or saved[2] != binding.plan.to_dict()
                                or saved[3] is not None):
                            raise MycelError("invalid_input", "A deferred receipt's original saved plan is inconsistent.")
                        for expected in binding.plan.parts:
                            saved_part = self.connection.execute(_PUBLISHED_PART_SQL, (binding.id, expected.order)).fetchone()
                            if saved_part != (expected.start_byte, expected.end_byte, expected.input_text.encode("utf-8"),
                                              expected.submitted_tokens, expected.planning_tokens):
                                raise MycelError("invalid_input", "A deferred receipt's original saved inputs are inconsistent.")
                envelope = {"format": 2, "kind": "quarantined", "reason": "catalog_incompatible", "payload": row[4]}
                self.connection.execute("UPDATE public.mycel_embedding_receipts SET payload=%s WHERE id=%s",
                                        (_payload_bytes(envelope), row[0]))
                counts = self._audit(repository, quarantined=len(results))
                self._guard()
            self.mutations[repository] = counts
            self.staged_parts.difference_update(result.part for result in results)
            return CommitReceipt(())
        except MycelError as error:
            if error.code != "busy":
                raise
            return CommitReceipt((), (), tuple(result.part for result in results))
