"""Public retained-reference reporting over one committed read-only snapshot.

This command does not retry resolution, ingest files, acquire mutation locks,
collect evidence or call a provider. A report describes the stored observation.
"""

from __future__ import annotations

from contextlib import ExitStack

from ._cli import Invocation, Result, for_repositories, invocation_store
from ._declared_refs import _raw, _record, _text
from ._errors import MycelError
from ._locks import snapshot_transaction
from ._resolver import SourceResolver
from ._source_refs import SourceAddress, SourceAddressError, parse_source_address


_PUBLIC_FAULTS = {
    "invalid_ref": "not_a_ref", "not_a_ref": "not_a_ref",
    "unregistered_repository": "unknown_repository",
    "disabled_repository": "disabled_repository",
    "missing_file": "not_found", "missing_name": "not_found",
    "missing_entity": "not_found", "entity_kind_mismatch": "not_a_ref", "ambiguous_entity": "ambiguous_title",
    "not_checked": "not_found", "owner_location_missing": "not_found",
    "ambiguous_path": "ambiguous_path", "ambiguous_name": "ambiguous_title",
    "ineligible_index": "not_a_ref", "one_chunk_required": "not_a_ref",
    "generated_text": "generated_text",
}


def _place(address: SourceAddress) -> dict:
    result = {"repository": address.repository, "root": address.root,
              "path": address.path, "address": address.address}
    if address.name is not None:
        result["name"] = address.name
    return result


def _report(row) -> dict:
    (identifier, repository, version, state, baseline_owner, chunk_id,
     version_metadata, file_repository, root, path, file_metadata,
     file_kind, file_location, chunk_locations) = row
    try:
        ref = _record(identifier, repository, version, {**state,
                      "baselineStatus": "baseline_missing" if baseline_owner is None else "retained"})
        owned = state["declarationLocation"]
        present = (file_repository == repository and file_kind == owned["kind"]
                   and file_location == owned["location"] and bool(chunk_locations))
        chunk = {"id": str(chunk_id), "version": version, "repository": repository,
                 "root": None, "path": None, "name": None, "address": None}
        if present:
            if len(chunk_locations) != 1:
                raise ValueError("Ambiguous owning chunk location")
            located = chunk_locations[0]
            name = located.get("name", version_metadata.get("name"))
            if not isinstance(name, str) or not name:
                raise ValueError("Missing owning chunk name")
            if "root" in file_metadata or "path" in file_metadata:
                root, path = file_metadata["root"], file_metadata["path"]
            address = SourceAddress(repository, root, path, name)
            chunk.update(_place(address))
        resolution_fault = ref.fault
        if resolution_fault is not None:
            fault = _PUBLIC_FAULTS[resolution_fault]
        else:
            fault = None
        candidates = [_place(parse_source_address(candidate)) for candidate in ref.candidates]
        if any(candidate["root"] is None for candidate in candidates):
            raise ValueError("Unqualified fault candidate")
        return {"id": ref.identifier, "chunk": chunk, "ref": ref.declared,
                "parsedRef": ref.declaration, "rawLine": ref.raw_line,
                "origin": ref.origin, "line": ref.line,
                "location": {"id": ref.location, "kind": owned["kind"], "name": owned["location"]},
                "ownerLocationAvailable": present,
                "state": ref.state, "fault": fault, "resolutionFault": resolution_fault,
                "resolvedAddress": ref.place, "candidates": candidates,
                "candidateCount": ref.candidate_count, "sourceState": ref.source_state,
                "baselineStatus": ref.baseline_status}
    except (KeyError, TypeError, ValueError, AttributeError, SourceAddressError):
        raise MycelError("store_format", "A retained reference has incompatible declaration or location metadata.") from None


