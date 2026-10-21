"""Atomic stated Origin Links composed from dependency assertions and verification."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation, MutationActivity
from ._dependency_application import RetainedDependencyResolver, _ROWS_SQL, _current_raw
from ._dependency_inputs import DependencyCaptureInputs
from ._derive import DeriveStore, _canonical_refs, _disk_key, _fault, _validate_ref_syntax
from ._errors import MycelError
from ._evidence import EvidenceError
from ._locks import atomic_transaction, operation_guard
from ._reconciliation import ReconciliationError
from ._relations import RELATION_ROWS_SQL, _relation_raw
from ._resolver import SourceResolver
from ._source_refs import format_entity_uri
from ._store import checked_store
from ._verification import ConfirmationStore, _identity, _located, _time, _require_confirmable


def public_reference(selection):
    """Write row entities as URIs; ordinary chunks/files retain their address."""
    if selection.kind != 'file' and len(selection.members) == 1:
        chunk = selection.members[0].chunk
        if chunk.kind in {'req', 'dec'}:
            return format_entity_uri(chunk.kind, chunk.identifier,
                (chunk.entity or {}).get('title', chunk.title or chunk.name), selection.place.repository)
    return selection.place.address


def checked_link(value):
    """Validate retained statement data without turning the claim into a proof."""
    required = {'chunk', 'origin', 'method', 'confidenceScore', 'confidence', 'who', 'when'}
    try:
        if (not isinstance(value, dict) or set(value) - required - {'review'} or not required <= set(value)
                or value['method'] not in {'stated', 'proven', 'inferred', 'recovered'}
                or value['confidence'] not in {'asserted', 'proven', 'inferred', 'candidate'}
                or type(value['confidenceScore']) not in {int, float}
                or not math.isfinite(value['confidenceScore']) or not 0 <= value['confidenceScore'] <= 1):
            raise ValueError()
        _validate_ref_syntax((value['chunk'], value['origin']))
        _time(value['when'])
        if not isinstance(value['who'], str) or not value['who'].strip():
            raise ValueError()
        if 'review' in value:
            review = value['review']
            if (not isinstance(review, dict) or set(review) != {'who', 'when', 'outcome'}
                    or any(not isinstance(review[key], str) or not review[key].strip() for key in review)):
                raise ValueError()
            _time(review['when'])
        return json.loads(json.dumps(value, allow_nan=False))
    except (KeyError, TypeError, ValueError, MycelError, OverflowError):
        raise MycelError('store_format', 'A retained Origin Link has incompatible metadata.') from None


def _pairs(values):
    if not isinstance(values, (tuple, list)) or not values:
        raise MycelError('invalid_input', 'Justify requires at least one chunk and Origin pair.')
    result = []
    for pair in values:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise MycelError('invalid_input', 'Every justification requires one chunk and one Origin.')
        _validate_ref_syntax(pair)
        result.append(tuple(pair))
    if len(set(result)) != len(result):
        raise MycelError('invalid_input', 'Duplicate exact justification pairs are not accepted.')
    return tuple(result)


def pairs_from_file(path):
    """Read the delegated MYC-D51 format, refusing duplicate or unknown fields."""
    def object_pairs(items):
        if len({key for key, _ in items}) != len(items):
            raise ValueError()
        return dict(items)
    pairs = []
    try:
        with Path(path).expanduser().open(encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line, object_pairs_hook=object_pairs)
                    if (not isinstance(row, dict) or set(row) != {'chunk', 'origin'}
                            or any(not isinstance(value, str) for value in row.values())):
                        raise ValueError()
                    _validate_ref_syntax((row['chunk'], row['origin']))
                except (TypeError, ValueError, MycelError):
                    raise MycelError('invalid_input', f'Justify input line {number} requires exactly chunk and origin references.') from None
                pairs.append((row['chunk'], row['origin']))
    except (OSError, UnicodeError, TypeError):
        raise MycelError('invalid_input', 'The justification file could not be read as UTF-8 JSON lines.') from None
    return _pairs(pairs)


class JustifyStore:
    def __init__(self, connection):
        self.connection = connection

    def apply(self, settings, chunk, origin, **options):
        return self.apply_pairs(settings, ((chunk, origin),), **options)[0]

    def apply_pairs(self, settings, pairs, *, by=None, captured_at=None, build=None, settings_home=None):
        settings.require_valid(require_store=False)
        pairs = _pairs(pairs)
        by = _identity(by)
        captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec='microseconds')
        _time(captured_at)
        guarded = tuple(sorted(settings.values['repos']))
        replies, counts = [], {}
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            for repository in guarded:
                stack.enter_context(operation_guard(self.connection, repository, 'pass'))
            audit = None if build is None else MutationActivity(self.connection, build=build)
            stack.enter_context(nullcontext() if audit is None else audit.session())
            try:
                with atomic_transaction(self.connection):
                    catalog = SourceResolver.from_transaction(self.connection, settings)
                    planned, files = [], {}
                    # Resolve every pair and its complete selected inputs before
                    # applying any assertion, including an invalid later pair.
                    for raw_chunk, raw_origin in pairs:
                        canonical = _canonical_refs(self.connection, settings, (raw_chunk, raw_origin),
                            ('endpoint', 'source'), catalog=catalog)
                        endpoint = catalog.resolve(canonical[0], purpose='endpoint')
                        source = catalog.resolve(canonical[1], purpose='source')
                        if endpoint.state != 'resolved':
                            _fault(endpoint, endpoint=True)
                        if source.state != 'resolved':
                            _fault(source)
                        if endpoint.selection.place.root == 'index' or source.selection.place.root == 'index':
                            raise MycelError('invalid_input', 'Justify requires a current chunk and a file-backed Origin.')
                        selection, member = endpoint.selection, endpoint.selection.members[0]
                        location, metadata = _located(self.connection, selection, settings=settings)
                        _require_confirmable(self.connection, member, metadata)
                        _, origin_metadata = _located(self.connection, source.selection, settings=settings)
                        for origin_member in source.selection.members:
                            _require_confirmable(self.connection, origin_member, origin_metadata)
                        owner = member.place.repository
                        for selected in (selection, source.selection):
                            files[(selected.file.repository, selected.file.identifier)] = selected.file
                        # Existing direct policy is also confirmed. Keep all of
                        # its physical inputs in the batch's final reread guard.
                        for row in self.connection.execute(_ROWS_SQL,
                                (owner, member.chunk.version, location)).fetchall():
                            resolved = RetainedDependencyResolver(catalog,
                                {_current_raw(row): row[6]['anchor']} if row[6].get('anchor') else {}).resolve(_current_raw(row))
                            if resolved.selection is not None:
                                file = resolved.selection.file
                                files[(file.repository, file.identifier)] = file
                        for row in self.connection.execute(RELATION_ROWS_SQL,
                                (owner, member.chunk.version, location)).fetchall():
                            resolved = RetainedDependencyResolver(catalog, {},
                                endpoint_refs=(_relation_raw(row[4]),)).resolve(_relation_raw(row[4]))
                            if resolved.selection is not None:
                                file = resolved.selection.file
                                files[(file.repository, file.identifier)] = file
                        planned.append((raw_chunk, raw_origin, selection, source.selection, location))
                    inputs = DependencyCaptureInputs(self.connection, settings, settings_home=settings_home)
                    for file in files.values():
                        manifest = inputs.observe(file.repository)
                        aliases = {(place.root, place.path) for place in file.aliases}
                        actual = [captured for captured in manifest.disk.files if aliases.intersection(
                            (place.root, place.path) for place in captured.aliases)]
                        if len(actual) != 1 or actual[0].source != file.source:
                            raise EvidenceError('changed_since_ingest', (file.primary.address,))
                    for raw_chunk, raw_origin, selection, origin, location in planned:
                        member = selection.members[0]
                        owner = member.place.repository
                        DeriveStore(self.connection).apply_in_transaction(settings, raw_chunk, raw_origin,
                            remove=False, captured_at=captured_at, settings_home=settings_home)
                        rows = self.connection.execute("""SELECT id,state FROM public.mycel_dependencies
                            WHERE repository=%s AND dependant_version=%s AND kind='asserted'
                              AND source_place=%s AND state->'declarationLocation'->>'file'=%s
                            ORDER BY id FOR UPDATE NOWAIT""",
                            (owner, member.chunk.version, origin.place.address, location)).fetchall()
                        if len(rows) != 1:
                            raise MycelError('store_format', 'The justification assertion has no unique owner.')
                        identifier, state = rows[0]
                        link = {'chunk': public_reference(selection), 'origin': public_reference(origin),
                            'method': 'stated', 'confidenceScore': 1.0, 'confidence': 'asserted',
                            'who': by, 'when': captured_at}
                        if state.get('originLink') is not None:
                            previous = checked_link(state['originLink'])
                            if 'review' in previous:
                                link['review'] = previous['review']
                        state = {**state, 'originLink': link,
                                 'originId': origin.members[0].chunk.identifier if origin.kind != 'file'
                                     and len(origin.members) == 1 and origin.members[0].chunk.kind in {'req', 'dec'} else None}
                        self.connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',
                                                (Jsonb(state), identifier))
                        verification = ConfirmationStore(self.connection).apply_in_transaction(settings, raw_chunk,
                            by=by, how='read', captured_at=captured_at, settings_home=settings_home,
                            guarded_repositories=guarded, expected_identifier=member.chunk.identifier)
                        reply = {'chunk': public_reference(selection), 'chunkVersion': member.chunk.version,
                            'origin': public_reference(origin), 'link': link, 'verification': verification}
                        replies.append(reply)
                        current = [value for value, planned_pair in zip(replies, planned)
                                   if planned_pair[2].place.repository == owner]
                        counts[(owner, 'justify')] = reply if len(pairs) == 1 else {'justifications': current}
                        if audit is not None:
                            audit.record_in_transaction(owner, 'justify', AppliedMutation(True, counts[owner, 'justify']))
                    inputs.verify()
            except EvidenceError as error:
                raise MycelError('invalid_input', 'Justify refused: '+error.status+'; '+', '.join(error.addresses or ()) + '.') from None
            except ReconciliationError as error:
                raise MycelError('invalid_input', 'Justify refused: '+error.status+'.') from None
            if audit is not None:
                audit.finish('done', counts=counts)
        return replies


def handle_justify(invocation):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store
    values, refs = {}, []
    arguments = iter(invocation.arguments)
    for argument in arguments:
        if argument in {'--by', '--file'}:
            value = next(arguments, None)
            if value is None or argument in values:
                raise MycelError('invalid_input', 'Justify options require one value and cannot repeat.')
            values[argument] = value
        else:
            refs.append(argument)
    bulk = '--file' in values
    if bulk and refs or not bulk and len(refs) != 2:
        raise MycelError('invalid_input', 'Use justify <chunk> <origin> or justify --file <pairs.jsonl>, with optional --by.')
    pairs = pairs_from_file(values['--file']) if bulk else _pairs((refs,))
    with invocation_store(invocation, operation='write') as (connection, _):
        replies = JustifyStore(connection).apply_pairs(invocation.settings, pairs,
            by=values.get('--by'), build=current_build())
    return Result({'justifications': replies} if bulk else replies[0])
