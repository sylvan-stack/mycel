"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_search_store as _support
from test_search_store import (
    ChunkRequirement,
    Deadline,
    DependencyFault,
    FreshnessResult,
    FreshnessScope,
    Jsonb,
    Path,
    PlanningError,
    SearchFileTests,
    SearchFreshnessStoreTests,
    SearchStoreTests,
    SimpleNamespace,
    SourceAddress,
    _Capture,
    _defaults,
    _fault_records,
    _freeze,
    _readable_file,
    checked_store,
    freshness_fixtures,
    load_settings,
    operation_guard,
    patch,
    ranking_fixtures,
    replace,
    search_from_store,
    tempfile,
    unittest,
    uuid4,
)


class SearchFileTests(_support.SearchFileTests):
# TEST-TIER-BEGIN tests/test_search_store.py::SearchFileTests.test_unpublished_upstream_fault_keeps_exact_original_places_and_honest_unknown_binding
    def test_unpublished_upstream_fault_keeps_exact_original_places_and_honest_unknown_binding(self):
        key = ('driver', 1)
        fault = DependencyFault('contract', 'not a source ref', 'not_a_ref')
        freshness = FreshnessResult(FreshnessScope(('fixture',)), (), (fault,), False, True,
            ('contract',), (ChunkRequirement('fixture', key, ('fixture', 'contract'), (fault,)),))
        selected = SimpleNamespace(chunk=SimpleNamespace(identifier=key[0], version=key[1]),
                                   place=SourceAddress('fixture', 'code', 'driver.py', 'drive'))
        resolver = SimpleNamespace(resolve=lambda ref: SimpleNamespace(candidates=()))
        places = {key: selected.place}
        upstream = (SourceAddress('contract', 'artifact', 'new.md', 'Second'),
                    SourceAddress('contract', 'artifact', 'new.md', 'First'))
        records = _fault_records(freshness, resolver, selected, places, {(key, fault): upstream})
        self.assertEqual([record['chunk']['address'] for record in records],
                         ['contract:@artifact/new.md#First', 'contract:@artifact/new.md#Second'])
        self.assertTrue(all(record['fault'] == 'not_a_ref' for record in records))
        unknown = _fault_records(freshness, resolver, selected, places)[0]['chunk']
        self.assertEqual(unknown, {'repository': 'contract', 'root': None, 'path': None,
                                   'name': None, 'address': None})
        other_key = ('other-driver', 2)
        other = SimpleNamespace(chunk=SimpleNamespace(identifier=other_key[0], version=other_key[1]),
                                place=SourceAddress('fixture', 'code', 'other.py', 'other'))
        separate = replace(freshness, chunk_requirements=(
            ChunkRequirement('fixture', key, ('fixture', 'contract'), (fault,)),
            ChunkRequirement('fixture', other_key, ('fixture', 'contract'), (fault,))))
        scoped = {(key, fault): (upstream[0],), (other_key, fault): (upstream[1],)}
        first = _fault_records(separate, resolver, selected, places, scoped)
        second = _fault_records(separate, resolver, other, places, scoped)
        self.assertEqual([item['chunk']['name'] for item in first], ['Second'])
        self.assertEqual([item['chunk']['name'] for item in second], ['First'])
        retained_key = ('upstream', 3)
        retained_fault = replace(fault, chunk=retained_key)
        retained = replace(freshness, chunk_requirements=(
            ChunkRequirement('fixture', key, ('fixture', 'contract'), (retained_fault,)),))
        old_place = SourceAddress('contract', 'artifact', 'renamed.md', 'Old')
        new_place = SourceAddress('contract', 'artifact', 'renamed.md', 'New')
        renamed = _fault_records(retained, resolver, selected,
            {**places, retained_key: old_place}, {(key, retained_fault): (new_place,)})
        self.assertEqual([item['chunk']['address'] for item in renamed],
                         ['contract:@artifact/renamed.md#New'])
