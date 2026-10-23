"""Versioned-file acceptance and real offline evaluator regression checks.

The injected search replies test accounting rather than implement a ranking.
MYC-13.11 through .17 additionally need genuine disposable-store proofs; these
unit checks cannot establish production search or MYC-4.25 ranking quality.
"""

from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from mycel._errors import MycelError
from mycel._evaluation import (EvaluationSet, PreparedQueryVector, RetrievalPlace,
                               RetrievalQuery, RetrievalReply, comparison_failures,
                               empty_retrieval_report, load_evaluation_file,
                               run_retrieval_evaluation)
from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress


QUERY = '[[query]]\ntext = "how does renewal decide"\nexpect = ["fixture:policy.py#Policy"]\n'
DRIFT = ('[[drift]]\nid="first"\nbefore="before"\ncurrent="current"\n'
         'dependant="dependant"\nexpect="needs_review"\n')


class EvaluationFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.file = Path(self.temporary.name) / 'evaluation.toml'

    def load(self, source):
        self.file.write_text(source, encoding='utf-8')
        return load_evaluation_file(self.file)

    def invalid(self, source, field):
        with self.assertRaises(MycelError) as error:
            self.load(source)
        self.assertEqual(error.exception.code, 'invalid_input')
        self.assertIn(str(self.file), error.exception.message)
        self.assertIn(field, error.exception.message)
        return error.exception

    def test_optional_sections_version_compatibility_exact_bytes_and_frozen_values(self):
        for source in ('', 'schema_version=1\n', 'query=[]\ndrift=[]\n'):
            suite = self.load(source)
            self.assertEqual((suite.schema_version, suite.queries, suite.drifts), (1, (), ()))
            self.assertEqual(suite.file_hash, sha256(source.encode()).hexdigest())
            with self.assertRaises(FrozenInstanceError):
                suite.file_hash = 'changed'
        suite = self.load(QUERY + DRIFT)
        self.assertEqual(len(suite.queries), 1)
        self.assertEqual(len(suite.drifts), 1)
        self.assertEqual(self.load(QUERY).drifts, ())
        self.assertEqual(self.load(DRIFT).queries, ())

    def test_unknown_fields_dotted_quoted_inline_and_multiline_have_exact_locations(self):
        cases = [
            ('unexpected=1\n', 'unexpected', 1),
            (QUERY + 'extra=true\n', 'query[0].extra', 4),
            ('query=[{text="x",expect=["fixture:f#x"],extra=true}]\n', 'query[0].extra', 1),
            ('[["query"]]\ntext="""first\n# ignored = 1\nsecond"""\nexpect=["fixture:f#x"]\n"extra"=true\n',
             'query[0].extra', 6),
            (DRIFT + 'nested.value=true\n', 'drift[0].nested', 7),
        ]
        for source, field, line in cases:
            with self.subTest(field=field, source=source):
                error = self.invalid(source, field)
                self.assertIn(f'line {line}', error.message)

    def test_wrong_version_and_section_shapes_refuse_before_calls(self):
        for source, field in [('schema_version=true\n', 'schema_version'),
                              ('schema_version=2\n', 'schema_version'),
                              ('schema_version="1"\n', 'schema_version'),
                              ('[query]\ntext="x"\nexpect=["fixture:f#x"]\n', 'query'),
                              ('query=[1]\n', 'query[0]'),
                              ('[drift]\nid="first"\n', 'drift'),
                              ('drift=["x"]\n', 'drift[0]')]:
            with self.subTest(source=source):
                self.invalid(source, field)

    def test_retrieval_requires_nonempty_text_expectations_and_exact_only(self):
        for source, field in [('[[query]]\nexpect=["fixture:f#x"]\n', 'query[0].text'),
                              ('[[query]]\ntext=1\nexpect=["fixture:f#x"]\n', 'query[0].text'),
                              ('[[query]]\ntext=" \\t"\nexpect=["fixture:f#x"]\n', 'query[0].text'),
                              ('[[query]]\ntext="x"\n', 'query[0].expect'),
                              ('[[query]]\ntext="x"\nexpect=[]\n', 'query[0].expect'),
                              ('[[query]]\ntext="x"\nexpect=[" "]\n', 'query[0].expect[0]'),
                              ('[[query]]\ntext="x"\nexpect=[1]\n', 'query[0].expect[0]'),
                              (QUERY + 'only="all"\n', 'query[0].only'),
                              (QUERY + 'only=false\n', 'query[0].only')]:
            with self.subTest(source=source):
                self.invalid(source, field)
        for only in ('code', 'docs'):
            self.assertEqual(self.load(QUERY + f'only="{only}"\n').queries[0].only, only)
        source = QUERY.replace('how does renewal decide', '  full query fidelity 雪  ')
        self.assertEqual(self.load(source).queries[0].text, '  full query fidelity 雪  ')
        # Syntax of individual addresses belongs to visible set faults later.
        self.assertEqual(self.load(QUERY.replace('fixture:policy.py#Policy', 'not a ref')).queries[0].expect,
                         ('not a ref',))

    def test_drift_required_strings_deletion_and_empty_present_source(self):
        for field in ('id', 'before', 'current', 'dependant', 'expect'):
            lines = [line for line in DRIFT.splitlines() if not line.startswith(field + '=')]
            self.invalid('\n'.join(lines) + '\n', f'drift[0].{field}')
            replacement = DRIFT.replace(next(line for line in DRIFT.splitlines()
                                              if line.startswith(field + '=')), field + '=1')
            self.invalid(replacement, f'drift[0].{field}')
        self.assertEqual(self.load(DRIFT.replace('current="current"', 'current=""')).drifts[0].current, '')
        deleted = DRIFT.replace('current="current"\n', 'source_state="deleted"\n')
        self.assertIsNone(self.load(deleted).drifts[0].current)
        self.assertEqual(self.load(deleted).drifts[0].source_state, 'deleted')
        self.invalid(deleted + 'current=""\n', 'drift[0].current')
        self.invalid(DRIFT + 'source_state="unknown"\n', 'drift[0].source_state')
        self.invalid(DRIFT + DRIFT, 'drift[1].id')

    def test_drift_context_availability_and_label_consistency(self):
        source = DRIFT + 'context=["first", "", "last"]\ncritical=["permission", "negation"]\n'
        case = self.load(source).drifts[0]
        self.assertEqual(case.context, ('first', '', 'last'))
        self.assertEqual(case.critical, ('permission', 'negation'))
        for extra, field in [('context="x"\n', 'context'), ('context=[1]\n', 'context[0]'),
                             ('unavailable=["baseline","baseline"]\n', 'unavailable'),
                             ('unavailable=["current"]\n', 'unavailable'),
                             ('unavailable=["context"]\n', 'expect'),
                             ('unchanged=1\n', 'unchanged'), ('unchanged=true\n', 'unchanged'),
                             ('critical=["unknown"]\n', 'critical')]:
            self.invalid(DRIFT + extra, 'drift[0].' + field)
        unresolved = DRIFT.replace('needs_review', 'unresolved')
        self.assertEqual(self.load(unresolved + 'unavailable=["baseline"]\ncritical=["deletion"]\n')
                         .drifts[0].unavailable, ('baseline',))
        for outcome in ('still_supported', 'insufficient_evidence', 'unresolved'):
            self.invalid(DRIFT.replace('needs_review', outcome) + 'critical=["operator"]\n', 'drift[0].expect')
        self.assertTrue(self.load(DRIFT.replace('needs_review', 'still_supported') + 'unchanged=true\n')
                        .drifts[0].unchanged)
        self.invalid(DRIFT.replace('needs_review', 'unsupported'), 'drift[0].expect')

    def test_both_sections_are_validated_and_input_failures_have_file_details(self):
        self.invalid(QUERY + DRIFT + 'unknown=true\n', 'drift[0].unknown')
        self.invalid(DRIFT + QUERY + 'only="all"\n', 'query[0].only')
        self.invalid('[[query]]\ntext =\n', 'line 2')
        self.invalid('schema_version=1\nschema_version=1\n', 'line 2')
        self.file.write_bytes(b'\xff')
        with self.assertRaisesRegex(MycelError, 'UTF-8') as error:
            load_evaluation_file(self.file)
        self.assertEqual(error.exception.code, 'invalid_input')
        self.file.unlink()
        with self.assertRaises(MycelError) as error:
            load_evaluation_file(self.file)
        self.assertEqual(error.exception.code, 'io')
        self.assertIn(str(self.file), error.exception.message)


