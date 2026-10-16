"""Public refs command proofs through the finite JSON and disposable-store boundaries."""

from contextlib import contextmanager
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psycopg.types.json import Jsonb

from mycel._cli import run
from mycel._coverage import proves
from mycel._declared_refs import DeclaredRefStore
from mycel._errors import MycelError
from mycel._settings import load_settings
from mycel._store import TABLES, STORE_FORMAT
try:
    from .test_declared_refs import retain, seed_document
    from . import test_located_declaration_transaction as producer_fixtures
except ImportError:
    from test_declared_refs import retain, seed_document
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
    @proves("MYC-0.6", "MYC-0.7", "MYC-0.10")
    def test_invalid_args_help_and_unknown_scope_stop_before_store_or_provider_access(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.owner]\nenabled=true\n')
            with patch("mycel._database.store_connection") as connect, \
                    patch("mycel._credentials.Credentials.embedding_key") as embedding, \
                    patch("mycel._credentials.Credentials.jev_key") as classifier, \
                    patch("subprocess.Popen") as child:
                for arguments in (("refs", "extra"), ("refs", "--limit", "1"),
                                  ("refs", "--all"), ("refs", "--repo", "")):
                    status, reply, stderr = invoke(config, arguments)
                    self.assertEqual((status, reply["error"]["code"], stderr), (1, "invalid_input", ""))
                    self.assertEqual(set(reply), {"error"})
                status, reply, stderr = invoke(config, ("refs", "--repo", "unknown"))
                self.assertEqual((status, reply["repositories"][0]["error"]["code"], stderr),
                                 (1, "unknown_repository", ""))
                status, reply, stderr = invoke(config, ("refs", "--help"))
                self.assertEqual((status, stderr), (0, ""))
                self.assertTrue(reply["commands"][0]["available"])
                self.assertIn("--unresolved", reply["commands"][0]["options"])
                connect.assert_not_called()
                embedding.assert_not_called()
                classifier.assert_not_called()
                child.assert_not_called()

    @proves("MYC-0.6", "MYC-0.7")
    def test_preflight_failures_have_one_closed_error_and_stops_have_status_two(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n'
                              '[repos.owner]\nenabled=true\n')
            for code in ("store_unavailable", "store_format", "busy"):
                with patch("mycel._database.store_connection", side_effect=MycelError(code, "Fictional preflight failure.")):
                    status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
                self.assertEqual((status, stderr), (1, ""))
                self.assertEqual(reply, {"error": {"code": code, "message": "Fictional preflight failure."}})
            with patch("mycel._database.store_connection", side_effect=KeyboardInterrupt):
                status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
            self.assertEqual((status, reply["error"]["code"]), (2, "refused"))
            self.assertEqual(stderr, "Stopped by the caller.\n")


