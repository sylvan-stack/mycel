"""Exact disk-location-owned citations inside the candidate read snapshot.

Only declared and asserted Source Refs supply citations. Stored baseline pins
are evidence of earlier inputs; current natural resolution supplies the code.
"""
from __future__ import annotations

from ._declared_refs import _text
from ._dependency_application import RetainedDependencyResolver
from ._errors import MycelError
from ._ranking import DocumentCitation, RankingGraph
from ._retrieval import _tie, select_chunks


_CITATIONS_SQL = """SELECT d.dependant_version,d.state,f.id,fv.snapshot_hash
    FROM public.mycel_dependencies d
    JOIN public.mycel_file_locations fl
      ON fl.id::text=d.state->'declarationLocation'->>'file'
    JOIN public.mycel_file_versions fv ON fv.id=fl.file_version
    JOIN public.mycel_files f ON f.id=fv.file_id AND f.repository=d.repository
    JOIN public.mycel_chunk_versions cv ON cv.id=d.dependant_version
    JOIN public.mycel_chunks c ON c.id=cv.chunk_id
      AND c.repository=f.repository
    JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version
      AND l.file_location=fl.id AND l.location=fl.location
    WHERE d.kind IN ('declared','asserted') AND fl.kind='disk' AND l.kind='disk'
      AND d.state->'declarationLocation'->>'kind'='disk'
      AND d.state->'declarationLocation'->>'location'=fl.location
    ORDER BY d.id"""


def graph_for(snapshot, repository: str, *, only: str | None = None) -> RankingGraph:
    """Keep visible citers and code selection in the same guarded MVCC view."""
    snapshot._require_active()
    if repository not in snapshot.repositories:
        raise MycelError('invalid_input', 'Ranking citations require a member of the active search scope.')
    selected = select_chunks(snapshot._settings, repository, snapshot.chunks,
                             only='docs')
    documents = tuple(sorted((chunk for chunk in selected
        if only != 'code' or chunk.repository == repository), key=_tie))
    by_version = {chunk.version: chunk for chunk in documents}
    current = {chunk.key: chunk for chunk in snapshot.chunks
               if chunk.repository == repository and chunk.origin == 'code'}
    files = {file.identifier: file for file in snapshot.resolver.files}
    cited = {chunk.key: {} for chunk in documents}
    for version, state, file_id, digest in snapshot._connection.execute(_CITATIONS_SQL).fetchall():
        document = by_version.get(version)
        file = files.get(str(file_id))
        if (document is None or file is None or file.repository != document.repository
                or file.snapshot_hash != digest or not snapshot.resolver.owns_policy(file.repository, state)):
            continue
        try:
            raw = _text(state['rawRef'])
            anchor = state.get('anchor')
            syntax = state.get('syntaxFault')
            if not isinstance(raw, str) or (anchor is not None and not isinstance(anchor, str)):
                raise ValueError()
            resolver = RetainedDependencyResolver(snapshot.resolver,
                {raw: anchor} if anchor else {}, {raw: syntax} if syntax else {})
            resolution = resolver.resolve(raw)
        except (KeyError, TypeError, ValueError):
            raise MycelError('store_format', 'A disk citation has incompatible retained reference metadata.') from None
        if resolution.state != 'resolved' or resolution.selection is None:
            continue
        for member in resolution.selection.members:
            code = current.get((member.chunk.identifier, member.chunk.version))
            if code is not None:
                cited[document.key][code.key] = code
    citations = tuple(DocumentCitation(document,
        tuple(sorted(cited[document.key].values(), key=_tie)))
        for document in documents if cited[document.key])
    return RankingGraph(documents, citations)
