"""Canonical, immutable semantic evidence for dependency classification.

There are no provider calls or store mutations here. Full capture manifests and
live file guards belong to the store boundary; only their semantic projections
enter the decision hash. These builders verify every supplied text rather than
substituting, normalizing, summarizing or truncating it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any

from ._evidence import (BaselineManifest, ComparisonRecord, EvidenceError,
                        SnapshotEvidence, canonical_json)
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address


PROTOCOL = 1
QUESTION_VERSION = "mycel-dependency-v1"
INSTRUCTION_VERSION = "mycel-review-v1"
ENVIRONMENT_VERSION = "mycel-review-env-v1"
ROUTING_REVISION = "mycel-drift-routing-v1"
LABELS = ("needs_review", "insufficient_evidence", "still_supported")
_PROMPTS = json.loads(files("mycel").joinpath("data/classification-prompts.json").read_text(encoding="utf-8"))
if (_PROMPTS.get("schema") != 1 or _PROMPTS.get("questionVersion") != QUESTION_VERSION
        or tuple(_PROMPTS.get("labels", ())) != LABELS
        or not isinstance(_PROMPTS.get("instruction"), str)
        or len(_PROMPTS.get("criteria", ())) != 3
        or not all(isinstance(value, str) for value in _PROMPTS["criteria"])):
    raise RuntimeError("The packaged classification question has incompatible fixed data.")
INSTRUCTION = _PROMPTS["instruction"]
CHOICE_CRITERIA = tuple(_PROMPTS["criteria"])
CRITERIA = INSTRUCTION + "\n\n" + "\n".join(
    f"{label}: {criterion}" for label, criterion in zip(LABELS, CHOICE_CRITERIA, strict=True))
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}\Z", re.ASCII)
_JEV_MODEL = re.compile(r"jev-[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)


def _fail(status: str = "snapshot_corrupt") -> None:
    raise EvidenceError(status)


def _copy(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _frozen(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(member) for key, member in value.items()})
    if type(value) in {tuple, list}:
        return tuple(_frozen(member) for member in value)
    return value


def _text(value: Any, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()) or "\0" in value:
        _fail()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _fail()
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail()
    return value


def _revision(value: Any) -> str:
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        _fail()
    return value


def _integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail()
    return value


def _members(value: Any) -> list:
    if type(value) is not list:
        _fail()
    return value


def _enum(value: Any, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        _fail()
    return value


def _texts(values: Any) -> list[DecisionText]:
    if type(values) not in {tuple, list} or any(not isinstance(value, DecisionText) for value in values):
        _fail("invalid_input")
    return list(values)


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        _fail()


def _place(value: SourceAddress | Mapping) -> dict:
    if isinstance(value, SourceAddress):
        try:
            if value.root not in {"code", "artifact"}:
                _fail()
            result = {"repository": value.repository, "root": value.root,
                      "path": value.path, "address": value.address}
            if value.name is not None:
                result["name"] = value.name
            return result
        except (SourceAddressError, TypeError, ValueError):
            _fail()
    result = _copy(value)
    _keys(result, {"repository", "root", "path", "address"}, {"name"})
    try:
        if _place(parse_source_address(result["address"])) != result:
            _fail()
    except (SourceAddressError, TypeError, ValueError):
        _fail()
    return result


def canonical_decimal(value: str | int | float | Decimal) -> str:
    """Convert a configured finite fraction to its shortest plain decimal text."""
    if type(value) not in {str, int, float, Decimal}:
        _fail("invalid_input")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= 1:
            _fail("invalid_input")
        result = format(number, "f")
    except (InvalidOperation, ValueError):
        _fail("invalid_input")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if number == 0 else result


def semantic_snapshot(evidence: SnapshotEvidence | Mapping) -> Mapping:
    """Keep exact/comparison identity; omit full-file hash and extraction guards."""
    if not isinstance(evidence, SnapshotEvidence):
        evidence = SnapshotEvidence.from_record(_copy(evidence))
    result = evidence.as_dict()
    result.pop("fileHash", None)
    result.pop("span", None)
    # comparisonSpan is relative to the exact snapshot, so it remains semantic.
    return _frozen(result)


def _semantic_snapshot(value: Any) -> SnapshotEvidence:
    value = _copy(value)
    _keys(value, {"snapshot", "hash", "bytes", "encoding"},
          {"comparison", "place", "comparisonSpan"})
    evidence = SnapshotEvidence.from_record(value)
    if evidence.encoding != "utf-8":
        _fail("insufficient_evidence")
    if evidence.comparison is not None:
        evidence.comparison.require_supported()
    return evidence


def semantic_baseline(baseline: BaselineManifest | Mapping) -> Mapping:
    """Project an already validated full manifest without capture-only identity."""
    if not isinstance(baseline, BaselineManifest):
        value = _copy(baseline)
        identifier = value.pop("id", None)
        baseline = BaselineManifest(value)
        if identifier is not None and identifier != baseline.identifier:
            _fail()
    result = _copy(baseline.payload)
    for key in ("id", "capturedAt", "location"):
        result.pop(key, None)
    result["dependant"] = semantic_snapshot(result["dependant"])
    for member in result["members"]:
        member["evidence"] = semantic_snapshot(member["evidence"])
    return _frozen(result)


def _baseline(value: Any) -> dict:
    _keys(value, {"schema", "ownerRepository", "dependantId", "dependantVersion", "dependant",
                  "kind", "source", "selection", "members", "pinnedHash", "selectionComparison"}, {"ref"})
    if type(value["schema"]) is not int or value["schema"] != 1:
        _fail()
    _text(value["ownerRepository"])
    _text(value["dependantId"])
    if not isinstance(value["dependantVersion"], str) or not re.fullmatch(r"[1-9][0-9]*", value["dependantVersion"]):
        _fail()
    _enum(value["kind"], {"declared", "asserted", "related", "generated"})
    if "ref" in value:
        _text(value["ref"], empty=True)
    source = _place(value["source"])
    dependant = _semantic_snapshot(value["dependant"])
    if (dependant.place is None or dependant.place.name is None
            or dependant.place.repository != value["ownerRepository"]
            or dependant.comparison is None or dependant.comparison.kind not in {"document_body", "code_text"}):
        _fail()
    members = _members(value["members"])
    _selection_members(source, value["selection"], [member.get("evidence") if isinstance(member, dict) else None
                                                  for member in members])
    identifiers = set()
    for member in members:
        _keys(member, {"place", "evidence"}, {"id"})
        if _place(member["place"]) != member["evidence"].get("place"):
            _fail()
        if "id" in member:
            identifier = _text(member["id"])
            if identifier in identifiers:
                _fail()
            identifiers.add(identifier)
    recorded = ComparisonRecord.from_record(value["selectionComparison"])
    recorded.require_supported()
    if value["selection"] == "family":
        projection = [{"place": member["place"], "comparison": member["evidence"]["comparison"]}
                      for member in members]
        selected_hash = sha256(canonical_json(projection)).hexdigest()
        if recorded.kind != "family":
            _fail()
    else:
        selected = ComparisonRecord.from_record(members[0]["evidence"]["comparison"])
        selected_hash = selected.hash
        if selected != recorded:
            _fail()
    if _hash(value["pinnedHash"]) != selected_hash or recorded.hash != selected_hash:
        _fail()
    return value


def _selection_members(place: dict, selection: Any, descriptors: list) -> None:
    if not isinstance(selection, str) or selection not in {"file", "chunk", "family"} or not descriptors:
        _fail()
    if (selection in {"file", "chunk"} and len(descriptors) != 1
            or (selection == "file") != ("name" not in place)):
        _fail()
    addresses = []
    for value in descriptors:
        evidence = _semantic_snapshot(value)
        if evidence.place is None or evidence.comparison is None:
            _fail()
        member_place = _place(evidence.place)
        if any(member_place[key] != place[key] for key in ("repository", "root", "path")):
            _fail()
        if selection in {"file", "chunk"} and member_place != place:
            _fail()
        if selection == "file":
            if evidence.comparison.kind != "file_bytes" or evidence.comparison.hash != evidence.hash:
                _fail()
        elif evidence.comparison.kind not in {"document_body", "code_text"} or evidence.place.name is None:
            _fail()
        elif selection == "family" and (evidence.comparison.kind != "code_text"
                or not (evidence.place.name == place["name"] or evidence.place.name.startswith(place["name"] + "."))):
            _fail()
        addresses.append(member_place["address"])
    if len(set(addresses)) != len(addresses) or addresses != sorted(addresses):
        _fail()
    if selection == "family" and addresses.count(place["address"]) != 1:
        _fail()


@dataclass(frozen=True)
class DecisionText:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = _copy(self.payload)
        _keys(value, {"locator", "snapshot", "text"})
        evidence = _semantic_snapshot(value["snapshot"])
        if value["locator"] != f"snapshot:{evidence.hash}":
            _fail()
        # Source text may contain NUL: it is data and canonical JSON escapes it.
        if not isinstance(value["text"], str):
            _fail()
        try:
            source = value["text"].encode("utf-8")
        except UnicodeError:
            _fail("insufficient_evidence")
        evidence.verify(source, textual=True)
        object.__setattr__(self, "payload", _frozen(value))

    @classmethod
    def create(cls, evidence: SnapshotEvidence | Mapping, source: bytes) -> DecisionText:
        if not isinstance(evidence, SnapshotEvidence):
            evidence = SnapshotEvidence.from_record(_copy(evidence))
        evidence.verify(source, textual=True)
        return cls({"locator": f"snapshot:{evidence.hash}", "snapshot": semantic_snapshot(evidence),
                    "text": source.decode("utf-8")})

    def as_dict(self) -> dict:
        return _copy(self.payload)


@dataclass(frozen=True)
class CurrentSelection:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = _copy(self.payload)
        _keys(value, {"locator", "state", "place", "selection", "members"})
        place = _place(value["place"])
        _enum(value["state"], {"present", "away", "deleted"})
        _enum(value["selection"], {"file", "chunk", "family"})
        members = _members(value["members"])
        texts = [DecisionText(member) for member in members]
        if value["state"] == "present":
            _selection_members(place, value["selection"], [item.payload["snapshot"] for item in texts])
        elif members:
            _fail()
        elif (value["selection"] == "file") != ("name" not in place):
            _fail()
        semantic = {key: member for key, member in value.items() if key != "locator"}
        if value["locator"] != "selection:" + sha256(canonical_json(semantic)).hexdigest():
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @classmethod
    def create(cls, state: str, place: SourceAddress | Mapping, selection: str,
               members: Sequence[DecisionText] = ()) -> CurrentSelection:
        value = {"state": state, "place": _place(place), "selection": selection,
                 "members": [member.as_dict() for member in _texts(members)]}
        value["locator"] = "selection:" + sha256(canonical_json(value)).hexdigest()
        return cls(value)

    def as_dict(self) -> dict:
        return _copy(self.payload)


def _before(baseline: dict, values: Any) -> list[DecisionText]:
    texts = [DecisionText(value) for value in _members(values)]
    if [item.as_dict()["snapshot"] for item in texts] != [member["evidence"] for member in baseline["members"]]:
        _fail()
    return texts


def governor_context(baseline: BaselineManifest, before: Sequence[DecisionText],
                     current: CurrentSelection, freshness: str) -> Mapping:
    if not isinstance(current, CurrentSelection):
        _fail("invalid_input")
    return _frozen({"role": "governor", "baseline": semantic_baseline(baseline),
                    "before": [item.as_dict() for item in _texts(before)], "current": current.as_dict(),
                    "freshness": freshness})


def ancestor_context(evidence: DecisionText) -> Mapping:
    if not isinstance(evidence, DecisionText):
        _fail("invalid_input")
    return _frozen({"role": "ancestor", "evidence": evidence.as_dict()})


def _context(value: Any) -> tuple[str, dict]:
    if not isinstance(value, dict):
        _fail()
    if value.get("role") == "governor":
        _keys(value, {"role", "baseline", "before", "current", "freshness"})
        baseline = _baseline(value["baseline"])
        _before(baseline, value["before"])
        current = CurrentSelection(value["current"])
        _enum(value["freshness"], {"fresh", "stale"})
        return current.payload["place"]["address"], value
    if value.get("role") == "ancestor":
        _keys(value, {"role", "evidence"})
        evidence = DecisionText(value["evidence"])
        place = evidence.payload["snapshot"].get("place")
        if place is None or place.get("name") is None:
            _fail()
        return place["address"], value
    _fail()


def _review_model(value: Any) -> dict | None:
    if value is None:
        return None
    _keys(value, {"provider", "model", "adapterRevision", "commandHash", "instructionVersion"})
    _text(value["provider"])
    model = _text(value["model"])
    lowered = model.strip().lower()
    if lowered in {"latest", "current", "default"} or lowered.endswith(("-latest", ":latest", "/latest")):
        _fail()
    _revision(value["adapterRevision"])
    _hash(value["commandHash"])
    if value["instructionVersion"] != INSTRUCTION_VERSION:
        _fail()
    return value


@dataclass(frozen=True)
class DecisionPayload:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = _copy(self.payload)
        _keys(value, {"protocol", "questionVersion", "criteria", "labels", "baseline", "before",
                      "current", "dependant", "context", "models", "routing"})
        if (type(value["protocol"]) is not int or value["protocol"] != PROTOCOL
                or value["questionVersion"] != QUESTION_VERSION or value["criteria"] != CRITERIA
                or value["labels"] != list(LABELS)):
            _fail()
        baseline = _baseline(value["baseline"])
        _before(baseline, value["before"])
        CurrentSelection(value["current"])
        dependant = DecisionText(value["dependant"])
        if (dependant.payload["snapshot"].get("place") != baseline["dependant"].get("place")
                or dependant.payload["snapshot"] != _frozen(baseline["dependant"])):
            _fail()
        context = [_context(item) for item in _members(value["context"])]
        addresses = [address for address, _ in context]
        records = [canonical_json(record) for _, record in context]
        if addresses != sorted(addresses) or len(set(records)) != len(records):
            _fail()
        _keys(value["models"], {"jev", "review"})
        _keys(value["models"]["jev"], {"provider", "model"})
        if value["models"]["jev"]["provider"] != "typesafe" or not isinstance(value["models"]["jev"]["model"], str) or not _JEV_MODEL.fullmatch(value["models"]["jev"]["model"]):
            _fail()
        _review_model(value["models"]["review"])
        _keys(value["routing"], {"revision", "confidenceFloor"})
        _revision(value["routing"]["revision"])
        floor = value["routing"]["confidenceFloor"]
        if not isinstance(floor, str) or canonical_decimal(floor) != floor:
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @classmethod
    def create(cls, *, baseline: BaselineManifest, before: Sequence[DecisionText],
               current: CurrentSelection, dependant: DecisionText, context: Sequence[Mapping] = (),
               jev_model: str = "jev-1.13.0", review: Mapping | None = None,
               routing_revision: str = ROUTING_REVISION, confidence_floor: Any = "0.7") -> DecisionPayload:
        if not isinstance(current, CurrentSelection) or not isinstance(dependant, DecisionText):
            _fail("invalid_input")
        if type(context) not in {tuple, list}:
            _fail("invalid_input")
        return cls({"protocol": PROTOCOL, "questionVersion": QUESTION_VERSION, "criteria": CRITERIA,
                    "labels": LABELS, "baseline": semantic_baseline(baseline),
                    "before": [item.as_dict() for item in _texts(before)], "current": current.as_dict(),
                    "dependant": dependant.as_dict(), "context": list(context),
                    "models": {"jev": {"provider": "typesafe", "model": jev_model}, "review": review},
                    "routing": {"revision": routing_revision, "confidenceFloor": canonical_decimal(confidence_floor)}})

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def input_hash(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()

    @property
    def evidence_locators(self) -> tuple[str, ...]:
        locators = {self.payload["dependant"]["locator"], self.payload["current"]["locator"]}
        locators.update(item["locator"] for item in self.payload["before"])
        locators.update(item["locator"] for item in self.payload["current"]["members"])
        for context in self.payload["context"]:
            if context["role"] == "ancestor":
                locators.add(context["evidence"]["locator"])
            else:
                locators.add(context["current"]["locator"])
                locators.update(item["locator"] for item in context["before"])
                locators.update(item["locator"] for item in context["current"]["members"])
        return tuple(sorted(locators))

    def as_dict(self) -> dict:
        return _copy(self.payload)

    @classmethod
    def from_bytes(cls, source: bytes, input_hash: str) -> DecisionPayload:
        if type(source) is not bytes or sha256(source).hexdigest() != _hash(input_hash):
            _fail()
        try:
            result = cls(json.loads(source))
        except (UnicodeError, ValueError, TypeError):
            _fail()
        if result.canonical_bytes != source:
            _fail()
        return result


@dataclass(frozen=True)
class ReviewCommandIdentity:
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = _copy(self.payload)
        _keys(value, {"argv", "executableSha256", "adapterRevision", "protocol",
                      "instructionVersion", "environmentVersion"})
        argv = _members(value["argv"])
        if not argv:
            _fail("invalid_input")
        for argument in argv:
            if not isinstance(argument, str) or not argument:
                _fail("invalid_input")
            _text(argument, empty=True)
        if not Path(argv[0]).is_absolute():
            _fail("invalid_input")
        if value["executableSha256"] is not None:
            _hash(value["executableSha256"])
        _revision(value["adapterRevision"])
        if (type(value["protocol"]) is not int or value["protocol"] != PROTOCOL
                or value["instructionVersion"] != INSTRUCTION_VERSION
                or value["environmentVersion"] != ENVIRONMENT_VERSION):
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @classmethod
    def inspect(cls, argv: Sequence[str], adapter_revision: str, resolved_home: Path | str) -> ReviewCommandIdentity:
        """Resolve and fingerprint once; never invoke an adapter or search PATH."""
        if type(argv) not in {tuple, list} or not argv:
            _fail("invalid_input")
        for argument in argv:
            if not isinstance(argument, str) or not argument or "\0" in argument:
                _fail("invalid_input")
            _text(argument, empty=True)
        home = Path(resolved_home)
        if not home.is_absolute():
            _fail("invalid_input")
        executable = str(home / argv[0][2:]) if argv[0].startswith("~/") else argv[0]
        if not Path(executable).is_absolute():
            _fail("invalid_input")
        try:
            resolved = Path(executable).resolve(strict=False)
        except (OSError, RuntimeError):
            # A broken/looping symlink is unavailable review work, while Jev
            # still has a deterministic command identity and may proceed.
            resolved = Path(os.path.abspath(executable))
        digest = None
        try:
            if stat.S_ISREG(resolved.stat().st_mode) and os.access(resolved, os.R_OK | os.X_OK):
                hasher = sha256()
                with resolved.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        hasher.update(block)
                digest = hasher.hexdigest()
        except OSError:
            pass
        return cls({"argv": [str(resolved), *argv[1:]], "executableSha256": digest,
                    "adapterRevision": adapter_revision, "protocol": PROTOCOL,
                    "instructionVersion": INSTRUCTION_VERSION, "environmentVersion": ENVIRONMENT_VERSION})

    @property
    def available(self) -> bool:
        return self.payload["executableSha256"] is not None

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def command_hash(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()

    def as_dict(self) -> dict:
        return _copy(self.payload)

    def model_identity(self, provider: str, model: str) -> Mapping:
        value = {"provider": provider, "model": model, "adapterRevision": self.payload["adapterRevision"],
                 "commandHash": self.command_hash, "instructionVersion": INSTRUCTION_VERSION}
        _review_model(value)
        return _frozen(value)


@dataclass(frozen=True)
class ReviewerRequest:
    decision: DecisionPayload
    timeout_ms: int

    def __post_init__(self):
        if not isinstance(self.decision, DecisionPayload) or self.decision.payload["models"]["review"] is None:
            _fail("reviewer_unconfigured")
        _integer(self.timeout_ms, 1)

    @property
    def payload(self) -> Mapping:
        review = self.decision.payload["models"]["review"]
        return _frozen({"protocol": PROTOCOL, "inputHash": self.decision.input_hash,
                        "questionVersion": QUESTION_VERSION, **review, "payload": self.decision.payload,
                        "judgements": LABELS, "evidenceLocators": self.decision.evidence_locators,
                        "budget": {"timeoutMs": self.timeout_ms, "maxProviderCalls": 1, "maxOutputBytes": 1048576}})

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def transmitted_bytes(self) -> bytes:
        return self.canonical_bytes + b"\n"


def _utc(value: Any) -> None:
    _text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            _fail()
    except (ValueError, TypeError):
        _fail()


@dataclass(frozen=True)
class EvidenceBundle:
    """Full immutable bundle manifest; its hash is separate from semantic input."""

    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        value = _copy(self.payload)
        _keys(value, {"schema", "ownerRepository", "baseline", "inputHash", "requestSnapshot", "evidence",
                      "sourceState", "guards", "disposition"})
        if type(value["schema"]) is not int or value["schema"] != 1:
            _fail()
        _text(value["ownerRepository"])
        _hash(value["baseline"])
        if value["requestSnapshot"] != "snapshot:" + _hash(value["inputHash"]):
            _fail()
        _enum(value["sourceState"], {"present", "away", "deleted"})
        _enum(value["disposition"], {"active", "complete", "obsolete", "error"})
        descriptors = [SnapshotEvidence.from_record(item) for item in _members(value["evidence"])]
        encoded = [canonical_json(item.as_dict()) for item in descriptors]
        if not descriptors or encoded != sorted(set(encoded)):
            _fail()
        guards = _members(value["guards"])
        addresses = []
        for guard in guards:
            _keys(guard, {"place", "event"}, {"hash", "changedAt"})
            addresses.append(_place(guard["place"])["address"])
            _enum(guard["event"], {"file_changed", "deleted", "generated"})
            if "hash" in guard:
                _hash(guard["hash"])
            if (guard["event"] == "deleted") != ("hash" not in guard):
                _fail()
            if "changedAt" in guard:
                _utc(guard["changedAt"])
        if addresses != sorted(set(addresses)):
            _fail()
        object.__setattr__(self, "payload", _frozen(value))

    @classmethod
    def create(cls, *, owner_repository: str, baseline_id: str, decision: DecisionPayload,
               evidence: Sequence[SnapshotEvidence | Mapping], guards: Sequence[Mapping],
               disposition: str = "active") -> EvidenceBundle:
        if not isinstance(decision, DecisionPayload) or type(evidence) not in {tuple, list} or type(guards) not in {tuple, list}:
            _fail("invalid_input")
        if decision.payload["baseline"]["ownerRepository"] != owner_repository:
            _fail()
        records = [item.as_dict() if isinstance(item, SnapshotEvidence) else _copy(item) for item in evidence]
        unique = {canonical_json(item): item for item in records}
        # All supplied text descriptors must occur with full metadata in the bundle.
        semantic = {canonical_json(semantic_snapshot(item)) for item in records}
        for text in _decision_texts(decision):
            if canonical_json(text["snapshot"]) not in semantic:
                _fail("baseline_missing")
        guard_records = [_copy(item) for item in guards]
        for guard in guard_records:
            _keys(guard, {"place", "event"}, {"hash", "changedAt"})
            _place(guard["place"])
        return cls({"schema": 1, "ownerRepository": owner_repository, "baseline": baseline_id,
                    "inputHash": decision.input_hash, "requestSnapshot": "snapshot:" + decision.input_hash,
                    "evidence": [unique[key] for key in sorted(unique)],
                    "sourceState": decision.payload["current"]["state"],
                    "guards": sorted(guard_records, key=lambda item: item["place"]["address"]),
                    "disposition": disposition})

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.payload)

    @property
    def evidence_hash(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()

    def as_dict(self) -> dict:
        return _copy(self.payload)

    @classmethod
    def from_bytes(cls, source: bytes, evidence_hash: str) -> EvidenceBundle:
        if type(source) is not bytes or sha256(source).hexdigest() != _hash(evidence_hash):
            _fail()
        try:
            result = cls(json.loads(source))
        except (UnicodeError, ValueError, TypeError):
            _fail()
        if result.canonical_bytes != source:
            _fail()
        return result


def _decision_texts(decision: DecisionPayload) -> tuple[Mapping, ...]:
    result = [*decision.payload["before"], *decision.payload["current"]["members"], decision.payload["dependant"]]
    for context in decision.payload["context"]:
        if context["role"] == "ancestor":
            result.append(context["evidence"])
        else:
            result.extend(context["before"])
            result.extend(context["current"]["members"])
    return tuple(result)
