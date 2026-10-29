"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_document_links as _support
from test_document_links import (
    Deadline,
    DeclaredRefStore,
    DocumentLinksStoreTests,
    Jsonb,
    declared_fixtures,
    ranking_fixtures,
    read_fixtures,
    read_from_store,
    search_from_store,
    unittest,
    uuid4,
)


class DocumentLinksStoreTests(_support.DocumentLinksStoreTests):
# TEST-TIER-BEGIN tests/test_document_links.py::DocumentLinksStoreTests.test_read_lists_both_directions_and_edge_kinds_completely_without_vectors
    def test_read_lists_both_directions_and_edge_kinds_completely_without_vectors(self):
        with self.base.connection() as connection:
            code = self.seed(connection, path='work.py', name='Work', source='needle work\n')
            expected = set()
            for index, (direction, edge) in enumerate((('source', 'declared'), ('source', 'asserted'),
                    ('dependant', 'declared'), ('dependant', 'asserted'))):
                root = 'code' if index % 2 else 'artifact'
                # Equal names and paths in distinct roots remain distinct Places.
                path = 'same.md' if index < 2 else f'guide{index}.md'
                document = self.seed(connection, root=root, path=path, kind='document',
                    name='Contract', source=f'# Contract\nSection {index}.\n')
                address = f'fixture:@{root}/{path}#Contract'
                if direction == 'source':
                    self.cite(connection, code, address, kind=edge)
                else:
                    self.cite(connection, document, 'fixture:@code/work.py#Work', kind=edge)
                expected.add((address, direction, edge))
            # Repeated equivalent declarations must not duplicate a DocumentLink.
            self.cite(connection, code, 'fixture:@artifact/same.md#Contract', kind='declared')
            before = self.base.contents(connection)
            reply = self.read(connection, code[1])
            self.assertEqual(self.signatures(reply), expected)
            self.assertEqual(len(reply['documents']), 4)
            for link in reply['documents']:
                place = link['section']
                self.assertEqual(place['repository'], 'fixture')
                self.assertEqual(place['name'], 'Contract')
                self.assertIn(place['root'], ('artifact', 'code'))
                self.assertEqual(place['address'], f"fixture:@{place['root']}/{place['path']}#Contract")
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
            self.assertEqual(self.base.contents(connection), before)
# TEST-TIER-END tests/test_document_links.py::DocumentLinksStoreTests.test_read_lists_both_directions_and_edge_kinds_completely_without_vectors

# TEST-TIER-BEGIN tests/test_document_links.py::DocumentLinksStoreTests.test_actual_declared_whole_file_and_class_family_describe_each_selected_code_chunk
    def test_actual_declared_whole_file_and_class_family_describe_each_selected_code_chunk(self):
        header = 'class Worker:\n    flag = True\n'
        method = '    def run(self):\n        return self.flag\n'
        other = '\ndef independent():\n    return 2\n'
        with self.base.connection() as connection:
            members = self.reads.seed(connection, 'src/work.py', header + method + other,
                (('Worker', 'class', header, {}), ('Worker.run', 'method', method, {'family': 'Worker'}),
                 ('independent', 'function', other, {})))
            for path, title, target in (('whole.md', 'Whole', 'fixture:@code/src/work.py'),
                                       ('family.md', 'Family', 'fixture:@code/src/work.py#Worker')):
                raw = f'# {title}\n<!-- sources:\n{target}\n-->\n'
                location, _, _, _ = declared_fixtures.seed_document(connection, 'fixture', path, raw)
                declared_fixtures.retain(connection, self.settings, location, raw)
            result = DeclaredRefStore(connection).recheck(self.settings, repository='fixture')
            self.assertTrue(all(ref.state == 'resolved' for ref in result.refs), result)
            before = self.base.contents(connection)
            whole = ('fixture:@artifact/whole.md#Whole', 'dependant', 'declared')
            family = ('fixture:@artifact/family.md#Family', 'dependant', 'declared')
            for name, member in members.items():
                with self.subTest(name=name):
                    expected = {whole, family} if name.startswith('Worker') else {whole}
                    self.assertEqual(self.signatures(self.read(connection, member[0])), expected)
            self.assertEqual(self.base.contents(connection), before)
