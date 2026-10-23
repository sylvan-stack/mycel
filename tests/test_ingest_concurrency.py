"""A real disjoint publication overlaps the selected public ingest transaction."""

from contextlib import contextmanager
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mycel._capture import capture_repository
from mycel._cli import run
from mycel._coverage import require_check_database
from mycel._ingest import _CompleteProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import require_transaction_guards
from mycel._resolver import SourceResolver, _CATALOG_SQL
from mycel._settings import load_settings

try:
    from . import test_ingest as ingest_fixtures
except ImportError:
    import test_ingest as ingest_fixtures


class IngestConcurrencyStoreTests(unittest.TestCase):
    check_kind = "store"

    def test_public_ingest_survives_disjoint_publication_inside_its_producer_transaction(self):
        require_check_database(self.store_fixture.database)
        self.assertIs(self.store_fixture.backend.real_store, True)
        with tempfile.TemporaryDirectory(prefix="mycel_ingest_concurrency_") as directory:
            base = Path(directory)
            for name in ("a", "b"):
                (base / name).mkdir()
                (base / name / "guide.md").write_text("# Guide\n" + name + " old.\n")
            config = base / "settings.toml"
            address = self.store_fixture.backend.address(self.store_fixture.database)
            config.write_text("[store]\naddress=" + json.dumps(address) + "\n" + "".join(
                "[repos." + name + "]\nenabled=true\nartifact_root=" +
                json.dumps(str(base / name)) + "\n" for name in ("a", "b")))
            settings = load_settings(path=config, home=base)
            with self.store_fixture.backend.connection(self.store_fixture.database) as selected, \
                    self.store_fixture.backend.connection(self.store_fixture.database) as disjoint:
                for name in ("a", "b"):
                    LocatedCaptureStore(selected).apply(settings, capture_repository(settings, name))
                a_bytes = b"# Guide\na changed selected text.\n"
                b_bytes = b"# Guide\nb concurrently changed text.\n"
                (base / "a" / "guide.md").write_bytes(a_bytes)
                (base / "b" / "guide.md").write_bytes(b_bytes)
                manifest = capture_repository(settings, "b")

                class OverlapConnection:
                    armed = False
                    fired = False
                    published = None

                    def __getattr__(self, name):
                        return getattr(selected, name)

                    def execute(self, sql, *arguments, **kwargs):
                        if sql == _CATALOG_SQL and self.armed and not self.fired:
                            # The source pass has already published its own
                            # prospective rows and holds its actual writer
                            # guards. The peer commits before its next catalog
                            # read, not before or after the source invocation.
                            require_transaction_guards(selected, ("a",))
                            self.fired = True
                            self.published = LocatedCaptureStore(disjoint).apply(settings, manifest)
                        return selected.execute(sql, *arguments, **kwargs)

                overlapping = OverlapConnection()
                original = _CompleteProducer.__call__

                def arm(producer, connection, result):
                    overlapping.armed = True
                    return original(producer, connection, result)

                @contextmanager
                def connected(credentials):
                    self.assertEqual(credentials.store_target().address, address)
                    yield overlapping

                output, diagnostics = StringIO(), StringIO()
                with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}), \
                        patch("mycel._database.store_connection", connected), \
                        patch("mycel._build_identity.current_build", return_value=None), \
                        patch.object(_CompleteProducer, "__call__", arm):
                    status = run(("ingest", "--repo", "a"), stdout=output, stderr=diagnostics)
                reply = json.loads(output.getvalue())
                self.assertEqual((status, diagnostics.getvalue()), (0, ""), reply)
                self.assertEqual(set(reply["repositories"]), {"a"})
                self.assertIs(reply["repositories"]["a"]["ran"], True)
                self.assertTrue(overlapping.fired)
                self.assertIs(overlapping.published.changed, True)
                catalog = SourceResolver.from_store(selected, settings)
                for name, exact in (("a", a_bytes), ("b", b_bytes)):
                    member, = catalog.resolve(name + ":@artifact/guide.md#Guide").selection.members
                    self.assertEqual(member.chunk.source, exact)
                    self.assertEqual((base / name / "guide.md").read_bytes(), exact)


class IngestCrossRepositoryStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = ingest_fixtures.IngestStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_foreign_refresh_and_requested_pass_share_cumulative_reply_and_final_activity(self):
        fixture = self.fixture
        fixture.add_repository("downstream",
            b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Answer\nStable answer.\n')
        status, initial = fixture.invoke("--repo", "fixture", "--repo", "downstream")
        self.assertEqual(status, 0, initial)
        (fixture.base.artifact / "guide.md").write_bytes(b"# Guide\nChanged selected source.\n")
        status, reply = fixture.invoke("--repo", "fixture", "--repo", "downstream")
        self.assertEqual(status, 0, reply)
        foreign = reply["repositories"]["fixture"]["dependencyRepositories"]["downstream"]
        direct = reply["repositories"]["downstream"]
        self.assertEqual(foreign["refsChecked"], 1)
        self.assertEqual(direct["refsChecked"], 2)
        self.assertEqual(direct["refsChanged"], 1)
        self.assertEqual(direct["files"]["changed"], 0)
        self.assertEqual(direct["pending"], direct["embedding"]["versions"]["pending"])
        from mycel._activity import activity_state
        with fixture.base.connect() as connection:
            entries = {}
            for repository in ("fixture", "downstream"):
                identifier = connection.execute("SELECT id FROM public.mycel_activity "
                    "WHERE repository=%s ORDER BY id DESC LIMIT 1", (repository,)).fetchone()[0]
                entries[repository] = activity_state(connection, identifier)
                self.assertEqual(entries[repository]["counts"], reply["repositories"][repository])
            self.assertEqual(entries["fixture"]["invocation"], entries["downstream"]["invocation"])
            self.assertEqual(entries["downstream"]["files"], [])
            self.assertEqual(entries["downstream"]["decisions"], [])

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

    def test_selected_source_pass_keeps_unrelated_pending_ref_in_same_foreign_chunk_exact(self):
        fixture = self.fixture
        third = self.prepare_two_sources()
        (third / "answer.md").write_bytes(b"# Answer\nChanged third source.\n")
        with fixture.base.connect() as connection:
            # A complete C publication deliberately leaves its dependency
            # observations to the later owning producer. A must observe only
            # its own affected ref, even though B also declares a ref to C.
            LocatedCaptureStore(connection).apply(fixture.base.settings,
                capture_repository(fixture.base.settings, "third"))
            before = self.third_dependency(connection)
        (fixture.base.artifact / "guide.md").write_bytes(b"# Guide\nChanged selected source.\n")
        status, reply = fixture.invoke("--repo", "fixture")
        self.assertEqual(status, 0, reply)
        self.assertTrue(reply["repositories"]["fixture"]["ran"])
        with fixture.base.connect() as connection:
            self.assertEqual(self.third_dependency(connection), before)
            self.selected_ref_changed(connection)

    def test_unindexed_unrelated_source_does_not_refuse_selected_foreign_ref_refresh(self):
        fixture = self.fixture
        third = self.prepare_two_sources()
        with fixture.base.connect() as connection:
            before = self.third_dependency(connection)
        (third / "answer.md").write_bytes(b"# Answer\nUnindexed unrelated third edit.\n")
        (fixture.base.artifact / "guide.md").write_bytes(b"# Guide\nChanged selected source.\n")
        status, reply = fixture.invoke("--repo", "fixture")
        self.assertEqual(status, 0, reply)
        self.assertTrue(reply.get("repositories", {}).get("fixture", {}).get("ran"), reply)
        self.assertNotIn("refused", reply["repositories"]["fixture"])
        self.assertEqual(reply["repositories"]["fixture"]["stalePending"], [])
        with fixture.base.connect() as connection:
            self.assertEqual(self.third_dependency(connection), before)
            self.selected_ref_changed(connection)
