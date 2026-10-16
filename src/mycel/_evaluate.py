"""Explicit evaluation dispatch with normal read-only retrieval integration."""

from pathlib import Path

from ._cli import Result
from ._errors import MycelError
from ._scope import RepositoryLocations


def evaluate(invocation, *, query_vectors=None, retrieval=None, drift=None):
    from ._build_identity import current_build
    from ._evaluation import empty_retrieval_report, load_evaluation_file, run_retrieval_evaluation
    if invocation.settings is None:
        raise MycelError("internal", "Settings were not loaded for this invocation.")
    if (invocation.all_repositories or len(invocation.repositories) > 1
            or tuple(invocation.arguments) not in {("--kind", "retrieval"),
                ("--kind", "drift"), ("--kind", "drift", "--live")}):
        raise MycelError("invalid_input", "Evaluation takes one repository and an explicitly selected supported kind.")
    kind = invocation.arguments[1]
    live = "--live" in invocation.arguments
    locations = RepositoryLocations(invocation.settings)
    if invocation.repositories:
        name = invocation.repositories[0]
        if name in invocation.settings.values["organizations"]:
            raise MycelError("invalid_input", "Evaluation takes one repository, not an organization.")
        repository = locations.named(name)[0]
    else:
        selected = locations.resolve_scope()
        if len(selected) != 1:
            raise MycelError("invalid_input", "Evaluation takes one repository, not an organization.")
        repository = selected[0]
        current = Path.cwd().resolve()
        if not any(current.is_relative_to(folder.path.resolve())
                   for folder in (repository.code, repository.documents) if folder is not None):
            raise MycelError("invalid_input", "Evaluation takes one repository, not an organization.")
    if not repository.enabled:
        raise MycelError("refused", "Evaluation requires an enabled repository.")
    repository.require_folders()
    if repository.documents is None or "evaluation" not in repository.settings:
        raise MycelError("settings", f"Repository {repository.name!r} needs a configured evaluation file in its artifact_root.")
    # Validate the whole file, including the unselected section, before calls.
    suite = load_evaluation_file(repository.documents.path / repository.settings["evaluation"])
    number = current_build()
    build = "development" if number is None else format(number, "x")
    if kind == "retrieval":
        if not suite.queries and (query_vectors is None or retrieval is None):
            from ._search_reply import SEARCH_REPLY
            report = empty_retrieval_report(suite, repository=repository.name, build=build,
                model=invocation.settings.values["embedding"]["model"], search_reply=SEARCH_REPLY)
        elif query_vectors is None or retrieval is None:
            from ._cli import invocation_store
            from ._evaluation_store import NormalQueryVectors, StoreRetrieval
            with invocation_store(invocation) as (connection, inspection):
                vectors = (NormalQueryVectors(invocation.settings, store_dimensions=inspection.dimensions)
                           if query_vectors is None else query_vectors)
                producer = StoreRetrieval(connection, invocation.settings) if retrieval is None else retrieval
                report = run_retrieval_evaluation(suite, repository=repository.name, build=build,
                    model=invocation.settings.values["embedding"]["model"],
                    query_vectors=vectors, retrieval=producer)
        else:
            report = run_retrieval_evaluation(suite, repository=repository.name, build=build,
                model=invocation.settings.values["embedding"]["model"],
                query_vectors=query_vectors, retrieval=retrieval)
    elif not suite.drifts and drift is None:
        report = _empty_drift(suite, repository.name, build, live)
    elif drift is None:
        from ._evaluation_drift import run_drift_evaluation
        report = run_drift_evaluation(suite, invocation.settings,
            repository=repository.name, build=build, live=live)
    else:
        report = drift(suite, repository=repository.name, build=build, live=live)
    # Evaluation can retain a complete diagnostic reply after local work was
    # stopped. Keep the common CLI interruption/failure status on that reply;
    # an unqualified but completed evaluation remains a successful report.
    status = (2 if report.get("interrupted") else int(bool(report.get("incomplete")))) if kind == "drift" else 0
    return Result(report, status)


def _empty_drift(suite, repository, build, live):
    """No fixtures ran; the not-yet-available pipeline has no measured identity."""
    return {"kind": "drift", "evaluationSchema": suite.schema_version,
            "repository": repository, "file": str(suite.file), "fileHash": suite.file_hash,
            "build": build, "live": live, "pipeline": None,
            **{key: 0 for key in ("cases", "distinctCases", "criticalCases", "criticalMisses",
                "unchangedCases", "routedCases", "jevUnresolvedOnRouted", "reviewerUnresolvedOnRouted",
                "jevCriticalMissesOnRouted", "reviewerCriticalMissesOnRouted",
                "jevErrorsOnRouted", "reviewerErrorsOnRouted", "elapsedMs")},
            "errorRate": None, "falsePositiveRate": None, "usage": None, "cost": None,
            "qualified": False, "qualificationFailures": ["The selected drift section is empty; no pipeline was evaluated."],
            "results": []}
