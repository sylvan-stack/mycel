# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Initial declared sources remain unresolved until a named source pass."""

from mycel import _dependency_inputs as inputs
from mycel._capture import capture_repository


import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run

try:
    from .test_classification_store import ClassificationStoreFixture
except ImportError:
    from test_classification_store import ClassificationStoreFixture


class InitialSourceIngestStoreTests(ClassificationStoreFixture):
    check_kind = "store"

    initialize_store = staticmethod(lambda backend, settings_file: None)

    def invoke(self, *arguments, successful=True):
        package = self.store_fixture.root / 'fictional-numbered-package'
        (package / 'data').mkdir(parents=True, exist_ok=True)
        (package / 'data/build-identity.json').write_bytes(b'{"schemaVersion":1,"build":26}\n')
        output, diagnostics = StringIO(), StringIO()
        with patch('mycel._build_identity.files', return_value=package), patch.dict(
                os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(list(arguments), stdout=output, stderr=diagnostics)
        reply = json.loads(output.getvalue())
        if successful:
            self.assertEqual((status, diagnostics.getvalue()), (0, ''), reply)
        else:
            self.assertEqual(status, 1, reply)
        return reply

    def dependencies(self, connection):
        return self.fixture.fixture.dependencies(connection)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
