"""Finite, read-only reporting of the stored code overview."""

from pathlib import Path

from ._errors import MycelError
from ._locks import snapshot_transaction
from ._overview_render import normalize_directory
from ._overview_store import OverviewStore
from ._scope import RepositoryLocations


def overview_repository(settings, names=(), *, cwd=None):
    """Resolve one enabled repository without checking or reading its files."""
    settings.require_valid()
    if (len(names) > 1 or any(not isinstance(name, str) for name in names)
            or (names and names[0] in settings.values["organizations"])):
        raise MycelError("invalid_input", "Overview takes one repository; an organization is not accepted.")
    locations = RepositoryLocations(settings)
    selected = locations.resolve_scope(names, cwd=cwd)
    if len(selected) != 1:
        raise MycelError("invalid_input", "Overview takes one repository; an organization is not accepted.")
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
                raise MycelError("invalid_input", "Overview requires a repository folder or an explicit repository.")
        except (OSError, RuntimeError, ValueError):
            raise MycelError("unknown_repository", "The overview repository folder cannot be resolved.") from None
    if not repository.enabled:
        raise MycelError("refused", "Overview requires an enabled repository.")
    return repository.name


def handle_overview(invocation):
    """Print the current index snapshot; never reconcile, refresh or embed."""
    from ._cli import Result, invocation_store
    if invocation.settings is None:
        raise MycelError("internal", "Settings were not loaded for this invocation.")
    if invocation.all_repositories or (invocation.arguments and
            (len(invocation.arguments) != 2 or invocation.arguments[0] != "--dir")):
        raise MycelError("invalid_input", "Use overview [--repo <name>] [--dir <relative directory>].")
    directory = normalize_directory(invocation.arguments[1]) if invocation.arguments else None
    repository = overview_repository(invocation.settings, invocation.repositories)
    with invocation_store(invocation) as (connection, _):
        with snapshot_transaction(connection):
            sections = OverviewStore(connection).sections(repository, directory)
    return Result({"repository": repository, "sections": sections})