def fixture_catalog():
    settings = SettingsSnapshot(Path('/fixture/config.toml'), _freeze({
        'repos': {'fixture': {'enabled': True}, 'disabled': {'enabled': False}}, 'store': {}}), True, True)
    def member(identifier, name, *, kind='function', family=None, title=None):
        source = name.encode()
        return ResolvedChunk(identifier, 1, name, kind, source, sha256(source).hexdigest(),
                             family=family, title=title)
    def file(identifier, root, path, members, *, aliases=()):
        source = b'whole file'
        place = SourceAddress('fixture', root, path)
        return ResolvedFile(identifier, 'fixture', place, aliases or (place,), source,
                            sha256(source).hexdigest(), tuple(members))
    header = member('header', 'Policy', kind='class')
    method = member('method', 'Policy.run', kind='method', family='Policy')
    files = [file('policy', 'code', 'policy.py', (header, method)),
             file('one', 'artifact', 'same.md', (member('one', 'One', kind='document'),)),
             file('two', 'code', 'same.md', (member('two', 'Two', kind='document'),)),
             file('repeat', 'artifact', 'repeat.md',
                  (member('repeat-one', 'One > Repeat', kind='document', title='Repeat'),
                   member('repeat-two', 'Two > Repeat', kind='document', title='Repeat'))),
             file('alias', 'artifact', 'guide.md', (member('guide', 'Guide', kind='document'),),
                  aliases=(SourceAddress('fixture', 'artifact', 'guide.md'),
                           SourceAddress('fixture', 'code', 'docs/guide.md')))]
    generated = member('generated', 'Area', kind='index')
    return SourceResolver(settings, tuple(files),
                          index=((SourceAddress('fixture', 'index', 'overview', 'Area'), generated),))