def _reports(row) -> list[dict]:
    """Expand occurrences sharing one edge/pin without losing their spelling.

    The complete dependency producer deduplicates equivalent source selections
    but retains every original declaration occurrence. Older declaration batches
    store one occurrence per dependency row. Both representations are readable.
    """
    report = _report(row)
    state = row[3]
    if "occurrences" not in state:
        return [{**report, "occurrence": 0}]
    try:
        occurrences = state["occurrences"]
        if not isinstance(occurrences, list) or not occurrences:
            raise ValueError("Missing retained occurrences")
        reports = []
        for ordinal, occurrence in enumerate(occurrences):
            declared = _text(occurrence["rawDeclared"])
            raw_line = _text(occurrence["rawLine"])
            origin, line = occurrence["origin"], occurrence["line"]
            if (origin not in {"frontmatter", "comment"}
                    or (line is not None and (type(line) is not int or line < 1))):
                raise ValueError("Invalid occurrence metadata")
            # Current producer occurrences retain the exact declaration text.
            # Comment parsing strips only spaces/tabs; YAML strings are exact.
            parsed = (_text(occurrence["rawRef"]) if "rawRef" in occurrence else
                      declared.strip(" \t") if origin == "comment" else declared)
            reports.append({**report, "occurrence": ordinal, "ref": declared,
                            "parsedRef": parsed, "rawLine": raw_line,
                            "origin": origin, "line": line})
        return reports
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MycelError("store_format", "A retained reference has incompatible occurrence metadata.") from None


def _justified_report(row):
    from ._justify import checked_link
    state = row[3]
    link = checked_link(state['originLink'])
    # Statements have no declaration line; retain the ordinary resolution and
    # location projection while reporting their actual source of authority.
    normalized = {**state, 'rawDeclared': state['rawRef'], 'rawLine': state['rawRef'],
                  'origin': 'stated', 'line': None}
    return {**_report((*row[:3], normalized, *row[4:])), 'occurrence': 0,
            'kind': 'asserted', 'originLink': link}


def _related_reports(row) -> list[dict]:
    """Project declared relation occurrences through the shared ref reporter.

    Relation rows keep literal legacy refs and exact hex alongside them. Their
    occurrence records supply the same physical spelling/location evidence as
    sources, without introducing dependency authority into this read path.
    """
    try:
        state = row[3]
        if state.get("ownership") != "declared" or state.get("managedDeclaration") is not True:
            raise ValueError("Unmanaged relation is not a declared ref")
        occurrences = state["occurrences"]
        if not isinstance(occurrences, list) or not occurrences:
            raise ValueError("Missing retained relation occurrences")
        first = occurrences[0]
        normalized = {**state,
            "rawRef": state["rawRefHex"] if "rawRefHex" in state else _raw(state["rawRef"]),
            "rawDeclared": first["rawDeclared"], "rawLine": first["rawLine"],
            "origin": first["origin"], "line": first["line"]}
        reports = _reports((*row[:3], normalized, *row[4:]))
        for report, occurrence in zip(reports, occurrences):
            syntax_fault = occurrence.get('syntaxFault')
            if syntax_fault is not None:
                report.update(state='invalid', fault=_PUBLIC_FAULTS[syntax_fault],
                    resolutionFault=syntax_fault, resolvedAddress=None,
                    candidates=[], candidateCount=0, sourceState='ineligible',
                    baselineStatus='baseline_missing')
        return [{**report, "kind": "related"} for report in reports]
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MycelError("store_format", "A declared relation has incompatible reference metadata.") from None


def _generated_fault(report: dict, namespaces: frozenset, physical_paths: frozenset) -> dict:
    """Label known generated targets without retrying their retained resolution.

    A first ingest resolves declarations before its final overview projection.
    The committed snapshot can therefore identify generated text while keeping
    that original missing/ineligible resolution, spelling and evidence intact.
    Physical legacy paths keep their existing file and ambiguity semantics.
    """
    if report["resolutionFault"] not in {"ineligible_index", "missing_file", "missing_name"}:
        return report
    try:
        place = parse_source_address(report["parsedRef"])
    except SourceAddressError:
        return report
    target = (place.repository, place.path)
    if target not in namespaces or place.root not in {None, "index"}:
        return report
    if place.root is None and target in physical_paths:
        return report
    return {**report, "fault": "generated_text"}


def _needs_generated_context(report: dict) -> bool:
    """Only reserved generated paths need committed namespace observations."""
    if report["resolutionFault"] not in {"ineligible_index", "missing_file", "missing_name"}:
        return False
    try:
        place = parse_source_address(report["parsedRef"])
    except SourceAddressError:
        return False
    return place.root in {None, "index"} and place.path in {"summaries", "overview"}


