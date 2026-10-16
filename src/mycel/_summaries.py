"""Explicit summary-generation staging for later tree/publication consumers."""

from dataclasses import dataclass

from ._errors import MycelError
from ._locks import InvocationIdentity
from ._safeguards import InvocationPolicy, require_model_call
from ._settings import SettingsSnapshot
from ._summary_evidence import (GenerationEvidenceStore, GenerationLease,
    GenerationMember, capture_generation)
from ._summary_request import (SummaryRequest, SummarySection,
    load_summary_prompts, plan_summary_requests, summary_command)
from ._summary_writer import SummaryWriter, WriterResult


def handle_summaries(invocation):
    """Dispatch stored plans and explicit summary lifecycle commands."""
    from ._cli import Result, invocation_store
    from ._summary_store import StoreSummaries, summary_repository
    if invocation.settings is None:
        raise MycelError("internal", "Settings were not loaded for this invocation.")
    arguments = invocation.arguments
    dry_run = "--dry-run" in arguments
    actions = tuple(argument for argument in arguments if argument != "--dry-run")
    if (actions not in {(), ("status",), ("build",), ("regenerate",), ("remove",)}
            or arguments.count("--dry-run") > 1 or invocation.all_repositories):
        raise MycelError("invalid_input", "Use summaries status, build, regenerate or remove for one repository.")
    action = actions[0] if actions else "status"
    if dry_run and action not in {"build", "regenerate"}:
        raise MycelError("invalid_input", "Only summaries build and regenerate accept --dry-run.")
    repository = summary_repository(invocation.settings, invocation.repositories)
    summary_command(invocation.settings, operation=action, dry_run=dry_run)
    if action == "build" and not dry_run:
        from ._summary_build import build_summaries
        return build_summaries(invocation)
    if action == "regenerate" and not dry_run:
        from ._summary_regenerate import regenerate_summaries
        return regenerate_summaries(invocation)
    if action == "remove":
        from pathlib import Path
        from ._safeguards import resolve_command
        configured = invocation.settings.values["summaries"].get("command")
        if configured:
            resolve_command(configured, home=Path.home(), allow_path_search=True)
        from ._summary_lifecycle import remove_summaries
        return remove_summaries(invocation)
    with invocation_store(invocation) as (connection, _):
        with StoreSummaries(connection, invocation.settings).snapshot((repository,)) as snapshot:
            reply = {"status": snapshot.status, "build": snapshot.build_plan,
                     "regenerate": snapshot.regeneration_plan}[action]()
    return Result(reply)


@dataclass(frozen=True)
class GeneratedSummary:
    request: SummaryRequest
    result: WriterResult
    evidence: GenerationLease

    def report(self):
        return {**self.request.report(), "attempts": self.result.attempts,
                "failure": self.result.reason, "manifest": self.evidence.manifest_hash}


def generate_summary_requests(settings: SettingsSnapshot, sections: tuple[SummarySection, ...], *,
                              operation: str, invocation: InvocationIdentity,
                              evidence_store: GenerationEvidenceStore) -> tuple[GeneratedSummary, ...]:
    """Retain all exact requests before entering the configured paid boundary.

    No searchable text, generated edge or activity is published by this stage.
    The owning operation keeps the invocation lease live and later transfers
    or releases its evidence together with its own publication/discard work.
    """
    require_model_call(InvocationPolicy("summaries", action=operation), "summary")
    command = summary_command(settings, operation=operation)
    prompts = load_summary_prompts(settings)
    requests = plan_summary_requests(sections, prompts)
    if not isinstance(evidence_store, GenerationEvidenceStore) or not isinstance(invocation, InvocationIdentity):
        raise MycelError("invalid_input", "Summary generation requires its owning invocation and evidence store.")
    writer = SummaryWriter(command, settings.values["summaries"]["at_once"])
    captures = tuple(capture_generation(request.sections[0].member.place.repository,
        tuple(GenerationMember(section.member, sent, section.member.place.address in request.cut,
                               position=section.position)
              for section, sent in zip(request.sections, request.sent_texts)),
        request=request.request, instruction=prompts.instruction, task=prompts.task,
        command=command, prompt_profile=prompts.profile) for request in requests)
    settings.require_current()
    leases = tuple(evidence_store.retain(invocation, capture) for capture in captures)
    settings.require_current()
    current_prompts = load_summary_prompts(settings)
    if current_prompts != prompts:
        raise MycelError("settings", "The summary instruction/task changed before generation.")
    results = writer.write_many(tuple(request.request for request in requests))
    completed = []
    for request, lease, result in zip(requests, leases, results):
        if result.response is not None:
            lease = evidence_store.retain_response(invocation, lease, result.response)
        completed.append(GeneratedSummary(request, result, lease))
    return tuple(completed)
