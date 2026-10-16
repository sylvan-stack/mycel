"""Explicit stale-summary repair with one guarded publication per existing place."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from ._activity import AppliedMutation, MutationActivity
from ._build_identity import current_build
from ._capture import capture_repository
from ._collection import CollectionStore
from ._credentials import Credentials
from ._embedding_plan import document_place_line, load_tokenizer, plan_batches, plan_chunk
from ._errors import MycelError
from ._evidence import EvidenceError
from ._locks import atomic_transaction, invocation_guard, operation_guard
from ._resolver import SelectionMember, SourceResolver
from ._safeguards import InvocationPolicy, _defer_cleanup_signals, require_model_call, resolve_command
from ._settings import _freeze
from ._source_refs import parse_source_address
from ._staleness import detection_guards
from ._store import checked_store
from ._summary_evidence import GenerationEvidenceStore, GenerationMember, capture_generation
from ._summary_request import SummarySection, load_summary_prompts, plan_summary_requests, summary_command
from ._summary_store import StoreSummaries, _published, _request_member, _summary_members, summary_result_reply
from ._summary_writer import SummaryWriter
from ._voyage import CommitReceipt, EmbeddingGuardFailure, PartIdentity, VoyageClient


def _snapshot(connection, settings, repository):
    with operation_guard(connection, repository, "pass"):
        with StoreSummaries(connection, settings).snapshot((repository,)) as snapshot:
            return snapshot._summaries, snapshot._current, snapshot._generated_stale, snapshot.resolver


@dataclass(frozen=True)
class RegenerationInputs:
    summary: object
    members: tuple[SelectionMember, ...]

    def verify(self, connection, settings, repository):
        """Guard both surviving selections and absent pins, including the target."""
        settings.require_current()
        scoped = replace(settings, values=_freeze({**settings.values,
            "repos": {name: {**value, "enabled": name == repository}
                      for name, value in settings.values["repos"].items()}}))
        catalog = SourceResolver.from_transaction(connection, scoped, guarded_repositories=(repository,))
        current = {member.chunk.identifier: member for file in catalog.files
                   for member in catalog._members(file, file.chunks)}
        current.update((chunk.identifier, SelectionMember(place, chunk)) for place, chunk in catalog.index)
        _, stale = _published(connection, catalog, current, repository)
        surviving = _summary_members(self.summary, current, catalog)
        members = tuple(member for _, member in surviving)
        # The mutation helper checks the exact old target before changing it;
        # final callbacks must also work after that target is replaced/deleted.
        if members != self.members:
            raise EvidenceError("inputs_changed")
        if any(member.chunk.identifier in stale for member in members if member.chunk.kind == "summary"):
            raise EvidenceError("stale_member")
        surviving_pins = {pin.chunk_id for pin, _ in surviving}
        missing = tuple(pin for pin in self.summary.state.members
                        if pin.chunk_id not in surviving_pins and pin.place.root != "index")
        if missing:
            observed = capture_repository(settings, repository)
            if not observed.deletion_safe:
                raise EvidenceError("inputs_changed")
            for pin in missing:
                matches = tuple(file for file in observed.disk.files if any(
                    alias.root == pin.place.root and alias.path == pin.place.path for alias in file.aliases))
                if any(file.parsed is not None and hasattr(file.parsed, "chunks")
                        and any(chunk.name == pin.place.name for chunk in file.parsed.chunks) for file in matches):
                    raise EvidenceError("inputs_changed")


def _release(connection, repository, invocation, leases):
    """Exact private ownership release does not wait for an ingest pass."""
    if not leases:
        return
    with _defer_cleanup_signals(), checked_store(connection), atomic_transaction(connection):
        for owner in leases:
            connection.execute("DELETE FROM public.mycel_evidence_owners WHERE id=%s AND repository=%s "
                "AND kind='summary_generation' AND invocation=%s", (owner, repository, invocation.id))
    leases.clear()
    try:
        with checked_store(connection), operation_guard(connection, repository, "pass"), atomic_transaction(connection):
            CollectionStore(connection).collect_evidence_in_transaction(repository)
    except MycelError as error:
        if error.code != "busy":
            raise


def regenerate_summary_set(connection, settings, repository, identity, *, activity=None,
                           writer=None, client=None, tokenizer=None, before_publish=None, _state=None):
    """Repair only the initial stale nodes, in ascending level and existing places.

    The caller retains the summary-operation and exact invocation guards. Each
    node refreshes its surviving original membership after lower publications;
    independent successful transactions survive later failures or interruption.
    """
    from ._summary_lifecycle import SummaryLifecycleStore
    policy = InvocationPolicy("summaries", action="regenerate")
    require_model_call(policy, "summary")
    command, prompts = summary_command(settings, operation="regenerate"), load_summary_prompts(settings)
    resolved_command = resolve_command(command, home=Path.home(), allow_path_search=True)
    executable_hash = sha256(Path(resolved_command[0]).read_bytes()).hexdigest()

    def configuration():
        try:
            settings.require_current()
            if (summary_command(settings, operation="regenerate") != command
                    or load_summary_prompts(settings) != prompts
                    or resolve_command(command, home=Path.home(), allow_path_search=True) != resolved_command
                    or sha256(Path(resolved_command[0]).read_bytes()).hexdigest() != executable_hash):
                raise EvidenceError("inputs_changed")
        except (OSError, MycelError):
            raise EvidenceError("inputs_changed") from None

    original, _, initial_stale, _ = _snapshot(connection, settings, repository)
    work = tuple(summary for summary in original if summary.member.chunk.identifier in initial_stale)
    evidence = GenerationEvidenceStore(connection)
    leases, cuts, failed, blocked = {}, {}, [], []
    written = deleted = 0
    stopped = None

    def reply(*, next_written=0, next_deleted=0):
        return summary_result_reply(repository, written=written + next_written, deleted=deleted + next_deleted,
            replaced=False, failed=failed, blocked=blocked, cut=tuple(cuts.values()), stopped=stopped)

    def remember():
        if _state is not None:
            _state["reply"] = reply()

    try:
        for planned in work:
            identifier, place = planned.member.chunk.identifier, planned.member.place
            try:
                configuration()
                summaries, current, stale, resolver = _snapshot(connection, settings, repository)
                summary = next((item for item in summaries if item.member.chunk.identifier == identifier), None)
                if summary is None or summary != planned:
                    raise EvidenceError("inputs_changed")
                if identifier not in stale:
                    continue
                members = tuple(member for _, member in _summary_members(summary, current, resolver))
                inputs = RegenerationInputs(summary, members)
                if len({member.chunk.identifier for member in members}) != len(members) or any(
                        not _request_member(member) or (member.chunk.kind == "summary" and
                        (member.chunk.identifier in stale or
                         int(member.place.name.split("/")[0]) >= summary.state.level)) for member in members):
                    raise EvidenceError("stale_member")
                mutation = SummaryLifecycleStore(connection, settings, identity, repository)

                def guard():
                    configuration()
                    inputs.verify(connection, settings, repository)

                if not members:
                    if before_publish is not None:
                        before_publish()
                    with _defer_cleanup_signals(), detection_guards(connection, settings, repository) as guards:
                        if guards.pending:
                            raise MycelError("busy", "Another invocation prevents this summary publication.")
                        with atomic_transaction(connection):
                            mutation.delete_in_transaction(summary, guarded_repositories=guards.writable, guard=guard)
                            if activity is not None:
                                activity.record_in_transaction(repository, "summaries_regenerate",
                                    AppliedMutation(True, reply(next_deleted=1)))
                            mutation.verify_in_transaction()
                        deleted += 1
                        remember()
                    continue
                sections = tuple(SummarySection(member, member.chunk.span[0] if member.chunk.span is not None else
                                                int(member.place.name.split("/")[1]))
                                 for member in members)
                requests = plan_summary_requests(sections, prompts)
                # A rebuild can split a larger group. Regeneration cannot add
                # places or silently omit any member of this existing summary.
                if len(requests) != 1:
                    raise EvidenceError("inputs_changed")
                request, = requests
                capture = capture_generation(repository,
                    tuple(GenerationMember(section.member, sent, section.member.place.address in request.cut,
                        position=section.position) for section, sent in zip(request.sections, request.sent_texts)),
                    request=request.request, instruction=prompts.instruction, task=prompts.task,
                    command=command, prompt_profile=prompts.profile)
                lease = evidence.retain(identity, capture)
                leases[lease.owner_id] = lease
                for address in request.cut:
                    cuts[address] = parse_source_address(address)
                configuration()
                if writer is None:
                    writer = SummaryWriter(command, settings.values["summaries"]["at_once"], before_launch=configuration)
                results = writer.write_many((request.request,))
                if len(results) != 1:
                    raise MycelError("internal", "The summary writer returned an incomplete regeneration.")
                result, = results
                if result.response is None:
                    failed.append({"summary": place.address, "reason": result.reason})
                    continue
                lease = evidence.retain_response(identity, lease, result.response)
                leases[lease.owner_id] = lease
                version = mutation.reserve_response(summary, lease)
                configuration()
                tokenizer = tokenizer or load_tokenizer(settings.values["embedding"]["model"])
                plan = plan_chunk(repository, identifier, str(version), result.response.decode("utf-8"),
                    kind="document", model=settings.values["embedding"]["model"],
                    dimensions=settings.values["embedding"]["dimensions"], tokenizer=tokenizer,
                    place_line=document_place_line(place.path, place.name))
                expected = {PartIdentity(repository, identifier, str(version), part.order) for part in plan.parts}
                writes, embedding_failures = {}, []

                def commit(values):
                    for value in values:
                        if (value.part not in expected or value.part in writes
                                or value.model != plan.model or value.dimensions != plan.dimensions):
                            raise MycelError("internal", "A regenerated summary vector has an invalid identity.")
                        writes[value.part] = value.vector
                    return CommitReceipt(tuple(value.part for value in values))

                def record_failures(values):
                    embedding_failures.extend(values)
                    return CommitReceipt(tuple(value.part for value in values))

                def embedding_guard():
                    try:
                        configuration()
                    except EvidenceError:
                        raise EmbeddingGuardFailure("invalid_input", "Summary inputs changed before embedding.") from None

                if client is None:
                    client = VoyageClient(Credentials(settings, policy), policy, tokenizer=tokenizer,
                        attempts=settings.values["embedding"]["attempts"], before_send=embedding_guard)
                progress = client.embed_repository(repository, plan_batches((plan,), tokenizer=tokenizer),
                    commit=commit, record_failures=record_failures)
                if progress.stopping_kind == "cancelled":
                    raise KeyboardInterrupt
                if progress.stopping_kind == "invalid_input":
                    raise EvidenceError("inputs_changed")
                if progress.stopping_kind or embedding_failures or set(writes) != expected:
                    failed.append({"summary": place.address, "reason": "embedding_failed"})
                    continue
                vectors = tuple(writes[PartIdentity(repository, identifier, str(version), part.order)] for part in plan.parts)
                if before_publish is not None:
                    before_publish()
                with _defer_cleanup_signals(), detection_guards(connection, settings, repository) as guards:
                    if guards.pending:
                        raise MycelError("busy", "Another invocation prevents this summary publication.")
                    with atomic_transaction(connection):
                        mutation.publish_in_transaction(summary, lease, plan, vectors,
                            guarded_repositories=guards.writable, guard=guard)
                        if activity is not None:
                            activity.record_in_transaction(repository, "summaries_regenerate",
                                AppliedMutation(True, reply(next_written=1)))
                        mutation.verify_in_transaction()
                    written += 1
                    remember()
            except EvidenceError as error:
                if error.status not in {"inputs_changed", "stale_member"}:
                    raise MycelError("store_format", "Summary generation evidence could not be validated.") from None
                blocked.append({"summary": place, "reason": error.status})
            finally:
                if written or deleted:
                    remember()
                _release(connection, repository, identity, leases)
        if failed or any(item["reason"] == "stale_member" for item in blocked):
            stopped = "failed"
        elif blocked:
            stopped = "inputs_changed"
    except KeyboardInterrupt:
        stopped = "interrupted"
    finally:
        try:
            _release(connection, repository, identity, leases)
        except KeyboardInterrupt:
            stopped = "interrupted"
    remember()
    return reply()


def regenerate_summaries(invocation, *, _store=None, _writer=None, _client=None, _tokenizer=None,
                         _before_publish=None):
    """Keep acknowledged publications in replies after late audit/close faults."""
    from ._cli import Result
    state = {}
    try:
        return _regenerate_summaries(invocation, _store=_store, _writer=_writer, _client=_client,
            _tokenizer=_tokenizer, _before_publish=_before_publish, _state=state)
    except (MycelError, KeyboardInterrupt) as error:
        if "reply" not in state:
            raise
        value = state["reply"]
        interrupted = isinstance(error, KeyboardInterrupt) or value.get("stopped") == "interrupted"
        fault = ({"code": "refused", "message": "Summary regeneration was stopped by the caller."}
                 if interrupted else error.to_dict()["error"])
        return Result({**value, "stopped": "interrupted" if interrupted else "failed",
                       "error": fault, "countsState": "committed_prefix"}, 2 if interrupted else 1)


def _regenerate_summaries(invocation, *, _store, _writer, _client, _tokenizer, _before_publish, _state):
    from ._cli import Result, invocation_store
    from ._summary_store import summary_repository
    settings = invocation.settings
    repository = summary_repository(settings, invocation.repositories)
    command = summary_command(settings, operation="regenerate")
    resolve_command(command, home=Path.home(), allow_path_search=True)
    with ExitStack() as stack:
        connection, _ = (_store if _store is not None else
            stack.enter_context(invocation_store(invocation, operation="embed")))
        stack.enter_context(checked_store(connection, dimensions=settings.values["embedding"]["dimensions"], operation="embed"))
        stack.enter_context(operation_guard(connection, repository, "summaries"))
        build = current_build()
        activity = None if build is None else stack.enter_context(MutationActivity(connection, build=build).session())
        identity = activity.invocation if activity is not None else stack.enter_context(invocation_guard(connection))
        value = regenerate_summary_set(connection, settings, repository, identity, activity=activity,
            writer=_writer, client=_client, tokenizer=_tokenizer, before_publish=_before_publish, _state=_state)
        stopped = value.get("stopped")
        if activity is not None:
            activity.finish("stopped" if stopped == "interrupted" else "failed" if stopped else "done",
                error={"code": "refused", "message": "Summary regeneration did not complete."} if stopped else None,
                counts={(repository, "summaries_regenerate"): value})
        return Result(value, 2 if stopped == "interrupted" else int(bool(stopped)))
