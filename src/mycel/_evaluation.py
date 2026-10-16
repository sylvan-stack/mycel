"""Strict versioned evaluation files and the offline retrieval measurement seam.

The engine owns validation, exact expectations and accounting. Query embedding
and normal search remain injected interfaces: no replacement ranking, provider
transport, freshness work or store mutation lives here. A retrieval adapter must
freeze effective settings and expose one consistent read-only snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import tomllib
from typing import Literal, Protocol

from ._errors import MycelError
from ._resolver import SelectionMember, SourceResolver
from ._settings import _key_lines, _qualified
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address


Route = Literal["identifier", "question"]
Outcome = Literal["still_supported", "needs_review", "insufficient_evidence", "unresolved"]
_OUTCOMES = frozenset({"still_supported", "needs_review", "insufficient_evidence", "unresolved"})
_CRITICAL = frozenset({"negation", "operator", "permission", "deletion"})
_UNAVAILABLE = frozenset({"baseline", "dependant", "context"})


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    expect: tuple[str, ...]
    only: Literal["code", "docs"] | None = None


@dataclass(frozen=True)
class DriftCase:
    id: str
    before: str
    dependant: str
    expect: Outcome
    source_state: Literal["present", "deleted"] = "present"
    current: str | None = None
    context: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    unchanged: bool = False
    critical: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationSet:
    file: Path
    file_hash: str
    queries: tuple[RetrievalQuery, ...] = ()
    drifts: tuple[DriftCase, ...] = ()
    schema_version: int = 1


class _Validation:
    def __init__(self, file: Path, source: str):
        self.file = file
        self.lines = _key_lines(source)

    def fault(self, path: tuple[str | int, ...], message: str) -> None:
        line = self.lines.get(path)
        # A missing member still identifies the enclosing table's line.
        if line is None:
            for length in range(len(path) - 1, 0, -1):
                if path[:length] in self.lines:
                    line = self.lines[path[:length]]
                    break
        location = _qualified(path) or "evaluation"
        if line is not None:
            location += f" (line {line})"
        raise MycelError("invalid_input", f"Evaluation file {self.file}: {location}: {message}")

    def members(self, value: Mapping, allowed: frozenset[str], path=()) -> None:
        for key in value:
            if key not in allowed:
                self.fault(path + (key,), "Unknown field.")

    def text(self, value, path, *, nonempty=False) -> str:
        if not isinstance(value, str) or (nonempty and not value.strip()):
            self.fault(path, "Expected nonempty text." if nonempty else "Expected text.")
        return value

    def texts(self, value, path, *, nonempty=False) -> tuple[str, ...]:
        if not isinstance(value, list) or (nonempty and not value):
            self.fault(path, "Expected a nonempty array of text." if nonempty else "Expected an array of text.")
        return tuple(self.text(item, path + (index,), nonempty=nonempty)
                     for index, item in enumerate(value))


def load_evaluation_file(path: Path | str) -> EvaluationSet:
    """Read exact UTF-8 TOML once and validate both sections before any call."""
    file = Path(path).absolute()
    try:
        raw = file.read_bytes()
    except OSError:
        raise MycelError("io", f"Evaluation file {file} could not be read.") from None
    try:
        source = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise MycelError("invalid_input", f"Evaluation file {file}: evaluation: Expected UTF-8 text.") from None
    try:
        value = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        # Python's decoder includes the offending line/column, but not contents.
        raise MycelError("invalid_input", f"Evaluation file {file}: malformed TOML: {error}") from None
    check = _Validation(file, source)
    check.members(value, frozenset({"schema_version", "query", "drift"}))
    schema = value.get("schema_version", 1)
    if type(schema) is not int or schema != 1:
        check.fault(("schema_version",), "Only integer schema version 1 is supported.")

    queries = []
    query_values = value.get("query", [])
    if not isinstance(query_values, list):
        check.fault(("query",), "Expected an array of query tables.")
    for ordinal, query in enumerate(query_values):
        path = ("query", ordinal)
        if not isinstance(query, dict):
            check.fault(path, "Expected a query table.")
        check.members(query, frozenset({"text", "expect", "only"}), path)
        text = check.text(query.get("text"), path + ("text",), nonempty=True)
        expect = check.texts(query.get("expect"), path + ("expect",), nonempty=True)
        only = query.get("only")
        if "only" in query and (not isinstance(only, str) or only not in {"code", "docs"}):
            check.fault(path + ("only",), "Expected code or docs.")
        queries.append(RetrievalQuery(text, expect, only))

    drifts, identifiers = [], set()
    drift_values = value.get("drift", [])
    if not isinstance(drift_values, list):
        check.fault(("drift",), "Expected an array of drift tables.")
    for ordinal, drift in enumerate(drift_values):
        path = ("drift", ordinal)
        if not isinstance(drift, dict):
            check.fault(path, "Expected a drift table.")
        check.members(drift, frozenset({"id", "before", "current", "dependant", "expect",
                                      "source_state", "context", "unavailable", "unchanged", "critical"}), path)
        identifier = check.text(drift.get("id"), path + ("id",))
        if identifier in identifiers:
            check.fault(path + ("id",), "Duplicate drift ID.")
        identifiers.add(identifier)
        before = check.text(drift.get("before"), path + ("before",))
        dependant = check.text(drift.get("dependant"), path + ("dependant",))
        expect = check.text(drift.get("expect"), path + ("expect",))
        if expect not in _OUTCOMES:
            check.fault(path + ("expect",), "Unsupported expected drift label.")
        state = drift.get("source_state", "present")
        if not isinstance(state, str) or state not in {"present", "deleted"}:
            check.fault(path + ("source_state",), "Expected present or deleted.")
        if state == "deleted":
            if "current" in drift:
                check.fault(path + ("current",), "Deleted sources require current to be absent.")
            current = None
        else:
            current = check.text(drift.get("current"), path + ("current",))
        context = check.texts(drift.get("context", []), path + ("context",))
        unavailable = check.texts(drift.get("unavailable", []), path + ("unavailable",))
        if len(set(unavailable)) != len(unavailable) or any(item not in _UNAVAILABLE for item in unavailable):
            check.fault(path + ("unavailable",), "Expected unique baseline, dependant or context entries.")
        if unavailable and expect != "unresolved":
            check.fault(path + ("expect",), "Unavailable required evidence must expect unresolved.")
        unchanged = drift.get("unchanged", False)
        if type(unchanged) is not bool:
            check.fault(path + ("unchanged",), "Expected a boolean.")
        if unchanged and expect != "still_supported":
            check.fault(path + ("unchanged",), "An unchanged case must expect still_supported.")
        critical = check.texts(drift.get("critical", []), path + ("critical",))
        if any(item not in _CRITICAL for item in critical):
            check.fault(path + ("critical",), "Unsupported critical-change label.")
        if critical and expect != ("unresolved" if unavailable else "needs_review"):
            check.fault(path + ("expect",), "Critical cases must expect needs_review, or unresolved with unavailable evidence.")
        drifts.append(DriftCase(identifier, before, dependant, expect, state, current,
                                context, unavailable, unchanged, critical))
    return EvaluationSet(file, sha256(raw).hexdigest(), tuple(queries), tuple(drifts))


@dataclass(frozen=True)
class PreparedQueryVector:
    """Normal search's vector or its explicit wording-only fallback reason."""

    vector: tuple[float, ...] | None
    reason: str | None = None

    def __post_init__(self):
        if self.vector is None:
            if not isinstance(self.reason, str) or not self.reason:
                raise MycelError("internal", "A wording-only query requires its normal-search fallback reason.")
        elif (type(self.vector) is not tuple or not self.vector or self.reason is not None
              or any(type(value) not in {float, int} or not math.isfinite(value) for value in self.vector)):
            raise MycelError("internal", "The prepared query vector is incompatible with normal search.")