class Vectors:
    def __init__(self, events, fallbacks=()):
        self.events, self.fallbacks = events, fallbacks

    def prepare(self, query):
        self.events.append(('prepare', query))
        return (PreparedQueryVector(None, 'no_key') if query.text in self.fallbacks
                else PreparedQueryVector((1.0, 0.0)))


class Snapshot:
    index_generation = 'generation-1'
    index_fingerprint = 'indexed-exact-inputs'
    settings_hash = 'effective-settings'
    search_reply = 3

    def __init__(self, events, replies, *, ineligible=()):
        self.resolver = fixture_catalog()
        self.events, self.replies, self.ineligible = events, replies, ineligible

    def eligible(self, query, member):
        self.events.append(('eligible', query, member.place.address))
        return member.chunk.identifier not in self.ineligible

    def search(self, query, vector, *, k, freshness):
        self.events.append(('search', query, vector, k, freshness))
        return self.replies[query.text]


class Adapter:
    def __init__(self, events, snapshot):
        self.events, self.value = events, snapshot

    @contextmanager
    def snapshot(self, repository):
        self.events.append(('open', repository))
        try:
            yield self.value
        finally:
            self.events.append(('close', repository))


def place(identifier, *, version=1, root='code', path='policy.py', name=None):
    return RetrievalPlace(identifier, version, SourceAddress('fixture', root, path, name or identifier))


