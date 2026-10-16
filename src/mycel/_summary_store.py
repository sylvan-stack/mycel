"""Read-only summary status and plans over one retained index snapshot.

The future publisher's handoff lives in the existing ``mycel_generated_state``
JSON column. Version 1 records the current summary chunk version, its level,
exact logical member pins, and identical set metadata on every published node.
It changes neither SQL tables nor the immutable generation-evidence format.
This reader never refreshes files, starts a writer, embeds, or publishes rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
import re
from uuid import UUID, NAMESPACE_URL, uuid5

import psycopg

from ._errors import MycelError
from ._locks import snapshot_transaction
from ._markdown import split_markdown
from ._refs import _place
from ._resolver import SelectionMember, SourceResolver, require_read_transaction
from ._retrieval_store import _copy, _disk_inputs
from ._scope import RepositoryLocations
from ._settings import SettingsSnapshot, _freeze
from ._source_refs import SourceAddress, parse_source_address, read_document_declarations
from ._store import checked_store
from ._summary_request import SummarySection, load_summary_prompts, plan_summary_requests


STATE_VERSION = 1
GROUPING_PROFILE = "mycel-summary-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SUMMARY_NAME = re.compile(r"([1-5])/([1-9][0-9]*)\Z")
SUMMARY_FAILURE_REASONS = frozenset({"io_failure", "start_failed", "timeout", "stdout_limit",
    "stderr_limit", "nonzero_exit", "invalid_utf8", "empty_response", "embedding_failed", "inputs_changed"})


def _bad_state():
    raise MycelError("store_format", "The published summary catalog has incompatible versioned state.")


def _request_member(member):
    return ((member.chunk.kind == "document" and member.place.root in {"code", "artifact"})
            or (member.chunk.kind == "summary" and member.place.root == "index"))


def _summary_members(summary, current, resolver, *, removed=()):
    """Resolve retained pins by logical identity, then their original place.

    Generated detection uses this same reconnect rule for a deleted source
    that returns with a new logical identity. Unrelated new sections remain
    outside the retained group. Return each original pin beside its survivor.
    """
    result = []
    for pin in summary.state.members:
        if pin.chunk_id in removed:
            continue
        member = current.get(pin.chunk_id)
        if member is None and pin.place.root != "index":
            resolution = resolver.resolve(pin.place.address, purpose="read")
            if resolution.selection is not None and len(resolution.selection.members) == 1:
                member = resolution.selection.members[0]
        if member is not None:
            result.append((pin, member))
    return tuple(result)


def _invalid_reply():
    raise MycelError("invalid_input", "The summary completion reply is invalid.")


def _reply_repository(repository):
    try:
        if not isinstance(repository, str) or not repository.strip():
            _invalid_reply()
        SourceAddress(repository, "index", "summaries").address
    except (TypeError, ValueError):
        _invalid_reply()


def _reply_place(value, repository, *, summary=False):
    try:
        if isinstance(value, SourceAddress):
            place = value
        elif isinstance(value, Mapping) and set(value) == {"repository", "root", "path", "name", "address"}:
            place = parse_source_address(value["address"])
            if dict(value) != _place(place):
                _invalid_reply()
        else:
            _invalid_reply()
        if (place.repository != repository or place.name is None or place.root is None
                or (summary and (place.root != "index" or place.path != "summaries"
                                 or not _SUMMARY_NAME.fullmatch(place.name)))
                or (not summary and place.root == "index" and
                    (place.path != "summaries" or not _SUMMARY_NAME.fullmatch(place.name)))):
            _invalid_reply()
        place.address
        return place
    except (TypeError, ValueError):
        _invalid_reply()


def _reply_order(place):
    if place.root == "index":
        level, ordinal = map(int, place.name.split("/"))
        return (place.root, place.path, level, ordinal, place.address)
    return (place.root, place.path, 0, 0, place.address)


def summary_removal_reply(repository: str, removed: int) -> dict:
    """Prepare the complete SYL-142 response without removing any rows."""
    _reply_repository(repository)
    if type(removed) is not int or removed < 0:
        _invalid_reply()
    return {"repository": repository, "removed": removed}


def summary_result_reply(repository: str, *, written: int, deleted: int, replaced: bool,
                         failed: Sequence[Mapping] = (), blocked: Sequence[Mapping] = (),
                         cut: Sequence[SourceAddress | Mapping] = (), stopped: str | None = None) -> dict:
    """Validate the future publisher's complete result, without publication.

    Failure reasons are redacted boundary codes. Blocked/stopped reasons use
    the accepted closed enums; every place is canonical and repository-owned.
    These constructors do not make pending mutation handlers return success.
    """
    _reply_repository(repository)
    if (any(type(count) is not int or count < 0 for count in (written, deleted))
            or type(replaced) is not bool or (stopped is not None and
                (not isinstance(stopped, str) or stopped not in {"interrupted", "failed", "inputs_changed"}))
            or any(not isinstance(values, Sequence) or isinstance(values, (str, bytes))
                   for values in (failed, blocked, cut))):
        _invalid_reply()
    failures, blockers, cuts = [], [], []
    for values, result, key, reasons in ((failed, failures, "summary", SUMMARY_FAILURE_REASONS),
            (blocked, blockers, "summary", {"stale_member", "inputs_changed"})):
        for item in values:
            if (not isinstance(item, Mapping) or set(item) != {key, "reason"}
                    or not isinstance(item["reason"], str) or item["reason"] not in reasons):
                _invalid_reply()
            value = item[key]
            if result is failures:
                try:
                    value = parse_source_address(value)
                    if value.address != item[key]:
                        _invalid_reply()
                except (TypeError, ValueError):
                    _invalid_reply()
            result.append((_reply_place(value, repository, summary=True), item["reason"]))
    cuts = [_reply_place(value, repository) for value in cut]
    failure_places = {place.address for place, _ in failures}
    blocked_places = {place.address for place, _ in blockers}
    if (len(failure_places) != len(failures) or len(blocked_places) != len(blockers)
            or failure_places & blocked_places or len({place.address for place in cuts}) != len(cuts)):
        _invalid_reply()
    reply = {"repository": repository, "written": written, "deleted": deleted, "replaced": replaced,
        "failed": [{"summary": place.address, "reason": reason}
                   for place, reason in sorted(failures, key=lambda item: _reply_order(item[0]))],
        "blocked": [{"summary": _place(place), "reason": reason}
                    for place, reason in sorted(blockers, key=lambda item: _reply_order(item[0]))],
        "cut": [_place(place) for place in sorted(cuts, key=_reply_order)]}
    if stopped is not None:
        reply["stopped"] = stopped
    return reply


def summary_repository(settings: SettingsSnapshot, names: Sequence[str] = (), *, cwd=None) -> str:
    """Reject an organization even when its scope contains just one member.

    No folder preflight or freshness pass is appropriate for stored reports.
    Folder bindings are consulted only to identify an implicit repository.
    """
    settings.require_valid()
    if len(names) > 1 or any(not isinstance(name, str) for name in names):
        raise MycelError("invalid_input", "Summaries take exactly one repository.")
    if names and names[0] in settings.values["organizations"]:
        raise MycelError("invalid_input", "Summaries take one repository; an organization is not accepted.")
    locations = RepositoryLocations(settings)
    selected = locations.resolve_scope(names, cwd=cwd)
    if len(selected) != 1:
        raise MycelError("invalid_input", "Summaries take one repository; an organization is not accepted.")
    repository = selected[0]
    if not names:
        try:
            current = (Path.cwd() if cwd is None else Path(cwd)).resolve()
            bindings = [(len(folder.path.resolve().parts), 1)
                for folder in (repository.code, repository.documents) if folder is not None
                and current.is_relative_to(folder.path.resolve())]
            organizations = [(len(root.resolve().parts), 0)
                for organization in locations.organizations
                for root in (organization.root, organization.documents)
                if current.is_relative_to(root.resolve())]
            if not bindings or (organizations and max(organizations) > max(bindings)):
                raise MycelError("invalid_input", "Summaries take one repository; an organization folder is not accepted.")
        except (OSError, RuntimeError, ValueError):
            raise MycelError("unknown_repository", "The summary repository folder cannot be resolved.") from None
    if not repository.enabled:
        raise MycelError("refused", "Summaries require an enabled repository.")
    return repository.name


@dataclass(frozen=True)
class SummaryMemberPin:
    """A logical member, with the exact version/hash used at publication."""

    chunk_id: str
    chunk_version: int
    snapshot_hash: str
    place: SourceAddress

    def to_dict(self):
        return {"chunkId": self.chunk_id, "chunkVersion": self.chunk_version,
                "snapshotHash": self.snapshot_hash, "place": self.place.address}


@dataclass(frozen=True)
class SummarySetMetadata:
    built_at: str
    grouping_profile: str
    build: int | None
    numerical_versions: Mapping[str, str]

    def to_dict(self):
        return {"builtAt": self.built_at, "groupingProfile": self.grouping_profile,
                "build": self.build, "numericalVersions": dict(self.numerical_versions)}


def summary_set_identifier(repository):
    """An unlocated catalog owner retains metadata even for an empty set."""
    return uuid5(NAMESPACE_URL, f"mycel:summary-set:{repository}")


@dataclass(frozen=True)
class PublishedSummaryState:
    """Validated JSON handoff for SYL-140's later atomic publisher.

    ``build`` is the positive MYC-15 integer, or null in source development;
    replies render numbered Builds as canonical lower-case hexadecimal.
    Numerical versions are historical recorded values, never substituted with
    the dependencies of the reader. Pins retain missing logical members too.
    """

    chunk_version: int
    level: int
    members: tuple[SummaryMemberPin, ...]
    metadata: SummarySetMetadata

    def to_dict(self):
        return {"schemaVersion": STATE_VERSION, "chunkVersion": self.chunk_version,
                "level": self.level, "members": [member.to_dict() for member in self.members],
                "set": self.metadata.to_dict()}

    @classmethod
    def from_dict(cls, value, *, repository: str):
        try:
            if (not isinstance(value, Mapping)
                    or set(value) != {"schemaVersion", "chunkVersion", "level", "members", "set"}
                    or type(value["schemaVersion"]) is not int or value["schemaVersion"] != STATE_VERSION
                    or type(value["chunkVersion"]) is not int or value["chunkVersion"] < 1
                    or type(value["level"]) is not int or not 1 <= value["level"] <= 5
                    or not isinstance(value["members"], (list, tuple))):
                _bad_state()
            members = []
            for pin in value["members"]:
                if (not isinstance(pin, Mapping)
                        or set(pin) != {"chunkId", "chunkVersion", "snapshotHash", "place"}
                        or not isinstance(pin["chunkId"], str)
                        or str(UUID(pin["chunkId"])) != pin["chunkId"]
                        or type(pin["chunkVersion"]) is not int or pin["chunkVersion"] < 1
                        or not isinstance(pin["snapshotHash"], str) or not _HASH.fullmatch(pin["snapshotHash"])):
                    _bad_state()
                place = parse_source_address(pin["place"])
                if (place.repository != repository or place.root not in {"code", "artifact", "index"}
                        or place.name is None or place.address != pin["place"]):
                    _bad_state()
                members.append(SummaryMemberPin(pin["chunkId"], pin["chunkVersion"], pin["snapshotHash"], place))
            if (len({member.chunk_id for member in members}) != len(members)
                    or len({member.place.address for member in members}) != len(members)):
                _bad_state()
            metadata = value["set"]
            if (not isinstance(metadata, Mapping)
                    or set(metadata) != {"builtAt", "groupingProfile", "build", "numericalVersions"}
                    or not isinstance(metadata["builtAt"], str)
                    or datetime.fromisoformat(metadata["builtAt"].replace("Z", "+00:00")).utcoffset() is None
                    or metadata["groupingProfile"] != GROUPING_PROFILE
                    or (metadata["build"] is not None and
                        (type(metadata["build"]) is not int or metadata["build"] < 1))
                    or not isinstance(metadata["numericalVersions"], Mapping)
                    or set(metadata["numericalVersions"]) != {"numpy", "scipy", "scikit-learn"}
                    or any(not isinstance(version, str) or not version.strip() or "\0" in version
                           for version in metadata["numericalVersions"].values())):
                _bad_state()
            return cls(value["chunkVersion"], value["level"], tuple(members),
                SummarySetMetadata(metadata["builtAt"], metadata["groupingProfile"], metadata["build"],
                                   _freeze(dict(metadata["numericalVersions"]))))
        except (TypeError, ValueError, KeyError, OverflowError):
            _bad_state()


@dataclass(frozen=True)
class _Summary:
    member: SelectionMember
    state: PublishedSummaryState

    @property
    def order(self):
        return (self.state.level, int(self.member.chunk.name.split("/")[1]), self.member.place.address)


@dataclass
class _Lease:
    active: bool = True


@dataclass(frozen=True)
class SummarySnapshot:
    repository: str
    resolver: SourceResolver
    sections: tuple[SummarySection, ...]
    not_embedded: int
    _vectors: Mapping[str, tuple[tuple[float, ...], ...]] = field(repr=False)
    _summaries: tuple[_Summary, ...] = field(repr=False)
    _current: Mapping[str, SelectionMember] = field(repr=False)
    _generated_stale: frozenset[str] = field(repr=False)
    _connection: object = field(repr=False, compare=False)
    _settings: SettingsSnapshot = field(repr=False, compare=False)
    _lease: _Lease = field(repr=False, compare=False)
    _metadata: SummarySetMetadata | None = field(default=None, repr=False)

    def _require_active(self):
        if not self._lease.active:
            raise MycelError("invalid_input", "The summary snapshot has ended.")
        require_read_transaction(self._connection)

    def status(self) -> dict:
        self._require_active()
        membership = {member.chunk.identifier for summary in self._summaries
                      for _, member in _summary_members(summary, self._current, self.resolver)}
        embedded_members = sum(section.member.chunk.identifier in membership for section in self.sections)
        levels = sorted({summary.state.level for summary in self._summaries})
        reply = {"repository": self.repository,
                 "commandSet": bool(self._settings.values["summaries"].get("command")),
                 "numericalVersions": {},
                 "levels": [{"level": level,
                             "summaries": sum(summary.state.level == level for summary in self._summaries),
                             "stale": sum(summary.state.level == level and
                                 summary.member.chunk.identifier in self._generated_stale
                                 for summary in self._summaries)} for level in levels],
                 "sections": {"inSummary": embedded_members, "inNone": len(self.sections) - embedded_members,
                              "notEmbedded": self.not_embedded}}
        metadata = self._metadata or (self._summaries[0].state.metadata if self._summaries else None)
        if metadata is not None:
            reply.update({"builtAt": metadata.built_at, "groupingProfile": metadata.grouping_profile,
                          "numericalVersions": dict(metadata.numerical_versions)})
            if metadata.build is not None:
                reply["build"] = format(metadata.build, "x")
        return reply

    def build_plan(self) -> dict:
        self._require_active()
        from ._build_identity import current_build
        from ._summary_grouping import SummaryNode, mean_vector, plan_summary_levels
        prompts = load_summary_prompts(self._settings)
        nodes = tuple(SummaryNode(section.member.chunk.identifier, section.member.place, section.position,
                                  mean_vector(self._vectors[section.member.chunk.identifier]), section)
                      for section in self.sections)

        def split_group(group, level):
            # Future text has no known size. Higher-level request counts are
            # estimates just like their stand-in vectors; exact leaf text fits.
            if level != 1:
                return (group,)
            by_key = {node.key: node for node in group}
            return tuple(tuple(by_key[section.member.chunk.identifier] for section in request.sections)
                         for request in plan_summary_requests(tuple(node.section for node in group), prompts))

        plan = plan_summary_levels(nodes, split_group=split_group)
        build = current_build()
        return {**plan.report(), "repository": self.repository, "sections": len(self.sections),
                "notEmbedded": self.not_embedded, "operation": "build", "dryRun": True,
                "build": "development" if build is None else format(build, "x")}

    def regeneration_plan(self) -> dict:
        self._require_active()
        write, remove, blocked, work = [], [], [], []
        prompts = None
        unresolved = set(self._generated_stale)
        removed = set()
        planned = set()
        levels = {summary.member.chunk.identifier: summary.state.level for summary in self._summaries}
        for summary in self._summaries:
            identifier = summary.member.chunk.identifier
            if identifier not in self._generated_stale:
                continue
            surviving = _summary_members(summary, self._current, self.resolver, removed=removed)
            members = tuple(member for _, member in surviving)
            surviving_pins = {pin.chunk_id for pin, _ in surviving}
            invalid_members = [member for member in members if not _request_member(member)]
            details = {"summary": _place(summary.member.place), "level": summary.state.level,
                "members": [{"pin": pin.to_dict(), "current": {
                    "chunkId": member.chunk.identifier, "chunkVersion": member.chunk.version,
                    "snapshotHash": member.chunk.snapshot_hash, "place": _place(member.place)}}
                    for pin, member in surviving],
                "missingMembers": [pin.to_dict() for pin in summary.state.members
                                   if pin.chunk_id not in surviving_pins],
                "invalidMembers": [_place(member.place) for member in invalid_members],
                "conditionalOn": [_place(member.place)
                                  for _, member in _summary_members(summary, self._current, self.resolver)
                                  if member.chunk.identifier in planned]}
            if not members:
                remove.append(_place(summary.member.place))
                removed.add(identifier)
                unresolved.discard(identifier)
                details.update({"action": "remove", "reason": "no_members"})
                planned.add(identifier)
            elif invalid_members or len({member.chunk.identifier for member in members}) != len(members) or any(
                     member.chunk.identifier in unresolved or
                     levels.get(member.chunk.identifier, 0) >= summary.state.level
                     for member in members if member.place.root == "index"):
                blocked.append({"summary": _place(summary.member.place), "reason": "stale_member"})
                details.update({"action": "blocked", "reason": "invalid_member" if invalid_members else "stale_member"})
            else:
                write.append(_place(summary.member.place))
                # This is the successful lower-level work assumed by a plan.
                # A failed real request will stay stale and block its parents.
                unresolved.discard(identifier)
                planned.add(identifier)
                details.update({"action": "write", "reason": "stale"})
            if members and not invalid_members and len({member.chunk.identifier for member in members}) == len(members):
                prompts = prompts or load_summary_prompts(self._settings)
                sections = tuple(SummarySection(member, member.chunk.span[0] if member.chunk.span is not None else
                    int(member.place.name.split("/")[1])) for member in members)
                requests = len(plan_summary_requests(sections, prompts))
                conditional_writes = any(member.chunk.identifier in planned for member in members)
                details.update({"boundedRequestsForCurrentText": requests, "requestFits": requests == 1,
                                "requiresBuild": requests > 1 and not conditional_writes})
            work.append(details)
        return {"repository": self.repository, "operation": "regenerate", "dryRun": True,
                "estimated": True, "successPolicy": "assume_lower_level_success",
                "write": write, "remove": remove, "blocked": blocked, "work": work}


class StoreSummaries:
    def __init__(self, connection, settings: SettingsSnapshot):
        settings.require_valid()
        self._connection = connection
        self._settings = replace(settings, values=_freeze(_copy(settings.values)))

    @contextmanager
    def snapshot(self, names: Sequence[str] = (), *, cwd=None):
        repository = summary_repository(self._settings, names, cwd=cwd)
        # An unrelated repository must not affect this one-repository report.
        scoped = replace(self._settings, values=_freeze({**self._settings.values,
            "repos": {name: {**value, "enabled": name == repository}
                      for name, value in self._settings.values["repos"].items()}}))
        dimensions = self._settings.values["embedding"]["dimensions"]
        try:
            with checked_store(self._connection, dimensions=dimensions), snapshot_transaction(self._connection):
                resolver = SourceResolver.from_read_transaction(self._connection, scoped)
                current = {member.chunk.identifier: member
                    for file in resolver.files for member in resolver._members(file, file.chunks)}
                for place, chunk in resolver.index:
                    if chunk.identifier in current:
                        _bad_state()
                    current[chunk.identifier] = SelectionMember(place, chunk)
                sections, not_embedded, vectors = summary_inputs(self._connection, resolver, self._settings, repository)
                summaries, stale = _published(self._connection, resolver, current, repository)
                metadata = _set_metadata(self._connection, repository, summaries)
                lease = _Lease()
                snapshot = SummarySnapshot(repository, resolver, sections, not_embedded,
                    vectors, summaries, _freeze(current), stale,
                    self._connection, self._settings, lease, metadata)
                try:
                    yield snapshot
                finally:
                    lease.active = False
        except psycopg.Error:
            raise MycelError("store_unavailable", "The summary snapshot could not be read.") from None


def summary_inputs(connection, resolver, settings, repository):
    """Read the same eligible leaves and vectors in a read or guarded write snapshot."""
    coverage = {chunk.identifier: chunk for chunk in _disk_inputs(connection, resolver)
                if chunk.origin == "documents" and chunk.kind == "document" and chunk.repository == repository}
    current = {member.chunk.identifier: member for file in resolver.files
               if file.repository == repository for member in resolver._members(file, file.chunks)}
    eligibility = {}
    for file in resolver.files:
        if file.repository != repository or not any(chunk.identifier in coverage for chunk in file.chunks):
            continue
        declarations = read_document_declarations(split_markdown(file.source), file=file.primary.address)
        if declarations.heartwood or declarations.generated:
            continue
        for position, chunk in enumerate(sorted(file.chunks,
                key=lambda chunk: (chunk.span[0] if chunk.span else 0, chunk.name, chunk.identifier))):
            if chunk.kind == "document":
                eligibility[chunk.identifier] = SummarySection(current[chunk.identifier], position)
    sections = tuple(sorted((section for identifier, section in eligibility.items()
        if identifier in coverage and coverage[identifier].fully_embedded), key=lambda section: section.order))
    not_embedded = sum(identifier in coverage and not coverage[identifier].fully_embedded for identifier in eligibility)
    return sections, not_embedded, _freeze({section.member.chunk.identifier:
        coverage[section.member.chunk.identifier].part_vectors for section in sections})


def _set_metadata(connection, repository, summaries):
    identifier = summary_set_identifier(repository)
    row = connection.execute('SELECT c.kind,c.file_id,g.kind,g.state FROM public.mycel_chunks c '
        'LEFT JOIN public.mycel_generated_state g ON g.chunk_id=c.id WHERE c.id=%s AND c.repository=%s',
        (identifier, repository)).fetchone()
    if row is None:
        return summaries[0].state.metadata if summaries else None
    if (row[:3] != ('summary_set', None, 'summary_set') or not isinstance(row[3], Mapping)
            or set(row[3]) != {'schemaVersion', 'set'} or type(row[3]['schemaVersion']) is not int
            or row[3]['schemaVersion'] != STATE_VERSION
            or connection.execute('SELECT EXISTS(SELECT 1 FROM public.mycel_chunk_versions WHERE chunk_id=%s)',
                                  (identifier,)).fetchone() != (False,)):
        _bad_state()
    parsed = PublishedSummaryState.from_dict({'schemaVersion': STATE_VERSION, 'chunkVersion': 1,
        'level': 1, 'members': [], 'set': row[3]['set']}, repository=repository).metadata
    if any(summary.state.metadata != parsed for summary in summaries):
        _bad_state()
    return parsed


def _published(connection, resolver, current, repository):
    states = {str(identifier): (kind, state) for identifier, kind, state in connection.execute(
        "SELECT chunk_id,kind,state FROM public.mycel_generated_state WHERE repository=%s ORDER BY chunk_id",
        (repository,)).fetchall()}
    summaries = []
    for place, chunk in resolver.index:
        if chunk.kind != "summary":
            continue
        row = states.get(chunk.identifier)
        if row is None or row[0] != "summary" or place.path != "summaries":
            _bad_state()
        state = PublishedSummaryState.from_dict(row[1], repository=repository)
        name = _SUMMARY_NAME.fullmatch(chunk.name)
        if not name or int(name[1]) != state.level or state.chunk_version != chunk.version:
            _bad_state()
        summaries.append(_Summary(SelectionMember(place, chunk), state))
    if len({summary.member.place.address for summary in summaries}) != len(summaries):
        _bad_state()
    if summaries and any(summary.state.metadata != summaries[0].state.metadata for summary in summaries):
        _bad_state()
    marked_versions = {version for (version,) in connection.execute(
        "SELECT DISTINCT chunk_version FROM public.mycel_stale_reasons WHERE repository=%s", (repository,)).fetchall()}
    stale = {member.chunk.identifier for member in current.values()
             if member.place.root == "index" and member.chunk.version in marked_versions}
    levels = {summary.member.chunk.identifier: summary.state.level for summary in summaries}
    for summary in summaries:
        generated = connection.execute('SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,'
            'd.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d '
            'LEFT JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 '
            "WHERE d.dependant_version=%s AND d.kind='generated' ORDER BY d.id",
            (summary.member.chunk.version,)).fetchall()
        if generated:
            from ._generated import generated_capture, generated_resolution, compare_generated
            from ._evidence import EvidenceError
            try:
                for row in generated:
                    from ._summary_evidence import GenerationEvidenceStore
                    capture = GenerationEvidenceStore(connection)._read(repository, row[8])
                    expected = tuple(SummaryMemberPin(item['id'], item['version'], item['source']['hash'],
                        parse_source_address(item['place']['address'])) for item in capture.manifest.payload['members'])
                    if expected != summary.state.members:
                        _bad_state()
                    _, pin = generated_capture(connection, row)
                    if compare_generated(pin, generated_resolution(resolver, row)):
                        stale.add(summary.member.chunk.identifier)
            except EvidenceError:
                stale.add(summary.member.chunk.identifier)
            continue
        if not summary.state.members:
            stale.add(summary.member.chunk.identifier)
        for pin in summary.state.members:
            member = current.get(pin.chunk_id)
            if (member is None or member.chunk.version != pin.chunk_version
                    or member.chunk.snapshot_hash != pin.snapshot_hash
                    or not _request_member(member)
                    or levels.get(pin.chunk_id, 0) >= summary.state.level):
                stale.add(summary.member.chunk.identifier)
    changed = True
    while changed:
        changed = False
        for summary in summaries:
            identifier = summary.member.chunk.identifier
            if identifier not in stale and any(pin.chunk_id in stale for pin in summary.state.members):
                stale.add(identifier)
                changed = True
    return tuple(sorted(summaries, key=lambda summary: summary.order)), frozenset(stale)
