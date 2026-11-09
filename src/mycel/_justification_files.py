"""Reconcile explicit, file-owned Origin Links in an ingest transaction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._deadline import check_deadline
from ._derive import _disk_key
from ._errors import MycelError
from ._justify import public_reference
from ._markdown import MarkdownDocument, _FENCE, _html_block, _html_ends, split_markdown
from ._resolver import SourceResolver
from ._source_refs import SourceAddress, SourceAddressError, format_entity_uri, parse_entity_uri, parse_source_address
from ._verification import _located


_PREFIX = 'justifications/'
_FOOTER = re.compile(r'Origins: (.+) · Intention (i-[0-9a-f]+) · (.+)')
_PART = re.compile(r'(.+) · lines ([1-9][0-9]*) to ([1-9][0-9]*)')
_LABEL = re.compile(r'[A-Z][A-Z0-9]*-(?:D?[0-9]+|[0-9]+\.[0-9]+)')


@dataclass(frozen=True)
class Declaration:
    document: str
    section: str
    chunk: str
    origins: tuple[str, ...]
    intention: str
    when: str

    def fault(self, reason: str, origin: str | None = None) -> dict:
        fault = {'file': self.document, 'section': self.section, 'fault': reason}
        if origin is not None:
            fault['origin'] = origin
        return fault


def _footer(body: str) -> str | None:
    """Read only an explicit terminal line, outside fenced or HTML blocks."""
    lines = re.split(r'\r\n?|\n', body.rstrip())
    if not lines or not lines[-1].startswith('Origins:'):
        return None
    fence = None
    html = None
    for line in lines[:-1]:
        if fence is not None:
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*', line):
                fence = None
        elif html is not None:
            if _html_ends(html, line):
                html = None
        elif (opener := _FENCE.fullmatch(line)) is not None:
            marker, info = opener.groups()
            if marker[0] != '`' or '`' not in info:
                fence = marker
        else:
            block = _html_block(line, can_start_type_seven=True)
            if block is not None and not _html_ends(block, line):
                html = block
    return lines[-1] if fence is None and html is None else None


def _recorded_at(value: str) -> str:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        day = datetime.strptime(value, '%d %B %Y').date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()


def declarations_from_capture(manifest) -> tuple[tuple[Declaration, ...], tuple[dict, ...]]:
    declarations, faults = [], []
    for file in manifest.disk.files:
        if not isinstance(file.parsed, MarkdownDocument):
            continue
        for alias in file.aliases:
            if alias.root != 'artifact' or not alias.path.startswith(_PREFIX) or not alias.path.endswith('.md'):
                continue
            document = alias.address(manifest.repository)
            for section in file.parsed.chunks:
                if section.heading_level != 2 or (footer := _footer(section.body)) is None:
                    continue
                piece = section.title
                part = _PART.fullmatch(piece)
                try:
                    match = _FOOTER.fullmatch(footer)
                    if match is None or (part is not None and int(part[2]) > int(part[3])):
                        raise ValueError()
                    refs, intention, recorded = match.groups()
                    origins = tuple(dict.fromkeys(ref.strip() for ref in refs.split(',')))
                    if not all(origins):
                        raise ValueError()
                    chunk = SourceAddress(manifest.repository, 'code', alias.path[len(_PREFIX):-3],
                                          piece if part is None else part[1]).address
                    when = _recorded_at(recorded)
                except ValueError:
                    faults.append({'file': document, 'section': section.name, 'fault': 'invalid_footer'})
                    continue
                declarations.append(Declaration(document, section.name, chunk, origins, intention, when))
    return tuple(declarations), tuple(faults)


def _label_refs(catalog, label: str) -> tuple[str, ...]:
    references = set()
    for file in catalog.files:
        references.update(format_entity_uri(chunk.kind, chunk.identifier,
                          (chunk.entity or {}).get('title', chunk.title or chunk.name), file.repository)
                          for chunk in file.chunks if chunk.kind in {'req', 'dec'} and chunk.name == label)
        if (label.startswith('OG-') and file.primary.root == 'artifact'
                and file.source.startswith(b'---') and label.encode() in file.source):
            try:
                goal = split_markdown(file.source)
            except ValueError:
                continue
            if goal.frontmatter.get('id') == label and goal.frontmatter.get('status') == 'active':
                heading = next((part.name for part in goal.chunks if part.heading_level == 1), None)
                if heading is not None:
                    references.add(SourceAddress(file.repository, 'artifact', file.primary.path, heading).address)
    return tuple(sorted(references))


def _origin(catalog, ref):
    address = None
    if _LABEL.fullmatch(ref):
        matches = _label_refs(catalog, ref)
        if len(matches) != 1:
            return None, 'ambiguous_origin' if matches else 'missing_origin'
        ref = matches[0]
    else:
        try:
            address = None if parse_entity_uri(ref) is not None else parse_source_address(ref)
        except SourceAddressError:
            return None, 'invalid_origin'
        if address is not None and (address.root not in {'code', 'artifact'} or address.name is None):
            return None, 'invalid_origin'
    resolved = catalog.resolve(ref, purpose='endpoint')
    if resolved.selection is None:
        return None, resolved.fault or 'missing_origin'
    origin = resolved.selection
    if (origin.file is None or origin.members[0].chunk.kind not in {'req', 'dec', 'document'}
            or address is not None and address.name != origin.place.name):
        return None, 'invalid_origin'
    return origin, None


def origin_repositories(declarations, catalog_factory) -> set[str]:
    repositories = set()
    catalog = None
    for reference in sorted({ref for declaration in declarations for ref in declaration.origins}):
        if not _LABEL.fullmatch(reference) and parse_entity_uri(reference) is None:
            try:
                repositories.add(parse_source_address(reference).repository)
            except SourceAddressError:
                pass
            continue
        if catalog is None:
            catalog = catalog_factory()
        origin, _ = _origin(catalog, reference)
        if origin is not None:
            repositories.add(origin.place.repository)
    return repositories


def _key(version, state):
    return (version, state['declarationLocation']['file'],
            state.get('originId') or state['originLink']['origin'])


def reconcile_in_transaction(connection, settings, repository, guarded, captured) -> dict:
    """Replace this clone's file-owned statements, leaving other claims alone."""
    declarations, parsed_faults = captured
    faults = list(parsed_faults)
    location = _disk_key(settings, repository)
    rows = connection.execute("""SELECT d.id,d.dependant_version,d.source_place,d.state,
        ARRAY(SELECT source_version FROM public.mycel_edges WHERE dependency=d.id ORDER BY source_version)
        FROM public.mycel_dependencies d WHERE d.repository=%s AND d.state ? 'originLink'
          AND d.state->'declarationLocation'->>'location'=%s ORDER BY d.id""", (repository, location)).fetchall()
    existing, independent = {}, set()
    for identifier, version, place, state, edges in rows:
        if not state['declarationLocation'].get('file') and 'justificationFile' not in state:
            continue
        key = _key(version, state)
        if 'justificationFile' in state:
            if key in existing:
                raise MycelError('store_format', 'A file-owned Origin Link has more than one record.')
            existing[key] = identifier, place, state, edges
        elif state['originLink']['method'] in {'stated', 'proven'}:
            independent.add(key)

    desired = {}
    if declarations:
        catalog = SourceResolver.from_transaction(connection, settings, guarded_repositories=guarded)
        origins = {ref: _origin(catalog, ref) for ref in {ref for item in declarations for ref in item.origins}}
        for item in declarations:
            check_deadline()
            endpoint = catalog.resolve(item.chunk, purpose='endpoint').selection
            if endpoint is None or endpoint.place.name != parse_source_address(item.chunk).name:
                faults.append(item.fault('missing_or_ambiguous_piece'))
                continue
            version = endpoint.members[0].chunk.version
            file_location, _ = _located(connection, endpoint, settings=settings)
            for ref in item.origins:
                origin, fault = origins[ref]
                if origin is None or origin.place.repository not in guarded:
                    faults.append(item.fault(fault or 'source_pending', ref))
                    continue
                source = origin.members[0].chunk
                if source.identifier == endpoint.members[0].chunk.identifier:
                    faults.append(item.fault('self_origin', ref))
                    continue
                link = {'chunk': public_reference(endpoint), 'origin': public_reference(origin),
                        'method': 'stated', 'confidenceScore': 1.0, 'confidence': 'asserted',
                        'who': f'Intention {item.intention}', 'when': item.when}
                state = {'declarationLocation': {'kind': 'disk', 'location': location, 'file': file_location},
                         'justificationFile': {'path': item.document, 'section': item.section, 'intention': item.intention},
                         'originId': source.identifier if source.kind in {'req', 'dec'} else None,
                         'rawRef': origin.place.address.encode('utf-8').hex(), 'originLink': link}
                key = _key(version, state)
                if key not in independent:
                    desired.setdefault(key, (version, origin.place.address, state, [source.version]))

    changed = 0
    for key in sorted(existing.keys() - desired.keys()):
        connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (existing[key][0],))
        changed += 1
    for key, (version, place, state, edges) in desired.items():
        previous = existing.get(key)
        if previous is not None:
            identifier, old_place, old_state, old_edges = previous
            old_link, link = old_state['originLink'], state['originLink']
            # Semantic audit may have lowered the confidence of this exact claim.
            if (old_edges == edges and old_state['justificationFile'] == state['justificationFile']
                    and all(old_link[name] == link[name] for name in ('chunk', 'origin', 'method', 'who', 'when'))):
                state['originLink'] = old_link
            if old_place == place and old_state == state and old_edges == edges:
                continue
        else:
            identifier = uuid4()
        connection.execute("""INSERT INTO public.mycel_dependencies
            (id,repository,dependant_version,declaration,source_place,kind,state)
            VALUES (%s,%s,%s,%s,%s,'origin',%s)
            ON CONFLICT(id) DO UPDATE SET declaration=EXCLUDED.declaration,
                source_place=EXCLUDED.source_place,state=EXCLUDED.state""",
            (identifier, repository, version, state['originLink']['origin'], place, Jsonb(state)))
        connection.execute('DELETE FROM public.mycel_edges WHERE dependency=%s', (identifier,))
        connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)', (identifier, edges[0]))
        changed += 1
    return {'changed': changed, 'faults': faults}
