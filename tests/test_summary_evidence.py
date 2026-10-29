# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Exact summary captures and named disposable configured-store checks."""

import json
import unittest
from dataclasses import replace
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from mycel._evidence import canonical_json, document_comparisons
from mycel._markdown import split_markdown
from mycel._resolver import ResolvedChunk, ResolvedFile, SelectionMember
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import GenerationMember, capture_generation
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests

PROMPTS = SummaryPrompts(b'  Exact instruction\r\n', b' Task before\n$sections\nafter  ', 'override')


def document(text='# Source\r\nComplete source 雪🙂\0 bytes.\r\n', *, path='source.md', repository='source'):
    parsed = split_markdown(text)
    primary = SourceAddress(repository, 'artifact', path)
    chunks = tuple(ResolvedChunk(str(uuid5(NAMESPACE_URL, f'{repository}:{path}:{chunk.name}')),
                   number + 1, chunk.name, 'document', chunk.text.encode(), chunk.snapshot_hash,
                   (chunk.span.byte_start, chunk.span.byte_end), chunk.title, None,
                   document_comparisons(chunk.body, chunk.title or ''), chunk.body.encode(),
                   (len(chunk.text.encode()) - len(chunk.body.encode()), len(chunk.text.encode())))
                   for number, chunk in enumerate(parsed.chunks))
    return ResolvedFile(str(uuid5(NAMESPACE_URL, f'file:{repository}:{path}')), repository, primary,
                        (primary,), parsed.source, parsed.file_hash, chunks)


def selections(file):
    return tuple(SelectionMember(SourceAddress(file.repository, file.primary.root, file.primary.path, chunk.name), chunk)
                 for chunk in file.chunks)


def planned(file, *, prompts=PROMPTS, command=('literal-writer', '$(literal)', '', '~literal'), owner='owner'):
    members = tuple(SummarySection(member, member.chunk.span[0]) for member in selections(file))
    requests = plan_summary_requests(members, prompts)
    captures = tuple(capture_generation(owner,
        tuple(GenerationMember(section.member, sent, section.member.place.address in request.cut,
                               position=section.position)
              for section, sent in zip(request.sections, request.sent_texts)),
        request=request.request, instruction=prompts.instruction, task=prompts.task,
        command=command, prompt_profile=prompts.profile) for request in requests)
    return requests, captures


def blob(capture, descriptor):
    return next(item.source for item in capture.snapshots if item.evidence.hash == descriptor['hash'])


class SummaryEvidenceTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class SummaryEvidenceStoreTests(unittest.TestCase):
    check_kind = "store"

    def seed(self, connection, file=None):
        file = file or document()
        for repository in ('owner', file.repository):
            connection.execute('INSERT INTO public.mycel_repository_state VALUES (%s,NULL,%s) ON CONFLICT DO NOTHING',
                               (repository, Jsonb([])))
        connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)',
            (UUID(file.identifier), file.repository, file.primary.root, file.primary.path, 'documents'))
        file_version, file_location = uuid4(), uuid4()
        connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s)',
            (file_version, UUID(file.identifier), file.snapshot_hash, file.source, Jsonb({})))
        connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s)',
            (file_location, file_version, 'disk', 'disk', Jsonb({})))
        chunks = []
        for chunk in file.chunks:
            connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s)',
                (UUID(chunk.identifier), file.repository, UUID(file.identifier), 'document', Jsonb({})))
            metadata = {'name': chunk.name, 'kind': chunk.kind, 'title': chunk.title,
                'span': {'start': chunk.span[0], 'end': chunk.span[1]},
                'bodySpan': {'start': chunk.body_span[0], 'end': chunk.body_span[1]}}
            version = connection.execute('INSERT INTO public.mycel_chunk_versions '
                '(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                (UUID(chunk.identifier), chunk.snapshot_hash, chunk.source,
                 chunk.source.decode().replace('\0', '\ufffd'), Jsonb(json.loads(canonical_json(chunk.comparison))),
                 Jsonb(metadata))).fetchone()[0]
            connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                (uuid4(), version, file_location, 'disk', 'disk', Jsonb({})))
            chunks.append(replace(chunk, version=version))
        return replace(file, chunks=tuple(chunks))

    def evidence_counts(self, connection):
        return connection.execute('SELECT (SELECT count(*) FROM public.mycel_snapshots),'
            '(SELECT count(*) FROM public.mycel_manifests),(SELECT count(*) FROM public.mycel_evidence_owners),'
            '(SELECT count(*) FROM public.mycel_evidence_references)').fetchone()

    def searchable_counts(self, connection):
        return connection.execute('SELECT (SELECT count(*) FROM public.mycel_chunks),'
            '(SELECT count(*) FROM public.mycel_chunk_versions),(SELECT count(*) FROM public.mycel_locations),'
            '(SELECT count(*) FROM public.mycel_vectors),(SELECT count(*) FROM public.mycel_activity)').fetchone()



# Archived complete imports; restore needed names in their original scope, not at this file tail.