@dataclass(frozen=True)
class RetrievalPlace:
    identifier: str
    version: int
    address: SourceAddress


@dataclass(frozen=True)
class RetrievalReply:
    route: Route
    meaning_used: bool
    results: tuple[RetrievalPlace, ...]


class QueryVectorProvider(Protocol):
    def prepare(self, query: RetrievalQuery) -> PreparedQueryVector: ...


class RetrievalSnapshot(Protocol):
    resolver: SourceResolver
    index_generation: str
    index_fingerprint: str
    settings_hash: str
    search_reply: int

    def eligible(self, query: RetrievalQuery, member: SelectionMember) -> bool: ...

    def search(self, query: RetrievalQuery, prepared: PreparedQueryVector, *,
               k: int, freshness: bool) -> RetrievalReply: ...


class RetrievalAdapter(Protocol):
    def snapshot(self, repository: str) -> AbstractContextManager[RetrievalSnapshot]: ...


def _hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _place(place: RetrievalPlace) -> dict:
    if not isinstance(place, RetrievalPlace):
        raise MycelError("internal", "Search returned an incompatible evaluation place.")
    address = place.address
    try:
        canonical = address.address
    except (AttributeError, SourceAddressError):
        raise MycelError("internal", "Search returned an incompatible evaluation place.") from None
    if (not isinstance(place.identifier, str) or not place.identifier or type(place.version) is not int
            or place.version < 1 or address.root is None or address.name is None):
        raise MycelError("internal", "Search returned an incompatible evaluation place.")
    return {"id": place.identifier, "version": place.version, "repository": address.repository,
            "root": address.root, "path": address.path, "name": address.name, "address": canonical}