# TEST-TIER-END tests/test_search_store.py::SearchFileTests.test_unpublished_upstream_fault_keeps_exact_original_places_and_honest_unknown_binding

# TEST-TIER-BEGIN tests/test_search_store.py::SearchFileTests.test_actual_root_distinguishes_collisions_and_rejects_missing_and_escaping_files
    def test_actual_root_distinguishes_collisions_and_rejects_missing_and_escaping_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            code, artifacts = base / 'checkout', base / 'artifacts'
            code.mkdir()
            artifacts.mkdir()
            (code / 'same.md').write_text('# Code document\n')
            (artifacts / 'same.md').write_text('# Artifact document\n')
            outside = base / 'outside.md'
            outside.write_text('# Outside\n')
            (code / 'escape.md').symlink_to(outside)
            config = base / 'settings.toml'
            config.write_text('[store]\naddress="postgresql://test@localhost/example"\n')
            settings = load_settings(path=config)
            settings = replace(settings, values=_freeze({**settings.values, 'repos': {
                'fixture': {**_defaults()[1], 'enabled': True,
                            'code_root': str(code), 'artifact_root': str(artifacts)}}}))
            for root, folder in (('code', code), ('artifact', artifacts)):
                value = _readable_file(SourceAddress('fixture', root, 'same.md', 'Heading'), settings)
                self.assertEqual(value, {'file': str(folder / 'same.md')})
            for path in ('missing.md', 'escape.md'):
                observed = _readable_file(SourceAddress('fixture', 'code', path, 'Heading'), settings)
                self.assertNotIn('file', observed)
                self.assertTrue(observed['unreadable'])
            missing_binding = replace(settings, values=_freeze({**settings.values, 'repos': {
                'fixture': {**_defaults()[1], 'enabled': True}}}))
            unavailable = _readable_file(SourceAddress('fixture', 'code', 'same.md', 'Heading'), missing_binding)
            self.assertEqual(unavailable, {'unreadable': 'The configured source root is unavailable.'})
# TEST-TIER-END tests/test_search_store.py::SearchFileTests.test_actual_root_distinguishes_collisions_and_rejects_missing_and_escaping_files



class SearchStoreTests(_support.SearchStoreTests):
# TEST-TIER-BEGIN tests/test_search_store.py::SearchStoreTests.test_reply_counts_current_disk_versions_with_partial_failed_and_wrong_model_coverage
    def test_reply_counts_current_disk_versions_with_partial_failed_and_wrong_model_coverage(self):
        fixture = self.base.base
        with fixture.connection() as connection:
            self.base.seed(connection, source='needle\n', path='complete.py')
            _, partial_id, partial_version = fixture.seed(connection, source='needle\nsecond\n', path='partial.py')
            fixture.plan(connection, partial_id, partial_version, 'needle\nsecond\n', split_lines=True,
                         vectors=((1.0, 0.0), None))
            _, failed_plan_id, failed_plan_version = fixture.seed(connection, source='needle\n', path='plan.py')
            fixture.plan(connection, failed_plan_id, failed_plan_version, 'needle\n',
                         plan_failure={'kind': 'planning'})
            _, failed_part_id, failed_part_version = fixture.seed(connection, source='needle\n', path='part.py')
            fixture.plan(connection, failed_part_id, failed_part_version, 'needle\n',
                         part_failure={'kind': 'content'})
            _, wrong_id, wrong_version = fixture.seed(connection, source='needle\n', path='old-model.py')
            fixture.plan(connection, wrong_id, wrong_version, 'needle\n', model='historical-model')
            fixture.seed(connection, repository='handbook', root='artifact', path='selected/guide.md',
                         kind='document', source='# Guide\nneedle\n')
            fixture.seed(connection, repository='handbook', root='artifact', path='outside.md',
                         kind='document', source='# Outside\nneedle\n')
            fixture.seed(connection, repository='disabled', source='needle\n')
            fixture.seed(connection, source='needle\n', path='branch.py', location_kind='branch')
            settings = self.base.settings(shared=({'repo': 'handbook', 'paths': ['selected']},
                                                   {'repo': 'disabled', 'paths': ['.']}))
            before = fixture.contents(connection)
            for only, expected, meaning in ((None, 5, 1), ('code', 4, 1), ('docs', 1, 0)):
                with self.subTest(only=only):
                    reply = self.search(connection, settings=settings, only=only, query_vector=self.base.query)
                    self.assertEqual(reply['schema'], 3)
                    self.assertEqual(reply['freshness']['withoutVector'], expected)
                    self.assertEqual(reply['candidates']['meaning'], meaning)
                    self.assertFalse(reply['freshness']['checked'])
                    self.assertFalse(reply['freshness']['finished'])
            self.assertEqual(fixture.contents(connection), before)