# TEST-TIER-END tests/test_document_links.py::DocumentLinksStoreTests.test_actual_declared_whole_file_and_class_family_describe_each_selected_code_chunk

# TEST-TIER-BEGIN tests/test_document_links.py::DocumentLinksStoreTests.test_current_anchored_versions_replace_old_pins_and_stale_marks_do_not_hide_links
    def test_current_anchored_versions_replace_old_pins_and_stale_marks_do_not_hide_links(self):
        with self.base.connection() as connection:
            old_code = self.seed(connection, path='work.py', name='OldWork', source='old work\n')
            old_doc = self.seed(connection, path='contract.md', root='artifact', name='OldContract',
                                kind='document', source='# OldContract\nOld body.\n')
            obsolete = self.seed(connection, path='obsolete.md', root='artifact', name='Obsolete',
                                 kind='document', source='# Obsolete\nNo current owner.\n')
            self.cite(connection, old_code, 'fixture:@artifact/obsolete.md#Obsolete')
            self.cite(connection, old_doc, 'fixture:@code/work.py#OldWork')
            self.make_historical(connection, old_code[0])
            self.make_historical(connection, old_doc[0])
            code = self.seed(connection, file_id=old_code[0], chunk_id=old_code[1], path='work.py',
                             name='CurrentWork', source='current needle work\n')
            document = self.seed(connection, file_id=old_doc[0], chunk_id=old_doc[1], root='artifact',
                path='contract.md', name='CurrentContract', kind='document', source='# CurrentContract\nChanged.\n')
            self.cite(connection, code, 'fixture:@artifact/contract.md#OldContract', kind='asserted',
                      anchor=old_doc[1], pinned=old_doc[2])
            self.cite(connection, document, 'fixture:@code/work.py#OldWork',
                      anchor=old_code[1], pinned=old_code[2])
            reason = {'kind': 'source_changed', 'edge': 'asserted', 'source': {
                'repository': 'fixture', 'root': 'artifact', 'path': 'contract.md',
                'name': 'CurrentContract', 'address': 'fixture:@artifact/contract.md#CurrentContract'}}
            connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,NULL,%s)',
                               (uuid4(), 'fixture', code[2], Jsonb(reason)))
            before = self.base.contents(connection)
            reply = self.read(connection, code[1])
            self.assertTrue(reply['stale'], reply)
            self.assertEqual(reply['name'], 'CurrentWork')
            self.assertEqual(self.signatures(reply), {
                ('fixture:@artifact/contract.md#CurrentContract', 'source', 'asserted'),
                ('fixture:@artifact/contract.md#CurrentContract', 'dependant', 'declared')})
            self.assertEqual(len(reply['documents']), 2)
            self.assertEqual(self.read(connection, obsolete[1])['documents'], [])
            self.assertEqual(self.base.contents(connection), before)
            # A section removed from disk stops describing immediately, even
            # while its exact versions, old pins and declarations remain stored.
            self.make_historical(connection, document[0])
            self.assertEqual(self.read(connection, code[1])['documents'], [])
# TEST-TIER-END tests/test_document_links.py::DocumentLinksStoreTests.test_current_anchored_versions_replace_old_pins_and_stale_marks_do_not_hide_links

