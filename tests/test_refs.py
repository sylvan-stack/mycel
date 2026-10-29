# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Public refs command proofs through the finite JSON and disposable-store boundaries."""

import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings
from mycel._store import TABLES

try:
    pass
    from . import test_located_declaration_transaction as producer_fixtures
except ImportError:
    import test_located_declaration_transaction as producer_fixtures


def invoke(config, arguments):
    output, diagnostics = StringIO(), StringIO()
    with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}):
        status = run(arguments, stdout=output, stderr=diagnostics)
    # json.loads also rejects a second concatenated JSON document.
    return status, json.loads(output.getvalue()), diagnostics.getvalue()


def store_state(connection):
    rows = {table.name: tuple(sorted(connection.execute(
        'SELECT * FROM public."' + table.name + '"').fetchall(), key=repr)) for table in TABLES}
    sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences WHERE schemaname='public'").fetchall()
    rows["sequences"] = tuple((name, connection.execute(
        'SELECT last_value,is_called FROM public."' + name + '"').fetchone()) for (name,) in sequences)
    return rows


class RefsCliTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class RefsStoreTests(unittest.TestCase):
    check_kind = "store"

    def configured(self, root, repositories, *, organizations=""):
        original = load_settings(path=self.store_fixture.settings_file)
        config = root / "report.toml"
        text = ('[store]\naddress=' + json.dumps(original.values["store"]["address"]) +
                '\n[embedding]\ndimensions=' + str(original.values["embedding"]["dimensions"]) + '\n')
        for name, values in repositories.items():
            text += '[repos.' + name + ']\n'
            for key, value in values.items():
                text += key + '=' + (str(value).lower() if type(value) is bool else json.dumps(value)) + '\n'
        config.write_text(text + organizations)
        return config, load_settings(path=config)


class RefsProducerStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = producer_fixtures.LocatedDeclarationTransactionStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.base = self.fixture.fixture



# Archived complete imports; restore needed names in their original scope, not at this file tail.
