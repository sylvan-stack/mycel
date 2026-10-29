"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_ingest_concurrency as _support
from test_ingest_concurrency import (LocatedCaptureStore ,Path ,SourceResolver ,StringIO ,_CATALOG_SQL ,_CompleteProducer ,capture_repository ,contextmanager ,json ,load_settings ,os ,patch ,require_check_database ,require_transaction_guards ,run ,tempfile)


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