# TEST-TIER-BEGIN tests/test_document_links.py::DocumentLinksStoreTests.test_relations_generated_edges_other_code_transitive_and_branch_only_sections_do_not_describe
    def test_relations_generated_edges_other_code_transitive_and_branch_only_sections_do_not_describe(self):
        with self.base.connection() as connection:
            code = self.seed(connection, path='work.py', name='Work', source='needle\n')
            intermediary = self.seed(connection, path='middle.py', name='Middle', source='middle\n')
            self.cite(connection, code, 'fixture:@code/middle.py#Middle', kind='asserted')
            document = self.seed(connection, path='guide.md', root='artifact', kind='document', name='Guide',
                                 source='# Guide\nA transitive relation.\n')
            self.cite(connection, document, 'fixture:@code/middle.py#Middle')
            self.cite(connection, intermediary, 'fixture:@artifact/guide.md#Guide', kind='asserted')
            self.cite(connection, document, 'fixture:@code/work.py#Work', kind='generated')
            connection.execute('INSERT INTO public.mycel_relations VALUES (%s,%s,%s,%s,%s,NULL)',
                (uuid4(), 'fixture', code[2], 'fixture:@artifact/guide.md#Guide', Jsonb({})))
            hidden = self.seed(connection, path='branch.md', root='artifact', kind='document', name='Branch',
                               source='# Branch\nBranch only.\n', location_kind='branch')
            self.cite(connection, hidden, 'fixture:@code/work.py#Work')
            self.cite(connection, code, 'fixture:@artifact/branch.md#Branch', kind='asserted', pinned=hidden[2])
            disabled = self.seed(connection, repository='disabled', path='hidden.md', root='artifact',
                                 kind='document', name='Disabled', source='# Disabled\nHidden.\n')
            self.cite(connection, disabled, 'fixture:@code/work.py#Work')
            file_version = connection.execute('SELECT file_version FROM public.mycel_file_locations '
                'WHERE id=(SELECT file_location FROM public.mycel_locations WHERE chunk_version=%s)',
                (document[2],)).fetchone()[0]
            branch = uuid4()
            connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,'branch','feature','{}')",
                               (branch, file_version))
            connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,'branch','feature','{}')",
                               (uuid4(), document[2], branch))
            self.cite(connection, document, 'fixture:@code/work.py#Work', location=branch)
            for kind in ('summary', 'overview'):
                generated = self.reads.generated(connection, kind=kind, name='1/1' if kind == 'summary' else 'Work')
                connection.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)',
                    (uuid4(), 'fixture', generated[1], 'fixture:@code/work.py#Work',
                     'fixture:@code/work.py#Work', 'asserted', Jsonb({})))
                self.cite(connection, code, generated[2], kind='asserted')
            before = self.base.contents(connection)
            self.assertEqual(self.read(connection, code[1])['documents'], [])
            reply = search_from_store(connection, self.settings, 'needle', ('fixture',),
                only='code', deadline=Deadline.after(30), no_fresh=True)
            self.assertFalse(next(row for row in reply['results'] if row['id'] == str(code[1]))['described'])
            self.assertEqual(self.base.contents(connection), before)
# TEST-TIER-END tests/test_document_links.py::DocumentLinksStoreTests.test_relations_generated_edges_other_code_transitive_and_branch_only_sections_do_not_describe

# TEST-TIER-BEGIN tests/test_document_links.py::DocumentLinksStoreTests.test_search_described_is_query_independent_and_uses_unembedded_unselected_documents
    def test_search_described_is_query_independent_and_uses_unembedded_unselected_documents(self):
        with self.base.connection() as connection:
            described = self.seed(connection, path='work.py', name='Policy', source='needle Policy\n')
            bare = self.seed(connection, path='bare.py', name='Bare', source='needle Bare\n')
            document = self.seed(connection, repository='handbook', root='artifact', path='unselected.md',
                kind='document', name='Governing', source='# Governing\nDifferent terminology.\n')
            self.cite(connection, described, 'handbook:@artifact/unselected.md#Governing', kind='asserted')
            before = self.base.contents(connection)
            for query in ('Policy Bare', 'how does needle work'):
                with self.subTest(query=query):
                    reply = search_from_store(connection, self.settings, query, ('fixture',),
                        only='code', k=20, deadline=Deadline.after(30), no_fresh=True)
                    results = {row['id']: row for row in reply['results']}
                    self.assertTrue(results[str(described[1])]['described'])
                    self.assertFalse(results[str(bare[1])]['described'])
                    self.assertEqual(results[str(described[1])]['documentedIn'], [])
                    self.assertNotIn(str(document[1]), results)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
            self.assertEqual(self.base.contents(connection), before)
# TEST-TIER-END tests/test_document_links.py::DocumentLinksStoreTests.test_search_described_is_query_independent_and_uses_unembedded_unselected_documents