# TEST-TIER-END tests/test_search_store.py::SearchStoreTests.test_reply_counts_current_disk_versions_with_partial_failed_and_wrong_model_coverage

# TEST-TIER-BEGIN tests/test_search_store.py::SearchStoreTests.test_unavailable_pinned_tokenizer_keeps_wording_and_unverified_plan_coverage
    def test_unavailable_pinned_tokenizer_keeps_wording_and_unverified_plan_coverage(self):
        with self.base.base.connection() as connection:
            _, identifier, _ = self.base.seed(connection, source='# Answer\nneedle\n',
                path='answer.md', root='artifact', kind='document', name='Answer')
            before = self.base.base.contents(connection)
            with patch('mycel._retrieval_store.load_tokenizer',
                       side_effect=PlanningError('Pinned tokenizer is unavailable.')):
                reply = self.search(connection, only='docs',
                    meaning_reason='The complete query could not be planned with the pinned tokenizer.')
            self.assertFalse(reply['meaning']['used'])
            self.assertIn('tokenizer', reply['meaning']['reason'])
            self.assertEqual(reply['candidates']['meaning'], 0)
            self.assertEqual(reply['freshness']['withoutVector'], 1)
            self.assertEqual([row['id'] for row in reply['results']], [str(identifier)])
            self.assertEqual(self.base.base.contents(connection), before)
# TEST-TIER-END tests/test_search_store.py::SearchStoreTests.test_unavailable_pinned_tokenizer_keeps_wording_and_unverified_plan_coverage

# TEST-TIER-BEGIN tests/test_search_store.py::SearchStoreTests.test_dimension_mismatch_discards_supplied_query_vector_and_answers_by_wording_without_writes
    def test_dimension_mismatch_discards_supplied_query_vector_and_answers_by_wording_without_writes(self):
        with self.base.base.connection() as connection:
            _, identifier, _ = self.base.seed(connection, source='# Answer\nneedle\n',
                path='answer.md', root='artifact', kind='document', name='Answer')
            settings = self.base.settings()
            settings = replace(settings, values=_freeze({**settings.values,
                'embedding': {**settings.values['embedding'], 'dimensions': 512}}))
            before = self.base.base.contents(connection)
            reply = self.search(connection, settings=settings, only='docs', query_vector=self.base.query)
            self.assertFalse(reply['meaning']['used'])
            self.assertIn('dimensions', reply['meaning']['reason'])
            self.assertEqual(reply['candidates']['meaning'], 0)
            self.assertEqual(reply['freshness']['withoutVector'], 1)
            self.assertEqual([row['id'] for row in reply['results']], [str(identifier)])
            self.assertEqual(self.base.base.contents(connection), before)
# TEST-TIER-END tests/test_search_store.py::SearchStoreTests.test_dimension_mismatch_discards_supplied_query_vector_and_answers_by_wording_without_writes

