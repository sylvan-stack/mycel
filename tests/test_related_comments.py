# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Declared relations share Markdown exclusions without becoming sources."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from mycel import _capture
from mycel._dependency_application import RetainedDependencyResolver
from mycel._dependency_inputs import DependencyCaptureInputs
from mycel._evidence import CaptureLocation, PinInputs
from mycel._source_refs import SourceAddress, read_document_declarations

import unittest

import test_capture as capture_fixtures
import test_resolver as resolver_fixtures

from mycel._markdown import split_markdown
from mycel._resolver import SourceResolver
from mycel._source_refs import read_document_declarations


class RelatedCommentTests(unittest.TestCase):
    def declarations(self, source):
        return read_document_declarations(split_markdown(source), file='docs/guide.md')

    def relations(self, source):
        return tuple(ref for group in self.declarations(source).chunk_relations
                     for ref in group.relations)


class RelatedCaptureTests(capture_fixtures._CaptureFixture, unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RelationEndpointResolverTests(unittest.TestCase):
    def catalog(self):
        header = resolver_fixtures.chunk('Policy', 'class Policy:\n', kind='class')
        method = resolver_fixtures.chunk('Policy.run', ' def run(self): pass\n',
                                        kind='method', family='Policy', number=2)
        file = resolver_fixtures.file('policy.py', 'complete bytes', root='code', members=(header, method))
        return SourceResolver(resolver_fixtures.settings(), (file,)), file, header


# Archived complete imports; restore needed names in their original scope, not at this file tail.
