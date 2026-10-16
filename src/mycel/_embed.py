"""Finite scoped embedding over retained exact text, with offline dry runs."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import replace
from ._activity import MutationActivity
from ._embedding_plan import code_place_line, document_place_line, _provenance
from ._embedding_store import EmbeddingContext, EmbeddingStore, _counts
from ._errors import MycelError
from ._locks import snapshot_transaction
from ._markdown import MarkdownDecodeError, split_markdown
from ._scope import RepositoryLocations
from ._settings import load_settings
from ._resolver import require_read_transaction
from ._store import exact_bytes
from ._voyage import EmbeddingGuardFailure, VoyageClient


_CONTEXTS_SQL = """SELECT v.id,c.kind,l.metadata,fl.metadata,f.path,fv.source_bytes
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
JOIN public.mycel_locations l ON l.chunk_version=v.id
LEFT JOIN public.mycel_file_locations fl ON fl.id=l.file_location
LEFT JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=c.file_id
LEFT JOIN public.mycel_files f ON f.id=fv.file_id
WHERE c.repository=%s ORDER BY v.id,
CASE l.kind WHEN 'disk' THEN 0 WHEN 'branch' THEN 1 WHEN 'stash' THEN 2 ELSE 3 END,
COALESCE(fl.metadata->>'root',''),COALESCE(fl.metadata->>'path',f.path,''),l.location,l.id"""


def retained_contexts(connection, repository: str, *, in_snapshot=False):
    """Capture a finite inventory and deterministic place metadata from ingest.

    Document paths come from their owning location, and full heading paths
    come from that location's exact retained file bytes and original span.
    No checkout, branch, stash or provider is read by this operation.
    """
    if in_snapshot:
        require_read_transaction(connection)
    with nullcontext() if in_snapshot else snapshot_transaction(connection):
        rows = connection.execute(_CONTEXTS_SQL, (repository,)).fetchall()
    contexts, documents = {}, {}
    for version, chunk_kind, metadata, file_metadata, path, source in rows:
        if version in contexts:
            continue
        located_kind = metadata.get('kind', chunk_kind) if isinstance(metadata, dict) else chunk_kind
        kind = "document" if located_kind in {"document", "summary", "overview"} else "code"
        try:
            path = (file_metadata or {}).get("path", path)
            if located_kind in {'summary', 'overview'}:
                if file_metadata is not None or path is not None:
                    raise ValueError('A generated index chunk must have no file')
                place = document_place_line(metadata['path'], (metadata['name'],))
            elif kind == "document":
                raw = exact_bytes(source)
                if raw not in documents:
                    documents[raw] = split_markdown(raw)
                span = metadata["span"]
                matches = tuple(chunk for chunk in documents[raw].chunks
                                if (chunk.span.byte_start, chunk.span.byte_end) == (span["start"], span["end"]))
                if len(matches) != 1:
                    raise ValueError("No exact retained section span")
                place = document_place_line(path, matches[0].heading_path)
            else:
                place = code_place_line(path, metadata["name"], metadata.get("kind", chunk_kind))
        except (KeyError, TypeError, ValueError, MarkdownDecodeError, MycelError):
            # Missing/invalid place metadata is a local planning failure for
            # this exact version. It cannot erase its complete retained text.
            place = ""
        contexts[version] = EmbeddingContext(place, kind)
    return contexts, frozenset(str(version) for version in contexts)


def _selection(invocation):
    from ._cli import repository_result
    locations = RepositoryLocations(invocation.settings)
    selected, errors = {}, {}
    if invocation.repositories:
        for name in invocation.repositories:
            try:
                for repository in locations.named(name):
                    selected.setdefault(repository.name, repository)
            except MycelError as error:
                errors[name] = {"error": error.to_dict()["error"]}
    else:
        selected = {repository.name: repository for repository in
                    locations.resolve_scope(all_repositories=invocation.all_repositories)}
    for name, repository in tuple(selected.items()):
        if not repository.enabled:
            errors[name] = {"error": {"code": "refused", "message": "The embedding repository is disabled in settings."}}
            del selected[name]
    if not selected:
        return (), errors, repository_result([{"repository": name, **error} for name, error in errors.items()], started=False)
    return tuple(selected), errors, None


def _summary(prepared, initial=None, *, sent_parts=0, discarded=0):
    before_complete = set() if initial is None else {value.version.version for value in initial.versions if value.complete}
    captured = set() if initial is None else {value.version.version for value in initial.versions}
    sent = sum(value.complete and value.version.version in captured and value.version.version not in before_complete
               for value in prepared.versions)
    counts = prepared.counts
    return {"sent": sent, "embedded": counts.embedded_versions, "pending": counts.pending_versions,
            "failed": counts.failed_versions, "deferred": counts.deferred_versions,
            "parts": {"sent": sent_parts, "embedded": counts.embedded_parts, "pending": counts.pending_parts,
                      "failed": counts.failed_parts, "deferred": counts.deferred_parts, "discarded": discarded},
            "obsoleteReceipts": prepared.obsolete_receipts, "obsoleteParts": prepared.obsolete_parts}


def _estimate(prepared):
    selection = []
    selected_inputs = {}
    for batch in prepared.batches:
        for item in batch.inputs:
            selected_inputs.setdefault(item.chunk_version, []).append(item)
    for version in prepared.versions:
        selected = selected_inputs.get(version.version.version, ())
        if selected:
            parts = {part.order: part for part in version.plan.parts}
            selection.append({"chunk": version.version.chunk_id, "version": version.version.version,
                "placeLine": version.plan.place_line,
                "parts": [{"order": item.part_order, "startByte": parts[item.part_order].start_byte,
                           "endByte": parts[item.part_order].end_byte,
                           "submittedTokens": parts[item.part_order].submitted_tokens,
                           "tokens": parts[item.part_order].planning_tokens} for item in selected]})
    failures = [{"chunk": version.version.chunk_id, "version": version.version.version,
                 "error": dict(version.failure)} for version in prepared.versions if version.failure is not None]
    return {**prepared.estimate, "selection": selection, "planningFailures": failures}


def _eligible_now(settings, repository):
    current = load_settings(path=settings.file, home=settings._home)
    return (current.valid and current.values["repos"].get(repository, {}).get("enabled") is True
            and current.values["embedding"]["model"] == settings.values["embedding"]["model"]
            and current.values["embedding"]["dimensions"] == settings.values["embedding"]["dimensions"])


def _committed_prefix(writer, prepared):
    """Project acknowledged transactions if a final store read is unavailable."""
    from ._voyage import PartIdentity
    versions = []
    staged = (set(prepared.staged) | writer.staged_parts) - writer.published.keys() - writer.discarded
    for value in prepared.versions:
        parts = []
        deleted = False
        for part in value.parts:
            identity = PartIdentity(value.version.repository, value.version.chunk_id, value.version.version, part.part.order)
            if identity in writer.discarded:
                deleted = True
                break
            published = writer.published.get(identity)
            parts.append(part if published is None else replace(part, vector=published.vector, failure=published.failure))
        if not deleted:
            versions.append(replace(value, parts=tuple(parts)))
    return replace(prepared, versions=tuple(versions), staged=tuple(staged),
                   counts=_counts(versions, eligible=prepared.eligible, staged=frozenset(staged)))


def embed(invocation, *, _store=None, _activity=None):
    """Retain already acknowledged progress even if final cleanup loses SQL."""
    from ._cli import Result
    state = {}
    try:
        return _embed(invocation, state, _store=_store, _activity=_activity)
    except (MycelError, KeyboardInterrupt) as error:
        if not state.get("started"):
            raise
        reply = state["reply"]
        interrupted = isinstance(error, KeyboardInterrupt)
        fault = ({"code": "refused", "message": "Embedding was stopped by the caller."} if interrupted
                 else error.to_dict()["error"])
        for repository in state["selected"]:
            reply["repositories"].setdefault(repository, {"error": fault})
        reply["error"] = fault
        reply["stopped"] = "interrupted" if interrupted else "gave_up"
        return Result(reply, 2 if interrupted else 1)


def _embed(invocation, state, *, _store=None, _activity=None):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store, repository_result
    from ._credentials import Credentials
    from ._safeguards import InvocationPolicy

    arguments = invocation.arguments
    if len(set(arguments)) != len(arguments) or any(arg not in {"--dry-run", "--retry-failed"} for arg in arguments):
        raise MycelError("invalid_input", "Use mycel embed [--repo <name> | --all] [--dry-run] [--retry-failed].")
    dry_run, retry_failed = "--dry-run" in arguments, "--retry-failed" in arguments
    selected, repositories, refusal = _selection(invocation)
    if refusal is not None:
        return refusal
    state["selected"] = selected
    policy = InvocationPolicy(invocation.command, dry_run=dry_run, embed=invocation.command == 'ingest')
    stopped = None
    with ExitStack() as stack:
        connection, inspection = (_store if _store is not None else
            stack.enter_context(invocation_store(invocation, operation="read" if dry_run else "embed")))

        def store_guard():
            row = connection.execute("SELECT index_generation FROM public.mycel_store WHERE singleton=true").fetchone()
            if row is None or str(row[0]) != inspection.index_generation:
                raise MycelError("store_format", "The index generation changed during embedding.")

        def current_guard():
            try:
                invocation.settings.require_current()
            except MycelError:
                raise EmbeddingGuardFailure("invalid_input", "The settings changed during embedding.") from None
            store_guard()

        build = None if dry_run else current_build()
        activity = _activity if _store is not None else None if build is None else MutationActivity(connection, build=build)
        if activity is not None and _store is None:
            stack.enter_context(activity.session())
        writer = EmbeddingStore(connection, invocation.settings, activity=activity,
            input_guard=current_guard, store_guard=store_guard)
        provenance = _provenance(writer.tokenizer)
        reply = {"model": writer.model, "dimensions": writer.dimensions,
                 "planner": {"version": provenance.planner_version, "tokenizerRevision": provenance.tokenizer_revision,
                             "tokenizerSha256": provenance.tokenizer_sha256}, "repositories": repositories}
        state["reply"] = reply
        # Acquisition remains lazy. Construct no provider or embedding
        # credential object at all for a read-only dry run.
        client = None if dry_run else VoyageClient(Credentials(invocation.settings, policy), policy,
            tokenizer=writer.tokenizer, attempts=invocation.settings.values["embedding"]["attempts"],
            before_send=current_guard)
        for repository in selected:
            try:
                contexts, captured = retained_contexts(connection, repository)
                initial = writer.prepare(repository, contexts=contexts, _captured=captured)
                selected_plan = (writer.prepare(repository, contexts=contexts, _captured=captured, retry_failed=True)
                                 if dry_run and retry_failed else initial)
            except MycelError as error:
                repositories[repository] = {"error": error.to_dict()["error"]}
                continue
            except KeyboardInterrupt:
                if not state.get("started"):
                    raise
                stopped = "interrupted"
                repositories[repository] = {"error": {"code": "refused", "message": "Embedding was stopped by the caller."}}
                continue
            state["started"] = True
            if dry_run:
                repositories[repository] = {**_summary(initial), "estimate": _estimate(selected_plan)}
                continue
            error = None
            progress = None
            prepared = initial
            try:
                if stopped == "interrupted":
                    raise MycelError("refused", "Embedding was stopped by the caller.")
                with writer.session(repository):
                    prepared = writer.prepare(repository, contexts=contexts, persist=True,
                                              retry_failed=retry_failed, _captured=captured)
                    progress = client.embed_repository(repository, prepared.batches,
                        commit=writer.commit, record_failures=writer.record_failures)
                    if progress.stopping_kind:
                        code = progress.stopping_kind if progress.stopping_kind in {
                            "busy", "store_unavailable", "store_format", "invalid_input", "refused"} else "refused"
                        error = {"code": code, "message": progress.stopping_reason}
                        stopped = "interrupted" if progress.stopping_kind == "cancelled" else stopped or "gave_up"
            except KeyboardInterrupt:
                stopped = "interrupted"
                error = {"code": "refused", "message": "Embedding was stopped by the caller."}
            except MycelError as failure:
                error = failure.to_dict()["error"]
                stopped = stopped or "gave_up"
            # Recount the complete current retained inventory. Concurrently
            # added versions stay pending and were never added to this send.
            stale_counts = False
            try:
                final_contexts, final_inventory = retained_contexts(connection, repository)
                final = writer.prepare(repository, contexts=final_contexts, _captured=final_inventory)
            except (MycelError, KeyboardInterrupt) as failure:
                final = _committed_prefix(writer, prepared)
                if isinstance(failure, KeyboardInterrupt):
                    stopped = "interrupted"
                    error = {"code": "refused", "message": "Embedding was stopped by the caller."}
                else:
                    error = failure.to_dict()["error"]
                    stopped = stopped or "gave_up"
                stale_counts = True
            try:
                eligible = _eligible_now(invocation.settings, repository)
            except KeyboardInterrupt:
                stopped = "interrupted"
                error = {"code": "refused", "message": "Embedding was stopped by the caller."}
                eligible = final.eligible
                stale_counts = True
            if not eligible:
                final = replace(final, eligible=False,
                    counts=_counts(final.versions, eligible=False, staged=frozenset(final.staged)))
            mutations = writer.mutations.get(repository, {})
            result = _summary(final, initial, sent_parts=mutations.get("sent", 0),
                              discarded=mutations.get("discarded", 0))
            if progress is not None:
                result["requests"] = progress.requests
                result["submittedInputs"] = progress.submitted_inputs
                result["providerTokens"] = progress.provider_tokens
            if error is not None:
                result["error"] = error
            if stale_counts:
                result["countsState"] = "committed_prefix"
            repositories[repository] = result
        if not state.get("started"):
            return repository_result([{"repository": name, **result} for name, result in repositories.items()],
                                     started=False)
        failures = [value["error"] for value in repositories.values() if "error" in value]
        failed = bool(failures or any(value.get("failed", 0) for value in repositories.values()))
        if dry_run:
            names = ("versions", "parts", "tokens", "planningFailed")
            reply["estimate"] = {name: sum(value.get("estimate", {}).get(name, 0) for value in repositories.values()) for name in names}
        if stopped is not None:
            reply["stopped"] = stopped
        if activity is not None and _store is None:
            outcome = "stopped" if stopped == "interrupted" else "failed" if failed else "done"
            final_error = None if outcome == "done" else (failures[0] if failures else
                          {"code": "refused", "message": "Selected embedding inputs have recorded failures."})
            final_counts = {(name, "embed"): repositories[name] for name in selected}
            try:
                activity.finish(outcome, error=final_error, counts=final_counts)
            except KeyboardInterrupt:
                stopped = "interrupted"
                reply["stopped"] = stopped
                final_error = {"code": "refused", "message": "Embedding was stopped by the caller."}
                activity.finish("stopped", error=final_error, counts=final_counts)
        return Result(reply, 2 if stopped == "interrupted" else int(failed))