# TEST-TIER-BEGIN tests/test_search_store.py::SearchStoreTests.test_same_version_has_identical_result_and_citation_marks_in_one_snapshot
    def test_same_version_has_identical_result_and_citation_marks_in_one_snapshot(self):
        with self.base.base.connection() as connection:
            code = self.base.seed(connection, path='work.py', name='Work', source='needle\n', cosine=.8)
            document = self.base.seed(connection, path='guide.md', root='code', kind='document',
                name='Guide', source='---\nstatus: heartwood\nimplemented: true\n---\n# Guide\nneedle\n', cosine=.95)
            self.base.cite(connection, document, 'fixture:@code/work.py#Work')
            reason = {'kind': 'source_changed', 'source': {'repository': 'fixture', 'root': 'code',
                'path': 'source.py', 'name': 'Source', 'address': 'fixture:@code/source.py#Source'}}
            connection.execute('INSERT INTO public.mycel_stale_reasons VALUES (%s,%s,%s,NULL,%s)',
                               (uuid4(), 'fixture', document[2], Jsonb(reason)))
            reply = self.search(connection, 'how needle works', query_vector=self.base.query)
            by_id = {item['id']: item for item in reply['results']}
            result, work = by_id[str(document[1])], by_id[str(code[1])]
            for citation in (work['via'], work['documentedIn'][0]):
                for name in ('stale', 'staleReasons', 'heartwood', 'dependencyCheck'):
                    self.assertEqual(citation[name], result[name])
                self.assertEqual(citation['address'], result['address'])
                self.assertEqual(citation['root'], 'code')
            self.assertEqual(result['origin'], 'document')
            self.assertTrue(result['stale'])
            self.assertTrue(result['heartwood'])
            self.assertFalse(result['dependencyCheck']['complete'])
# TEST-TIER-END tests/test_search_store.py::SearchStoreTests.test_same_version_has_identical_result_and_citation_marks_in_one_snapshot

# TEST-TIER-BEGIN tests/test_search_store.py::SearchStoreTests.test_each_organization_member_has_its_own_reply_and_result_limit
    def test_each_organization_member_has_its_own_reply_and_result_limit(self):
        with self.base.base.connection() as connection:
            for owner in ('fixture', 'other', 'disabled'):
                for number in range(4):
                    self.base.base.seed(connection, repository=owner, path=f'{number}.py', source='needle\n')
            reply = self.search(connection, names=('team',), settings=self.base.settings(organization=True), k=2)
            self.assertEqual(reply['organization'], 'team')
            self.assertEqual([member['repository'] for member in reply['repositories']],
                             ['fixture', 'handbook', 'other'])
            self.assertEqual([len(member['results']) for member in reply['repositories']], [2, 0, 2])
            for member in reply['repositories']:
                self.assertTrue(all(item['repository'] == member['repository'] for item in member['results']))
# TEST-TIER-END tests/test_search_store.py::SearchStoreTests.test_each_organization_member_has_its_own_reply_and_result_limit



