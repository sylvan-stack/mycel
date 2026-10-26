"""Finite local Origin recovery with exact evidence and guarded model boundaries."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
import threading
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._classification_eligibility import observe_input, classification_eligibility
from ._classification_payload import DecisionText, OriginDecisionPayload, ReviewCommandIdentity, ReviewerRequest
from ._classification_runner import ClassifyDependencies, _BoundaryFailure
from ._classification_store import ClassificationStore
from ._deadline import DeadlineConnection, deadline_guard, deadline_suspended, check_deadline
from ._dependency_application import RetainedDependencyResolver, _ROWS_SQL, _current_raw
from ._derive import _disk_key, _fault
from ._document_links import document_links
from ._drift_store import DriftStore
from ._errors import MycelError
from ._evidence import EvidenceError, _chunk_snapshot, snapshot
from ._freshness import Deadline
from ._jev import JevFailure, JevRequest, JevResponse, route_response
from ._justify import checked_link, public_reference, confidence_band as _confidence_band
from ._locks import atomic_transaction, operation_guard, mutation_guard, read_snapshot, invocation_guard
from ._origins import _selection, origins_in_transaction
from ._resolver import SourceResolver
from ._retrieval import meaning_candidates
from ._retrieval_store import _disk_inputs
from ._reviewer import ReviewerFailure, validate_response as validate_review_response
from ._safeguards import InvocationPolicy, CompletedChild, run_git
from ._scope import RepositoryLocations
from ._store import checked_store
from ._undocumented import normalize_paths
from ._verification import _located, _require_confirmable

SOURCES = ('document', 'test', 'commit', 'issue', 'embedding')
_LINEAR = re.compile(r'https?://(?:[^/\s]+\.)?linear\.app(?:/|\b)|\bLinear issue\b|^#\s+SYL-\d+', re.I | re.M)
_URL = re.compile(r'https?://[^\s<>"\[\]()]+')
_ISSUE = re.compile(r'(?<![\w/])#([1-9][0-9]*)\b')
_ORIGIN_ROWS = """SELECT id,state,kind FROM public.mycel_dependencies WHERE repository=%s
    AND dependant_version=%s AND state->'declarationLocation'->>'file'=%s
    AND state ? 'originLink' ORDER BY id FOR UPDATE NOWAIT"""


def confidence_band(score):
    return _confidence_band(score, model_claim=True)


def _text(file, member):
    blob = _chunk_snapshot(member, file)
    return DecisionText.create(blob.evidence, blob.source)


def _history(repository, selection, *, cancelled=lambda: False):
    """Read only the invoking clone. Never fetch, checkout or run a Git hook."""
    if repository.code is None or selection.place.root != 'code':
        return {'available': False, 'reason': 'no_local_code_history'}, ()
    symbol = selection.members[0].chunk.name.split('.')[-1]
    try:
        root = run_git(('rev-parse', '--show-toplevel'), cwd=repository.code.path,
                       cancelled=cancelled)
        if root.returncode:
            return {'available': False, 'reason': 'no_local_git_history'}, ()
        from pathlib import Path
        checkout = Path(root.stdout.decode().strip()).resolve()
        relative = (repository.code.path / selection.place.path).resolve().relative_to(checkout).as_posix()
        result = run_git(('log', '--reverse', '-S'+symbol, '--format=%H%x00%B%x00',
                          'HEAD', '--', relative), cwd=checkout, cancelled=cancelled)
        if result.returncode:
            return {'available': False, 'reason': 'git_history_unavailable'}, ()
        fields = result.stdout.decode('utf-8', errors='strict').split('\0')
        if len(fields) < 3:
            return {'available': False, 'reason': 'introducing_commit_not_found'}, ()
        commit, message = fields[0].strip(), fields[1]
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
            raise ValueError()
        raw = (commit+'\n'+message).encode()
        blob = snapshot(raw)
        return {'available': True, 'commit': commit, 'message': message,
                'locator': 'snapshot:'+blob.evidence.hash}, (DecisionText.create(blob.evidence, raw),)
    except (MycelError, UnicodeError, ValueError, OSError):
        return {'available': False, 'reason': 'git_history_unavailable'}, ()


def _match_symbol(text, symbol):
    return re.search(r'(?<![\w.])'+re.escape(symbol)+r'(?![\w.])', text) is not None


def _checked_result(pair, record):
    """Revalidate retained stages before reuse or effects; a hash alone is no proof."""
    try:
        if record['inputHash'] != pair.decision.input_hash or record['status'] != 'complete':
            raise ValueError()
        if 'review' in record:
            request = ReviewerRequest(pair.decision,1)
            response = validate_review_response(CompletedChild(0,json.dumps(record['review'],allow_nan=False).encode(),b'',0),request)
            label,score,model = response.judgement,response.confidence_score,request.payload['model']
        else:
            stage = record['jev']
            value = stage['jev'];exact = value['exactDecimals']
            response = JevResponse(value['model'],value['label'],
                {key:Decimal(number) for key,number in exact['probabilities'].items()},
                Decimal(exact['confidence']),value['usage'],value['tied'],
                reported_confidence=Decimal(exact['reportedConfidence']),labels=tuple(pair.decision.payload['labels']))
            if (stage['inputHash'] != pair.decision.input_hash or stage['status'] != 'complete'
                    or response.as_dict() != value or route_response(pair.decision,response).status != 'complete'):
                raise ValueError()
            label,score,model = response.label,float(response.confidence),response.model
        if (record['judgement'],record['confidenceScore'],record['model']) != (label,score,model):
            raise ValueError()
    except (KeyError,TypeError,ValueError,ArithmeticError,JevFailure,ReviewerFailure):
        raise EvidenceError('snapshot_corrupt') from None


def _same_origin(catalog, state, selection):
    result = catalog.resolve(state['originLink']['origin'],purpose='endpoint')
    return (result.state == 'resolved' and result.selection.members[0].chunk.identifier ==
            selection.members[0].chunk.identifier)


@dataclass(frozen=True)
class RecoveryPair:
    chunk: str
    origin: str
    sources: tuple[str, ...]
    decision: OriginDecisionPayload = field(repr=False)
    files: tuple = field(repr=False)
    signatures: tuple = field(repr=False)
    observations: tuple = field(repr=False)
    status: str
    eligible_at: str | None
    previous_link: dict | None = field(default=None, repr=False)

    def as_dict(self):
        return {'chunk': self.chunk, 'origin': self.origin, 'sources': list(self.sources),
                'inputHash': self.decision.input_hash, 'questionVersion': self.decision.payload['questionVersion'],
                'status': self.status, 'eligibleAt': self.eligible_at,
                'bytes': {'jev': len(JevRequest(self.decision).body),
                          'payload': len(self.decision.canonical_bytes)}}


class RecoveryStore:
    def __init__(self, connection):
        self.connection = connection
        self.step_captures = {}  # One step re-reads bytes but parses only what changed.

    @contextmanager
    def guarded(self, settings, *, require_current=True):
        with ExitStack() as stack:
            stack.enter_context(checked_store(self.connection))
            for owner in sorted(settings.values['repos']):
                stack.enter_context(operation_guard(self.connection, owner, 'pass'))
            with atomic_transaction(self.connection):
                if require_current:
                    settings.require_current()
                yield SourceResolver.from_transaction(self.connection, settings)
                if require_current:
                    settings.require_current()

    def context(self, catalog, selections):
        """Complete current direct governors and document ancestors; one hop only."""
        current, files = {}, {}
        for selection in selections:
            member = selection.members[0]
            location, _ = _located(self.connection, selection, settings=catalog.settings, lock=False)
            rows = self.connection.execute(_ROWS_SQL.replace(' FOR UPDATE NOWAIT', ''),
                (member.place.repository, member.chunk.version, location)).fetchall()
            for row in rows:
                if row[6].get('originLink', {}).get('method') in {'inferred', 'recovered'}:
                    continue  # Other model proposals do not bootstrap this judgement.
                resolved = RetainedDependencyResolver(catalog,
                    {_current_raw(row): row[6]['anchor']} if row[6].get('anchor') else {}).resolve(_current_raw(row))
                if resolved.state != 'resolved' or resolved.selection.file is None:
                    raise EvidenceError('context_missing')
                source = resolved.selection
                files[source.file.identifier] = source.file
                for item in source.members:
                    current[item.place.address] = _text(source.file, item)
            if member.chunk.kind in {'document', 'req', 'dec'}:
                from ._markdown import split_markdown
                parsed = split_markdown(selection.file.source)
                row = next((item for item in parsed.entities if item.uuid == member.chunk.identifier),None)
                name = row.section if row is not None else member.chunk.name
                section = next((item for item in parsed.chunks if item.name == name), None)
                if section is None:
                    raise EvidenceError('context_missing')
                for depth in range(1, len(section.heading_path)+(1 if row is not None else 0)):
                    candidates = [item for item in parsed.chunks
                        if item.heading_path == section.heading_path[:depth]
                        and item.span.byte_start <= section.span.byte_start]
                    if not candidates:
                        raise EvidenceError('context_missing')
                    ancestor = max(candidates, key=lambda item: item.span.byte_start)
                    matches = [item for item in catalog._members(selection.file, selection.file.chunks)
                               if item.chunk.span == (ancestor.span.byte_start, ancestor.span.byte_end)]
                    if len(matches) != 1:
                        raise EvidenceError('context_missing')
                    current[matches[0].place.address] = _text(selection.file, matches[0])
        return tuple(current[key] for key in sorted(current)), files

    def prepare_pair(self, settings, catalog, chunk, origin, sources, history, *, at, previous=None,
                     previous_link=None):
        endpoint = catalog.resolve(chunk, purpose='endpoint')
        source = catalog.resolve(origin, purpose='endpoint')
        for result in (endpoint, source):
            if result.state != 'resolved':
                _fault(result, endpoint=True)
        selections = endpoint.selection, source.selection
        files = {item.file.identifier: item.file for item in selections if item.file is not None}
        if len(files) == 0 or any(item.file is None for item in selections):
            raise EvidenceError('insufficient_evidence')
        for selected in selections:
            _, metadata = _located(self.connection, selected, settings=settings, lock=False)
            _require_confirmable(self.connection, selected.members[0], metadata)
        if _LINEAR.search(source.selection.file.source.decode('utf-8')):
            raise EvidenceError('linear_is_not_an_origin')
        repository = RepositoryLocations(settings).named(selections[0].place.repository)[0]
        _, observed_history = _history(repository,selections[0])
        if tuple(item.as_dict() for item in history) != tuple(item.as_dict() for item in observed_history):
            raise EvidenceError('obsolete')
        context, context_files = self.context(catalog, selections)
        files.update(context_files)
        fault = DriftStore(self.connection)._physical(settings, tuple(files.values()), (), {}, catalog,
                                                      previous=self.step_captures)
        if fault:
            raise EvidenceError(fault)
        options = settings.values['drifts']
        review = None
        if options.get('review_command'):
            command = ReviewCommandIdentity.inspect(options['review_command'], options['review_revision'],
                                                    settings._home)
            review = command.model_identity(options['review_provider'], options['review_model'])
        decision = OriginDecisionPayload.create(chunk=_text(selections[0].file, selections[0].members[0]),
            candidate=_text(selections[1].file, selections[1].members[0]), sources=sources, history=history,
            context=context, jev_model=options['model'], review=review, confidence_floor=options['confidence_floor'])
        old = {} if previous is None else {item['identity']: item for item in previous}
        # A pending request of the same file preserves fallback observation time.
        if previous is None:
            rows = self.connection.execute("SELECT metadata FROM public.mycel_manifests WHERE repository=%s "
                "AND kind='origin_recovery' ORDER BY metadata->>'at' DESC,hash", (selections[0].place.repository,)).fetchall()
            for metadata, in rows:
                for item in metadata.get('observations', ()):
                    old.setdefault(item['identity'], item)
        from dataclasses import replace
        from ._settings import _freeze
        values = {key: dict(value) if hasattr(value,'items') else value for key,value in settings.values.items()}
        values['repos'] = {name:dict(value) for name,value in settings.values['repos'].items()}
        for owner in RepositoryLocations(settings).repositories:
            if owner.code is not None:
                values['repos'][owner.name]['code_root'] = str(owner.code.path)
        located_settings = replace(settings,values=_freeze(values))
        records = [record for file in sorted(files.values(), key=lambda item: item.primary.address)
                   for record in ClassificationStore._stat_file(located_settings, file)]
        observations = tuple(observe_input(record['place']['address'], record['hash'], observed_at=at,
            modified_at=datetime.fromtimestamp(record['signature'][4]/1e9, timezone.utc),
            previous=old.get(record['place']['address'])) for record in records)
        eligible = classification_eligibility(observations, at=at, debounce_seconds=options['debounce_seconds'])
        signatures = tuple((file.identifier, file.snapshot_hash, tuple(alias.address for alias in file.aliases))
                           for file in sorted(files.values(), key=lambda item: item.identifier))
        return RecoveryPair(public_reference(selections[0]), public_reference(selections[1]), tuple(sorted(sources)),
            decision, tuple(files.values()), signatures, observations, eligible.status, eligible.eligible_at, previous_link)

    def preview(self, settings, repository, *, chunk=None, paths=(), review=False, at,
                pair_limit=None, cancelled=lambda: False):
        paths = normalize_paths(paths)
        with checked_store(self.connection), read_snapshot(self.connection):
            catalog = SourceResolver.from_read_transaction(self.connection, settings)
            report = origins_in_transaction(self.connection, settings, repository, chunk=chunk, paths=paths)
            targets = [row for row in report['chunks'] if
                (any(link['method'] in {'inferred', 'recovered'} for link in row['links']) if review else not row['links'])]
            mapping = {public_reference(_selection(file, member)): _selection(file, member)
                       for file in catalog.files for member in catalog._members(file, file.chunks)}
            if chunk is None and not review:
                targets = [row for row in targets if
                    mapping[row['chunk']].members[0].chunk.kind not in {'req', 'dec'}
                    and (mapping[row['chunk']].members[0].chunk.kind != 'document'
                         or mapping[row['chunk']].file.document_declarations.role != 'authored')]
            documents = [(file, member) for file in catalog.files for member in catalog._members(file, file.chunks)
                         if member.chunk.kind in {'document', 'req', 'dec'}
                         and not _LINEAR.search(file.source.decode('utf-8'))]
            links = document_links(self.connection, catalog)
            retrieval = _disk_inputs(self.connection, catalog)
            vectors = {item.key: item for item in retrieval}
            repo = RepositoryLocations(settings).named(repository)[0]
            pairs, chunks = [], []
            limit = settings.values['drifts']['candidates'] if pair_limit is None else pair_limit
            attempted, capped = 0, False
            for target_index, target in enumerate(targets):
                check_deadline()
                if cancelled():
                    raise MycelError('refused','Recovery was cancelled during local selection.')
                selected = mapping[target['chunk']]
                member = selected.members[0]
                candidates = {}
                def add(reference, source):
                    origin = mapping.get(reference)
                    if origin is None:
                        resolved = catalog.resolve(reference,purpose='endpoint')
                        if resolved.state == 'resolved':
                            origin = resolved.selection
                            reference = public_reference(origin)
                    if (origin is not None and origin.members[0].chunk.identifier != member.chunk.identifier
                            and not _LINEAR.search(origin.file.source.decode('utf-8'))):
                        candidates.setdefault(reference, set()).add(source)
                history, history_texts = _history(repo, selected, cancelled=cancelled)
                if review:
                    for link in target['links']:
                        if link['method'] in {'inferred', 'recovered'}:
                            add(link['origin'], 'commit' if link['method'] == 'recovered' else 'document')
                else:
                    for link in links.get((member.chunk.identifier, member.chunk.version), ()):
                        resolved = catalog.resolve(link['section']['address'], purpose='endpoint')
                        if resolved.state == 'resolved':
                            add(public_reference(resolved.selection), 'document')
                    symbol = member.chunk.name
                    leaf = symbol.split('.')[-1]
                    for file, item in documents:
                        if _match_symbol(item.chunk.source.decode('utf-8'), symbol):
                            add(public_reference(_selection(file, item)), 'document')
                    for file in catalog.files:
                        if file.repository != repository:
                            continue
                        for item in catalog._members(file, file.chunks):
                            if (item.chunk.kind not in {'document','req','dec'}
                                    and (re.search(r'(^|/)(?:tests?|__tests__)(/|_)|(^|/)test_', item.place.path)
                                         or item.chunk.name.split('.')[-1].startswith('test_'))
                                    and re.search(r'(?<!\w)'+re.escape(leaf)+r'\s*\(', item.chunk.source.decode('utf-8'))):
                                add(public_reference(_selection(file,item)), 'test')
                    if history.get('available'):
                        message = history['message']
                        urls = [url.rstrip('.,:;') for url in _URL.findall(message) if not _LINEAR.search(url)]
                        numbers = _ISSUE.findall(message)
                        for file, item in documents:
                            body = item.chunk.source.decode('utf-8')
                            if history['commit'] in body:
                                add(public_reference(_selection(file,item)), 'commit')
                            # Snapshots carry the exact upstream URL. Bare #N uses
                            # only that repository's documents, avoiding cross-project collisions.
                            if any(url in body for url in urls) or (file.repository == repository and any(
                                    re.search(r'https?://[^\s]+/(?:issues|pull|pulls)/'+number+r'(?!\d)', body)
                                    for number in numbers)):
                                add(public_reference(_selection(file,item)), 'issue')
                    embedded = vectors.get((member.chunk.identifier,member.chunk.version))
                    if embedded is not None and embedded.fully_embedded:
                        scores = {}
                        entities = tuple(item for item in retrieval if item.kind in {'req','dec'})
                        for vector in embedded.part_vectors:
                            for candidate in meaning_candidates(vector, entities, k=10):
                                scores[candidate.chunk.key] = max(scores.get(candidate.chunk.key,-2),candidate.score)
                        for key in sorted(scores, key=lambda key:(-scores[key],key))[:10]:
                            item = next(item for item in entities if item.key == key)
                            resolved = catalog.resolve(item.place.address, purpose='endpoint')
                            if resolved.state == 'resolved':
                                add(public_reference(resolved.selection), 'embedding')
                embedded = vectors.get((member.chunk.identifier,member.chunk.version))
                chunk_reply = {'chunk': target['chunk'], 'history': history,
                    'embedding': {'available': bool(embedded and embedded.fully_embedded)}, 'candidates': []}
                if not chunk_reply['embedding']['available']:
                    chunk_reply['embedding']['reason'] = 'chunk_vectors_unavailable'
                if history.get('available') and not any('commit' in source for source in candidates.values()):
                    chunk_reply['history'] = {**history, 'originAvailable': False, 'reason': 'commit_snapshot_unavailable'}
                for origin in sorted(candidates):
                    record = {'origin': origin, 'sources': sorted(candidates[origin])}
                    if attempted >= limit:
                        capped = True
                        chunk_reply['candidates'].append({**record, 'status': 'not_selected'})
                        continue
                    attempted += 1
                    try:
                        pair = self.prepare_pair(settings, catalog, target['chunk'], origin, candidates[origin],
                            history_texts, at=at, previous_link=next((link for link in target['links']
                                                                  if link['origin'] == origin),None))
                        pairs.append(pair); record.update(pair.as_dict())
                    except (EvidenceError, MycelError) as error:
                        record.update(status='unresolved', reason=error.status if isinstance(error,EvidenceError) else error.code.value)
                    chunk_reply['candidates'].append(record)
                reasons = {'document':'no_matching_document_sections','test':'no_calling_tests',
                           'commit':'commit_snapshot_unavailable','issue':'upstream_snapshot_unavailable',
                           'embedding':'chunk_vectors_unavailable' if not chunk_reply['embedding']['available'] else 'no_embedded_entities'}
                chunk_reply['sourceAvailability'] = {source: {'available':any(source in values for values in candidates.values()),
                    **({} if any(source in values for values in candidates.values()) else {'reason':reasons[source]})}
                    for source in SOURCES}
                chunks.append(chunk_reply)
                if attempted >= limit:
                    capped |= target_index + 1 < len(targets)
                    break
            return pairs, {'repository': repository, 'chunks': chunks, 'capped': capped}

    def check(self, settings, pair, *, at, require_eligible=True):
        with self.guarded(settings) as catalog:
            current = self.prepare_pair(settings, catalog, pair.chunk, pair.origin, pair.sources,
                tuple(DecisionText(item) for item in pair.decision.as_dict()['history']), at=at,
                previous=pair.observations, previous_link=pair.previous_link)
            if current.decision != pair.decision or current.signatures != pair.signatures:
                raise EvidenceError('obsolete')
            if require_eligible and current.status != 'pending_jev':
                raise EvidenceError('pending_debounce')
            # A newly stated link can never be overwritten by an in-flight model.
            endpoint = catalog.resolve(pair.chunk,purpose='endpoint').selection
            location,_ = _located(self.connection,endpoint,settings=settings)
            rows = self.connection.execute(_ORIGIN_ROWS,(endpoint.place.repository,endpoint.members[0].chunk.version,location)).fetchall()
            for row in rows:
                link = row[1].get('originLink')
                origin = catalog.resolve(pair.origin,purpose='endpoint').selection
                if link and _same_origin(catalog,row[1],origin) and link['method'] not in {'inferred','recovered'}:
                    raise EvidenceError('obsolete')
            return current

    def retain(self, settings, pair, *, at, invocation, record=None):
        repository = pair.decision.payload['chunk']['snapshot']['place']['repository']
        digest, raw = pair.decision.input_hash, pair.decision.canonical_bytes
        with self.guarded(settings,require_current=False):
            previous = self.connection.execute('SELECT kind,bytes,metadata FROM public.mycel_manifests '
                'WHERE repository=%s AND hash=%s FOR UPDATE NOWAIT', (repository,digest)).fetchone()
            if previous is not None and (previous[0] != 'origin_recovery' or bytes(previous[1]) != raw):
                raise EvidenceError('snapshot_corrupt')
            metadata = {**({} if previous is None else previous[2]), 'schema':1, 'at':at,
                        'observations':list(pair.observations)}
            if record is not None:
                metadata['record'] = record
            self.connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT(repository,hash) DO UPDATE SET metadata=EXCLUDED.metadata',
                (repository,digest,'origin_recovery',raw,Jsonb(metadata)))
            owner = self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT(repository,kind,identity) DO UPDATE SET invocation=EXCLUDED.invocation RETURNING id',
                (uuid4(),repository,'origin_recovery',digest,None if invocation is None else invocation.id)).fetchone()[0]
            texts = [pair.decision.payload['chunk'],pair.decision.payload['candidate'],
                     *pair.decision.payload['context'],*pair.decision.payload['history']]
            blobs = {item['snapshot']['hash']:item for item in texts}
            for digest_text,item in sorted(blobs.items()):
                source = item['text'].encode('utf-8')
                snapshot_metadata = {'schema':1,'bytes':len(source),'encoding':'utf-8'}
                self.connection.execute('INSERT INTO public.mycel_snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (repository,digest_text,source,Jsonb(snapshot_metadata)))
                stored = self.connection.execute('SELECT bytes,metadata FROM public.mycel_snapshots WHERE repository=%s AND hash=%s',
                                                (repository,digest_text)).fetchone()
                if stored is None or bytes(stored[0]) != source or stored[1] != snapshot_metadata:
                    raise EvidenceError('snapshot_corrupt')
            expected = [(None,digest)]+[(member,None) for member in sorted(blobs)]
            reference = self.connection.execute('SELECT snapshot_hash,manifest_hash FROM public.mycel_evidence_references '
                'WHERE owner=%s ORDER BY ordinal',(owner,)).fetchall()
            if reference and reference != expected:
                raise EvidenceError('snapshot_corrupt')
            if not reference:
                for ordinal,(snapshot_hash,manifest_hash) in enumerate(expected):
                    self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,%s,%s,%s)',
                        (owner,repository,snapshot_hash,manifest_hash,ordinal))
        return metadata.get('record')

    def finish(self, settings, repository, invocation):
        """Release ended leases, retaining a finite request/result history."""
        with self.guarded(settings,require_current=False):
            self.connection.execute("UPDATE public.mycel_evidence_owners SET invocation=NULL WHERE repository=%s "
                "AND kind='origin_recovery' AND invocation=%s", (repository,invocation.id))
            older = self.connection.execute("SELECT o.id,o.identity FROM public.mycel_evidence_owners o "
                "JOIN public.mycel_manifests m ON m.repository=o.repository AND m.hash=o.identity "
                "WHERE o.repository=%s AND o.kind='origin_recovery' AND o.invocation IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM public.mycel_dependencies d WHERE d.repository=o.repository "
                "AND d.state->'recovery'->>'inputHash'=o.identity) "
                "ORDER BY m.metadata->>'at' DESC,o.identity OFFSET 1000", (repository,)).fetchall()
            for owner,digest in older:
                snapshots = self.connection.execute('SELECT snapshot_hash FROM public.mycel_evidence_references '
                    'WHERE owner=%s AND snapshot_hash IS NOT NULL',(owner,)).fetchall()
                self.connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s',(owner,))
                self.connection.execute('DELETE FROM public.mycel_manifests m WHERE repository=%s AND hash=%s '
                    'AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r '
                    'WHERE r.repository=m.repository AND r.manifest_hash=m.hash)',(repository,digest))
                for snapshot_hash, in snapshots:
                    self.connection.execute('DELETE FROM public.mycel_snapshots s WHERE repository=%s AND hash=%s '
                        'AND NOT EXISTS (SELECT 1 FROM public.mycel_evidence_references r '
                        'WHERE r.repository=s.repository AND r.snapshot_hash=s.hash)',(repository,snapshot_hash))

    def apply(self, settings, pair, record, *, at, review=False, activity=None):
        _checked_result(pair,record)
        with self.guarded(settings) as catalog:
            # check() owns a transaction; use the same exact preparation here
            # rather than nesting guards/commits inside the application.
            current = self.prepare_pair(settings,catalog,pair.chunk,pair.origin,pair.sources,
                tuple(DecisionText(item) for item in pair.decision.as_dict()['history']),at=at,
                previous=pair.observations,previous_link=pair.previous_link)
            if current.decision != pair.decision or current.signatures != pair.signatures or current.status != 'pending_jev':
                raise EvidenceError('obsolete')
            endpoint = catalog.resolve(pair.chunk,purpose='endpoint').selection
            source = catalog.resolve(pair.origin,purpose='endpoint').selection
            location,_ = _located(self.connection,endpoint,settings=settings)
            existing = self.connection.execute(_ORIGIN_ROWS,
                (endpoint.place.repository,endpoint.members[0].chunk.version,location)).fetchall()
            prior = [row for row in existing if _same_origin(catalog,row[1],source)]
            if len(prior)>1 or prior and prior[0][1]['originLink']['method'] not in {'inferred','recovered'}:
                raise EvidenceError('obsolete')
            judgement = record['judgement']
            if judgement == 'unrelated':
                if review and prior:
                    self.connection.execute("DELETE FROM public.mycel_dependencies WHERE id=%s AND kind='origin'",
                                            (prior[0][0],))
                    if activity is not None:
                        from ._activity import AppliedMutation
                        activity.record_in_transaction(endpoint.place.repository,'recovery',AppliedMutation(True,
                            {'chunk':pair.chunk,'origin':pair.origin,'action':'withdraw','inputHash':pair.decision.input_hash}))
                    fault = DriftStore(self.connection)._physical(settings,pair.files,(),{},catalog,previous=self.step_captures)
                    if fault:
                        raise EvidenceError(fault)
                return None
            identifier = prior[0][0] if prior else uuid4()
            state = {} if not prior else prior[0][1]
            score = record['confidenceScore']
            link = {'chunk':pair.chunk,'origin':pair.origin,
                'method': ('recovered' if set(pair.sources)&{'commit','issue'} else 'inferred')
                    if not review or pair.previous_link is None else pair.previous_link['method'],
                'confidenceScore':score,'confidence':confidence_band(score),
                'who':record['model'],'when':at}
            if review:
                link['review'] = {'who':record['model'],'when':at,'outcome':judgement}
            link = checked_link(link)
            state = {**state,'declarationLocation':{'kind':'disk','location':_disk_key(settings,endpoint.place.repository),'file':location},
                     'rawRef':source.place.address.encode('utf-8').hex(),'originLink':link,'recovery':{'inputHash':pair.decision.input_hash,'record':record},
                     'originId':source.members[0].chunk.identifier if source.members[0].chunk.kind in {'req','dec'} else None}
            # Inference is a claim, not an authoritative Source Ref. Its own
            # dependency kind keeps a describing section's reverse Source Ref
            # from becoming a circular derivation or a freshness confirmation.
            self.connection.execute("INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,'origin',%s,NULL) "
                "ON CONFLICT(id) DO UPDATE SET state=EXCLUDED.state,source_place=EXCLUDED.source_place",
                (identifier,endpoint.place.repository,endpoint.members[0].chunk.version,pair.origin,
                 source.place.address,Jsonb(state)))
            self.connection.execute('DELETE FROM public.mycel_edges WHERE dependency=%s',(identifier,))
            self.connection.execute('INSERT INTO public.mycel_edges VALUES (%s,%s)',
                                    (identifier,source.members[0].chunk.version))
            if activity is not None:
                from ._activity import AppliedMutation
                activity.record_in_transaction(endpoint.place.repository,'recovery',AppliedMutation(True,
                    {'chunk':pair.chunk,'origin':pair.origin,'link':link,'inputHash':pair.decision.input_hash}))
            fault = DriftStore(self.connection)._physical(settings,pair.files,(),{},catalog,previous=self.step_captures)
            if fault:
                raise EvidenceError(fault)
            return link


def run_recovery(store, settings, repository, *, chunk=None, paths=(), dry_run=False, review=False,
                 k=None, dependencies=None, activity=None, deadline=None):
    settings.require_valid()
    if any(type(flag) is not bool for flag in (dry_run,review)) or k is not None and (type(k) is not int or k<1):
        raise MycelError('invalid_input','Recovery requires boolean flags and a positive pair cap.')
    dependencies = dependencies or ClassifyDependencies()
    options = settings.values['drifts']
    deadline = deadline or Deadline.after(options['seconds'],clock=dependencies.monotonic)
    reply = {'repository':repository,'dryRun':dry_run,'review':review,'selected':0,'completed':0,
             'jevCalls':0,'reviewCalls':0,'errors':0,'incomplete':False,'capped':False,'chunks':[],'pairs':[],'status':0}
    policy = InvocationPolicy('recovery',dry_run=dry_run)
    store = RecoveryStore(DeadlineConnection(store.connection))
    stopped = threading.Event()
    def ensure():
        if stopped.is_set() or dependencies.cancelled() or deadline.cancelled():
            raise _BoundaryFailure('cancelled' if dependencies.cancelled() else 'deadline')
    try:
        with deadline_guard(deadline), ExitStack() as stack:
            if not dry_run:
                stack.enter_context(operation_guard(store.connection,repository,'classify'))
                for owner in sorted(settings.values['repos']):
                    stack.enter_context(mutation_guard(store.connection,owner))
                invocation = stack.enter_context(invocation_guard(store.connection))
            else:
                invocation = None
            pairs, plan = store.preview(settings,repository,chunk=chunk,paths=paths,review=review,
                                         at=dependencies.utc_now(), pair_limit=options['candidates'] if k is None else k,
                                         cancelled=dependencies.cancelled)
            reply['chunks'] = plan['chunks']
            reply['capped'] = plan['capped']
            pairs.sort(key=lambda pair:(pair.eligible_at or '',pair.chunk,pair.origin,pair.decision.input_hash))
            selected = pairs[:options['candidates'] if k is None else k]
            reply['selected'] = len(selected)
            reply['pairs'] = [pair.as_dict() for pair in selected]
            reply['maxCalls'] = {'jev':0 if review else len(selected)*options['attempts'],
                                 'review':len(selected)*options['attempts']}
            if dry_run:
                return reply
            try:
                for pair,item in zip(selected,reply['pairs'],strict=True):
                    attempts = []
                    record = {'status':pair.status,'inputHash':pair.decision.input_hash,'attempts':attempts}
                    try:
                        ensure()
                        previous = store.retain(settings,pair,at=dependencies.utc_now(),invocation=invocation)
                        if pair.status != 'pending_jev':
                            continue
                        def guard():
                            ensure(); store.check(settings,pair,at=dependencies.utc_now()); ensure()
                        def call(stage,client):
                            for attempt in range(options['attempts']):
                                guard()
                                try:
                                    def count():
                                        ensure();reply['jevCalls' if stage=='jev' else 'reviewCalls']+=1
                                    result = client.classify(pair.decision,deadline=deadline.expires_at,
                                        before_call=guard,cancelled=lambda: dependencies.cancelled() or deadline.cancelled(),on_call=count)
                                    ensure();guard()
                                    attempts.append({'stage':stage,'attempt':attempt+1,'status':'complete'})
                                    return result
                                except (JevFailure,ReviewerFailure) as error:
                                    attempts.append({'stage':stage,'attempt':attempt+1,'failure':error.as_dict()})
                                    if not error.retryable or attempt+1 == options['attempts']:
                                        raise
                                    delay = max(2**attempt,error.retry_after_seconds or 0)
                                    limit = options['jev_timeout_seconds' if stage=='jev' else 'review_timeout_seconds']
                                    if delay >= min(deadline.remaining(),limit):
                                        raise
                                    until = dependencies.monotonic()+delay
                                    while dependencies.monotonic()<until:
                                        ensure();dependencies.wait(stopped,min(.05,until-dependencies.monotonic()))
                        if not review and previous and previous.get('status')=='complete':
                            guard();_checked_result(pair,previous);record = {**previous,'reused':True}
                        else:
                            outcome = None if review else call('jev',dependencies.jev_factory(settings,policy))
                            if outcome is not None:
                                if outcome.decision != pair.decision:
                                    raise EvidenceError('obsolete')
                                record['jev'] = outcome.as_dict()
                            if outcome is not None and outcome.status == 'complete':
                                record.update(status='complete',judgement=outcome.judgement,
                                    confidenceScore=float(outcome.response.confidence),model=outcome.response.model)
                            else:
                                if pair.decision.payload['models']['review'] is None:
                                    record.update(status='needs_llm_review',reason='reviewer_unconfigured')
                                    continue
                                command = ReviewCommandIdentity.inspect(options['review_command'],options['review_revision'],settings._home)
                                result = call('review',dependencies.reviewer_factory(settings,policy,command))
                                if (result.request.decision != pair.decision or result.confidence_score is None):
                                    raise EvidenceError('snapshot_corrupt')
                                record.update(status='complete',judgement=result.judgement,confidenceScore=result.confidence_score,
                                    model=pair.decision.payload['models']['review']['model'],review=result.as_dict())
                        ensure()
                        link = store.apply(settings,pair,record,at=dependencies.utc_now(),review=review,activity=activity)
                        record['link'] = link
                        reply['completed'] += 1
                    except (EvidenceError,MycelError,JevFailure,ReviewerFailure,_BoundaryFailure) as error:
                        reason = error.status if isinstance(error,EvidenceError) else error.code.value if isinstance(error,MycelError) else error.reason if isinstance(error,_BoundaryFailure) else error.code
                        record.update(status='error',reason=reason)
                        reply['errors'] += 1;reply['status']=1
                        if reason in {'deadline','cancelled'}:
                            reply['incomplete']=True;stopped.set()
                    except KeyboardInterrupt:
                        stopped.set();record.update(status='error',reason='cancelled')
                        reply.update(incomplete=True,status=2)
                    except Exception:
                        stopped.set();record.update(status='error',reason='internal')
                        reply.update(incomplete=True,status=1);reply['errors']+=1
                    finally:
                        item.update(record)
                        # Even expired/obsolete attempts retain their original immutable request.
                        with deadline_suspended():
                            store.retain(settings,pair,at=dependencies.utc_now(),invocation=invocation,record=record)
                    if stopped.is_set():
                        break
            finally:
                with deadline_suspended():
                    store.finish(settings,repository,invocation)
            return reply
    except (MycelError,EvidenceError,_BoundaryFailure,KeyboardInterrupt) as error:
        reply.update(status=2 if isinstance(error,KeyboardInterrupt) else 1,incomplete=True,
            error=error.to_dict()['error'] if isinstance(error,MycelError) else
                {'code':'refused','message':'Recovery could not complete its guarded selection.'})
        return reply


def handle_recovery(invocation, dependencies=None):
    from ._activity import MutationActivity
    from ._build_identity import current_build
    from ._cli import Result, invocation_store
    values = iter(invocation.arguments)
    paths,refs,flags,k = [],[],set(),None
    for value in values:
        if value in {'--dry-run','--review'}:
            flags.add(value)
        elif value == '--path':
            paths.append(next(values))
        elif value == '--k':
            k = int(next(values))
        else:
            refs.append(value)
    dry_run = '--dry-run' in flags
    settings = invocation.settings
    dependencies = dependencies or ClassifyDependencies()
    deadline = Deadline.after(settings.values['drifts']['seconds'],clock=dependencies.monotonic)
    with ExitStack() as stack:
        stack.enter_context(deadline_guard(deadline))
        connection,_ = stack.enter_context(invocation_store(invocation,operation='read' if dry_run else 'write'))
        if refs:
            with read_snapshot(connection):
                result = SourceResolver.from_read_transaction(connection,settings).resolve(refs[0],purpose='endpoint')
                if result.state != 'resolved':
                    _fault(result,endpoint=True)
                repository = result.selection.place.repository
            if invocation.repositories and invocation.repositories != (repository,):
                raise MycelError('invalid_input','Recovery chunk and repository scope must agree.')
        else:
            selected = RepositoryLocations(settings).resolve_scope(invocation.repositories)
            if len(selected) != 1 or not selected[0].enabled:
                raise MycelError('invalid_input','Recovery requires one enabled repository.')
            repository = selected[0].name
        build = None if dry_run else current_build()
        activity = None if build is None else stack.enter_context(MutationActivity(connection,build=build).session())
        reply = run_recovery(RecoveryStore(connection),settings,repository,chunk=refs[0] if refs else None,
            paths=paths,dry_run=dry_run,review='--review' in flags,k=k,dependencies=dependencies,activity=activity,deadline=deadline)
        if activity is not None:
            activity.finish('done' if reply['status']==0 else 'refused',counts={(repository,'recovery'):reply})
        return Result(reply,reply['status'])