def _share(found: int, expected: int) -> float | None:
    return found / expected if expected else None


def _base_report(suite: EvaluationSet, *, repository: str, build: str, model: str,
                 search_reply: int) -> dict:
    return {"kind": "retrieval", "evaluationSchema": suite.schema_version, "repository": repository,
            "file": str(suite.file), "fileHash": suite.file_hash, "build": build, "model": model,
            "searchReply": search_reply, "queries": len(suite.queries)}


def empty_retrieval_report(suite: EvaluationSet, *, repository: str, build: str, model: str,
                           search_reply: int = 3, settings_hash: str | None = None) -> dict:
    """An empty section needs no vectors or store; no index was measured."""
    if suite.queries:
        raise MycelError("internal", "An empty retrieval report requires an empty query section.")
    return {**_base_report(suite, repository=repository, build=build, model=model, search_reply=search_reply),
            "indexGeneration": None, "indexFingerprint": None, "settingsHash": settings_hash,
            "queryVectorsHash": _hash([]), "byWordingAlone": 0, "faultsOfTheSet": 0,
            "recall": {"at3": None, "at10": None},
            "byRoute": {route: {"queries": 0, "at3": None, "at10": None}
                        for route in ("identifier", "question")}, "results": []}


_EXPECTATION_FAULTS = {
    "invalid_ref": "malformed", "not_a_ref": "malformed",
    "ambiguous_path": "ambiguous", "ambiguous_name": "ambiguous",
    "disabled_repository": "ineligible", "unregistered_repository": "ineligible",
    "ineligible_index": "ineligible", "one_chunk_required": "not_one_chunk",
    "missing_file": "not_in_index", "missing_name": "not_in_index",
}


def _expectation(snapshot: RetrievalSnapshot, query: RetrievalQuery, declared: str,
                 positions: Mapping[tuple[str, int], int]) -> tuple[dict, tuple[str, int] | None]:
    result = {"place": declared}
    # A file selection is a set fault even when it happens to contain one chunk.
    try:
        parsed = parse_source_address(declared)
    except SourceAddressError:
        result["fault"] = "malformed"
        return result, None
    if parsed.name is None:
        result["fault"] = "not_one_chunk"
        return result, None
    resolved = snapshot.resolver.resolve(declared, purpose="read")
    if resolved.state != "resolved" or resolved.selection is None:
        try:
            result["fault"] = _EXPECTATION_FAULTS[resolved.fault]
        except KeyError:
            raise MycelError("internal", "Expectation resolution returned an unsupported fault.") from None
        return result, None
    selection = resolved.selection
    if selection.kind not in {"chunk", "index"} or len(selection.members) != 1:
        result["fault"] = "not_one_chunk"
        return result, None
    member = selection.members[0]
    if not snapshot.eligible(query, member):
        result["fault"] = "ineligible"
        return result, None
    key = (member.chunk.identifier, member.chunk.version)
    result["resolved"] = _place(RetrievalPlace(*key, member.place))
    if key in positions:
        result["position"] = positions[key]
    return result, key


