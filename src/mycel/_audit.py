"""Stored Origin audit observations and explicit operator settlement."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import PurePosixPath
import re
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from ._activity import AppliedMutation
from ._drift_store import DriftStore
from ._errors import MycelError
from ._evidence import canonical_json, _chunk_snapshot, snapshot
from ._justify import checked_link, public_reference
from ._locks import read_snapshot, invocation_is_live
from ._markdown import split_markdown
from ._origins import _selection
from ._recovery import RecoveryStore
from ._resolver import SourceResolver
from ._scope import RepositoryLocations
from ._source_refs import SourceAddressError, parse_source_address
from ._staleness import current_stale_reasons
from ._store import checked_store
from ._undocumented import normalize_paths
from ._verification import _identity, _time

DETERMINISTIC = ('unresting_requirement','missing_origin','multiple_chapters','stale_chain',
                 'missing_discussion','duplicate_id','missing_term')
SEMANTIC = ('nonconforming','contradictory','ambiguous')
SCHEMA = 'mycel-origin-audit-finding-v1'
RETENTION = 1000


def _hash(value):
    return sha256(canonical_json(value)).hexdigest()


def _at():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _in_path(path, paths):
    return not paths or any(value=='.' or path==value or path.startswith(value+'/') for value in paths)


def _claim(identifier, link):
    return {'id':str(identifier), **{key:link[key] for key in ('chunk','origin','method','who','when')}}


def current_graph(connection, settings, repository, *, paths=(), catalog=None):
    catalog = catalog or SourceResolver.from_read_transaction(connection,settings)
    current = {member.chunk.version:(file,member) for file in catalog.files
               for member in catalog._members(file,file.chunks)}
    selected = {version:(file,member) for version,(file,member) in current.items()
                if file.repository==repository and _in_path(member.place.path,paths)}
    location = RepositoryLocations(settings).named(repository)[0].disk_location
    locations = {repo.name:repo.disk_location for repo in RepositoryLocations(settings).repositories}
    links = {}
    for identifier,owner,version,state in connection.execute("SELECT id,repository,dependant_version,state "
            "FROM public.mycel_dependencies WHERE state ? 'originLink' ORDER BY id").fetchall():
        if version not in current or state.get('declarationLocation',{}).get('location')!=locations.get(owner):
            continue
        link = checked_link(state['originLink'])
        links.setdefault(version,[]).append({'id':str(identifier),'link':link,'claim':_claim(identifier,link),'originId':state.get('originId')})
    return catalog,current,selected,links,location


def observation(repository, location, kind, subject, path, *, facts, links=(), input_hash=None):
    result={'schema':SCHEMA,'repository':repository,'location':location,'kind':kind,
            'subject':subject,'path':path,'links':sorted(links,key=lambda item:item['id']),'facts':facts}
    if input_hash is not None:result['inputHash']=input_hash
    return result


def finding_id(observed):
    return str(uuid5(NAMESPACE_URL,'mycel:origin-audit:'+_hash(observed)))


def deterministic_observations(connection, settings, repository, *, paths=(), catalog=None):
    catalog,current,selected,links,location=current_graph(connection,settings,repository,paths=paths,catalog=catalog)
    rested=set()
    for group in links.values():
        for item in group:
            if item['originId']:rested.add(item['originId'])
            resolved=catalog.resolve(item['link']['origin'],purpose='endpoint')
            if resolved.state=='resolved':rested.add(resolved.selection.members[0].chunk.identifier)
    marks={str(identifier):metadata.get('needsNothing') for identifier,metadata in connection.execute(
        "SELECT id,metadata FROM public.mycel_chunks WHERE repository=%s AND kind='req'",(repository,)).fetchall()}
    for mark in marks.values():
        if mark is not None and (not isinstance(mark,dict) or set(mark)!={'who','when','reason'} or any(not isinstance(v,str) or not v.strip() for v in mark.values())):
            raise MycelError('store_format','A needs-nothing mark has incompatible metadata.')
    result=[]
    def add(kind,file,member,facts,disputed=(),evidence_files=()):
        result.append((observation(repository,location,kind,public_reference(_selection(file,member)),
            member.place.path,facts={**facts,'subjectVersion':member.chunk.snapshot_hash},
            links=[item['claim'] for item in disputed]),(_chunk_snapshot(member,file),)+
            tuple(snapshot(item.source,place=item.primary) for item in {item.identifier:item for item in evidence_files}.values())))
    for version,(file,member) in selected.items():
        chunk=member.chunk;ref=public_reference(_selection(file,member));own=links.get(version,[])
        if chunk.kind=='req' and (chunk.entity or {}).get('status')!='withdrawn' and chunk.identifier not in rested and marks.get(chunk.identifier) is None:
            add('unresting_requirement',file,member,{'version':chunk.snapshot_hash})
        if chunk.kind not in {'document','req','dec'} and not own:
            add('missing_origin',file,member,{'version':chunk.snapshot_hash})
        if chunk.kind=='dec' and not (chunk.entity or {}).get('discussion'):
            add('missing_discussion',file,member,{'version':chunk.snapshot_hash})
        chapters={};requirements=[]
        for item in own:
            origin=catalog.resolve(item['link']['origin'],purpose='endpoint')
            if origin.state=='resolved' and len(origin.selection.members)==1 and origin.selection.members[0].chunk.kind=='req':
                place=origin.selection.place;chapters.setdefault((place.repository,place.root,place.path),[]).append(item['id']);requirements.append(item)
        if len(chapters)>1:
            add('multiple_chapters',file,member,{'chapters':[list(key) for key in sorted(chapters)]},requirements)
    grouped={}
    for owner,version,reason in current_stale_reasons(connection,settings,selected):
        if owner==repository and version in selected:
            grouped.setdefault(version,[]).append({key:value for key,value in reason.items() if key!='classification'})
    for version,reasons in grouped.items():
        file,member=selected[version];add('stale_chain',file,member,{'reasons':sorted(reasons,key=lambda item:canonical_json(item))},links.get(version,[]))
    # Parsing uses only retained complete file bytes. Physical aliases occur once.
    seen_files=set();ids={};uuid_faults={};glossaries=set()
    files=[file for file in catalog.files if file.repository==repository]
    for file in catalog.files:
        for alias in file.aliases:
            if PurePosixPath(alias.path).name.casefold()=='glossary.md':glossaries.add((alias.repository,alias.root,alias.path))
    for file in files:
        if file.identifier in seen_files:continue
        seen_files.add(file.identifier)
        if not any(chunk.kind in {'document','req','dec'} for chunk in file.chunks):continue
        parsed=split_markdown(file.source)
        for row in parsed.entities:
            ids.setdefault(('human',row.id),[]).append((file,row))
            ids.setdefault(('uuid',row.uuid),[]).append((file,row))
        for fault in parsed.diagnostics:
            if fault.code=='entity_repeated_uuid':
                match=re.search(r'UUID ([0-9a-f-]{36})',fault.message)
                if match:uuid_faults.setdefault(match[1],[]).append((file,fault.line))
        for group in file.document_declarations.chunk_sources:
            members=[member for member in catalog._members(file,file.chunks) if member.chunk.name==group.chunk]
            if not members:continue
            member=members[0]
            if not _in_path(member.place.path,paths):continue
            for declared in group.sources:
                try:place=parse_source_address(declared.ref)
                except SourceAddressError:continue
                if place.name is None or not any(owner==place.repository and path==place.path and (place.root is None or root==place.root) for owner,root,path in glossaries):continue
                resolved=catalog.resolve(declared.ref,purpose='endpoint')
                if resolved.state!='resolved':
                    targets=tuple(item for item in catalog.files if any(alias.repository==place.repository and alias.path==place.path and (place.root is None or alias.root==place.root) for alias in item.aliases))
                    add('missing_term',file,member,{'term':place.name,'glossary':place.address,'state':resolved.state,
                        'glossaryVersions':sorted(item.snapshot_hash for item in targets)},evidence_files=targets)
    for (kind,value),rows in ids.items():
        unique={(file.identifier,row.byte_start):(file,row) for file,row in rows}
        if len(unique)<2:continue
        rows=list(unique.values());file,row=rows[0]
        if not any(_in_path(item.primary.path,paths) for item,_ in rows):continue
        candidates=catalog._members(file,file.chunks);member=next((m for m in candidates if m.chunk.name==row.section),candidates[0])
        add('duplicate_id',file,member,{'identityKind':kind,'identity':value,
            'occurrences':sorted(file.primary.address+':'+str(row.line) for file,row in rows),
            'fileVersions':sorted({item.snapshot_hash for item,_ in rows})},evidence_files=tuple(item for item,_ in rows))
    for value,rows in uuid_faults.items():
        file,line=rows[0]
        if not _in_path(file.primary.path,paths):continue
        members=catalog._members(file,file.chunks);offset=sum(len(part) for part in file.source.splitlines(keepends=True)[:line-1]);member=next((m for m in members if m.chunk.span and m.chunk.span[0]<=offset<m.chunk.span[1]),members[0])
        add('duplicate_id',file,member,{'identityKind':'uuid','identity':value,
            'occurrences':sorted(file.primary.address+':'+str(line) for file,line in rows),
            'fileVersions':sorted({item.snapshot_hash for item,_ in rows})},evidence_files=tuple(item for item,_ in rows))
    unique={finding_id(value):(value,blobs) for value,blobs in result}
    return [unique[key] for key in sorted(unique)]


class AuditStore(RecoveryStore):
    def _rows(self,repository):
        return self.connection.execute("SELECT hash,bytes,metadata FROM public.mycel_manifests "
            "WHERE repository=%s AND kind='origin_audit_finding' ORDER BY hash",(repository,)).fetchall()

    def _wire(self,row):
        digest,raw,metadata=row
        try:
            observed=json.loads(bytes(raw));wire=metadata['finding']
            if (type(metadata.get('schema')) is not int or metadata.get('schema')!=1 or canonical_json(observed)!=bytes(raw) or _hash(observed)!=digest or observed['schema']!=SCHEMA or wire['id']!=finding_id(observed)
                    or wire['observationHash']!=digest or wire['state'] not in {'open','settled'}
                    or wire['kind'] not in DETERMINISTIC+SEMANTIC
                    or any(wire[key]!=observed[key] for key in ('kind','repository','location','subject','path','links','facts'))):raise ValueError()
            _time(wire['openedAt'])
            semantic=observed['kind'] in SEMANTIC
            if (set(observed)!={'schema','repository','location','kind','subject','path','links','facts'} | ({'inputHash'} if semantic else set())
                    or wire['mode']!=('semantic' if semantic else 'deterministic')
                    or not isinstance(observed['facts'],dict) or not isinstance(observed['links'],list)
                    or any(not isinstance(observed[key],str) or not observed[key] for key in ('repository','location','subject','path'))):raise ValueError()
            if semantic:
                score=wire['confidenceScore'];record=wire['evidence']['record']
                if (type(score) not in {int,float} or not math.isfinite(score) or not 0<=score<=1
                        or wire['evidence']['inputHash']!=observed['inputHash']
                        or record['inputHash']!=observed['inputHash'] or record['status']!='complete'
                        or record['judgement']!=wire['kind'] or record['confidenceScore']!=score):raise ValueError()
            if wire['state']=='open' and 'settlement' in wire:raise ValueError()
            if wire['state']=='settled':
                closed=wire['settlement'];_time(closed['when'])
                if set(closed)!={'who','when','reason'}:raise ValueError()
                if any(not isinstance(closed[key],str) or not closed[key].strip() for key in ('who','reason')):raise ValueError()
            return wire
        except (KeyError,TypeError,ValueError,MycelError):
            raise MycelError('store_format','A retained Origin audit finding has incompatible state.') from None

    def list_in_transaction(self,settings,repository,*,paths=(),closed=False):
        location=RepositoryLocations(settings).named(repository)[0].disk_location
        values=[self._wire(row) for row in self._rows(repository)]
        return sorted((row for row in values if row['location']==location and _in_path(row['path'],paths)
                       and (closed or row['state']=='open')),key=lambda row:(row['kind'],row['subject'],row['id']))

    def open_in_transaction(self,observed,*,at,blobs=(),record=None,request_hash=None):
        repository=observed['repository'];digest=_hash(observed);raw=canonical_json(observed)
        row=self.connection.execute('SELECT hash,bytes,metadata FROM public.mycel_manifests '
            'WHERE repository=%s AND hash=%s FOR UPDATE NOWAIT',(repository,digest)).fetchone()
        if row is not None:return self._wire(row),False
        wire={'id':finding_id(observed),'observationHash':digest,**{key:observed[key] for key in
            ('kind','repository','location','subject','path','links','facts')},'mode':'deterministic' if observed['kind'] in DETERMINISTIC else 'semantic',
            'state':'open','openedAt':at}
        if record is not None:wire.update(confidenceScore=record['confidenceScore'],evidence={'inputHash':request_hash,'record':record})
        self.connection.execute('INSERT INTO public.mycel_manifests VALUES (%s,%s,%s,%s,%s)',
            (repository,digest,'origin_audit_finding',raw,Jsonb({'schema':1,'finding':wire})))
        owner=uuid4();self.connection.execute('INSERT INTO public.mycel_evidence_owners VALUES (%s,%s,%s,%s,NULL)',
            (owner,repository,'origin_audit_finding',digest))
        self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,0)',(owner,repository,digest))
        if request_hash is not None:self.connection.execute('INSERT INTO public.mycel_evidence_references VALUES (%s,%s,NULL,%s,1)',(owner,repository,request_hash))
        DriftStore(self.connection)._retain(repository,owner,blobs)
        return wire,True

    def deterministic(self,settings,repository,*,paths=(),dry_run=False,closed=False,at=None,activity=None):
        paths=normalize_paths(paths);at=at or _at();new=[]
        if dry_run:
            with checked_store(self.connection),read_snapshot(self.connection):
                observed=deterministic_observations(self.connection,settings,repository,paths=paths)
                stored=self.list_in_transaction(settings,repository,paths=paths,closed=closed)
                known={self._wire(row)['id'] for row in self._rows(repository)};proposed=[]
                for value,_ in observed:
                    if finding_id(value) not in known:proposed.append({'id':finding_id(value),**value,'state':'proposed','mode':'deterministic'})
                return stored+proposed,0
        with self.guarded(settings) as catalog:
            for value,blobs in deterministic_observations(self.connection,settings,repository,paths=paths,catalog=catalog):
                finding,created=self.open_in_transaction(value,at=at,blobs=blobs)
                if created:new.append(finding)
            if new and activity is not None:activity.record_in_transaction(repository,'audit',AppliedMutation(True,{'newFindings':len(new)}))
            self.prune_in_transaction(repository)
            return self.list_in_transaction(settings,repository,paths=paths,closed=closed),len(new)

    def settle(self,settings,repository,identifier,*,reason,by=None,at=None,activity=None):
        try:identifier=str(UUID(identifier))
        except (ValueError,TypeError,AttributeError):raise MycelError('invalid_input','Settlement requires an exact finding UUID.') from None
        if not isinstance(reason,str) or not reason.strip():raise MycelError('invalid_input','Settlement requires a nonempty reason.')
        by=_identity(by);at=at or _at();location=RepositoryLocations(settings).named(repository)[0].disk_location
        with self.guarded(settings):
            found=[(row,self._wire(row)) for row in self._rows(repository) if self._wire(row)['id']==identifier]
            if len(found)!=1 or found[0][1]['location']!=location:raise MycelError('invalid_input','The finding is unavailable in this repository and clone.')
            row,wire=found[0]
            if wire['state']=='settled':
                if wire['settlement']['reason']!=reason.strip() or wire['settlement']['who']!=by:
                    raise MycelError('invalid_input','A recorded settlement cannot be replaced.')
                return wire,False
            wire={**wire,'state':'settled','settlement':{'who':by,'when':at,'reason':reason.strip()}}
            self.connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                (Jsonb({'schema':1,'finding':wire}),repository,row[0]))
            if activity is not None:activity.record_in_transaction(repository,'audit',AppliedMutation(True,{'settled':1,'finding':identifier}))
            self.prune_in_transaction(repository)
            return wire,True

    def _release(self,owner,repository):
        refs=self.connection.execute('SELECT snapshot_hash,manifest_hash FROM public.mycel_evidence_references WHERE owner=%s',(owner,)).fetchall()
        self.connection.execute('DELETE FROM public.mycel_evidence_owners WHERE id=%s',(owner,))
        for blob,manifest in refs:
            if manifest is not None:self.connection.execute('DELETE FROM public.mycel_manifests m WHERE repository=%s AND hash=%s '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_evidence_references r WHERE r.repository=m.repository AND r.manifest_hash=m.hash)',(repository,manifest))
            if blob is not None:self.connection.execute('DELETE FROM public.mycel_snapshots s WHERE repository=%s AND hash=%s '
                'AND NOT EXISTS(SELECT 1 FROM public.mycel_evidence_references r WHERE r.repository=s.repository AND r.snapshot_hash=s.hash)',(repository,blob))

    def prune_in_transaction(self,repository):
        for row in self._rows(repository):self._wire(row)
        older=self.connection.execute("SELECT o.id FROM public.mycel_evidence_owners o JOIN public.mycel_manifests m "
            "ON m.repository=o.repository AND m.hash=o.identity WHERE o.repository=%s AND o.kind='origin_audit_finding' "
            "AND m.metadata->'finding'->>'state'='settled' ORDER BY m.metadata->'finding'->'settlement'->>'when' DESC,"
            "m.metadata->'finding'->>'id' DESC OFFSET %s",(repository,RETENTION)).fetchall()
        for owner, in older:self._release(owner,repository)
        leases=self.connection.execute("SELECT id,invocation FROM public.mycel_evidence_owners WHERE repository=%s "
            "AND kind='origin_audit_request' AND invocation IS NOT NULL",(repository,)).fetchall()
        for owner,invocation in leases:
            if not invocation_is_live(self.connection,invocation):self.connection.execute(
                'UPDATE public.mycel_evidence_owners SET invocation=NULL WHERE id=%s',(owner,))
        older=self.connection.execute("SELECT o.id FROM public.mycel_evidence_owners o JOIN public.mycel_manifests m "
            "ON m.repository=o.repository AND m.hash=o.identity WHERE o.repository=%s AND o.kind='origin_audit_request' "
            "AND o.invocation IS NULL AND NOT EXISTS(SELECT 1 FROM public.mycel_evidence_references r "
            "JOIN public.mycel_evidence_owners f ON f.id=r.owner WHERE r.repository=o.repository "
            "AND r.manifest_hash=o.identity AND f.kind='origin_audit_finding') "
            "ORDER BY m.metadata->>'at' DESC,o.identity DESC OFFSET %s",(repository,RETENTION)).fetchall()
        for owner, in older:self._release(owner,repository)
