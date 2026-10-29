"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_ingest_concurrency as _support
from test_ingest_concurrency import (
    IngestConcurrencyStoreTests,
    IngestCrossRepositoryStoreTests,
    LocatedCaptureStore,
    Path,
    SourceResolver,
    StringIO,
    _CATALOG_SQL,
    _CompleteProducer,
    capture_repository,
    contextmanager,
    ingest_fixtures,
    json,
    load_settings,
    os,
    patch,
    require_check_database,
    require_transaction_guards,
    run,
    tempfile,
    unittest,
)


class IngestConcurrencyStoreTests(_support.IngestConcurrencyStoreTests):
# TEST-TIER-BEGIN tests/test_ingest_concurrency.py::IngestConcurrencyStoreTests.test_public_ingest_survives_disjoint_publication_inside_its_producer_transaction
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
# TEST-TIER-END tests/test_ingest_concurrency.py::IngestConcurrencyStoreTests.test_public_ingest_survives_disjoint_publication_inside_its_producer_transaction



class IngestCrossRepositoryStoreTests(_support.IngestCrossRepositoryStoreTests):
# TEST-TIER-BEGIN tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_foreign_refresh_and_requested_pass_share_cumulative_reply_and_final_activity
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
# TEST-TIER-END tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_foreign_refresh_and_requested_pass_share_cumulative_reply_and_final_activity

# TEST-TIER-BEGIN tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_selected_source_pass_keeps_unrelated_pending_ref_in_same_foreign_chunk_exact
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
# TEST-TIER-END tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_selected_source_pass_keeps_unrelated_pending_ref_in_same_foreign_chunk_exact

# TEST-TIER-BEGIN tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_unindexed_unrelated_source_does_not_refuse_selected_foreign_ref_refresh
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
# TEST-TIER-END tests/test_ingest_concurrency.py::IngestCrossRepositoryStoreTests.test_unindexed_unrelated_source_does_not_refuse_selected_foreign_ref_refresh
