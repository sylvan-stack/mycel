"""Actual retrieval producers inside the evaluator's sole read-only snapshot.

These store checks cover actual normal retrieval and explicitly selected-kind
dispatch for MYC-13.11. They neither qualify the separate full Drift pipeline
nor measure semantic quality/MYC-4.25.
"""

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from psycopg import pq

from mycel._cli import parse, run
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._evaluate import evaluate
from mycel._evaluation import (EvaluationSet, PreparedQueryVector, RetrievalQuery,
                               run_retrieval_evaluation)
from mycel._evaluation_store import NormalQueryVectors, StoreRetrieval
from mycel._locks import atomic_transaction
from mycel._resolver import SourceResolver
from mycel._retrieval_store import (CandidateSnapshot, StoreCandidates,
                                    candidate_snapshot_in_transaction)
from mycel._search import QueryEmbedding
from mycel._search_reply import SEARCH_REPLY
from mycel._safeguards import InvocationPolicy
from mycel._settings import _freeze, load_settings
from mycel._store import TABLES

try:
    from . import test_evaluate_cli as cli_fixtures
    from . import test_ranking_store as ranking_fixtures
    from . import test_read_store as read_fixtures
except ImportError:
    import test_evaluate_cli as cli_fixtures
    import test_ranking_store as ranking_fixtures
    import test_read_store as read_fixtures


class _RecordingConnection:
    def __init__(self, connection):
        self.connection, self.statements = connection, []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *arguments, **options):
        self.statements.append(statement)
        return self.connection.execute(statement, *arguments, **options)


class _Vectors:
    def __init__(self, connection, vector, *, reasons=None):
        self.connection, self.vector = connection, vector
        self.reasons, self.queries = reasons or {}, []

    def prepare(self, query):
        if self.connection.info.transaction_status != pq.TransactionStatus.IDLE:
            raise AssertionError('Query preparation entered an index transaction.')
        self.queries.append(query)
        reason = self.reasons.get(query.text)
        return PreparedQueryVector(None, reason) if reason is not None else PreparedQueryVector(self.vector)


def _state(connection):
    rows = {table.name: connection.execute(f'SELECT to_jsonb(t),xmin::text FROM public.{table.name} t '
            'ORDER BY to_jsonb(t)::text').fetchall() for table in TABLES}
    names = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
                               "WHERE schemaname='public' ORDER BY sequencename").fetchall()
    rows['sequences'] = {name: connection.execute('SELECT last_value,is_called FROM public."' + name + '"').fetchone()
                         for name, in names}
    return rows


@contextmanager
def _forbid_side_effects():
    """Actual ranking is allowed; freshness, publication and transports are not."""
    with ExitStack() as stack:
        for target in (
            'mycel._search_store._run_search_freshness',
            'mycel._freshness_store.StoreFreshnessAdapter.discover',
            'mycel._capture._Capture.capture', 'mycel._ingest.ingest',
            'mycel._activity.MutationActivity.session',
            'mycel._classification_store.ClassificationStore.prepare',
            'mycel._classification_store.ClassificationStore.apply',
            'mycel._classification_store.ClassificationStore.reuse',
            'mycel._summary_writer.SummaryWriter.write',
            'mycel._voyage._https_request',
        ):
            stack.enter_context(patch(target, side_effect=AssertionError(target)))
        # The evaluator borrows its existing transaction; a nested ordinary
        # search snapshot would violate the sole-snapshot contract.
        stack.enter_context(patch.object(StoreCandidates, 'snapshot', side_effect=AssertionError('nested snapshot')))
        yield


