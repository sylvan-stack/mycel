"""Internal, settings-only repository folders and command scope.

The settings snapshot is authoritative. Looking for a configured name directly
under an organization establishes membership; it never registers extra names.
All filesystem inspection here is read-only, with no store or Git invocation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Any, Literal

from ._errors import ErrorCode, MycelError
from ._settings import SettingsSnapshot


@dataclass(frozen=True)
class Folder:
    path: Path
    source: Literal["repository", "organization"]
    subfolders: tuple[str, ...] = ()

    def report(self, *, code: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {"folder": str(self.path), "from": self.source}
        if code and self.subfolders:
            result["subfolders"] = list(self.subfolders)
        return result


@dataclass(frozen=True)
class Organization:
    name: str
    root: Path
    documents: Path

    def report(self) -> dict[str, str]:
        return {"name": self.name, "root": str(self.root), "documents": str(self.documents)}


@dataclass(frozen=True)
class Repository:
    name: str
    enabled: bool
    organization: str | None = None
    code: Folder | None = None
    documents: Folder | None = None
    fault: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    _organizations: tuple[str, ...] = field(default=(), repr=False)
    _candidate_roots: tuple[Path, ...] = field(default=(), repr=False)

    clones: tuple[Folder, ...] = field(default=(), repr=False)
    primary_code: Folder | None = field(default=None, repr=False)
    readonly_root: Path | None = None
    location: str | None = None

    def at(self, cwd: Path) -> Repository:
        primary = self.primary_code or self.code
        if self.fault is not None:
            return replace(self, code=primary, location=None)
        matches = []
        for folder in ((primary,) if primary is not None else ()) + self.clones:
            resolved = _resolved(folder.path)
            if cwd.is_relative_to(resolved):
                matches.append((len(resolved.parts), folder, resolved))
        if not matches:
            return replace(self, code=primary, location=None)
        _, folder, resolved = max(matches, key=lambda item: item[0])
        return replace(self, code=folder, location=None if primary is not None and
                       resolved == _resolved(primary.path) else str(resolved))

    @property
    def disk_location(self) -> str:
        if self.location is None:
            return "disk"
        return json.dumps({"kind": "disk", "checkout": None, "identity": "disk",
                           "clone": self.location}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def report(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "enabled": self.enabled}
        if self.organization is not None:
            result["organization"] = self.organization
        if self.code is not None:
            result["code"] = self.code.report(code=True)
        if self.documents is not None:
            result["documents"] = self.documents.report()
        if self.clones:
            primary = self.primary_code or self.code
            result["codeLocations"] = [str(folder.path) for folder in
                (((primary,) if primary is not None else ()) + self.clones)]
            result["location"] = self.disk_location
        if self.readonly_root is not None:
            result["readonlyRoot"] = str(self.readonly_root)
        if self.fault is not None:
            result["fault"] = self.fault
        return result

    def require_folders(self) -> None:
        """Refuse only work on this repository, preserving other results."""
        if self.fault is not None:
            raise MycelError(ErrorCode.SETTINGS, f"Repository {self.name!r}: {self.fault}")

    @property
    def code_roots(self) -> tuple[Path, ...]:
        """Source-code subfolders; Markdown still uses the whole code root."""
        self.require_folders()
        if self.code is None:
            return ()
        if not self.code.subfolders:
            return (self.code.path,)
        return tuple(self.code.path / subfolder for subfolder in self.code.subfolders)

    @property
    def document_roots(self) -> tuple[Folder, ...]:
        """Both configured document locations with their root provenance.

        Scan/address tasks determine overlapping-file aliases; retaining both
        here preserves the source root rather than silently preferring one.
        """
        self.require_folders()
        return tuple(folder for folder in (self.code, self.documents) if folder is not None)


def _resolved(path: Path) -> Path:
    return path.resolve()


def _direct_name(name: str) -> bool:
    return bool(name) and name not in {".", ".."} and Path(name).name == name and "/" not in name


def _checkout(path: Path) -> bool:
    # A worktree has a .git file; a regular checkout has a .git directory.
    # A symlink is an alias rather than a direct organization child.
    marker = path / ".git"
    return (not path.is_symlink() and path.is_dir()
            and (marker.is_dir() or marker.is_file()))


class RepositoryLocations:
    """One invocation's resolved folders, preserving per-repository faults."""

    def __init__(self, snapshot: SettingsSnapshot, *, cwd: Path | str | None = None):
        snapshot.require_valid()
        self.snapshot = snapshot
        self.cwd = _resolved(Path.cwd() if cwd is None else Path(cwd))
        self.organizations = tuple(
            Organization(name, Path(value["root"]), Path(value["artifact_root"]))
            for name, value in sorted(snapshot.values["organizations"].items())
        )
        self.repositories = tuple(
            self._repository(name, value)
            for name, value in sorted(snapshot.values["repos"].items())
        )
        self._repositories = {repository.name: repository for repository in self.repositories}
        self._organizations = {organization.name: organization for organization in self.organizations}

    def _repository(self, name: str, value: Mapping[str, Any]) -> Repository:
        code = (Folder(Path(value["code_root"]), "repository", tuple(value["code_subdirs"]))
                if "code_root" in value else None)
        documents = (Folder(Path(value["artifact_root"]), "repository")
                     if "artifact_root" in value else None)
        matches: list[tuple[Organization, Path]] = []
        faults: list[str] = []
        try:
            for organization in self.organizations:
                if code is not None:
                    candidate = code.path
                    if _resolved(candidate).parent != _resolved(organization.root):
                        continue
                else:
                    if not _direct_name(name):
                        continue
                    candidate = organization.root / name
                    if not _checkout(candidate):
                        continue
                matches.append((organization, candidate))
        except (OSError, RuntimeError, ValueError):
            faults.append("Organization membership cannot be resolved from its configured folders.")

        organization_name = None
        candidates: tuple[Path, ...] = ()
        if len(matches) > 1:
            names = ", ".join(repr(organization.name) for organization, _ in matches)
            correction = "give this repository an explicit code_root" if code is None else "give the organizations distinct roots"
            faults.append(f"Found under several organizations: {names}; {correction}.")
            candidates = tuple(candidate for _, candidate in matches)
        elif matches:
            organization, candidate = matches[0]
            organization_name = organization.name
            if code is None:
                code = Folder(candidate, "organization", tuple(value["code_subdirs"]))
            if documents is None:
                if not _direct_name(name):
                    faults.append("The repository name cannot form a direct-child document folder; give artifact_root.")
                else:
                    documents = Folder(organization.documents / "repos" / name, "organization")

        if code is None and documents is None and not faults:
            faults.append("No organization member or configured code_root/artifact_root gives this repository a folder.")
        if code is None and value["code_subdirs"]:
            faults.append("code_subdirs requires a code_root or an organization checkout.")
        if code is not None:
            try:
                root = _resolved(code.path)
                for subfolder in code.subfolders:
                    if not _resolved(code.path / subfolder).is_relative_to(root):
                        faults.append(f"code_subdirs path {subfolder!r} resolves outside code_root.")
            except (OSError, RuntimeError, ValueError):
                faults.append("code_root or one of its code_subdirs cannot be resolved.")
        if documents is not None and "evaluation" in value:
            try:
                if not _resolved(documents.path / value["evaluation"]).is_relative_to(_resolved(documents.path)):
                    faults.append("evaluation resolves outside artifact_root.")
            except (OSError, RuntimeError, ValueError):
                faults.append("artifact_root or its evaluation path cannot be resolved.")
        elif "evaluation" in value and not faults:
            faults.append("evaluation requires an artifact_root or organization document folder.")

        clones = []
        primary_root, readonly = None, None
        try:
            primary_root = None if code is None else _resolved(code.path)
            for path in value.get("code_clones", ()):
                resolved = _resolved(Path(path))
                if resolved != primary_root and all(_resolved(item.path) != resolved for item in clones):
                    clones.append(Folder(resolved, "repository", tuple(value["code_subdirs"])))
            if clones and code is None:
                faults.append("code_clones requires a primary code_root or organization checkout.")
            readonly = Path(value["readonly_root"]).resolve() if "readonly_root" in value else None
            if readonly is not None and readonly not in {primary_root, *(item.path for item in clones)}:
                faults.append("readonly_root must name the primary code_root or a listed code_clones folder.")
        except (OSError, RuntimeError, ValueError):
            faults.append("The configured clone locations cannot be resolved.")
        return Repository(name, value["enabled"], organization_name, code, documents,
                          " ".join(faults) if faults else None, value,
                          tuple(organization.name for organization, _ in matches), candidates,
                          tuple(clones), code, readonly).at(self.cwd)

    def repositories_reply(self) -> dict[str, Any]:
        """The MYC-5 repos report includes disabled and locally faulty names."""
        return {"organizations": [organization.report() for organization in self.organizations],
                "repositories": [repository.report() for repository in self.repositories]}

    def _members(self, organization: str) -> tuple[Repository, ...]:
        members = tuple(repository for repository in self.repositories
                        if repository.enabled and organization in repository._organizations)
        if not members:
            raise MycelError(ErrorCode.REFUSED,
                             f"Organization {organization!r} has no enabled configured member.")
        return members

    def named(self, name: str) -> tuple[Repository, ...]:
        """Resolve exact configured names; an explicit repo may be disabled."""
        repository, organization = self._repositories.get(name), self._organizations.get(name)
        if repository is not None and organization is not None:
            raise MycelError(ErrorCode.UNKNOWN_REPOSITORY,
                             f"Name {name!r} identifies both a repository and an organization.")
        if repository is not None:
            return (repository,)
        if organization is not None:
            return self._members(name)
        raise MycelError(ErrorCode.UNKNOWN_REPOSITORY, f"No configured repository or organization is named {name!r}.")

    def resolve_scope(self, names: Sequence[str] = (), *, all_repositories: bool = False,
                      cwd: Path | str | None = None) -> tuple[Repository, ...]:
        """Resolve named, all-enabled, or longest containing folder scope.

        A selected record may carry a local fault. The operation can report it
        alongside successful repositories by calling require_folders per entry.
        """
        if names and all_repositories:
            raise MycelError(ErrorCode.INVALID_INPUT, "Select named repositories or --all, not both.")
        if names:
            selected: dict[str, Repository] = {}
            for name in names:
                for repository in self.named(name):
                    selected.setdefault(repository.name, repository)
            return tuple(repository.at(_resolved(Path(cwd))) if cwd is not None else repository
                         for repository in selected.values())
        if all_repositories:
            selected = tuple(repository for repository in self.repositories if repository.enabled)
            if not selected:
                raise MycelError(ErrorCode.REFUSED, "No enabled configured repository could be selected.")
            return selected
        try:
            current = self.cwd if cwd is None else _resolved(Path(cwd))
        except (OSError, RuntimeError, ValueError):
            raise MycelError(ErrorCode.UNKNOWN_REPOSITORY, "The current directory cannot be resolved.") from None

        bindings: list[tuple[int, int, str, bool]] = []
        for repository in self.repositories:
            roots = tuple(folder.path for folder in (repository.primary_code, repository.code,
                repository.documents, *repository.clones) if folder is not None)
            for root in (*roots, *repository._candidate_roots):
                try:
                    resolved = _resolved(root)
                    if current.is_relative_to(resolved):
                        bindings.append((len(resolved.parts), 1, repository.name, True))
                except (OSError, RuntimeError, ValueError):
                    continue
        for organization in self.organizations:
            for root in (organization.root, organization.documents):
                try:
                    resolved = _resolved(root)
                    if current.is_relative_to(resolved):
                        bindings.append((len(resolved.parts), 0, organization.name, False))
                except (OSError, RuntimeError, ValueError):
                    continue
        if not bindings:
            raise MycelError(ErrorCode.UNKNOWN_REPOSITORY,
                             "The current directory belongs to no configured repository or organization.")
        priority = max(binding[:2] for binding in bindings)
        winners = {(name, is_repository) for depth, kind, name, is_repository in bindings
                   if (depth, kind) == priority}
        if len(winners) != 1:
            raise MycelError(ErrorCode.UNKNOWN_REPOSITORY,
                             "The longest containing folder belongs to several configured names: "
                             + ", ".join(repr(name) for name, _ in sorted(winners)) + ".")
        name, is_repository = next(iter(winners))
        return ((self._repositories[name].at(current),) if is_repository else
                tuple(repository.at(current) for repository in self._members(name)))
