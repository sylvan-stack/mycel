"""Exact summary captures and named disposable configured-store checks."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from psycopg.types.json import Jsonb

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._evidence import EvidenceError, canonical_json, document_comparisons
from mycel._locks import invocation_guard
from mycel._markdown import split_markdown
from mycel._resolver import ResolvedChunk, ResolvedFile, SelectionMember
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress
from mycel._summary_evidence import (CUT_NOTICE, GenerationCapture, GenerationEvidenceStore,
    GenerationManifest, GenerationMember, capture_generation)
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
    @proves('MYC-8.9', 'MYC-8.12')
    def test_capture_keeps_raw_prompts_literal_argv_full_sources_and_canonical_immutable_manifest(self):
        file = document()
        requests, captures = planned(file)
        capture, = captures
        request, = requests
        payload = capture.manifest.payload
        self.assertEqual(blob(capture, payload['request']), request.request)
        self.assertEqual(blob(capture, payload['instruction']), PROMPTS.instruction)
        self.assertEqual(blob(capture, payload['task']), PROMPTS.task)
        self.assertEqual(payload['command'], ('literal-writer', '$(literal)', '', '~literal'))
        self.assertEqual(payload['commandHash'], sha256(canonical_json(payload['command'])).hexdigest())
        member, = payload['members']
        self.assertEqual(member['place']['address'], selections(file)[0].place.address)
        self.assertEqual((member['id'], member['version']), (file.chunks[0].identifier, 1))
        self.assertEqual(blob(capture, member['source']), file.chunks[0].source)
        self.assertEqual(blob(capture, member['sent']), file.chunks[0].source)
        self.assertFalse(member['cut'])
        self.assertEqual(GenerationManifest.from_bytes(capture.manifest.canonical_bytes,
                                                      capture.manifest.identifier), capture.manifest)
        with self.assertRaises(TypeError):
            payload['members'][0]['version'] = 99
        raw = json.loads(capture.manifest.canonical_bytes)
        independent = GenerationManifest(raw)
        raw['members'][0]['comparison']['body']['hash'] = '0' * 64
        self.assertEqual(independent, capture.manifest)

    @proves('MYC-8.11')
    def test_cut_keeps_complete_unicode_source_and_exact_sent_prefix_notice_without_omitted_members(self):
        file = document('# Source\n' + '🙂雪' * 30_000)
        requests, captures = planned(file)
        request, = requests
        capture, = captures
        member, = capture.manifest.payload['members']
        sent = blob(capture, member['sent'])
        self.assertTrue(member['cut'])
        self.assertEqual(blob(capture, member['source']), file.chunks[0].source)
        self.assertTrue(sent.endswith(CUT_NOTICE.encode()))
        self.assertTrue(file.chunks[0].source.startswith(sent[:-len(CUT_NOTICE.encode())]))
        self.assertEqual(len(request.request.decode()), 48_000)
        response = '  Exact response 雪\r\n\0end.  '.encode()
        completed = capture.with_response(response)
        self.assertEqual(blob(completed, completed.manifest.payload['response']), response)
        self.assertNotEqual(completed.manifest.identifier, capture.manifest.identifier)
        self.assertNotIn('response', capture.manifest.payload)

    @proves('MYC-8.9', 'MYC-8.12')
    def test_changed_framing_corrupt_descriptors_order_and_unsupported_comparison_are_refused(self):
        file = document('# First\nOne.\n# Second\nTwo.\n')
        _, captures = planned(file)
        original, = captures
        for mutation in (
                lambda value: value['members'].reverse(),
                lambda value: value['members'][0].update(cut=True),
                lambda value: value.update(commandHash='0' * 64),
                lambda value: value['request'].update(bytes=0),
                lambda value: value['members'][0]['place'].update(address='source:@artifact/wrong.md#First'),
                lambda value: value['members'][0]['comparison']['body'].update(revision='unknown')):
            value = json.loads(original.manifest.canonical_bytes)
            mutation(value)
            with self.assertRaises(EvidenceError):
                GenerationCapture(GenerationManifest(value), original.snapshots)
        member = selections(file)[0]
        with self.assertRaises(EvidenceError):
            GenerationMember(member, b'omitted complete text')
        with self.assertRaises(EvidenceError):
            GenerationMember(member, b'unrelated' + CUT_NOTICE.encode(), True)
        with self.assertRaises(EvidenceError):
            original.with_response(b' \n\t')
        with self.assertRaises(EvidenceError):
            original.with_response(b'\xff')
        with self.assertRaises(EvidenceError):
            GenerationManifest.from_bytes(original.manifest.canonical_bytes + b' ', original.manifest.identifier)
        kwargs = dict(request=b'wrong request', instruction=PROMPTS.instruction, task=PROMPTS.task,
                      command=('literal',))
        with self.assertRaises(EvidenceError):
            capture_generation('owner', (GenerationMember(member, member.chunk.source),), **kwargs)

    @proves('MYC-8.9')
    def test_fileless_higher_level_summary_has_exact_member_identity_and_no_mutable_source_pointer(self):
        source = b'Complete lower-level summary.'
        chunk = ResolvedChunk(str(uuid4()), 7, '1/2', 'summary', source, sha256(source).hexdigest())
        member = SelectionMember(SourceAddress('owner', 'index', 'summaries', '1/2'), chunk)
        request, = plan_summary_requests((SummarySection(member, 0),), PROMPTS)
        captured = capture_generation('owner', (GenerationMember(member, source),), request=request.request,
            instruction=PROMPTS.instruction, task=PROMPTS.task, command=('writer',), prompt_profile='override')
        self.assertEqual(captured.manifest.payload['members'][0]['place']['address'], 'owner:@index/summaries#1%2F2')
        self.assertEqual(blob(captured, captured.manifest.payload['members'][0]['source']), source)


class SummaryEvidenceStoreTests(unittest.TestCase):
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

    @proves('MYC-8.25', 'MYC-16.5', 'MYC-16.6', kind='store')
    def test_real_request_lease_response_roundtrip_is_owner_scoped_private_and_survives_source_removal(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            file = self.seed(connection)
            _, captures = planned(file)
            capture, = captures
            store = GenerationEvidenceStore(connection)
            counts = self.searchable_counts(connection)
            with invocation_guard(connection) as invocation:
                lease = store.retain(invocation, capture)
                self.assertEqual(store.read('owner', lease.manifest_hash), capture)
                self.assertEqual(connection.execute('SELECT repository,invocation FROM public.mycel_evidence_owners '
                    'WHERE id=%s', (lease.owner_id,)).fetchone(), ('owner', invocation.id))
                self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_snapshots WHERE repository=%s',
                    ('source',)).fetchone()[0], 0)
                response = '  Complete answer 雪🙂\r\n\0end  '.encode()
                completed_lease = store.retain_response(invocation, lease, response)
                completed = capture.with_response(response)
                self.assertEqual(store.read('owner', completed_lease.manifest_hash), completed)
                self.assertEqual(store.read('owner', lease.manifest_hash), capture)
                self.assertEqual(self.searchable_counts(connection), counts)
                with self.assertRaises(EvidenceError):
                    store.retain_response(invocation, lease, b'different output')
                self.assertEqual(store.retain_response(invocation, completed_lease, response), completed_lease)
            connection.execute('DELETE FROM public.mycel_files WHERE repository=%s', ('source',))
            self.assertEqual(store.read('owner', completed_lease.manifest_hash), completed)
            with self.assertRaises(EvidenceError) as fault:
                store.read('source', completed_lease.manifest_hash)
            self.assertEqual(fault.exception.status, 'baseline_missing')

    @proves('MYC-8.25', 'MYC-16.6', kind='store')
    def test_real_cut_evidence_retains_uncut_source_and_exact_sent_utf8_prefix_and_notice(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            file = self.seed(connection, document('# Source\n' + '🙂雪' * 30_000))
            requests, captures = planned(file)
            capture, = captures
            store = GenerationEvidenceStore(connection)
            with invocation_guard(connection) as invocation:
                lease = store.retain(invocation, capture)
                retained = store.read('owner', lease.manifest_hash)
                member, = retained.manifest.payload['members']
                self.assertEqual(blob(retained, member['source']), file.chunks[0].source)
                self.assertEqual(blob(retained, member['sent']), requests[0].sent_texts[0])
                self.assertNotEqual(member['source']['hash'], member['sent']['hash'])
                self.assertEqual(len(blob(retained, retained.manifest.payload['request']).decode()), 48_000)

    @proves('MYC-8.25', 'MYC-16.9', kind='store')
    def test_real_corrupt_snapshot_or_manifest_metadata_refuses_read_and_response_without_partial_writes(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            file = self.seed(connection)
            _, captures = planned(file)
            capture, = captures
            store = GenerationEvidenceStore(connection)
            with invocation_guard(connection) as invocation:
                lease = store.retain(invocation, capture)
                counts = self.evidence_counts(connection)
                descriptor = capture.manifest.payload['members'][0]['source']
                connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 1, 'bytes': 0, 'encoding': 'utf-8'}), 'owner', descriptor['hash']))
                for call in (lambda: store.read('owner', lease.manifest_hash),
                             lambda: store.retain(invocation, capture),
                             lambda: store.retain_response(invocation, lease, b'answer')):
                    with self.assertRaises(EvidenceError) as fault:
                        call()
                    self.assertEqual(fault.exception.status, 'snapshot_corrupt')
                self.assertEqual(self.evidence_counts(connection), counts)
                connection.execute('UPDATE public.mycel_snapshots SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 1, 'bytes': descriptor['bytes'], 'encoding': 'utf-8'}), 'owner', descriptor['hash']))
                connection.execute('UPDATE public.mycel_manifests SET metadata=%s WHERE repository=%s AND hash=%s',
                    (Jsonb({'schema': 2}), 'owner', lease.manifest_hash))
                with self.assertRaises(EvidenceError) as fault:
                    store.read('owner', lease.manifest_hash)
                self.assertEqual(fault.exception.status, 'snapshot_corrupt')

    @proves('MYC-8.25', 'MYC-16.13', kind='store')
    def test_real_foreign_nonactive_and_forged_invocations_or_changed_member_addresses_cannot_retain(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            file = self.seed(connection)
            _, captures = planned(file)
            capture, = captures
            store = GenerationEvidenceStore(connection)
            with invocation_guard(connection) as invocation:
                for forged in (replace(invocation, backend_pid=invocation.backend_pid + 1),
                               replace(invocation, liveness_key=invocation.liveness_key + 1),
                               replace(invocation, index_generation=uuid4())):
                    with self.assertRaises(EvidenceError) as fault:
                        store.retain(forged, capture)
                    self.assertEqual(fault.exception.status, 'invalid_input')
                with self.store_fixture.backend.connection(self.store_fixture.database) as foreign:
                    with self.assertRaises(EvidenceError) as fault:
                        GenerationEvidenceStore(foreign).retain(invocation, capture)
                    self.assertEqual(fault.exception.status, 'invalid_input')
                connection.execute('UPDATE public.mycel_locations SET metadata=%s WHERE chunk_version=%s',
                    (Jsonb({'name': 'Changed current heading'}), file.chunks[0].version))
                with self.assertRaises(EvidenceError) as fault:
                    store.retain(invocation, capture)
                self.assertEqual(fault.exception.status, 'inputs_changed')
            with self.assertRaises(EvidenceError) as fault:
                store.retain(invocation, capture)
            self.assertEqual(fault.exception.status, 'invalid_input')
            self.assertEqual(self.evidence_counts(connection), (0, 0, 0, 0))

    @proves('MYC-8.25', 'MYC-16.13', kind='store')
    def test_real_mid_write_failure_rolls_back_entire_request_and_response_capture(self):
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            file = self.seed(connection)
            _, captures = planned(file)
            capture, = captures
            store = GenerationEvidenceStore(connection)
            write = store._write
            def injected(item):
                write(item)
                connection.execute('SELECT 1/0')
            with invocation_guard(connection) as invocation:
                with patch.object(store, '_write', injected), self.assertRaises(MycelError):
                    store.retain(invocation, capture)
                self.assertEqual(self.evidence_counts(connection), (0, 0, 0, 0))
                lease = store.retain(invocation, capture)
                counts = self.evidence_counts(connection)
                with patch.object(store, '_write', injected), self.assertRaises(MycelError):
                    store.retain_response(invocation, lease, b'exact answer')
                self.assertEqual(self.evidence_counts(connection), counts)
                self.assertEqual(store.read('owner', lease.manifest_hash), capture)

    @proves('MYC-8.25', 'MYC-16.6', kind='store')
    def test_real_generation_caller_retains_exact_stdin_cut_source_and_stdout_with_live_private_lease(self):
        from mycel._summaries import generate_summary_requests

        with self.store_fixture.backend.connection(self.store_fixture.database) as connection, tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observed = root / 'stdin.bin'
            executable = root / 'fictional-summary-command.py'
            answer = ' Exact fictional answer 雪🙂\r\n\0ending '.encode()
            executable.write_text('import pathlib, sys\n'
                'pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n'
                'sys.stdout.buffer.write(bytes.fromhex(sys.argv[2]))\n', encoding='utf-8')
            command = (sys.executable, str(executable), str(observed), answer.hex())
            config = root / 'config.toml'
            config.write_text('[summaries]\ncommand=' + json.dumps(command) + '\nat_once=1\n', encoding='utf-8')
            settings = load_settings(path=config)
            file = self.seed(connection, document('# Source\n' + '🙂雪' * 30_000, repository='owner'))
            sections = tuple(SummarySection(member, member.chunk.span[0]) for member in selections(file))
            store = GenerationEvidenceStore(connection)
            counts = self.searchable_counts(connection)
            with invocation_guard(connection) as invocation:
                result, = generate_summary_requests(settings, sections, operation='build', invocation=invocation,
                                                   evidence_store=store)
                self.assertEqual(result.result.response, answer)
                retained = store.read('owner', result.evidence.manifest_hash)
                self.assertEqual(blob(retained, retained.manifest.payload['request']), observed.read_bytes())
                self.assertEqual(observed.read_bytes(), result.request.request)
                self.assertEqual(blob(retained, retained.manifest.payload['response']), answer)
                member, = retained.manifest.payload['members']
                self.assertTrue(member['cut'])
                self.assertEqual(blob(retained, member['source']), file.chunks[0].source)
                self.assertEqual(blob(retained, member['sent']), result.request.sent_texts[0])
                self.assertEqual(retained.manifest.payload['command'], command)
                self.assertEqual(self.searchable_counts(connection), counts)
                self.assertEqual(connection.execute('SELECT invocation FROM public.mycel_evidence_owners WHERE id=%s',
                    (result.evidence.owner_id,)).fetchone(), (invocation.id,))


if __name__ == '__main__':
    unittest.main()
