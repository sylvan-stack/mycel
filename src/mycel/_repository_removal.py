"""Atomic removal of one repository's persisted index and evidence.

Settings determine only the reply's membership flag. Disabled and forgotten
owners remain removable without opening any of their source folders. Surviving
dependants keep their own immutable evidence and natural source places; normal
read resolution reports the now absent source.
"""
from __future__ import annotations

from contextlib import ExitStack

from ._activity import AppliedMutation, MutationActivity
from ._collection import CollectionStore
from ._errors import MycelError
from ._locks import atomic_transaction, operation_guard, removal_guard
from ._settings import SettingsSnapshot
from ._store import checked_store


_AFFECTED = """SELECT DISTINCT d.repository FROM public.mycel_dependencies d
    JOIN public.mycel_edges e ON e.dependency=d.id
    JOIN public.mycel_chunk_versions v ON v.id=e.source_version
    JOIN public.mycel_chunks c ON c.id=v.chunk_id
    WHERE c.repository=%s AND d.repository<>%s ORDER BY d.repository"""

_COUNTS = """SELECT
    (SELECT count(*) FROM public.mycel_files WHERE repository=%s AND corpus='documents'),
    (SELECT count(*) FROM public.mycel_chunks WHERE repository=%s),
    (SELECT count(*) FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c
       ON c.id=v.chunk_id WHERE c.repository=%s),
    (SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p
       ON p.id=v.plan_id JOIN public.mycel_chunk_versions cv ON cv.id=p.chunk_version
       JOIN public.mycel_chunks c ON c.id=cv.chunk_id WHERE c.repository=%s),
    (SELECT count(*) FROM public.mycel_edges e JOIN public.mycel_dependencies d ON d.id=e.dependency
       JOIN public.mycel_chunk_versions v ON v.id=e.source_version
       JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE d.repository=%s OR c.repository=%s),
    (SELECT count(*) FROM public.mycel_snapshots WHERE repository=%s),
    (SELECT count(*) FROM public.mycel_manifests WHERE repository=%s),
    (SELECT count(*) FROM public.mycel_drifts WHERE repository=%s),
    (SELECT count(*) FROM public.mycel_verifications WHERE repository=%s)"""

_COUNT_NAMES = ('documents', 'chunks', 'versions', 'vectors', 'edges', 'evidenceBlobs',
                'evidenceManifests', 'drifts', 'verifications')


class RepositoryRemovalStore:
    def __init__(self, connection):
        self.connection = connection

    def remove(self, settings: SettingsSnapshot, repository: str, *, build: int | None = None) -> dict:
        """Optionally attach numbered-build activity to the atomic removal."""
        committed = []
        try:
            if build is None:
                return self._remove(settings, repository, committed=committed)
            with MutationActivity(self.connection, build=build).session() as activity:
                reply = self._remove(settings, repository, activity=activity, committed=committed)
                activity.finish('done', counts={(None, 'remove'): reply})
            return reply
        except (Exception, KeyboardInterrupt) as error:
            if not committed:
                raise
            # The deletion transaction already committed. Closing its audit is
            # a separate write and cannot turn the actual removed counts into
            # an uncommitted/zero reply.
            interrupted = isinstance(error, KeyboardInterrupt)
            failure = (MycelError('refused', 'Stopped by the caller.') if interrupted else
                error if isinstance(error, MycelError) else MycelError(
                    'internal', 'The completed removal activity could not be closed.'))
            return {**committed[0], 'countsState': 'committed_prefix', **failure.to_dict(),
                    **({'stopped': 'interrupted'} if interrupted else {})}

    def _remove(self, settings: SettingsSnapshot, repository: str, *, activity=None, committed: list) -> dict:
        """Commit the whole removal, or retain every feature row on failure.

        Exclusive removal protection precedes discovery of foreign resolved
        edges. Their owners' short pass guards stabilize the cascading edge
        deletion without changing their dependency records or retained bytes.
        The private lock registry and invocation identities are shared protocol
        state rather than repository-owned index rows and remain intact.
        """
        if not isinstance(settings, SettingsSnapshot):
            raise MycelError('invalid_input', 'Repository removal requires validated settings.')
        settings.require_valid()
        if not isinstance(repository, str) or not repository or '\0' in repository:
            raise MycelError('invalid_input', 'Repository removal requires one exact repository name.')
        try:
            repository.encode('utf-8')
        except UnicodeError:
            raise MycelError('invalid_input', 'Repository removal requires an exact UTF-8 name.') from None
        known = repository in settings.values['repos']
        with checked_store(self.connection), removal_guard(self.connection, repository), ExitStack() as guards:
            affected = tuple(row[0] for row in self.connection.execute(
                _AFFECTED, (repository, repository)).fetchall())
            guarded = tuple(sorted({repository, *affected}))
            for name in guarded:
                guards.enter_context(operation_guard(self.connection, name, 'pass'))
            with atomic_transaction(self.connection):
                settings.require_current()
                exists = self.connection.execute("""SELECT EXISTS (
                    SELECT 1 FROM public.mycel_repository_state WHERE repository=%s
                    UNION ALL SELECT 1 FROM public.mycel_embedding_receipts WHERE repository=%s)""",
                    (repository, repository)).fetchone()[0]
                if not known and not exists:
                    raise MycelError('unknown_repository', 'The repository has no indexed rows and is not configured.')
                row = self.connection.execute(_COUNTS, (repository,) * 10).fetchone()
                removed = dict(zip(_COUNT_NAMES, row, strict=True))
                CollectionStore(self.connection).remove_repository_in_transaction(
                    repository, guarded_repositories=guarded)
                # Receipts deliberately have no searchable-version/repository
                # foreign key: an obsolete returned embedding still needs an
                # explicit owner deletion even after its source version went.
                self.connection.execute('DELETE FROM public.mycel_embedding_receipts WHERE repository=%s',
                                        (repository,))
                reply = {'repository': repository, 'known': known, 'removed': removed}
                if activity is not None:
                    activity.record_in_transaction(None, 'remove', AppliedMutation(bool(exists), reply))
                settings.require_current()
            # Remember the exact result after commit and before session guard
            # cleanup, which may itself fail after the deletion is durable.
            committed.append(reply)
        return reply
