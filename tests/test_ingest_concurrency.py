# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""A real disjoint publication overlaps the selected public ingest transaction."""

import unittest

try:
    from . import test_ingest as ingest_fixtures
except ImportError:
    import test_ingest as ingest_fixtures


class IngestConcurrencyStoreTests(unittest.TestCase):
    check_kind = "store"


class IngestCrossRepositoryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = ingest_fixtures.IngestStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)


    def prepare_two_sources(self):
        fixture = self.fixture
        third = fixture.add_repository("third", b"# Answer\nOriginal third source.\n")
        fixture.add_repository("downstream",
            b'---\nsources: ["fixture:@artifact/guide.md#Guide", "third:@artifact/answer.md#Answer"]\n'
            b'---\n# Answer\nUnchanged dependant.\n<!-- related:\n'
            b'fixture:@artifact/guide.md#Guide\nthird:@artifact/answer.md#Answer\n-->\n')
        status, reply = fixture.invoke("--repo", "fixture", "--repo", "third", "--repo", "downstream")
        self.assertEqual(status, 0, reply)
        return third

    def third_dependency(self, connection):
        # The unrelated dependency includes its baseline, natural/current
        # address, source state, reasons and exact physical row generation.
        return {
            "dependencies": connection.execute("SELECT to_jsonb(d),xmin::text FROM public.mycel_dependencies d "
                "WHERE repository='downstream' AND source_place LIKE 'third:%' ORDER BY id").fetchall(),
            "relations": connection.execute("SELECT to_jsonb(r),xmin::text FROM public.mycel_relations r "
                "WHERE repository='downstream' AND right_place LIKE 'third:%' ORDER BY id").fetchall(),
            "stale": connection.execute("SELECT to_jsonb(s),xmin::text FROM public.mycel_stale_reasons s "
                "WHERE repository='downstream' AND reason->'source'->>'repository'='third' ORDER BY id").fetchall(),
        }

    def selected_ref_changed(self, connection):
        selected = connection.execute("SELECT state FROM public.mycel_dependencies "
            "WHERE repository='downstream' AND source_place LIKE 'fixture:%'").fetchone()[0]
        self.assertIn("source_changed", selected["reasons"])
        related = connection.execute("SELECT state FROM public.mycel_relations "
            "WHERE repository='downstream' AND right_place LIKE 'fixture:%'").fetchone()[0]
        self.assertIn("related_changed", related["reasons"])


# Archived complete imports; restore needed names in their original scope, not at this file tail.