class RefsStoreTests(unittest.TestCase):
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

    @proves("MYC-2.6", "MYC-1.28", kind="store")
    def test_public_report_preserves_every_occurrence_fault_and_canonical_candidate_without_writes(self):
        text = ('---\nsources: ["malformed\\0ref", "source:@artifact/found.md#Found"]\n---\n'
                '# Answer\n<!-- sources:\n  not a ref  \nunknown:path\ndisabled:path\n'
                'source:missing.md\nsource:collision.md#Same\nsource:headings.md#Same\n'
                'source:@artifact/found.md#Found\nsource:@index/summaries#1%2F7\n-->\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, settings = self.configured(root, {"owner": {"enabled": True}, "source": {"enabled": True},
                                                     "disabled": {"enabled": False}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                location, _, chunks, versions = seed_document(connection, "owner", "answer.md", text)
                seed_document(connection, "source", "collision.md", "# Same\n", root="artifact")
                seed_document(connection, "source", "collision.md", "# Same\n", root="code")
                seed_document(connection, "source", "headings.md", "# One\n## Same\n# Two\n## Same\n")
                seed_document(connection, "source", "found.md", "# Found\n")
                retain(connection, settings, location, text)
                DeclaredRefStore(connection).recheck(settings, repository="owner")
                before = store_state(connection)
                config_before = config.read_bytes()

                @contextmanager
                def connected(credentials):
                    self.assertEqual(credentials.store_target().address, settings.values["store"]["address"])
                    yield connection

                # Reuse this real generated-store session to isolate reporting
                # children from the permitted store-password Keychain reader.
                with patch("mycel._database.store_connection", connected), \
                        patch("mycel._declared_refs.DeclaredRefStore.recheck", side_effect=AssertionError("Report retried refs")), \
                        patch("mycel._credentials.Credentials.embedding_key", side_effect=AssertionError("Report requested embedding key")), \
                        patch("mycel._credentials.Credentials.jev_key", side_effect=AssertionError("Report requested classifier key")), \
                        patch("mycel._locks.allocate_key", side_effect=AssertionError("Report allocated a lock")), \
                        patch("subprocess.Popen", side_effect=AssertionError("Report spawned a child")):
                    status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
                    filtered_status, filtered, filtered_stderr = invoke(config, ("refs", "--unresolved", "--repo", "owner"))
                self.assertEqual((status, stderr, filtered_status, filtered_stderr), (0, "", 0, ""), (reply, filtered))
                refs = reply["repositories"][0]["result"]["refs"]
                faults = filtered["repositories"][0]["result"]["refs"]
                self.assertEqual(len(refs), 10)
                self.assertEqual(len(faults), 8)
                self.assertEqual({ref["fault"] for ref in faults},
                                 {"not_a_ref", "unknown_repository", "disabled_repository", "not_found",
                                  "ambiguous_path", "ambiguous_title"})
                self.assertIn("malformed\0ref", {ref["ref"] for ref in refs})
                spaced = next(ref for ref in refs if ref["parsedRef"] == "not a ref")
                self.assertEqual((spaced["ref"], spaced["rawLine"]), ("  not a ref  ", "  not a ref  \n"))
                self.assertEqual(sum(ref["ref"] == "source:@artifact/found.md#Found" for ref in refs), 2)
                for ref in refs:
                    self.assertEqual(ref["chunk"], {"id": str(chunks[0]), "version": versions[0], "repository": "owner",
                                                   "root": "artifact", "path": "answer.md", "name": "Answer",
                                                   "address": "owner:@artifact/answer.md#Answer"})
                    self.assertEqual(ref["location"], {"id": location, "kind": "disk", "name": "disk"})
                    self.assertTrue(ref["ownerLocationAvailable"])
                    self.assertEqual(ref["baselineStatus"], "baseline_missing")
                ambiguous = next(ref for ref in refs if ref["fault"] == "ambiguous_path")
                self.assertEqual([candidate["address"] for candidate in ambiguous["candidates"]],
                                 ["source:@artifact/collision.md", "source:@code/collision.md"])
                self.assertEqual(ambiguous["candidateCount"], 2)
                self.assertEqual(store_state(connection), before)
                self.assertEqual(config.read_bytes(), config_before)

    @proves("MYC-2.6", "MYC-1.28", kind="store")
    def test_scope_preserves_partial_errors_expands_organizations_and_reads_absent_folders(self):
        text = "# Answer\n<!-- sources:\nunknown:path\n-->\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkouts"
            checkout.mkdir()
            for name in ("one", "two", "disabled"):
                (checkout / name / ".git").mkdir(parents=True)
            organizations = ('[organizations.group]\nroot=' + json.dumps(str(checkout)) +
                             '\nartifact_root=' + json.dumps(str(root / "missing_artifacts")) + '\n')
            config, settings = self.configured(root, {"one": {"enabled": True}, "two": {"enabled": True},
                                                     "disabled": {"enabled": False}}, organizations=organizations)
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                for name in ("one", "two", "disabled", "unconfigured"):
                    location, _, _, _ = seed_document(connection, name, "answer.md", text)
                    if name != "unconfigured" and name != "disabled":
                        retain(connection, settings, location, text)
                before = store_state(connection)
                status, reply, stderr = invoke(config, ("refs", "--repo", "unknown", "--repo", "group", "--repo", "one"))
                self.assertEqual((status, stderr), (1, ""))
                self.assertEqual([row["repository"] for row in reply["repositories"]], ["unknown", "one", "two"])
                self.assertEqual(reply["repositories"][0]["error"]["code"], "unknown_repository")
                self.assertEqual([len(row["result"]["refs"]) for row in reply["repositories"][1:]], [1, 1])
                current = Path.cwd()
                try:
                    os.chdir(checkout)
                    status, implicit, stderr = invoke(config, ("refs", "--unresolved"))
                finally:
                    os.chdir(current)
                self.assertEqual((status, stderr), (0, ""))
                self.assertEqual([row["repository"] for row in implicit["repositories"]], ["one", "two"])
                self.assertEqual(store_state(connection), before)

    @proves("MYC-2.6", "MYC-1.28", kind="store")
    def test_unchecked_and_missing_owner_are_reported_without_fabricating_locations_or_retrying(self):
        text = "# Answer\n<!-- sources:\nunknown:path\n-->\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, settings = self.configured(root, {"owner": {"enabled": True}, "source": {"enabled": True}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                location, _, _, _ = seed_document(connection, "owner", "answer.md", text)
                retain(connection, settings, location, text)
                status, reply, stderr = invoke(config, ("refs", "--repo", "owner", "--unresolved"))
                unchecked = reply["repositories"][0]["result"]["refs"][0]
                self.assertEqual((status, stderr, unchecked["resolutionFault"]), (0, "", "not_checked"))
                self.assertEqual(unchecked["state"], "unresolved")
                connection.execute("DELETE FROM public.mycel_locations WHERE file_location=%s", (location,))
                connection.execute("DELETE FROM public.mycel_file_locations WHERE id=%s", (location,))
                DeclaredRefStore(connection).recheck(settings, repository="owner")
                before = store_state(connection)
                status, reply, stderr = invoke(config, ("refs", "--repo", "owner", "--unresolved"))
                missing = reply["repositories"][0]["result"]["refs"][0]
                self.assertEqual((status, stderr, missing["resolutionFault"]), (0, "", "owner_location_missing"))
                self.assertFalse(missing["ownerLocationAvailable"])
                self.assertIsNone(missing["chunk"]["address"])
                self.assertEqual(missing["location"], {"id": location, "kind": "disk", "name": "disk"})
                self.assertEqual(store_state(connection), before)

    @proves("MYC-0.8", "MYC-1.28", kind="store")
    def test_wrong_format_and_structure_contention_refuse_without_repair_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _ = self.configured(root, {"owner": {"enabled": True}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                from mycel._locks import structure_guard
                with structure_guard(connection, exclusive=True):
                    status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
                self.assertEqual((status, reply["error"]["code"], stderr), (1, "busy", ""))
                connection.execute("UPDATE public.mycel_store SET format=%s", (STORE_FORMAT + 1,))
                before = store_state(connection)
                status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
                self.assertEqual((status, reply["error"]["code"], stderr), (1, "store_format", ""))
                self.assertEqual(store_state(connection), before)

    @proves("MYC-2.6", "MYC-1.28", kind="store")
    def test_each_retained_location_reports_its_own_name_and_binding_for_a_shared_exact_version(self):
        text = "# Answer\n<!-- sources:\nunknown:path\n-->\n"
        with tempfile.TemporaryDirectory() as directory:
            config, settings = self.configured(Path(directory), {"owner": {"enabled": True}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
                disk, file_id, chunks, versions = seed_document(connection, "owner", "new.md", text)
                branch, _, _, branch_versions = seed_document(connection, "owner", "new.md", text,
                    kind="branch", location="branches/old", file_id=file_id, chunk_ids=chunks)
                retain(connection, settings, disk, text)
                retain(connection, settings, branch, text)
                connection.execute("UPDATE public.mycel_file_locations SET metadata=%s WHERE id=%s",
                    (Jsonb({"root": "code", "path": "old.md", "aliases": [{"root": "code", "path": "old.md"}]}), branch))
                connection.execute("UPDATE public.mycel_locations SET metadata=metadata || %s WHERE file_location=%s",
                    (Jsonb({"name": "Former answer"}), branch))
                self.assertEqual(versions, branch_versions)
                before = store_state(connection)
                status, reply, stderr = invoke(config, ("refs", "--repo", "owner"))
                self.assertEqual((status, stderr), (0, ""))
                refs = {ref["location"]["id"]: ref for ref in reply["repositories"][0]["result"]["refs"]}
                self.assertEqual(set(refs), {disk, branch})
                self.assertEqual(refs[disk]["chunk"]["address"], "owner:@artifact/new.md#Answer")
                self.assertEqual(refs[branch]["chunk"]["address"], "owner:@code/old.md#Former%20answer")
                self.assertEqual(refs[branch]["location"]["kind"], "branch")
                self.assertEqual(store_state(connection), before)

    @proves("MYC-1.28", kind="store")
    def test_all_repository_reports_share_one_database_enforced_readonly_snapshot(self):
        text = "# Answer\n<!-- sources:\nunknown:path\n-->\n"
        with tempfile.TemporaryDirectory() as directory:
            config, settings = self.configured(Path(directory), {"one": {"enabled": True}, "two": {"enabled": True}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as peer:
                for name in ("one", "two"):
                    location, _, _, _ = seed_document(peer, name, "answer.md", text)
                    retain(peer, settings, location, text)
                from mycel._locks import snapshot_transaction
                from mycel._refs import _report
                snapshots = []

                @contextmanager
                def observe(connection):
                    with snapshot_transaction(connection):
                        snapshots.append(connection.execute(
                            "SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation')").fetchone())
                        yield

                advanced = False
                def advance_after_first_row(row):
                    nonlocal advanced
                    result = _report(row)
                    if not advanced:
                        advanced = True
                        peer.execute("UPDATE public.mycel_dependencies SET state=state || %s WHERE repository='two'",
                                     (Jsonb({"resolution": {"state": "invalid", "fault": "unregistered_repository"}}),))
                    return result

                with patch("mycel._refs.snapshot_transaction", observe), \
                        patch("mycel._refs._report", advance_after_first_row):
                    status, reply, stderr = invoke(config, ("refs", "--repo", "one", "--repo", "two"))
                self.assertEqual((status, stderr), (0, ""))
                self.assertEqual(snapshots, [("on", "repeatable read")])
                self.assertEqual([entry["result"]["refs"][0]["resolutionFault"] for entry in reply["repositories"]],
                                 ["not_checked", "not_checked"])
                status, newer, stderr = invoke(config, ("refs", "--repo", "two"))
                self.assertEqual(newer["repositories"][0]["result"]["refs"][0]["resolutionFault"], "unregistered_repository")


class RefsProducerStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = producer_fixtures.LocatedDeclarationTransactionStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.base = self.fixture.fixture

    @proves("MYC-2.6", "MYC-1.28", kind="store")
    def test_complete_producer_reports_all_equivalent_and_malformed_occurrences_per_location(self):
        text = (b'---\nsources: ["fixture:@artifact/source.md#Source", "fixture:@artifact/source.md#Source", '
                b'"malformed\\0ref", "not a ref"]\n---\n# Guide\nPlain body.\n'
                b'<!-- sources:\n  fixture:source.md#Source  \nfixture:@artifact/source.md#Source\n'
                b'  not a ref  \nnot a ref\n-->\n')
        (self.base.artifact / "guide.md").write_bytes(text)
        from mycel._located_dependencies import LocatedDependencyProducer
        with self.base.connect() as connection:
            producer = LocatedDependencyProducer(self.base.settings, captured_at="2026-10-09T10:00:00Z",
                                                 settings_home=self.base.base)
            self.fixture.publish(connection, batch_handoff=producer)
            stored = connection.execute("SELECT state FROM public.mycel_dependencies WHERE kind='declared'").fetchall()
            self.assertTrue(any(len(state["occurrences"]) == 4 for (state,) in stored))
            before = store_state(connection)
            status, reply, stderr = invoke(self.base.config, ("refs", "--repo", "fixture"))
            self.assertEqual((status, stderr), (0, ""), reply)
            refs = reply["repositories"][0]["result"]["refs"]
            disk = [ref for ref in refs if ref["location"]["kind"] == "disk"]
            branch = [ref for ref in refs if ref["location"]["kind"] == "branch"]
            self.assertEqual((len(disk), len(branch)), (8, 1))
            resolved = [ref for ref in disk if ref["state"] == "resolved"]
            self.assertEqual(len(resolved), 4)
            self.assertEqual(len({ref["id"] for ref in resolved}), 1)
            self.assertEqual({ref["occurrence"] for ref in resolved}, {0, 1, 2, 3})
            legacy = next(ref for ref in resolved if ref["parsedRef"] == "fixture:source.md#Source")
            self.assertEqual((legacy["ref"], legacy["rawLine"], legacy["origin"], legacy["line"]),
                             ("  fixture:source.md#Source  ", "  fixture:source.md#Source  \n", "comment", 7))
            self.assertEqual(sum(ref["origin"] == "frontmatter" for ref in resolved), 2)
            self.assertEqual([ref["parsedRef"] for ref in branch], ["fixture:@artifact/source.md#Source"])
            malformed = [ref for ref in disk if ref["fault"] == "not_a_ref"]
            self.assertEqual(len(malformed), 4)
            self.assertIn("malformed\0ref", {ref["ref"] for ref in malformed})
            invalid = [ref for ref in malformed if ref["parsedRef"] == "not a ref"]
            self.assertEqual(len(invalid), 3)
            self.assertEqual({ref["origin"] for ref in invalid}, {"frontmatter", "comment"})
            filtered_status, filtered, filtered_stderr = invoke(self.base.config, ("refs", "--repo", "fixture", "--unresolved"))
            self.assertEqual((filtered_status, filtered_stderr), (0, ""))
            self.assertEqual(filtered["repositories"][0]["result"]["count"], 4)
            self.assertEqual(store_state(connection), before)


if __name__ == "__main__":
    unittest.main()