def refs(invocation: Invocation) -> Result:
    """Report selected owners; --unresolved includes every stored ref fault."""
    if invocation.arguments not in ((), ("--unresolved",)):
        raise MycelError("invalid_input", "Use mycel refs [--repo <name>] [--unresolved] without positional arguments.")
    unresolved = bool(invocation.arguments)
    with ExitStack() as stack:
        connection = None
        namespaces, physical_paths = frozenset(), frozenset()
        generated_context_loaded = False

        def prepare() -> None:
            nonlocal connection
            connection, _ = stack.enter_context(invocation_store(invocation))
            stack.enter_context(snapshot_transaction(connection))

        def report(repository) -> dict:
            nonlocal namespaces, physical_paths, generated_context_loaded
            rows = connection.execute(_REFS_SQL, (repository.name,)).fetchall()
            retained = [ref for row in rows for ref in _reports(row)]
            related = connection.execute(_RELATED_REFS_SQL, (repository.name,)).fetchall()
            retained.extend(ref for row in related for ref in _related_reports(row))
            justified = connection.execute(_JUSTIFIED_REFS_SQL, (repository.name,)).fetchall()
            retained.extend(_justified_report(row) for row in justified)
            if invocation.settings.values['repos'][repository.name].get('code_clones'):
                retained = [ref for ref in retained if ref['location']['kind'] == 'disk'
                            and ref['location']['name'] == repository.disk_location]
            if not generated_context_loaded and any(_needs_generated_context(ref) for ref in retained):
                catalog = SourceResolver.from_read_transaction(connection, invocation.settings)
                namespaces = frozenset((place.repository, place.path) for place, chunk in catalog.index
                                       if chunk.kind in {"summary", "overview"})
                physical_paths = frozenset((file.repository, alias.path) for file in catalog.files
                                           for alias in file.aliases)
                generated_context_loaded = True
            retained = [_generated_fault(ref, namespaces, physical_paths) for ref in retained]
            retained.sort(key=lambda ref: (ref["id"], ref["occurrence"]))
            selected = [ref for ref in retained if ref["fault"] is not None] if unresolved else retained
            return {"refs": selected, "count": len(selected), "unresolvedOnly": unresolved}

        return for_repositories(invocation, report, needs_folders=False, prepare=prepare)


_REFS_SQL = """SELECT d.id,d.repository,d.dependant_version,d.state,d.baseline_owner,
       c.id,v.metadata,f.repository,f.root,f.path,fl.metadata,fl.kind,fl.location,
       locations.metadata
FROM public.mycel_dependencies d
JOIN public.mycel_chunk_versions v ON v.id=d.dependant_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id
LEFT JOIN public.mycel_file_locations fl
  ON fl.id::text=d.state->'declarationLocation'->>'file'
LEFT JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=c.file_id
LEFT JOIN public.mycel_files f ON f.id=fv.file_id AND c.repository=d.repository
LEFT JOIN LATERAL (
  SELECT jsonb_agg(l.metadata ORDER BY l.id) AS metadata
  FROM public.mycel_locations l
  WHERE l.chunk_version=d.dependant_version AND l.file_location=fl.id
    AND l.kind=fl.kind AND l.location=fl.location
) locations ON true
WHERE d.kind='declared' AND d.repository=%s AND d.state ? 'declarationLocation'
ORDER BY d.id"""

_JUSTIFIED_REFS_SQL = _REFS_SQL.replace("d.kind='declared'",
    "d.kind='asserted' AND d.state ? 'originLink'")


_RELATED_REFS_SQL = """SELECT r.id,r.repository,r.left_version,r.state,r.baseline_owner,
       c.id,v.metadata,f.repository,f.root,f.path,fl.metadata,fl.kind,fl.location,
       locations.metadata
FROM public.mycel_relations r
JOIN public.mycel_chunk_versions v ON v.id=r.left_version
JOIN public.mycel_chunks c ON c.id=v.chunk_id
LEFT JOIN public.mycel_file_locations fl
  ON fl.id::text=r.state->'declarationLocation'->>'file'
LEFT JOIN public.mycel_file_versions fv ON fv.id=fl.file_version AND fv.file_id=c.file_id
LEFT JOIN public.mycel_files f ON f.id=fv.file_id AND c.repository=r.repository
LEFT JOIN LATERAL (
  SELECT jsonb_agg(l.metadata ORDER BY l.id) AS metadata
  FROM public.mycel_locations l
  WHERE l.chunk_version=r.left_version AND l.file_location=fl.id
    AND l.kind=fl.kind AND l.location=fl.location
) locations ON true
WHERE r.repository=%s AND r.state->>'ownership'='declared'
  AND r.state->'managedDeclaration'='true'::jsonb AND r.state ? 'declarationLocation'
ORDER BY r.id"""
