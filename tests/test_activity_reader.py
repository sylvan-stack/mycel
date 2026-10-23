"""Public pass identity details through the finite CLI and real-store boundary."""

from contextlib import contextmanager
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from mycel._activity import AppliedMutation, FileChange, IdentityChange, MutationActivity
from mycel._cli import Invocation, run
from mycel._activity_reader import handle_activity
from mycel._errors import MycelError
from mycel._settings import load_settings
from mycel._store import TABLES


def invoke(arguments):
    output, diagnostics = StringIO(), StringIO()
    status = run(arguments, stdout=output, stderr=diagnostics)
    return status, json.loads(output.getvalue()), diagnostics.getvalue()


def state(connection):
    return {table.name: tuple(sorted(connection.execute(
        'SELECT * FROM public."' + table.name + '"').fetchall(), key=repr)) for table in TABLES}


class ActivityReaderTests(unittest.TestCase):
    def test_invalid_identifiers_and_filters_stop_before_store_access(self):
        with patch("mycel._activity_reader.invocation_store") as connect:
            for arguments in (("--entry", "0"), ("--entry", "-1"), ("--entry", "01"),
                              ("--entry", "one"), ("--entry", str(2**63)),
                              ("--entry", "1", "extra"), ("--kind", "unsupported-kind")):
                with self.subTest(arguments=arguments):
                    with self.assertRaises(MycelError) as failure:
                        handle_activity(Invocation("activity", arguments=arguments))
                    self.assertEqual(failure.exception.code, "invalid_input")
            for invocation in (Invocation("activity", repositories=("fixture",), arguments=("--entry", "1")),
                               Invocation("activity", all_repositories=True, arguments=("--entry", "1"))):
                with self.assertRaisesRegex(MycelError, "exclusive"):
                    handle_activity(invocation)
            connect.assert_not_called()

    def test_cli_entry_syntax_and_help_are_finite_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.toml"
            config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n[repos.fixture]\nenabled=true\n')
            with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}), \
                    patch("mycel._database.store_connection") as connect, \
                    patch("mycel._credentials.Credentials.embedding_key") as embedding:
                for arguments in (("activity", "--entry"), ("activity", "--entry", "0"),
                                  ("activity", "--entry", "1", "--all"),
                                  ("activity", "--entry", "1", "--repo", "fixture")):
                    status, reply, stderr = invoke(arguments)
                    self.assertEqual((status, reply["error"]["code"], stderr), (1, "invalid_input", ""))
                status, reply, stderr = invoke(("activity", "--help"))
                self.assertEqual((status, stderr), (0, ""))
                self.assertIn("--entry <id>", reply["commands"][0]["options"])
                connect.assert_not_called()
                embedding.assert_not_called()


class ActivityReaderStoreTests(unittest.TestCase):
    check_kind = "store"

    def test_public_pass_details_preserve_all_ordered_identity_decisions_without_writes(self):
        settings = load_settings(path=self.store_fixture.settings_file)
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            connection.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) VALUES ('fixture','{}')")
            files = (FileChange("code", "same.py", "disk", "changed"),
                     FileChange("artifact", "same.py", "topic", "added"))
            decisions = tuple(IdentityChange("code", "same.py", "disk", uuid4(), decision, name,
                              "previous" if decision == "renamed" else None)
                              for decision, name in (("renamed", "z"), ("unchanged", "a"),
                                  ("edited", "b"), ("new", "c"), ("removed", "d")))
            decisions += (IdentityChange("artifact", "same.py", "topic", uuid4(), "new", "section"),)
            with MutationActivity(connection, build=31).session() as audit:
                def write(c):
                    c.execute("UPDATE public.mycel_repository_state SET read_locations='{}' WHERE repository='fixture'")
                    return AppliedMutation(True, {"filesChanged": 2}, files=files, decisions=decisions)
                audit.apply("fixture", "ingest", write)
                identifier = connection.execute("SELECT id FROM public.mycel_activity").fetchone()[0]
                audit.finish("done")
            before = state(connection)
            @contextmanager
            def connected(credentials):
                yield connection
            with patch.dict(os.environ, {"MYCEL_CONFIG": str(settings.file)}), \
                    patch("mycel._database.store_connection", connected), \
                    patch("mycel._credentials.Credentials.embedding_key") as embedding:
                status, reply, stderr = invoke(("activity", "--entry", str(identifier)))
            self.assertEqual((status, stderr), (0, ""))
            entry, = reply["entries"]
            self.assertEqual((entry["id"], entry["build"], entry["outcome"]), (str(identifier), "1f", "done"))
            self.assertEqual(entry["counts"], {"filesChanged": 2})
            self.assertEqual([item["decision"] for item in entry["decisions"]],
                             ["new", "unchanged", "edited", "new", "removed", "renamed"])
            self.assertEqual(entry["decisions"][-1]["previousName"], "previous")
            self.assertTrue(all("previousName" not in item for item in entry["decisions"][:-1]))
            self.assertEqual(entry["files"][0]["root"], "artifact")
            self.assertEqual(state(connection), before)
            embedding.assert_not_called()

    def test_running_and_unfinished_entry_details_do_not_rewrite_activity_or_prune(self):
        settings = load_settings(path=self.store_fixture.settings_file)
        with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
            connection.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) VALUES ('fixture','{}')")
            @contextmanager
            def opened(invocation):
                yield connection, None
            with MutationActivity(connection, build=1).session() as audit:
                audit.apply("fixture", "ingest", lambda c: AppliedMutation(True, {"filesChanged": 0}))
                identifier = connection.execute("SELECT id FROM public.mycel_activity").fetchone()[0]
                invocation = Invocation("activity", arguments=("--entry", str(identifier)), settings=settings)
                before = state(connection)
                with patch("mycel._activity_reader.invocation_store", opened):
                    entry = handle_activity(invocation).value["entries"][0]
                self.assertEqual(entry["outcome"], "running")
                self.assertNotIn("endedAt", entry)
                self.assertEqual(state(connection), before)
            # Model a retained open entry after its exact session has ended;
            # the substrate separately proves actual abrupt process death.
            connection.execute("UPDATE public.mycel_activity SET outcome=NULL,ended_at=NULL WHERE id=%s", (identifier,))
            before = state(connection)
            with patch("mycel._activity_reader.invocation_store", opened):
                entry = handle_activity(invocation).value["entries"][0]
            self.assertEqual(entry["outcome"], "unfinished")
            self.assertEqual(state(connection), before)