def run_retrieval_evaluation(suite: EvaluationSet, *, repository: str, build: str, model: str,
                             query_vectors: QueryVectorProvider, retrieval: RetrievalAdapter) -> dict:
    """Measure injected normal searches; all vectors precede the sole snapshot.

    The suite must come from full-file validation, including the unselected drift
    section. Normal query-vector failures must be represented by PreparedQueryVector
    fallback results, exactly as normal search does, rather than dropped queries.
    """
    prepared = tuple(query_vectors.prepare(query) for query in suite.queries)
    if any(not isinstance(vector, PreparedQueryVector) for vector in prepared):
        raise MycelError("internal", "Query preparation returned an incompatible evaluation vector.")
    vectors_hash = _hash([{"text": query.text, "only": query.only,
                           "vector": vector.vector, "reason": vector.reason}
                          for query, vector in zip(suite.queries, prepared, strict=True)])
    totals = {route: {"queries": 0, "expected": 0, "at3": 0, "at10": 0}
              for route in ("identifier", "question")}
    results, wording_only, faults = [], 0, 0
    with retrieval.snapshot(repository) as snapshot:
        if (any(not isinstance(value, str) or not value
                for value in (snapshot.index_generation, snapshot.index_fingerprint, snapshot.settings_hash))
                or type(snapshot.search_reply) is not int or snapshot.search_reply < 1):
            raise MycelError("internal", "The evaluation snapshot has incomplete input identities.")
        for query, vector in zip(suite.queries, prepared, strict=True):
            reply = snapshot.search(query, vector, k=10, freshness=False)
            if (not isinstance(reply, RetrievalReply) or reply.route not in totals
                    or type(reply.meaning_used) is not bool or type(reply.results) is not tuple
                    or len(reply.results) > 10 or (reply.meaning_used and vector.vector is None)):
                raise MycelError("internal", "Normal search returned an incompatible evaluation reply.")
            returned = [_place(place) for place in reply.results]
            keys = tuple((place.identifier, place.version) for place in reply.results)
            # Logical-chunk collapse is a search invariant, not an evaluator rank
            # rewrite. Reject violations without moving later result positions.
            if len({place.identifier for place in reply.results}) != len(keys):
                raise MycelError("internal", "Normal search returned a duplicate logical chunk.")
            positions = {key: position for position, key in enumerate(keys, 1)}
            expected, distinct, faulted = [], set(), False
            for declared in query.expect:
                outcome, key = _expectation(snapshot, query, declared, positions)
                expected.append(outcome)
                if key is None:
                    faulted = True
                    faults += 1
                else:
                    distinct.add(key)
            if not reply.meaning_used:
                wording_only += 1
            route = totals[reply.route]
            route["queries"] += 1
            if not faulted:
                route["expected"] += len(distinct)
                route["at3"] += sum(positions.get(key, 11) <= 3 for key in distinct)
                route["at10"] += sum(key in positions for key in distinct)
            results.append({"text": query.text, "route": reply.route, "included": not faulted,
                            "returned": returned, "expected": expected})
        overall_expected = sum(route["expected"] for route in totals.values())
        report = {**_base_report(suite, repository=repository, build=build, model=model,
                                search_reply=snapshot.search_reply),
                  "indexGeneration": snapshot.index_generation, "indexFingerprint": snapshot.index_fingerprint,
                  "settingsHash": snapshot.settings_hash, "queryVectorsHash": vectors_hash,
                  "byWordingAlone": wording_only, "faultsOfTheSet": faults,
                  "recall": {metric: _share(sum(route[metric] for route in totals.values()), overall_expected)
                             for metric in ("at3", "at10")},
                  "byRoute": {name: {"queries": route["queries"],
                                      **{metric: _share(route[metric], route["expected"])
                                         for metric in ("at3", "at10")}}
                              for name, route in totals.items()}, "results": results}
    return report


_COMPARISON_INPUTS = ("evaluationSchema", "repository", "fileHash", "model", "searchReply",
                      "indexGeneration", "indexFingerprint", "settingsHash", "queryVectorsHash")


def comparison_failures(before: Mapping, after: Mapping) -> tuple[str, ...]:
    """Builds may differ; measurements require complete, matching frozen inputs."""
    if before.get("kind") != "retrieval" or after.get("kind") != "retrieval":
        return ("kind",)
    return tuple(key for key in _COMPARISON_INPUTS
                 if before.get(key) is None or after.get(key) is None or before[key] != after[key])
