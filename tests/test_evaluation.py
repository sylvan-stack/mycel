# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Versioned-file acceptance and real offline evaluator regression checks.

The injected search replies test accounting rather than implement a ranking.
MYC-13.11 through .17 additionally need genuine disposable-store proofs; these
unit checks cannot establish production search or MYC-4.25 ranking quality.
"""
from dataclasses import FrozenInstanceError

from mycel._evaluation import (EvaluationSet, PreparedQueryVector, RetrievalPlace,
                               RetrievalQuery, RetrievalReply, comparison_failures,
                               empty_retrieval_report, load_evaluation_file,
                               run_retrieval_evaluation)


import tempfile
import unittest
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from mycel._errors import MycelError
from mycel._evaluation import (
    EvaluationSet,
    PreparedQueryVector,
    RetrievalPlace,
    load_evaluation_file,
    run_retrieval_evaluation,
)
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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
