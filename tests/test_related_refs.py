# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Read-only projections of declared relation occurrences and their faults."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from mycel._cli import Invocation
from mycel._errors import MycelError
from mycel._settings import _freeze
import test_resolver as resolver_fixtures

import unittest

from mycel import _refs
from mycel._declared_refs import _raw, _stored


def row(identifier='related', *, raw='fixture:missing.md', fault='missing_file',
        state='unresolved', kind='disk', location='disk', occurrences=None):
    declared = '  ' + raw + '  '
    occurrence = {'rawDeclared': _raw(declared), 'rawLine': _raw(declared + '\r\n'),
                  'origin': 'comment', 'line': 3, 'syntaxFault': None}
    relation = {'rawRef': _stored(raw), 'rawRefHex': _raw(raw), 'ownership': 'declared',
        'managedDeclaration': True, 'occurrences': occurrences or [occurrence],
        'declarationLocation': {'file': 'file-location', 'kind': kind, 'location': location},
        'resolution': {'state': state, 'fault': fault, 'place': None, 'candidates': [], 'candidateCount': 0},
        'sourceState': 'unresolved'}
    return (identifier, 'fixture', 1, relation, None, 'chunk-id', {'name': 'Guide'},
            'fixture', 'artifact', 'guide.md', {}, kind, location, [{'name': 'Guide'}])


class _ReadOnlyRows:
    def __init__(self, dependencies, related):
        self.dependencies, self.related = dependencies, related
        self.queries = []
        self.in_snapshot = False

    def execute(self, sql, parameters):
        if not self.in_snapshot or not sql.startswith('SELECT '):
            raise AssertionError('Reporting must use the established read-only snapshot')
        self.queries.append((sql, parameters))
        if sql == _refs._REFS_SQL:
            values = self.dependencies
        elif sql == _refs._RELATED_REFS_SQL:
            values = self.related
        elif sql == _refs._JUSTIFIED_REFS_SQL:
            values = []
        else:
            raise AssertionError('Reporting may only select retained rows')
        class Cursor:
            def fetchall(self):
                return values
        return Cursor()


class RelatedRefTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
