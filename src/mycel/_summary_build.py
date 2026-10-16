"""Explicit finite summary trees: private levels, then one guarded replacement."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from ._activity import AppliedMutation, MutationActivity
from ._build_identity import current_build
from ._capture import capture_repository
from ._credentials import Credentials
from ._embedding_plan import document_place_line, load_tokenizer, plan_batches, plan_chunk
from ._errors import MycelError
from ._evidence import EvidenceError
from ._locks import atomic_transaction, invocation_guard, operation_guard
from ._resolver import SourceResolver
from ._safeguards import InvocationPolicy, require_model_call, resolve_command, _defer_cleanup_signals
from ._source_refs import SourceAddress, parse_source_address
from ._staleness import detection_guards
from ._store import checked_store
from ._summary_evidence import GenerationMember, capture_generation
from ._summary_grouping import (GROUPING_PROFILE, MAX_LEVELS, TOP_NODES, SummaryNode,
    group_summary_nodes, mean_vector, numerical_versions)
from ._summary_request import SummarySection, load_summary_prompts, plan_summary_requests, summary_command
from ._summary_store import StoreSummaries, SummarySetMetadata, summary_result_reply
from ._summary_writer import SummaryWriter
from ._voyage import CommitReceipt, EmbeddingGuardFailure, PartIdentity, VoyageClient


@dataclass(frozen=True)
class BuildInputs:
    sections: tuple
    vectors: object
    files: tuple
    not_embedded: int

    @classmethod
    def capture(cls, connection, settings, repository):
        with operation_guard(connection, repository, "pass"):
            with StoreSummaries(connection, settings).snapshot((repository,)) as snapshot:
                selected = {section.member.chunk.identifier for section in snapshot.sections}
                files = tuple(file for file in snapshot.resolver.files if file.repository == repository
                    and any(chunk.identifier in selected for chunk in file.chunks))
                result = cls(snapshot.sections, snapshot._vectors, files, snapshot.not_embedded)
            return result

    @staticmethod
    def signature(sections, vectors, not_embedded):
        return (tuple((section.member, section.position) for section in sections),
                tuple((section.member.chunk.identifier, vectors[section.member.chunk.identifier])
                      for section in sections), not_embedded)

    def physical(self, settings, repository):
        if not self.files:
            return
        observed = capture_repository(settings, repository)
        if not observed.deletion_safe:
            raise EvidenceError("inputs_changed")
        for file in self.files:
            expected = sorted((alias.root, alias.path) for alias in file.aliases)
            actual = [source for source in observed.disk.files if any(
                (alias.root, alias.path) in expected for alias in source.aliases)]
            if (len(actual) != 1 or actual[0].source != file.source
                    or sorted((alias.root, alias.path) for alias in actual[0].aliases) != expected):
                raise EvidenceError("inputs_changed")

    def verify(self, connection, settings, repository):
        from ._summary_store import summary_inputs
        catalog = SourceResolver.from_transaction(connection, settings, guarded_repositories=(repository,))
        sections, not_embedded, vectors = summary_inputs(connection, catalog, settings, repository)
        if self.signature(sections, vectors, not_embedded) != self.signature(
                self.sections, self.vectors, self.not_embedded):
            raise EvidenceError("inputs_changed")
        self.physical(settings, repository)


def _level_requests(nodes, prompts):
    """Canonical real request parts; statistical singletons move up unchanged."""
    requests, promoted = [], {}
    for group in group_summary_nodes(nodes):
        if len(group) == 1:
            promoted.setdefault(group[0].key, group[0])
        else:
            requests.extend(plan_summary_requests(tuple(node.section for node in group), prompts))
    requests.sort(key=lambda request: tuple(section.order for section in request.sections))
    return tuple(requests), tuple(sorted(promoted.values(), key=lambda node: node.order))


def build_summary_tree(connection, settings, repository, identity, *, activity=None,
                       writer=None, client=None, tokenizer=None, before_publish=None):
    """Caller retains summary-operation/removal/liveness guards until cleanup.

    Tests inject the same writer/client interfaces with local stand-ins. No
    product row is staged before the final transaction, including lower levels.
    """
    from ._summary_publication import SummaryPublicationStore, StagedSummaryEmbedding
    policy = InvocationPolicy("summaries", action="build")
    require_model_call(policy, "summary")
    command, prompts = summary_command(settings, operation="build"), load_summary_prompts(settings)
    resolved_command = resolve_command(command, home=Path.home(), allow_path_search=True)
    executable_hash = sha256(Path(resolved_command[0]).read_bytes()).hexdigest()

    def configuration():
        try:
            settings.require_current()
            if (summary_command(settings, operation="build") != command
                    or load_summary_prompts(settings) != prompts
                    or resolve_command(command, home=Path.home(), allow_path_search=True) != resolved_command
                    or sha256(Path(resolved_command[0]).read_bytes()).hexdigest() != executable_hash):
                raise EvidenceError("inputs_changed")
        except OSError:
            raise EvidenceError("inputs_changed") from None
        except MycelError:
            raise EvidenceError("inputs_changed") from None

    inputs = BuildInputs.capture(connection, settings, repository)
    versions = numerical_versions()
    metadata = SummarySetMetadata(datetime.now(timezone.utc).isoformat(), GROUPING_PROFILE,
                                  current_build(), versions)
    store = SummaryPublicationStore(connection, settings, identity, repository)
    staged, cuts, failures = [], {}, []
    published = False
    reply = None
    try:
        inputs.physical(settings, repository)
        current = tuple(SummaryNode(section.member.chunk.identifier, section.member.place, section.position,
            mean_vector(inputs.vectors[section.member.chunk.identifier]), section) for section in inputs.sections)
        for level in range(1, MAX_LEVELS + 1):
            if len(current) <= TOP_NODES:
                break
            requests, promoted = _level_requests(current, prompts)
            if not requests:
                break
            leases = []
            for request in requests:
                configuration()
                capture = capture_generation(repository,
                    tuple(GenerationMember(section.member, sent, section.member.place.address in request.cut,
                                           position=section.member.chunk.span[0]
                                               if section.member.chunk.span is not None else section.position)
                          for section, sent in zip(request.sections, request.sent_texts)),
                    request=request.request, instruction=prompts.instruction, task=prompts.task,
                    command=command, prompt_profile=prompts.profile)
                leases.append(store.retain_request(capture))
                for address in request.cut:
                    cuts[address] = parse_source_address(address)
            configuration()
            if writer is None:
                writer = SummaryWriter(command, settings.values["summaries"]["at_once"],
                                       before_launch=configuration)
            results = writer.write_many(tuple(request.request for request in requests))
            if len(results) != len(requests):
                raise MycelError("internal", "The summary writer returned an incomplete level.")
            pending = []
            for ordinal, (request, lease, result) in enumerate(zip(requests, leases, results), 1):
                place = SourceAddress(repository, "index", "summaries", f"{level}/{ordinal}")
                if result.response is None:
                    failures.append({"summary": place.address, "reason": result.reason})
                else:
                    pending.append(store.stage_response(lease, result.response, place=place, level=level))
            if failures:
                reply = summary_result_reply(repository, written=0, deleted=0, replaced=False,
                    failed=failures, cut=tuple(cuts.values()), stopped="failed")
                break
            configuration()
            tokenizer = tokenizer or load_tokenizer(settings.values["embedding"]["model"])
            plans = tuple(plan_chunk(repository, item.member.chunk.identifier, str(item.member.chunk.version),
                item.member.chunk.source.decode("utf-8"), kind="document", model=settings.values["embedding"]["model"],
                dimensions=settings.values["embedding"]["dimensions"], tokenizer=tokenizer,
                place_line=document_place_line("summaries", (item.member.place.name,))) for item in pending)
            writes, embedding_failures = {}, []
            expected = {PartIdentity(repository, plan.chunk_id, plan.chunk_version, part.order)
                        for plan in plans for part in plan.parts}

            def commit(values):
                for value in values:
                    if (value.part not in expected or value.part in writes
                            or value.model != settings.values["embedding"]["model"]
                            or value.dimensions != settings.values["embedding"]["dimensions"]):
                        raise MycelError("internal", "A staged summary vector has an invalid identity.")
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
            progress = client.embed_repository(repository, plan_batches(plans, tokenizer=tokenizer),
                                              commit=commit, record_failures=record_failures)
            if progress.stopping_kind == "cancelled":
                raise KeyboardInterrupt
            if progress.stopping_kind == "invalid_input":
                raise EvidenceError("inputs_changed")
            if progress.stopping_kind or embedding_failures or set(writes) != expected:
                failures.extend({"summary": item.member.place.address, "reason": "embedding_failed"}
                    for item, plan in zip(pending, plans) if any(PartIdentity(repository, plan.chunk_id,
                        plan.chunk_version, part.order) not in writes for part in plan.parts))
                if not failures:
                    failures = [{"summary": item.member.place.address, "reason": "embedding_failed"} for item in pending]
                reply = summary_result_reply(repository, written=0, deleted=0, replaced=False,
                    failed=failures, cut=tuple(cuts.values()), stopped="failed")
                break
            output = list(promoted)
            for item, plan in zip(pending, plans):
                vectors = tuple(writes[PartIdentity(repository, plan.chunk_id, plan.chunk_version, part.order)]
                                for part in plan.parts)
                staged.append(StagedSummaryEmbedding(item, plan, vectors))
                section = SummarySection(item.member, int(item.member.place.name.split("/")[1]))
                output.append(SummaryNode(item.member.chunk.identifier, item.member.place, section.position,
                                          mean_vector(vectors), section))
            current = tuple(sorted(output, key=lambda node: node.order))
        if reply is None:
            if before_publish is not None:
                before_publish()

            def guard():
                configuration()
                inputs.verify(connection, settings, repository)

            # A late signal cannot fall between commit acknowledgement and the
            # in-memory outcome/lease transition and misreport a committed tree.
            with _defer_cleanup_signals(), detection_guards(connection, settings, repository) as guards:
                if guards.pending:
                    raise MycelError("busy", "Another invocation prevents this summary publication.")
                with atomic_transaction(connection):
                    guard()
                    store.publish_in_transaction(tuple(staged), metadata=metadata,
                        guarded_repositories=guards.writable, guard=guard)
                    reply = summary_result_reply(repository, written=len(staged), deleted=0, replaced=True,
                                                 cut=tuple(cuts.values()))
                    reply["notEmbedded"] = inputs.not_embedded
                    if activity is not None:
                        activity.record_in_transaction(repository, "summaries_build", AppliedMutation(True, reply))
                    guard()
                    store.verify_in_transaction()
                    store.release_in_transaction()
                published = True
                store.confirm_release()
    except EvidenceError as error:
        if error.status not in {"inputs_changed", "stale_member"}:
            raise MycelError("store_format", "Summary generation evidence could not be validated.") from None
        reply = summary_result_reply(repository, written=0, deleted=0, replaced=False,
                                     cut=tuple(cuts.values()), stopped="inputs_changed")
    except KeyboardInterrupt:
        if not published:
            reply = summary_result_reply(repository, written=0, deleted=0, replaced=False,
                                         cut=tuple(cuts.values()), stopped="interrupted")
    finally:
        store.release()
    reply["notEmbedded"] = inputs.not_embedded
    if activity is not None and not published:
        with operation_guard(connection, repository, "pass"), atomic_transaction(connection):
            activity.record_in_transaction(repository, "summaries_build", AppliedMutation(False, reply))
    return reply


def build_summaries(invocation, *, _store=None, _writer=None, _client=None, _tokenizer=None,
                    _before_publish=None):
    from ._cli import Result, invocation_store
    from ._summary_store import summary_repository
    settings = invocation.settings
    repository = summary_repository(settings, invocation.repositories)
    command = summary_command(settings, operation="build")
    resolve_command(command, home=Path.home(), allow_path_search=True)
    with ExitStack() as stack:
        connection, _ = (_store if _store is not None else
            stack.enter_context(invocation_store(invocation, operation="embed")))
        stack.enter_context(checked_store(connection, dimensions=settings.values["embedding"]["dimensions"],
                                          operation="embed"))
        stack.enter_context(operation_guard(connection, repository, "summaries"))
        build = current_build()
        activity = None if build is None else stack.enter_context(MutationActivity(connection, build=build).session())
        identity = activity.invocation if activity is not None else stack.enter_context(invocation_guard(connection))
        reply = build_summary_tree(connection, settings, repository, identity, activity=activity,
            writer=_writer, client=_client, tokenizer=_tokenizer, before_publish=_before_publish)
        stopped = reply.get("stopped")
        if activity is not None:
            activity.finish("done" if reply["replaced"] else "stopped" if stopped == "interrupted" else "failed",
                error=None if reply["replaced"] else {"code": "refused", "message": "Summary build did not publish."},
                counts={(repository, "summaries_build"): reply})
        return Result(reply, 2 if stopped == "interrupted" else int(not reply["replaced"]))
