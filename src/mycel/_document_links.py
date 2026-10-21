"""Complete direct document links inside a caller's current disk snapshot.

Dependency declarations own their exact disk locations. Their current natural
selections, including file and class families, supply the opposite endpoint;
baseline pins do not make an old version current. No embedding, relation,
generated edge, provider or publication participates in this projection.
"""
from __future__ import annotations

from collections import defaultdict

from ._declared_refs import _text
from ._dependency_application import RetainedDependencyResolver
from ._errors import MycelError
from ._refs import _place
from ._resolver import SourceResolver, require_read_transaction


_DEPENDENCIES_SQL = """SELECT d.dependant_version,d.kind,d.state,f.id,fv.snapshot_hash
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


def document_links(connection, resolver: SourceResolver) -> dict[tuple[str, int], tuple[dict, ...]]:
    """Map each described code version to all its direct document sections.

    The caller retains its checked, read-only repeatable snapshot throughout.
    Missing keys mean an empty list. Links are deduplicated by section,
    direction and edge kind, then ordered by the section's repository, root,
    path and name, direction and kind. Code outside the result scope can still
    have a describing document: shared-document settings and query vectors do
    not restrict explicit dependency links.
    """
    require_read_transaction(connection)
    files = {file.identifier: file for file in resolver.files
             if resolver.settings.values['repos'].get(file.repository, {}).get('enabled', False)}
    corpora = {str(identifier): corpus for identifier, corpus in connection.execute(
        'SELECT id,corpus FROM public.mycel_files WHERE id=ANY(%s::uuid[])',
        (list(files),)).fetchall()}
    current = {}
    for file in files.values():
        origin = corpora.get(file.identifier)
        if origin not in {'code', 'documents'}:
            raise MycelError('store_format', 'The document-link catalog has an incompatible corpus origin.')
        for chunk in file.chunks:
            current[chunk.version] = file, chunk, origin
    links = defaultdict(dict)
    for version, kind, state, identifier, digest in connection.execute(_DEPENDENCIES_SQL).fetchall():
        dependant = current.get(version)
        if dependant is None:
            continue
        file, chunk, origin = dependant
        if (file.identifier != str(identifier) or file.snapshot_hash != digest
                or not resolver.owns_policy(file.repository, state)):
            continue
        try:
            raw = _text(state['rawRef'])
            anchor, syntax = state.get('anchor'), state.get('syntaxFault')
            if ((anchor is not None and not isinstance(anchor, str))
                    or (syntax is not None and not isinstance(syntax, str))):
                raise ValueError()
            selected = RetainedDependencyResolver(resolver,
                {raw: anchor} if anchor else {}, {raw: syntax} if syntax else {}).resolve(raw)
        except (KeyError, TypeError, ValueError):
            raise MycelError('store_format', 'A document link has incompatible retained reference metadata.') from None
        if selected.state != 'resolved' or selected.selection is None:
            continue
        for member in selected.selection.members:
            source = current.get(member.chunk.version)
            if source is None or source[1].identifier != member.chunk.identifier:
                continue
            source_file, source_chunk, source_origin = source
            if origin == 'code' and source_origin == 'documents':
                code, section, direction = chunk, resolver._place(source_file, source_chunk), 'source'
            elif origin == 'documents' and source_origin == 'code':
                code, section, direction = source_chunk, resolver._place(file, chunk), 'dependant'
            else:
                continue
            order = (section.repository, section.root, section.path, section.name or '', direction, kind)
            links[code.identifier, code.version][order] = {
                'section': _place(section), 'direction': direction, 'edge': kind}
    return {key: tuple(links[key][order] for order in sorted(links[key])) for key in sorted(links)}