class SearchFreshnessStoreTests(_support.SearchFreshnessStoreTests):
# TEST-TIER-BEGIN tests/test_search_store.py::SearchFreshnessStoreTests.test_recursive_freshness_marks_returned_driver_without_returning_checked_upstreams
    def test_recursive_freshness_marks_returned_driver_without_returning_checked_upstreams(self):
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            pins, outside = self.base.pins(connection), self.base.owned(connection, 'outside')
            self.base.glossary.write_bytes(b'# Glossary\nChanged governing source.\n')
            self.base.outside.write_bytes(b'# Unrelated\nUnchecked unrelated edit.\n')
            with patch('mycel._embed.embed', side_effect=AssertionError('search embedded pending chunks')):
                reply = self.search(connection)
            self.assertTrue(reply['freshness']['finished'], reply)
            self.assertTrue(reply['freshness']['checked'])
            driver = next(item for item in reply['results'] if item['name'] == 'Driver')
            self.assertTrue(driver['dependencyCheck']['complete'])
            self.assertTrue(driver['stale'])
            self.assertTrue(any(reason['kind'] == 'upstream_stale' and
                reason['via'][0]['repository'] == 'contract' for reason in driver['staleReasons']))
            self.assertTrue(all(item['repository'] == 'fixture' for item in reply['results']))
            self.assertEqual(self.base.pins(connection), pins)
            self.assertEqual(self.base.owned(connection, 'outside'), outside)
            self.assertGreater(reply['freshness']['withoutVector'], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
# TEST-TIER-END tests/test_search_store.py::SearchFreshnessStoreTests.test_recursive_freshness_marks_returned_driver_without_returning_checked_upstreams

# TEST-TIER-BEGIN tests/test_search_store.py::SearchFreshnessStoreTests.test_ref_faults_keep_only_the_affected_result_incomplete_after_finished_checks
    def test_ref_faults_keep_only_the_affected_result_incomplete_after_finished_checks(self):
        faulted = self.base.folders['fixture'] / 'faulted.md'
        faulted.write_bytes(self.base.document('Faulted', 'glossary:@artifact/missing.md#Missing'))
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            reply = self.search(connection)
            self.assertTrue(reply['freshness']['finished'], reply)
            rows = {item['name']: item for item in reply['results']}
            self.assertFalse(rows['Faulted']['dependencyCheck']['complete'])
            self.assertEqual({item['ref'] for item in rows['Faulted']['dependencyCheck']['faults']},
                             {'glossary:@artifact/missing.md#Missing'})
            self.assertTrue(rows['Independent']['dependencyCheck']['complete'])
            self.assertEqual(rows['Independent']['dependencyCheck']['faults'], [])
            self.assertTrue(rows['Driver']['dependencyCheck']['complete'])
# TEST-TIER-END tests/test_search_store.py::SearchFreshnessStoreTests.test_ref_faults_keep_only_the_affected_result_incomplete_after_finished_checks

# TEST-TIER-BEGIN tests/test_search_store.py::SearchFreshnessStoreTests.test_new_unpublished_upstream_fault_names_captured_section_in_downstream_reply
    def test_new_unpublished_upstream_fault_names_captured_section_in_downstream_reply(self):
        with self.base.base.connect() as connection, self.base.base.connect() as blocker:
            self.base.prepare(connection)
            self.base.driver.write_bytes(self.base.document('Driver', 'contract:@artifact/new.md#New'))
            second_driver = self.base.folders['fixture'] / 'second-driver.md'
            second_driver.write_bytes(self.base.document('SecondDriver', 'contract:@artifact/new.md#Other'))
            self.base.publish(connection, 'fixture')
            new_source = self.base.folders['contract'] / 'new.md'
            new_source.write_bytes(self.base.document('New', 'later:@artifact/deep.md#Deep', 'not a source ref')
                                   + b'# Other\n<!-- sources: not a source ref -->\n'
                                     b'A second new upstream section with the same malformed ref.\n')
            (self.base.folders['later'] / 'deep.md').write_bytes(b'# Deep\nA source blocked before publication.\n')
            with checked_store(blocker), operation_guard(blocker, 'later', 'pass'):
                reply = self.search(connection)
            self.assertFalse(reply['freshness']['finished'])
            driver = next(item for item in reply['results'] if item['name'] == 'Driver')
            self.assertFalse(driver['dependencyCheck']['complete'])
            malformed = [fault for fault in driver['dependencyCheck']['faults']
                         if fault['ref'] == 'not a source ref']
            self.assertEqual([fault['chunk']['address'] for fault in malformed],
                             ['contract:@artifact/new.md#New'])
            second = next(item for item in reply['results'] if item['name'] == 'SecondDriver')
            self.assertEqual([fault['chunk']['address'] for fault in second['dependencyCheck']['faults']
                              if fault['ref'] == 'not a source ref'], ['contract:@artifact/new.md#Other'])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_files "
                "WHERE repository='contract' AND path='new.md'").fetchone(), (0,))
# TEST-TIER-END tests/test_search_store.py::SearchFreshnessStoreTests.test_new_unpublished_upstream_fault_names_captured_section_in_downstream_reply