class RetrievalEvaluationUnitTests(unittest.TestCase):
    def suite(self, queries):
        return EvaluationSet(Path('/fixture/evaluation.toml'), 'exact-file-hash', tuple(queries))

    def run_evaluation(self, queries, replies, *, fallbacks=(), ineligible=()):
        events = []
        snapshot = Snapshot(events, replies, ineligible=ineligible)
        report = run_retrieval_evaluation(self.suite(queries), repository='fixture', build='1',
                    model='voyage-code-4', query_vectors=Vectors(events, fallbacks),
                    retrieval=Adapter(events, snapshot))
        return report, events

    def test_exact_positions_header_alias_and_duplicate_expectations_account_once(self):
        """MYC-13.12/.17 core: read class header, aliases and duplicate scoring."""
        query = RetrievalQuery('  How does Policy decide?  ', (
            'fixture:policy.py#Policy', 'fixture:@code/policy.py#Policy',
            'fixture:guide.md#Guide', 'fixture:docs/guide.md#Guide'))
        results = tuple(place(f'filler-{i}') for i in range(2)) + (
            place('header', name='Policy'), place('guide', root='artifact', path='guide.md', name='Guide'))
        report, events = self.run_evaluation((query,), {query.text: RetrievalReply('question', True, results)})
        expected = report['results'][0]['expected']
        self.assertEqual([item['position'] for item in expected], [3, 3, 4, 4])
        self.assertEqual([item['resolved']['id'] for item in expected], ['header', 'header', 'guide', 'guide'])
        self.assertEqual(report['recall'], {'at3': 0.5, 'at10': 1.0})
        self.assertEqual(report['byRoute']['identifier'], {'queries': 0, 'at3': None, 'at10': None})
        self.assertEqual(report['results'][0]['text'], query.text)
        search = next(event for event in events if event[0] == 'search')
        self.assertEqual(search[1], query)
        self.assertEqual(search[3:], (10, False))

    def test_vectors_all_precede_one_snapshot_and_wording_only_is_counted(self):
        """MYC-13.11/.14/.17: exact vector preparation ordering and fallback."""
        queries = (RetrievalQuery('Policy', ('fixture:policy.py#Policy',)),
                   RetrievalQuery('How does it decide?', ('fixture:policy.py#Policy',)))
        replies = {query.text: RetrievalReply(route, semantic, (place('header', name='Policy'),))
                   for query, route, semantic in zip(queries, ('identifier', 'question'), (True, False))}
        report, events = self.run_evaluation(queries, replies, fallbacks=(queries[1].text,))
        self.assertEqual([event[0] for event in events],
                         ['prepare', 'prepare', 'open', 'search', 'eligible', 'search', 'eligible', 'close'])
        self.assertEqual(report['byWordingAlone'], 1)
        self.assertEqual((report['build'], report['model'], report['searchReply']), ('1', 'voyage-code-4', 3))
        self.assertEqual(report['byRoute'], {route: {'queries': 1, 'at3': 1.0, 'at10': 1.0}
                                            for route in ('identifier', 'question')})
        self.assertEqual(len(report['queryVectorsHash']), 64)

    def test_position_ten_absence_and_whole_faulted_query_exclusion(self):
        """MYC-13.12/.13/.17: exact kth positions and entire invalid-query exclusion."""
        queries = (RetrievalQuery('valid?', ('fixture:policy.py#Policy', 'fixture:guide.md#Guide')),
                   RetrievalQuery('broken?', ('fixture:policy.py#Policy', 'fixture:missing.py#Missing')))
        results = tuple(place(f'filler-{i}') for i in range(9)) + (place('header', name='Policy'),)
        report, _ = self.run_evaluation(queries, {query.text: RetrievalReply('question', True, results)
                                                 for query in queries})
        self.assertEqual(report['recall'], {'at3': 0.0, 'at10': 0.5})
        self.assertEqual(report['byRoute']['question']['queries'], 2)
        self.assertEqual(report['results'][0]['expected'][0]['position'], 10)
        self.assertNotIn('position', report['results'][0]['expected'][1])
        self.assertFalse(report['results'][1]['included'])
        self.assertEqual(report['results'][1]['expected'][1]['fault'], 'not_in_index')
        self.assertEqual(report['faultsOfTheSet'], 1)

    def test_every_resolver_fault_file_selection_and_eligibility_are_visible(self):
        """MYC-13.13/.17: resolution fault mapping and zero denominators."""
        cases = [('not a ref', 'malformed'), ('fixture:missing.py#Missing', 'not_in_index'),
                 ('fixture:policy.py#Missing', 'not_in_index'), ('fixture:same.md#One', 'ambiguous'),
                 ('fixture:repeat.md#Repeat', 'ambiguous'), ('disabled:f.py#x', 'ineligible'),
                 ('unregistered:f.py#x', 'ineligible'), ('fixture:policy.py', 'not_one_chunk'),
                 ('fixture:guide.md', 'not_one_chunk'), ('fixture:guide.md#Guide', 'ineligible')]
        query = RetrievalQuery('faulted?', tuple(ref for ref, _ in cases))
        report, _ = self.run_evaluation((query,), {query.text: RetrievalReply('question', True, ())},
                                       ineligible=('guide',))
        self.assertEqual([item['fault'] for item in report['results'][0]['expected']],
                         [fault for _, fault in cases])
        self.assertEqual(report['faultsOfTheSet'], len(cases))
        self.assertEqual(report['recall'], {'at3': None, 'at10': None})
        self.assertFalse(report['results'][0]['included'])

    def test_generated_index_chunk_is_a_read_result_and_wrong_version_does_not_hit(self):
        """MYC-13.17: read-role index chunks and exact on-disk version matching."""
        query = RetrievalQuery('Area', ('fixture:@index/overview#Area',))
        report, _ = self.run_evaluation((query,), {query.text: RetrievalReply('identifier', True, (
            place('generated', version=2, root='index', path='overview', name='Area'),))})
        self.assertTrue(report['results'][0]['included'])
        self.assertNotIn('position', report['results'][0]['expected'][0])
        self.assertEqual(report['recall'], {'at3': 0.0, 'at10': 0.0})

    def test_empty_selected_section_has_null_shares_and_no_query_calls(self):
        """MYC-13.10/.17: empty set retains measured snapshot identities."""
        report, events = self.run_evaluation((), {})
        self.assertEqual(events, [('open', 'fixture'), ('close', 'fixture')])
        self.assertEqual(report['queries'], 0)
        self.assertEqual(report['recall'], {'at3': None, 'at10': None})
        self.assertEqual(report['results'], [])
        self.assertEqual(report['indexGeneration'], 'generation-1')
        unmeasured = empty_retrieval_report(self.suite(()), repository='fixture', build='1', model='voyage-code-4')
        self.assertIsNone(unmeasured['indexGeneration'])
        self.assertIn('indexGeneration', comparison_failures(unmeasured, unmeasured))
        events = []
        snapshot = Snapshot(events, {})
        snapshot.index_generation = ''
        with self.assertRaisesRegex(MycelError, 'incomplete input identities'):
            run_retrieval_evaluation(self.suite(()), repository='fixture', build='1', model='voyage-code-4',
                query_vectors=Vectors(events), retrieval=Adapter(events, snapshot))
        self.assertEqual(events, [('open', 'fixture'), ('close', 'fixture')])

    def test_comparisons_require_same_file_vectors_settings_model_reply_and_index(self):
        """MYC-13.17: Build-only changes are comparable; frozen inputs must match."""
        query = RetrievalQuery('Policy', ('fixture:policy.py#Policy',))
        report, _ = self.run_evaluation((query,), {query.text: RetrievalReply('identifier', True, ())})
        self.assertEqual(comparison_failures(report, {**report, 'build': '2'}), ())
        keys = ('evaluationSchema', 'repository', 'fileHash', 'model', 'searchReply',
                'indexGeneration', 'indexFingerprint', 'settingsHash', 'queryVectorsHash')
        for key in keys:
            self.assertEqual(comparison_failures(report, {**report, key: 'changed'}), (key,))
            self.assertEqual(comparison_failures(report, {**report, key: None}), (key,))
        self.assertEqual(comparison_failures(report, {**report, 'kind': 'drift'}), ('kind',))
        changed, _ = self.run_evaluation((query,), {query.text: RetrievalReply('identifier', False, ())},
                                         fallbacks=(query.text,))
        self.assertNotEqual(report['queryVectorsHash'], changed['queryVectorsHash'])

    def test_search_contract_violations_fail_without_rewriting_ranks(self):
        """MYC-13.11/.17: search collapse/top-ten/route contracts fail closed."""
        query = RetrievalQuery('Policy', ('fixture:policy.py#Policy',))
        malformed = [RetrievalReply('bad', True, ()), RetrievalReply('identifier', 1, ()),
                     RetrievalReply('identifier', True, (None,)),
                     RetrievalReply('identifier', True, tuple(place(str(i)) for i in range(11))),
                     RetrievalReply('identifier', True, (place('header'), place('header'))),
                     RetrievalReply('identifier', True, (place('header'), place('header', version=2))),
                     RetrievalReply('identifier', True, (RetrievalPlace('x', 1, SourceAddress('fixture', None, 'x', 'x')),))]
        for reply in malformed:
            with self.subTest(reply=reply), self.assertRaises(MycelError) as error:
                self.run_evaluation((query,), {query.text: reply})
            self.assertEqual(error.exception.code, 'internal')
        with self.assertRaises(MycelError):
            self.run_evaluation((query,), {query.text: RetrievalReply('identifier', True, ())}, fallbacks=(query.text,))

    def test_vectors_are_finite_exact_sequences_and_fallback_has_reason(self):
        """MYC-13.17 input fingerprints never hash nonfinite or unspecified inputs."""
        for vector, reason in (((), None), ([1.0], None), ((True,), None), ((float('nan'),), None),
                               ((float('inf'),), None), ((1.0,), 'fallback'), (None, None)):
            with self.subTest(vector=vector, reason=reason), self.assertRaises(MycelError):
                PreparedQueryVector(vector, reason)
        self.assertEqual(PreparedQueryVector((1.0, 0.0)).vector, (1.0, 0.0))
        self.assertEqual(PreparedQueryVector(None, 'service_timeout').reason, 'service_timeout')
        class InvalidVectors:
            def prepare(self, query):
                return None
        events = []
        query = RetrievalQuery('Policy', ('fixture:policy.py#Policy',))
        with self.assertRaisesRegex(MycelError, 'incompatible evaluation vector'):
            run_retrieval_evaluation(self.suite((query,)), repository='fixture', build='1', model='voyage-code-4',
                query_vectors=InvalidVectors(), retrieval=Adapter(events, Snapshot(events, {})))
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
