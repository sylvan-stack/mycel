"""Read-only, exact-blob corroboration of local Git rename correspondences.

The caller supplies checked physical checkout scopes and captured/stored bytes.
Equal bytes alone never create an edge: every edge needs Git's rename record and
both complete regular blobs. This module allocates no persistent identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

from ._capture import FileAlias
from ._errors import MycelError
from ._safeguards import run_git

_OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z', re.ASCII)


def _invalid(message):
    raise MycelError('invalid_input', message)


@dataclass(frozen=True, order=True)
class GitPlace:
    checkout: str
    identity: tuple[int, int]
    path: str

    def __post_init__(self):
        path = PurePosixPath(self.path)
        if (not Path(self.checkout).is_absolute() or not self.path or path.is_absolute()
                or path.as_posix() != self.path or '..' in path.parts or '\0' in self.path
                or len(self.identity) != 2 or any(type(value) is not int for value in self.identity)):
            _invalid('A Git correspondence requires a checked checkout and exact relative path.')

    @property
    def logical(self):
        return (str(Path(self.checkout) / self.path), self.checkout, self.identity)


@dataclass(frozen=True)
class GitFileSnapshot:
    place: GitPlace
    commit: str
    source: bytes
    aliases: tuple[FileAlias, ...]

    def __post_init__(self):
        if (not isinstance(self.commit, str) or not _OID.fullmatch(self.commit) or not isinstance(self.source, bytes)
                or not self.aliases or any(not isinstance(alias, FileAlias) for alias in self.aliases)):
            _invalid('A Git correspondence requires full commit IDs, complete bytes and qualified aliases.')

    @property
    def key(self):
        return self.place, self.commit


@dataclass(frozen=True)
class GitRename:
    before: GitFileSnapshot
    after: GitFileSnapshot
    similarity: int

    def record(self, repository):
        return {'kind': 'git', 'beforeCommit': self.before.commit, 'afterCommit': self.after.commit,
                'source': self.before.aliases[0].address(repository),
                'destination': self.after.aliases[0].address(repository), 'similarity': self.similarity}


@dataclass(frozen=True)
class GitCorrespondences:
    renames: tuple[GitRename, ...]

    def peers(self, logical, source):
        """Return corroborated endpoints reachable from an exact placed input.

        A disk input can anchor to a Git snapshot only at its checked place and
        with the same complete bytes. Paths in separate checkout scopes never
        connect. Each returned proof chain consists solely of rename edges.
        """
        edges, snapshots = {}, {}
        for rename in self.renames:
            for own, peer in ((rename.before, rename.after), (rename.after, rename.before)):
                snapshots[own.key] = own
                edges.setdefault(own.key, []).append((peer.key, rename))
        pending = [(key, ()) for key, snapshot in snapshots.items()
                   if snapshot.place.logical in logical and snapshot.source == source]
        seen = {key for key, _ in pending}
        output = []
        while pending:
            key, chain = pending.pop(0)
            for peer, proof in edges[key]:
                if peer in seen:
                    continue
                seen.add(peer)
                following = (*chain, proof)
                output.append((snapshots[peer], following))
                pending.append((peer, following))
        return tuple(output)


def _renames(raw):
    try:
        fields = raw.decode('utf-8', errors='strict').split('\0')
        if fields.pop() != '':
            raise ValueError
        output, index = [], 0
        while index < len(fields):
            status = fields[index]
            index += 1
            if re.fullmatch(r'[RC](?:100|0[0-9]{2}|[0-9]{1,2})', status):
                before, after = fields[index:index + 2]
                index += 2
                if not before or not after:
                    raise ValueError
                if status[0] == 'R':
                    output.append((before, after, int(status[1:])))
            elif status in {'A', 'D', 'M', 'T', 'U', 'X', 'B'}:
                if not fields[index]:
                    raise ValueError
                index += 1
            else:
                raise ValueError
        return tuple(output)
    except (UnicodeError, IndexError, ValueError):
        _invalid('The local Git rename inventory is malformed or incomplete.')


def build_correspondences(inputs: tuple[GitFileSnapshot, ...]) -> GitCorrespondences:
    """Recheck local commits, rename records and complete blobs with finite reads."""
    snapshots = {}
    for snapshot in inputs:
        prior = snapshots.get(snapshot.key)
        if prior is not None and prior.source != snapshot.source:
            _invalid('One Git file snapshot has conflicting complete source bytes.')
        if prior is None:
            snapshots[snapshot.key] = snapshot
    groups = {}
    for snapshot in snapshots.values():
        groups.setdefault((snapshot.place.checkout, snapshot.place.identity), {}).setdefault(
            snapshot.commit, {})[snapshot.place.path] = snapshot
    output = []
    for (checkout, identity), commits in sorted(groups.items()):
        directory = Path(checkout)
        try:
            info = directory.stat()
            if (info.st_dev, info.st_ino) != identity or directory.resolve(strict=True) != directory:
                _invalid('The Git correspondence checkout scope changed.')
        except (OSError, RuntimeError):
            _invalid('The Git correspondence checkout scope is unavailable.')
        kinds, trees, blobs, ancestry = {}, {}, {}, {}

        def read(arguments, **kwargs):
            result = run_git(arguments, cwd=directory, **kwargs)
            if result.returncode:
                _invalid('The complete local Git correspondence evidence is unavailable.')
            return result.stdout

        def exact(snapshot):
            if snapshot.commit not in kinds:
                if read(('cat-file', '-t', snapshot.commit)) != b'commit\n':
                    _invalid('A Git correspondence must name a local commit object.')
                kinds[snapshot.commit] = True
            if snapshot.commit not in trees:
                try:
                    raw = read(('ls-tree', '-r', '-l', '-z', '--full-tree', snapshot.commit))
                    records = raw.split(b'\0')
                    if records.pop() != b'':
                        raise ValueError
                    entries = {}
                    for record in records:
                        header, path = record.split(b'\t', 1)
                        mode, kind, oid, size = header.split()
                        name = path.decode('utf-8', errors='strict')
                        if name in entries:
                            raise ValueError
                        entries[name] = (mode, kind, oid.decode('ascii'), size)
                    trees[snapshot.commit] = entries
                except (UnicodeError, ValueError):
                    _invalid('The complete Git correspondence tree inventory is malformed.')
            entry = trees[snapshot.commit].get(snapshot.place.path)
            if entry is None or entry[0] not in {b'100644', b'100755'} or entry[1] != b'blob':
                _invalid('A Git rename endpoint is not the captured regular file.')
            _, _, oid, size = entry
            if not _OID.fullmatch(oid) or not size.isdigit() or int(size) != len(snapshot.source):
                _invalid('A Git rename endpoint has changed or incomplete source bytes.')
            if oid not in blobs:
                blobs[oid] = read(('cat-file', '-p', oid), stdout_limit=max(1, int(size)))
            if blobs[oid] != snapshot.source:
                _invalid('A Git rename endpoint does not corroborate the complete captured bytes.')

        def ancestor_order(before, after):
            # An empty A ^B walk proves that A is reachable from B. One output
            # record suffices for the negative case; no unbounded history is
            # returned, and Git still uses the shared finite read deadline.
            pair = before, after
            if pair not in ancestry:
                order = 0
                for ancestor, descendant, direction in ((before, after, 1), (after, before, -1)):
                    raw = read(('log', '--format=%H', '--max-count=1', ancestor, '^' + descendant, '--'))
                    if raw == b'':
                        order = direction
                        break
                    if raw != ancestor.encode('ascii') + b'\n':
                        _invalid('The local Git ancestry proof is malformed or incomplete.')
                ancestry[pair] = order
            return ancestry[pair]

        ordered = sorted(commits)
        for index, before_commit in enumerate(ordered):
            for after_commit in ordered[index + 1:]:
                inventory = _renames(read(('diff', '-M', '--name-status', '-z', before_commit, after_commit, '--')))
                for before_path, after_path, similarity in inventory:
                    before, after = commits[before_commit].get(before_path), commits[after_commit].get(after_path)
                    if before is None or after is None:
                        continue
                    exact(before)
                    exact(after)
                    order = ancestor_order(before_commit, after_commit)
                    if order:
                        output.append(GitRename(before, after, similarity) if order == 1
                                      else GitRename(after, before, similarity))
    return GitCorrespondences(tuple(output))