class EvaluationRetrievalUnitTests(unittest.TestCase):
    @proves('MYC-0.10', kind='unit')
    def test_query_adapter_passes_explicit_evaluation_intent_through_normal_preparation_and_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = cli_fixtures.EvaluateCliTests().configured(root)
            settings = load_settings(path=config)
            vector = (1.0,) + (0.0,) * 1023
            policy = InvocationPolicy('evaluate', kind='retrieval')
            calls = []

            def prepared(supplied, text, **options):
                self.assertEqual(supplied.values, settings.values)
                self.assertEqual(options['policy'], policy)
                self.assertEqual(options['credentials']._policy, policy)
                calls.append(text)
                return QueryEmbedding(reason='Normal provider fallback with exact reason.')

            query = RetrievalQuery('  complete query 雪\n', ('a:f.py#f',))
            adapter = NormalQueryVectors(settings, store_dimensions=1024, prepare=prepared)
            result = adapter.prepare(query)
            self.assertIsNone(result.vector)
            self.assertEqual(result.reason, 'Normal provider fallback with exact reason.')
            self.assertEqual(calls, [query.text])

            def client(credentials, supplied_policy, **options):
                self.assertEqual(supplied_policy, policy)
                self.assertEqual(credentials._policy, policy)
                self.assertIn('tokenizer', options)
                return SimpleNamespace(query=lambda request: SimpleNamespace(vectors=(vector,)))

            with patch('mycel._credentials.Credentials.embedding_key', side_effect=AssertionError('real credential')), \
                    patch('mycel._voyage._https_request', side_effect=AssertionError('real provider')):
                result = NormalQueryVectors(settings, store_dimensions=1024, client_factory=client).prepare(query)
            self.assertEqual(result.vector, vector)
            self.assertIsNone(result.reason)

    @proves('MYC-13.10', 'MYC-0.10', kind='unit')
    def test_full_schema_validation_and_empty_selected_sections_precede_all_execution_adapters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = cli_fixtures.EvaluateCliTests()
            config = fixture.configured(root)
            settings = load_settings(path=config)
            file = root / 'a' / 'evaluation.toml'
            vectors, retrieval, drift = Mock(), Mock(), Mock()
            with patch('mycel._cli.invocation_store', side_effect=AssertionError('store')), \
                    patch('mycel._evaluation_store.NormalQueryVectors', side_effect=AssertionError('query provider')), \
                    patch('mycel._voyage._https_request', side_effect=AssertionError('network')):
                for kind, contents in (
                    ('retrieval', '[[query]]\ntext="needle"\nexpect=["a:f.py#f"]\n'
                     '[[drift]]\nid="broken"\nbefore="old"\ndependant="d"\nexpect="needs_review"\n'),
                    ('drift', '[[query]]\ntext="needle"\nexpect=["a:f.py#f"]\nunknown=true\n'),
                ):
                    file.write_text(contents)
                    invocation = replace(parse(('evaluate', '--repo', 'a', '--kind', kind)), settings=settings)
                    with self.subTest(kind=kind), self.assertRaises(MycelError) as error:
                        evaluate(invocation, query_vectors=vectors, retrieval=retrieval, drift=drift)
                    self.assertEqual(error.exception.code, 'invalid_input')
                    self.assertIn(str(file), error.exception.message)
                for kind, contents in (
                    ('retrieval', '[[drift]]\nid="valid"\nbefore="old"\ncurrent="new"\n'
                     'dependant="d"\nexpect="needs_review"\n'),
                    ('drift', '[[query]]\ntext="needle"\nexpect=["a:f.py#f"]\n'),
                ):
                    file.write_text(contents)
                    invocation = replace(parse(('evaluate', '--repo', 'a', '--kind', kind)), settings=settings)
                    report = evaluate(invocation).value
                    self.assertEqual(report['results'], [])
                    if kind == 'retrieval':
                        self.assertEqual(report['recall'], {'at3': None, 'at10': None})
                        self.assertIsNone(report['indexFingerprint'])
                    else:
                        self.assertFalse(report['qualified'])
                vectors.prepare.assert_not_called()
                retrieval.snapshot.assert_not_called()
                drift.assert_not_called()


class EvaluationRetrievalStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.ranking = ranking_fixtures.RankingStoreTests()
        self.ranking.store_fixture = self.store_fixture
        self.ranking.setUp()
        self.base = self.ranking.base
        self.vector = self.ranking.query
        self.settings = self.ranking.settings(shared=({'repo': 'handbook', 'paths': ['selected']},))

    def seed(self, connection, **options):
        result = self.ranking.seed(connection, **options)
        # Exact file-location corpus ownership is part of the evaluator's
        # input contract. The older ranking fixture supplies no such metadata.
        connection.execute('UPDATE public.mycel_file_locations fl SET metadata=fl.metadata || '
            'jsonb_build_object(\'corpus\',f.corpus) FROM public.mycel_file_versions fv '
            'JOIN public.mycel_files f ON f.id=fv.file_id WHERE fl.file_version=fv.id AND f.id=%s', (result[0],))
        return result

    def suite(self, *queries):
        return EvaluationSet(Path('/fictional/evaluation.toml'), sha256(b'controlled labelled query set').hexdigest(),
                             tuple(queries))

    def measure(self, connection, queries, *, settings=None, vectors=None):
        vectors = vectors or _Vectors(connection, self.vector)
        return run_retrieval_evaluation(self.suite(*queries), repository='fixture', build='1f',
            model='voyage-code-4', query_vectors=vectors,
            retrieval=StoreRetrieval(connection, settings or self.settings))

    def normal(self, connection, queries, *, settings=None, vector=None):
        selected = self.settings if settings is None else settings
        result = []
        with StoreCandidates(connection, selected).snapshot(('fixture',)) as snapshot:
            for query in queries:
                ranked, = snapshot.ranked(query.text, vector, k=10, only=query.only)
                result.append((ranked.route, [(entry.chunk.identifier, entry.chunk.version,
                                              entry.chunk.place.address) for entry in ranked.results]))
        return result

    @staticmethod
    def actual(report):
        return [(row['route'], [(place['id'], place['version'], place['address']) for place in row['returned']])
                for row in report['results']]

    @proves('MYC-13.11', kind='store')
    def test_actual_top_ten_matches_normal_routes_scopes_bridges_shared_aliases_and_generated_results(self):
        with self.base.connection() as connection:
            for number in range(25):
                self.seed(connection, path=f'direct{number:02}.py', name=f'Direct{number}',
                          source='needle routing direct code\n', cosine=.5)
            target = self.seed(connection, path='target.py', name='NeedlePolicy', source='needle policy code\n', cosine=.4)
            guide = self.seed(connection, path='guide.md', root='artifact', kind='document', name='Guide',
                              source='# Guide\nNeedle routing policy.\n', cosine=.9)
            self.ranking.cite(connection, guide, 'fixture:@code/target.py#NeedlePolicy')
            shared = self.seed(connection, repository='handbook', path='docs/shared.md', root='code',
                kind='document', name='Shared', source='# Shared\nNeedle shared routing.\n', cosine=.96,
                aliases=(('artifact', 'selected/shared.md'),))
            self.seed(connection, repository='handbook', root='artifact', path='outside.md', kind='document',
                      name='Outside', source='# Outside\nNeedle outside.\n', cosine=.99)
            self.seed(connection, repository='disabled', root='artifact', path='hidden.md', kind='document',
                      name='Hidden', source='# Hidden\nNeedle hidden.\n', cosine=.99)
            self.seed(connection, path='branch.py', name='Branch', source='needle branch\n',
                      location_kind='branch', cosine=.99)
            generated = []
            for kind, name, cosine in (('summary', '1/1', .92), ('overview', 'net', .91)):
                text = 'needle generated routing\n'
                member = read_fixtures.ReadStoreTests.generated(connection, kind=kind, name=name, text=text)
                self.base.plan(connection, member[0], member[1], text, vectors=((cosine, (1-cosine*cosine)**.5),))
                generated.append(member)
            queries = (
                RetrievalQuery('NeedlePolicy', ('fixture:@code/target.py#NeedlePolicy',), 'code'),
                RetrievalQuery('how does needle routing work', ('fixture:@code/target.py#NeedlePolicy',), 'code'),
                RetrievalQuery('how does needle routing work', ('handbook:@artifact/selected/shared.md#Shared',)),
                RetrievalQuery('how does needle routing work', (generated[0][2], generated[1][2],
                    'handbook:@artifact/selected/shared.md#Shared'), 'docs'))
            expected = self.normal(connection, queries, vector=self.vector)
            vectors = _Vectors(connection, self.vector)
            recorded = _RecordingConnection(connection)
            before = _state(connection)
            observed = []
            actual_ranked = CandidateSnapshot.ranked

            def ranked(snapshot, *arguments, **options):
                self.assertEqual(vectors.queries, list(queries))
                self.assertEqual(options.get('k'), 10)
                self.assertEqual(connection.execute("SELECT current_setting('transaction_read_only'), "
                    "current_setting('transaction_isolation')").fetchone(), ('on', 'repeatable read'))
                observed.append(snapshot)
                return actual_ranked(snapshot, *arguments, **options)

            with _forbid_side_effects(), patch.object(CandidateSnapshot, 'ranked', ranked), \
                    patch.object(SourceResolver, 'from_read_transaction',
                                 wraps=SourceResolver.from_read_transaction) as resolve, \
                    patch('mycel._retrieval_store.candidate_snapshot_in_transaction',
                          wraps=candidate_snapshot_in_transaction) as candidates:
                report = self.measure(recorded, queries, vectors=vectors)
            self.assertEqual(self.actual(report), expected)
            self.assertEqual(len(observed), len(queries))
            self.assertTrue(all(snapshot is observed[0] for snapshot in observed))
            self.assertEqual(report['byWordingAlone'], 0)
            self.assertEqual(report['searchReply'], SEARCH_REPLY)
            self.assertEqual(report['faultsOfTheSet'], 0)
            self.assertEqual(len(report['results'][0]['returned']), 10)
            self.assertEqual(report['results'][1]['returned'][0]['id'], str(target[1]))
            self.assertEqual(report['results'][1]['expected'][0]['position'], 1)
            shared_place = report['results'][2]['expected'][0]['resolved']
            self.assertEqual(shared_place['address'], 'handbook:@code/docs/shared.md#Shared')
            self.assertEqual(shared_place['id'], str(shared[1]))
            self.assertTrue(all(row['included'] for row in report['results']))
            # checked_store separately inspects catalogs and format metadata;
            # only this resolver/candidate pair reads the evaluation index.
            resolve.assert_called_once()
            candidates.assert_called_once()
            self.assertIs(candidates.call_args.args[1], observed[0].resolver)
            self.assertIs(candidates.call_args.kwargs['lease'], observed[0]._lease)
            self.assertFalse(observed[0]._lease.active)
            self.assertEqual(_state(connection), before)

    @proves('MYC-13.11', kind='store')
    def test_wording_fallback_uses_actual_normal_positions_and_never_creates_vector_or_cache_state(self):
        with self.base.connection() as connection:
            code = self.seed(connection, path='needle.py', name='Needle', source='needle only source\n', embedded=False)
            self.seed(connection, path='answer.md', root='artifact', kind='document', name='Answer',
                      source='# Answer\nneedle only source\n', embedded=False)
            queries = (RetrievalQuery('Needle', ('fixture:@code/needle.py#Needle',), 'code'),
                       RetrievalQuery('how does needle work', ('fixture:@code/needle.py#Needle',)),
                       RetrievalQuery('how does needle docs work', ('fixture:@artifact/answer.md#Answer',), 'docs'))
            expected = self.normal(connection, queries, vector=None)
            reasons = {query.text: 'The normal query provider is unavailable.' for query in queries}
            vectors = _Vectors(connection, self.vector, reasons=reasons)
            before = _state(connection)
            with _forbid_side_effects():
                report = self.measure(connection, queries, vectors=vectors)
            self.assertEqual(self.actual(report), expected)
            self.assertEqual(report['byWordingAlone'], len(queries))
            self.assertEqual(report['recall'], {'at3': 1.0, 'at10': 1.0})
            self.assertEqual(report['results'][0]['returned'][0]['id'], str(code[1]))
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_vectors').fetchone(), (0,))
            self.assertEqual(_state(connection), before)

    @proves('MYC-13.11', kind='store')
    def test_dimension_mismatch_keeps_normal_wording_without_calling_query_preparation(self):
        with self.base.connection() as connection:
            self.seed(connection, path='needle.py', name='Needle', source='needle source\n')
            settings = replace(self.settings, values=_freeze({**self.settings.values,
                'embedding': {**self.settings.values['embedding'], 'dimensions': 512}}))
            queries = (RetrievalQuery('Needle', ('fixture:@code/needle.py#Needle',), 'code'),)
            expected = self.normal(connection, queries, settings=settings, vector=None)
            prepare = Mock(side_effect=AssertionError('query preparation on dimension mismatch'))
            vectors = NormalQueryVectors(settings, store_dimensions=1024, prepare=prepare)
            before = _state(connection)
            with _forbid_side_effects():
                report = self.measure(connection, queries, settings=settings, vectors=vectors)
            self.assertEqual(self.actual(report), expected)
            self.assertEqual(report['byWordingAlone'], 1)
            prepare.assert_not_called()
            self.assertEqual(_state(connection), before)

    @proves('MYC-13.11', kind='store')
    def test_peer_publication_cannot_mix_actual_ranking_expectations_or_fingerprints_between_queries(self):
        with self.base.connection() as connection, self.base.connection() as writer:
            old = self.seed(connection, path='needle.py', name='Needle', source='needle original\n', cosine=.8)
            self.seed(connection, path='stable.py', name='Stable', source='needle stable\n', cosine=.6)
            queries = (RetrievalQuery('how does needle work', ('fixture:@code/needle.py#Needle',), 'code'),) * 2
            vectors = _Vectors(connection, self.vector)
            actual_ranked = CandidateSnapshot.ranked
            committed, current, calls = [], [], []

            def ranked(snapshot, *arguments, **options):
                self.assertEqual(vectors.queries, list(queries))
                result = actual_ranked(snapshot, *arguments, **options)
                if not calls:
                    with atomic_transaction(writer):
                        writer.execute("UPDATE public.mycel_locations SET kind='branch',location='old' "
                                       'WHERE chunk_version=%s', (old[2],))
                        writer.execute("UPDATE public.mycel_file_locations SET kind='branch',location='old' "
                            'WHERE file_version IN (SELECT id FROM public.mycel_file_versions WHERE file_id=%s)', (old[0],))
                        current.append(self.seed(writer, file_id=old[0], chunk_id=old[1], path='needle.py',
                            name='NewNeedle', source='needle newer publication\n', cosine=.1))
                    committed.append(_state(writer))
                calls.append(result)
                return result

            with _forbid_side_effects(), patch.object(CandidateSnapshot, 'ranked', ranked):
                report = self.measure(connection, queries, vectors=vectors)
            self.assertEqual(len(calls), 2)
            for row in report['results']:
                self.assertEqual((row['returned'][0]['id'], row['returned'][0]['version']), (str(old[1]), old[2]))
                self.assertEqual(row['expected'][0]['resolved']['version'], old[2])
                self.assertEqual(row['expected'][0]['position'], 1)
            self.assertEqual(_state(writer), committed[0])
            with StoreRetrieval(connection, self.settings).snapshot('fixture') as after:
                self.assertNotEqual(report['indexFingerprint'], after.index_fingerprint)
                self.assertEqual(after.resolver.resolve('fixture:@code/needle.py#Needle', purpose='read').fault, 'missing_name')
                member = after.resolver.resolve('fixture:@code/needle.py#NewNeedle', purpose='read').selection.members[0]
                self.assertEqual(member.chunk.version, current[0][2])
            self.assertEqual(_state(writer), committed[0])

    @proves('MYC-13.11', kind='store')
    def test_actual_results_resolve_class_headers_and_exclude_every_faulted_ground_truth_query(self):
        with self.base.connection() as connection:
            header = 'class Policy:\n'
            method = '    def apply(self):\n        return 1\n'
            members = read_fixtures.ReadStoreTests().seed(connection, 'policy.py', header + method,
                (('Policy', 'class', header, {}), ('Policy.apply', 'method', method, {'family': 'Policy'})))
            connection.execute("UPDATE public.mycel_file_locations fl SET metadata=fl.metadata || '{\"corpus\":\"code\"}' "
                'FROM public.mycel_file_versions fv JOIN public.mycel_files f ON f.id=fv.file_id '
                "WHERE fl.file_version=fv.id AND f.repository='fixture' AND f.path='policy.py'")
            for name, member in members.items():
                self.base.plan(connection, member[0], member[1], member[2],
                               vectors=((.8 if name == 'Policy' else .7, .6 if name == 'Policy' else (1-.7*.7)**.5),))
            for root in ('code', 'artifact'):
                self.seed(connection, path='same.md', root=root, kind='document', name='Same',
                          source=f'# Same\n{root} document.\n')
            queries = (
                RetrievalQuery('Policy', ('fixture:@code/policy.py#Policy', 'fixture:policy.py#Policy'), 'code'),
                RetrievalQuery('missing answer', ('fixture:@code/policy.py#Policy', 'fixture:missing.py#Missing'), 'code'),
                RetrievalQuery('whole file', ('fixture:@code/policy.py',), 'code'),
                RetrievalQuery('malformed ref', ('not a ref',), 'code'),
                RetrievalQuery('ambiguous ref', ('fixture:same.md#Same',), 'docs'),
                RetrievalQuery('ineligible ref', ('fixture:@artifact/same.md#Same',), 'code'))
            before = _state(connection)
            with _forbid_side_effects():
                report = self.measure(connection, queries)
            self.assertEqual(report['faultsOfTheSet'], 5)
            self.assertEqual(report['recall'], {'at3': 1.0, 'at10': 1.0})
            valid, *faulted = report['results']
            self.assertTrue(valid['included'])
            self.assertEqual([row['resolved']['id'] for row in valid['expected']], [members['Policy'][0]] * 2)
            self.assertEqual([row['resolved']['version'] for row in valid['expected']], [members['Policy'][1]] * 2)
            self.assertEqual(valid['expected'][0]['position'], valid['expected'][1]['position'])
            self.assertTrue(all(not row['included'] for row in faulted))
            self.assertEqual([row['expected'][-1]['fault'] for row in faulted],
                             ['not_in_index', 'not_one_chunk', 'malformed', 'ambiguous', 'ineligible'])
            self.assertEqual(_state(connection), before)

    @proves('MYC-13.11', kind='store')
    def test_nonempty_public_cli_uses_real_default_retrieval_with_fake_preparer_before_its_snapshot(self):
        with self.base.connection() as connection:
            code = self.seed(connection, path='needle.py', name='Needle', source='needle public source\n')
            artifact = Path(self.settings.values['repos']['fixture']['artifact_root'])
            artifact.mkdir(parents=True)
            file = artifact / 'evaluation.toml'
            file.write_text('[[query]]\ntext="Needle"\nexpect=["fixture:@code/needle.py#Needle"]\nonly="code"\n'
                '[[drift]]\nid="selected-only"\nbefore="old"\ncurrent="new"\n'
                'dependant="dependent text"\nexpect="needs_review"\n')
            settings = replace(self.settings, values=_freeze({**self.settings.values,
                'repos': {name: {**value, **({'evaluation': 'evaluation.toml'} if name == 'fixture' else {})}
                          for name, value in self.settings.values['repos'].items()}}))
            recorded = _RecordingConnection(connection)
            vectors = _Vectors(connection, self.vector)
            drift = Mock(side_effect=AssertionError('unselected Drift'))

            @contextmanager
            def connected(credentials):
                yield recorded

            output, diagnostic = StringIO(), StringIO()
            before = _state(connection)
            observed = []
            actual_ranked = CandidateSnapshot.ranked

            def ranked(snapshot, *arguments, **options):
                self.assertEqual([query.text for query in vectors.queries], ['Needle'])
                self.assertEqual(options.get('k'), 10)
                self.assertEqual(connection.execute("SELECT current_setting('transaction_read_only'), "
                    "current_setting('transaction_isolation')").fetchone(), ('on', 'repeatable read'))
                observed.append(snapshot)
                return actual_ranked(snapshot, *arguments, **options)

            with _forbid_side_effects(), patch('mycel._cli.load_settings', return_value=settings), \
                    patch('mycel._database.store_connection', connected), \
                    patch('mycel._build_identity.current_build', return_value=31), \
                    patch.object(CandidateSnapshot, 'ranked', ranked), \
                    patch.object(SourceResolver, 'from_read_transaction',
                                 wraps=SourceResolver.from_read_transaction) as resolve, \
                    patch('mycel._retrieval_store.candidate_snapshot_in_transaction',
                          wraps=candidate_snapshot_in_transaction) as candidates:
                status = run(('evaluate', '--repo', 'fixture'), stdout=output, stderr=diagnostic,
                    handlers={'evaluate': lambda invocation: evaluate(invocation, query_vectors=vectors, drift=drift)})
            self.assertEqual((status, diagnostic.getvalue()), (0, ''))
            report = json.loads(output.getvalue())
            self.assertEqual((report['kind'], report['repository'], report['build'], report['searchReply']),
                             ('retrieval', 'fixture', '1f', SEARCH_REPLY))
            self.assertEqual(report['queries'], 1)
            self.assertEqual(report['results'][0]['returned'][0]['id'], str(code[1]))
            self.assertEqual(report['results'][0]['expected'][0]['position'], 1)
            self.assertEqual(report['fileHash'], sha256(file.read_bytes()).hexdigest())
            self.assertEqual([query.text for query in vectors.queries], ['Needle'])
            # CLI and producer metadata preflights may precede this one index
            # snapshot; neither may construct a separate result catalog.
            resolve.assert_called_once()
            candidates.assert_called_once()
            self.assertEqual(len(observed), 1)
            self.assertIs(candidates.call_args.args[1], observed[0].resolver)
            self.assertIs(candidates.call_args.kwargs['lease'], observed[0]._lease)
            self.assertFalse(observed[0]._lease.active)
            drift.assert_not_called()

            # The same nonempty file takes only the explicitly selected Drift
            # branch, including --live. Full pipeline qualification is separate.
            forbidden_vectors, forbidden_retrieval = Mock(), Mock()
            selected_drift = Mock(return_value={'kind': 'drift', 'dispatch': 'selected'})
            with _forbid_side_effects(), patch('mycel._cli.load_settings', return_value=settings), \
                    patch('mycel._cli.invocation_store', side_effect=AssertionError('unselected retrieval')), \
                    patch('mycel._build_identity.current_build', return_value=31):
                for live in (False, True):
                    output, diagnostic = StringIO(), StringIO()
                    selected_drift.reset_mock()
                    status = run(('evaluate', '--repo', 'fixture', '--kind', 'drift',
                                  *(('--live',) if live else ())), stdout=output, stderr=diagnostic,
                        handlers={'evaluate': lambda invocation: evaluate(invocation,
                            query_vectors=forbidden_vectors, retrieval=forbidden_retrieval, drift=selected_drift)})
                    self.assertEqual((status, diagnostic.getvalue()), (0, ''))
                    self.assertEqual(json.loads(output.getvalue()), {'kind': 'drift', 'dispatch': 'selected'})
                    selected_drift.assert_called_once()
                    suite = selected_drift.call_args.args[0]
                    self.assertEqual((len(suite.queries), len(suite.drifts)), (1, 1))
                    self.assertEqual(selected_drift.call_args.kwargs,
                                     {'repository': 'fixture', 'build': '1f', 'live': live})
            forbidden_vectors.prepare.assert_not_called()
            forbidden_retrieval.snapshot.assert_not_called()
            self.assertEqual(_state(connection), before)