# TEST-TIER-BEGIN tests/test_search_store.py::SearchFreshnessStoreTests.test_unpublished_renamed_heading_fault_uses_captured_place_with_retained_identity
    def test_unpublished_renamed_heading_fault_uses_captured_place_with_retained_identity(self):
        with self.base.base.connect() as connection, self.base.base.connect() as blocker:
            path = self.base.folders['later'] / 'renamed.md'
            path.write_bytes(self.base.document('Old', 'glossary:@artifact/glossary.md#Glossary'))
            self.base.prepare(connection)
            self.base.publish(connection, 'later')
            self.base.contract.write_bytes(self.base.document('Contract',
                'glossary:@artifact/glossary.md#Glossary', 'later:@artifact/renamed.md#Old'))
            self.base.publish(connection, 'contract')
            original = self.base.key(connection, 'later:@artifact/renamed.md#Old')
            pins, later_before = self.base.pins(connection), self.base.owned(connection, 'later')
            path.write_bytes(self.base.document('New', 'outside:@artifact/deep.md#Deep',
                                               'not a source ref'))
            (self.base.folders['outside'] / 'deep.md').write_bytes(b'# Deep\nBlocked source.\n')
            with checked_store(blocker), operation_guard(blocker, 'outside', 'pass'):
                reply = self.search(connection)
            self.assertFalse(reply['freshness']['finished'])
            driver = next(item for item in reply['results'] if item['name'] == 'Driver')
            malformed = [fault for fault in driver['dependencyCheck']['faults']
                         if fault['ref'] == 'not a source ref']
            self.assertEqual([fault['chunk']['address'] for fault in malformed],
                             ['later:@artifact/renamed.md#New'])
            self.assertFalse(driver['dependencyCheck']['complete'])
            self.assertEqual(self.base.key(connection, 'later:@artifact/renamed.md#Old'), original)
            self.assertEqual(self.base.pins(connection), pins)
            self.assertEqual(self.base.owned(connection, 'later'), later_before)
# TEST-TIER-END tests/test_search_store.py::SearchFreshnessStoreTests.test_unpublished_renamed_heading_fault_uses_captured_place_with_retained_identity

# TEST-TIER-BEGIN tests/test_search_store.py::SearchFreshnessStoreTests.test_busy_source_and_skipped_or_expired_checks_keep_index_reply_and_unchanged_pending_source
    def test_busy_source_and_skipped_or_expired_checks_keep_index_reply_and_unchanged_pending_source(self):
        with self.base.base.connect() as connection, self.base.base.connect() as blocker:
            self.base.prepare(connection)
            source_before = self.base.owned(connection, 'glossary')
            self.base.glossary.write_bytes(b'# Glossary\nUnchecked source edit.\n')
            with checked_store(blocker), operation_guard(blocker, 'glossary', 'pass'):
                reply = self.search(connection)
            driver = next(item for item in reply['results'] if item['name'] == 'Driver')
            independent = next(item for item in reply['results'] if item['name'] == 'Independent')
            self.assertFalse(reply['freshness']['finished'])
            self.assertFalse(driver['dependencyCheck']['complete'])
            self.assertFalse(independent['dependencyCheck']['complete'])
            self.assertEqual(next(item['state'] for item in reply['freshness']['repositories']
                                  if item['repository'] == 'glossary'), 'busy')
            self.assertEqual(self.base.owned(connection, 'glossary'), source_before)
            for options in ({'no_fresh': True}, {'deadline': Deadline.after(0)}):
                before = self.base.contents(connection)
                with patch.object(_Capture, 'capture', side_effect=AssertionError('pending work captured')):
                    pending = self.search(connection, **options)
                self.assertFalse(pending['freshness']['finished'])
                self.assertTrue(pending['results'])
                self.assertTrue(all(not item['dependencyCheck']['complete'] for item in pending['results']))
                self.assertEqual(self.base.contents(connection), before)
# TEST-TIER-END tests/test_search_store.py::SearchFreshnessStoreTests.test_busy_source_and_skipped_or_expired_checks_keep_index_reply_and_unchanged_pending_source
