"""Finite Origin audit questions, exact evidence, and atomic disputed claims."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
import threading
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation
from ._audit import AuditStore, _claim, current_graph, observation
from ._classification_eligibility import observe_input, classification_eligibility
from ._classification_payload import AuditDecisionPayload, DecisionText, ReviewCommandIdentity
from ._classification_runner import ClassifyDependencies, _BoundaryFailure
from ._classification_store import ClassificationStore
from ._deadline import DeadlineConnection, deadline_guard, deadline_suspended, check_deadline
from ._derive import _fault
from ._drift_store import DriftStore
from ._errors import MycelError
from ._evidence import EvidenceError
from ._freshness import Deadline
from ._jev import JevFailure, JevRequest
from ._justify import checked_link, confidence_band, public_reference
from ._locks import (read_snapshot, operation_guard, mutation_guard, invocation_guard)
from ._origins import _selection
from ._recovery import _text, _checked_result
from ._resolver import SourceResolver
from ._reviewer import ReviewerFailure
from ._safeguards import InvocationPolicy
from ._scope import RepositoryLocations
from ._settings import _freeze
from ._store import checked_store
from ._undocumented import normalize_paths
from ._verification import _located, _require_confirmable


@dataclass(frozen=True)
class AuditPair:
    repository: str
    location: str
    question: str
    subject: str
    path: str
    claims: tuple
    decision: AuditDecisionPayload = field(repr=False)
    files: tuple = field(repr=False)
    signatures: tuple = field(repr=False)
    observations: tuple = field(repr=False)
    status: str
    eligible_at: str | None

    def as_dict(self):
        return {'question': self.question, 'subject': self.subject, 'links': list(self.claims),
                'inputHash': self.decision.input_hash, 'questionVersion': self.decision.payload['questionVersion'],
                'status': self.status, 'eligibleAt': self.eligible_at,
                'bytes': {'jev': len(JevRequest(self.decision).body), 'payload': len(self.decision.canonical_bytes)}}


class SemanticAuditStore(AuditStore):
    def prepare_pair(self, settings, catalog, repository, question, subject, claims, *, at, previous=None):
        endpoint = catalog.resolve(subject, purpose='endpoint')
        if endpoint.state != 'resolved':
            _fault(endpoint, endpoint=True)
        selected = endpoint.selection
        if selected.place.repository != repository or selected.file is None:
            raise EvidenceError('obsolete')
        if question == 'ambiguity' and (selected.members[0].chunk.kind != 'req'
                or (selected.members[0].chunk.entity or {}).get('status') == 'withdrawn'):
            raise EvidenceError('obsolete')
        _, _, _, graph, location = current_graph(self.connection, settings, repository, catalog=catalog)
        current = {item['id']: item for item in graph.get(selected.members[0].chunk.version, ())}
        if any(claim['id'] not in current or current[claim['id']]['claim'] != claim for claim in claims):
            raise EvidenceError('obsolete')
        origins = {}
        for claim in claims:
            resolved = catalog.resolve(current[claim['id']]['link']['origin'], purpose='endpoint')
            if resolved.state != 'resolved':
                _fault(resolved, endpoint=True)
            origin = resolved.selection
            if origin.file is None:
                raise EvidenceError('insufficient_evidence')
            origins[origin.place.address] = origin
        origins = tuple(origins[key] for key in sorted(origins))
        selections = (selected, *origins)
        files = {item.file.identifier: item.file for item in selections}
        for selection in selections:
            _, metadata = _located(self.connection, selection, settings=settings, lock=False)
            _require_confirmable(self.connection, selection.members[0], metadata)
        context, context_files = self.context(catalog, selections)
        files.update(context_files)
        fault = DriftStore(self.connection)._physical(settings, tuple(files.values()), (), {}, catalog,
                                                      previous=self.step_captures)
        if fault:
            raise EvidenceError(fault)
        options = settings.values['drifts']
        review = None
        if options.get('review_command'):
            command = ReviewCommandIdentity.inspect(options['review_command'], options['review_revision'], settings._home)
            review = command.model_identity(options['review_provider'], options['review_model'])
        decision = AuditDecisionPayload.create(question=question,
            subject=_text(selected.file, selected.members[0]),
            origins=tuple(_text(item.file, item.members[0]) for item in origins), context=context,
            jev_model=options['model'], review=review, confidence_floor=options['confidence_floor'])
        old = {} if previous is None else {item['identity']: item for item in previous}
        if previous is None:
            for metadata, in self.connection.execute("SELECT metadata FROM public.mycel_manifests WHERE repository=%s "
                    "AND kind='origin_audit_request' ORDER BY metadata->>'at' DESC,hash", (repository,)).fetchall():
                for item in metadata.get('observations', ()):
                    if item['identity'] not in old or item['lastObservedAt'] > old[item['identity']]['lastObservedAt']:
                        old[item['identity']] = item
        # Stat the selected configured clone, including complete uncited spans.
        values = {key: dict(value) if hasattr(value, 'items') else value for key, value in settings.values.items()}
        values['repos'] = {name: dict(value) for name, value in settings.values['repos'].items()}
        for owner in RepositoryLocations(settings).repositories:
            if owner.code is not None:
                values['repos'][owner.name]['code_root'] = str(owner.code.path)
        located_settings = replace(settings, values=_freeze(values))
        records = [record for file in sorted(files.values(), key=lambda item: item.primary.address)
                   for record in ClassificationStore._stat_file(located_settings, file)]
        observations = tuple(observe_input(RepositoryLocations(settings).named(record['place']['repository'])[0].disk_location+':'+record['place']['address'], record['hash'], observed_at=at,
            modified_at=datetime.fromtimestamp(record['signature'][4]/1e9, timezone.utc),
            previous=old.get(RepositoryLocations(settings).named(record['place']['repository'])[0].disk_location+':'+record['place']['address'])) for record in records)
        eligible = classification_eligibility(observations, at=at, debounce_seconds=options['debounce_seconds'])
        signatures = tuple((file.identifier, file.snapshot_hash, tuple(alias.address for alias in file.aliases))
                           for file in sorted(files.values(), key=lambda item: item.identifier))
        return AuditPair(repository, location, question, public_reference(selected), selected.place.path,
                         tuple(claims), decision, tuple(files.values()), signatures, observations,
                         eligible.status, eligible.eligible_at)

    def preview(self, settings, repository, *, paths=(), at, pair_limit, cancelled=lambda: False):
        paths = normalize_paths(paths)
        with checked_store(self.connection), read_snapshot(self.connection):
            catalog, _, selected, links, _ = current_graph(self.connection, settings, repository, paths=paths)
            # Bounds apply before exact preparation, including unresolved pairs.
            # Descriptor generation itself is finite and never calls a model.
            def descriptors():
                targets = sorted(selected.items(), key=lambda item: item[1][1].place.address)
                for question in ('conformance', 'consistency', 'ambiguity'):
                    for version, (file, member) in targets:
                        subject = public_reference(_selection(file, member))
                        own = sorted(links.get(version, ()), key=lambda item: (item['link']['origin'], item['id']))
                        if question == 'conformance':
                            for item in own:
                                yield question, subject, (item['claim'],)
                        elif question == 'consistency':
                            unique = {}
                            for item in own:
                                resolved = catalog.resolve(item['link']['origin'], purpose='endpoint')
                                identity = (resolved.selection.members[0].chunk.identifier if resolved.state == 'resolved'
                                            else item['link']['origin'])
                                unique.setdefault(identity, item)
                            for a, b in combinations(unique.values(), 2):
                                yield question, subject, tuple(sorted((a['claim'], b['claim']), key=lambda claim: claim['id']))
                        elif member.chunk.kind == 'req' and (member.chunk.entity or {}).get('status') != 'withdrawn':
                            yield question, subject, ()
            pairs, unresolved, capped, attempted = [], [], False, 0
            for question, subject, claims in descriptors():
                check_deadline()
                if cancelled():
                    raise MycelError('refused', 'Audit was cancelled during local selection.')
                if attempted >= pair_limit:
                    capped = True
                    break
                attempted += 1
                try:
                    pairs.append(self.prepare_pair(settings, catalog, repository, question, subject, claims, at=at))
                except (EvidenceError, MycelError) as error:
                    unresolved.append({'question': question, 'subject': subject, 'links': list(claims),
                        'status': 'unresolved', 'reason': error.status if isinstance(error, EvidenceError) else error.code.value})
            return pairs, {'capped': capped, 'attempted': attempted, 'unresolved': unresolved}

    def check_in_transaction(self, settings, catalog, pair, *, at):
        current = self.prepare_pair(settings, catalog, pair.repository, pair.question,
                                   pair.subject, pair.claims, at=at, previous=pair.observations)
        if (current.decision != pair.decision or current.signatures != pair.signatures
                or current.location != pair.location):
            raise EvidenceError('obsolete')
        if current.status != 'pending_jev':
            raise EvidenceError('pending_debounce')
        return current

    def check(self, settings, pair, *, at):
        with self.guarded(settings) as catalog:
            self.check_in_transaction(settings, catalog, pair, at=at)

    def retain(self, settings, pair, *, at, invocation, record=None):
        repository = pair.repository
        digest, raw = pair.decision.input_hash, pair.decision.canonical_bytes
        with self.guarded(settings, require_current=False):
            previous = self.connection.execute('SELECT kind,bytes,metadata FROM public.mycel_manifests '
                'WHERE repository=%s AND hash=%s FOR UPDATE NOWAIT', (repository, digest)).fetchone()
            if previous is not None and (previous[0] != 'origin_audit_request' or bytes(previous[1]) != raw):
                raise EvidenceError('snapshot_corrupt')
            metadata = {**({} if previous is None else previous[2]), 'schema': 1, 'at': at,
                        'observations': list({item['identity']:item for item in
                            [*(() if previous is None else previous[2].get('observations', ())), *pair.observations]}.values())}
            guards=dict(metadata.get('guardsByLocation', {}))
            guards[pair.location]={'location':pair.location,'claims':list(pair.claims),'files':list(pair.signatures)}
            metadata['guardsByLocation']=guards
            if record is not None:
                metadata['attempt'] = record
                if record.get('status') == 'complete' or metadata.get('record', {}).get('status') != 'complete':
                    metadata['record'] = record
            self.connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT(repository,hash) DO UPDATE SET metadata=EXCLUDED.metadata',
                (repository, digest, 'origin_audit_request', raw, Jsonb(metadata)))
            owner = self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT(repository,kind,identity) DO UPDATE SET invocation=EXCLUDED.invocation RETURNING id',
                (uuid4(), repository, 'origin_audit_request', digest, None if invocation is None else invocation.id)).fetchone()[0]
            payload = pair.decision.as_dict()
            texts = [payload['subject'], *payload['origins'], *payload['context']]
            from ._evidence import SnapshotEvidence, Snapshot
            blobs = tuple(Snapshot(SnapshotEvidence.from_record(item['snapshot']), item['text'].encode()) for item in texts)
            DriftStore(self.connection)._retain(repository, owner, blobs)
            existing = self.connection.execute('SELECT 1 FROM public.mycel_evidence_references WHERE owner=%s AND manifest_hash=%s',
                                               (owner, digest)).fetchone()
            if existing is None:
                ordinal = self.connection.execute('SELECT coalesce(max(ordinal),-1)+1 FROM public.mycel_evidence_references WHERE owner=%s', (owner,)).fetchone()[0]
                self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,%s)',
                                        (owner, repository, digest, ordinal))
        return metadata.get('record')

    def finish(self, settings, repository, invocation):
        with self.guarded(settings, require_current=False):
            self.connection.execute("UPDATE public.mycel_evidence_owners SET invocation=NULL WHERE repository=%s "
                "AND kind='origin_audit_request' AND invocation=%s", (repository, invocation.id))
            self.prune_in_transaction(repository)

    def apply(self, settings, pair, record, *, at, activity=None):
        _checked_result(pair, record)
        with self.guarded(settings) as catalog:
            self.check_in_transaction(settings, catalog, pair, at=at)
            rows = []
            if pair.claims:
                rows = self.connection.execute('SELECT id,state FROM public.mycel_dependencies WHERE id=ANY(%s) '
                    'ORDER BY id FOR UPDATE NOWAIT', ([claim['id'] for claim in pair.claims],)).fetchall()
                if tuple(sorted((_claim(identifier, checked_link(state['originLink'])) for identifier, state in rows),
                                key=lambda item: item['id'])) != tuple(sorted(pair.claims, key=lambda item: item['id'])):
                    raise EvidenceError('obsolete')
            negative = {'conformance': 'nonconforming', 'consistency': 'contradictory', 'ambiguity': 'ambiguous'}[pair.question]
            if record['judgement'] != negative:
                return {'finding': None, 'lowered': 0, 'created': False}
            observed = observation(pair.repository, pair.location, negative, pair.subject, pair.path,
                facts={'question': pair.question, 'questionVersion': pair.decision.payload['questionVersion']},
                links=pair.claims, input_hash=pair.decision.input_hash)
            finding, created = self.open_in_transaction(observed, at=at, record=record, request_hash=pair.decision.input_hash)
            lowered = 0
            if negative == 'nonconforming' and finding['state'] == 'open':
                for identifier, state in rows:
                    link = checked_link(state['originLink'])
                    score = float(min(Decimal(str(link['confidenceScore'])), Decimal(1)-Decimal(str(record['confidenceScore']))))
                    if score < link['confidenceScore']:
                        link = {**link, 'confidenceScore': score,
                                'confidence': confidence_band(score, model_claim=link['method'] in {'inferred', 'recovered'}),
                                'review': {'who': record['model'], 'when': at, 'outcome': 'nonconforming'}}
                        self.connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',
                            (Jsonb({**state, 'originLink': checked_link(link)}), identifier))
                        lowered += 1
            if (created or lowered) and activity is not None:
                activity.record_in_transaction(pair.repository, 'audit', AppliedMutation(True,
                    {'finding': finding['id'], 'newFindings': int(created), 'lowered': lowered, 'inputHash': pair.decision.input_hash}))
            # A source edit during the activity callback rolls back both effects.
            self.check_in_transaction(settings, catalog, pair, at=at)
            return {'finding': finding['id'], 'lowered': lowered, 'created': created}


def run_audit(store, settings, repository, *, paths=(), dry_run=False, deterministic=False, closed=False,
                 k=None, dependencies=None, activity=None, deadline=None):
    settings.require_valid()
    if any(type(flag) is not bool for flag in (dry_run,deterministic,closed)) or k is not None and (type(k) is not int or k<1):
        raise MycelError('invalid_input','Audit requires boolean flags and a positive pair cap.')
    dependencies = dependencies or ClassifyDependencies()
    options = settings.values['drifts']
    deadline = deadline or Deadline.after(options['seconds'],clock=dependencies.monotonic)
    reply = {'repository':repository,'dryRun':dry_run,'deterministic':deterministic,'location':RepositoryLocations(settings).named(repository)[0].disk_location,'paths':list(normalize_paths(paths)),
             'findings':[],'newFindings':0,'settled':None,'reused':0,'selected':0,'completed':0,
             'jevCalls':0,'reviewCalls':0,'errors':0,'incomplete':False,'capped':False,'pairs':[],'status':0}
    policy = InvocationPolicy('audit',dry_run=dry_run or deterministic)
    store = SemanticAuditStore(DeadlineConnection(store.connection))
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
            repo=RepositoryLocations(settings).named(repository)[0]
            if not repo.enabled:
                raise MycelError('invalid_input','Audit requires one enabled repository.')
            reply['findings'],reply['newFindings']=store.deterministic(settings,repository,paths=paths,
                dry_run=dry_run,closed=closed,at=dependencies.utc_now(),activity=activity)
            if deterministic:
                return reply
            pairs,plan=store.preview(settings,repository,paths=paths,at=dependencies.utc_now(),
                pair_limit=options['candidates'] if k is None else k,cancelled=dependencies.cancelled)
            reply['capped']=plan['capped'];reply['attempted']=plan['attempted']
            reply['selected']=len(pairs);reply['pairs']=[pair.as_dict() for pair in pairs]+plan['unresolved']
            reply['maxCalls']={'jev':len(pairs)*options['attempts'],'review':len(pairs)*options['attempts']}
            if dry_run:
                return reply
            try:
                for pair,item in zip(pairs,reply['pairs'][:len(pairs)],strict=True):
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
                        if previous and previous.get('status')=='complete':
                            guard();_checked_result(pair,previous);record = {**previous,'reused':True};reply['reused']+=1
                        else:
                            outcome = call('jev',dependencies.jev_factory(settings,policy))
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
                        effects = store.apply(settings,pair,record,at=dependencies.utc_now(),activity=activity)
                        record['effects'] = effects
                        reply['newFindings'] += int(effects['created'])
                        reply['completed'] += 1
                    except (EvidenceError,MycelError,JevFailure,ReviewerFailure,_BoundaryFailure) as error:
                        reason = error.status if isinstance(error,EvidenceError) else error.code.value if isinstance(error,MycelError) else error.reason if isinstance(error,_BoundaryFailure) else error.code
                        record.update(status='error',reason=reason)
                        reply['errors'] += 1;reply['status']=1
                        if reason in {'deadline','cancelled'}:
                            reply['incomplete']=True;stopped.set()
                            if reason=='cancelled':reply['status']=2
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
            with deadline_suspended(),checked_store(store.connection),read_snapshot(store.connection):
                reply['findings']=store.list_in_transaction(settings,repository,paths=paths,closed=closed)
            return reply
    except (MycelError,EvidenceError,_BoundaryFailure,KeyboardInterrupt) as error:
        reply.update(status=2 if isinstance(error,KeyboardInterrupt) or getattr(error,'reason',None)=='cancelled' or dependencies.cancelled() else 1,incomplete=True,
            error=error.to_dict()['error'] if isinstance(error,MycelError) else
                {'code':'refused','message':'Audit could not complete its guarded selection.'})
        return reply



def handle_audit(invocation, dependencies=None):
    from ._activity import MutationActivity
    from ._build_identity import current_build
    from ._cli import Result, invocation_store
    arguments = iter(invocation.arguments)
    paths, flags, values = [], set(), {}
    for argument in arguments:
        if argument == '--path':
            paths.append(next(arguments))
        elif argument in {'--dry-run', '--deterministic', '--closed'}:
            flags.add(argument)
        else:
            values[argument] = next(arguments)
    dry_run = '--dry-run' in flags
    settings = invocation.settings
    dependencies = dependencies or ClassifyDependencies()
    deadline = Deadline.after(settings.values['drifts']['seconds'], clock=dependencies.monotonic)
    scope = RepositoryLocations(settings).resolve_scope(invocation.repositories)
    if len(scope) != 1 or not scope[0].enabled:
        raise MycelError('invalid_input', 'Audit requires one enabled repository.')
    repository = scope[0].name
    with deadline_guard(deadline), ExitStack() as stack:
        connection, _ = stack.enter_context(invocation_store(invocation, operation='read' if dry_run else 'write'))
        build = None if dry_run else current_build()
        activity = None if build is None else stack.enter_context(MutationActivity(connection, build=build).session())
        store = SemanticAuditStore(connection)
        if '--settle' in values:
            finding, changed = store.settle(settings, repository, values['--settle'], reason=values['--reason'],
                by=values.get('--by'), at=dependencies.utc_now(), activity=activity)
            with checked_store(connection), read_snapshot(connection):
                findings = store.list_in_transaction(settings, repository)
            reply = {'repository': repository, 'location': scope[0].disk_location, 'paths': [],
                'deterministic': True, 'dryRun': False, 'findings': findings, 'newFindings': 0,
                'settled': finding, 'changed': changed, 'selected': 0, 'completed': 0, 'reused': 0,
                'capped': False, 'jevCalls': 0, 'reviewCalls': 0, 'errors': 0, 'incomplete': False, 'pairs': [], 'status': 0}
        else:
            reply = run_audit(store, settings, repository, paths=paths, dry_run=dry_run,
                deterministic='--deterministic' in flags, closed='--closed' in flags,
                k=int(values['--k']) if '--k' in values else None, dependencies=dependencies, activity=activity, deadline=deadline)
        if activity is not None:
            activity.finish('done' if reply['status'] == 0 else 'refused', counts={(repository, 'audit'): reply})
        return Result(reply, reply['status'])
