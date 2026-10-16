"""Configured disposable-store proofs for exact reads and bounded freshness."""

from hashlib import sha256
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._cli import run
from mycel._capture import _Capture
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._freshness import Deadline
from mycel._declared_refs import DeclaredRefStore
from mycel._locks import operation_guard
from mycel._read import ReadSelectionError
from mycel._read_store import read_from_store
from mycel._resolver import SourceResolver
from mycel._source_refs import SourceAddress
from mycel._store import checked_store, search_text

try:
    from . import test_declared_refs as declared_fixtures
    from . import test_freshness_store as freshness_fixtures
    from . import test_retrieval_store as retrieval_fixtures
except ImportError:
    import test_declared_refs as declared_fixtures
    import test_freshness_store as freshness_fixtures
    import test_retrieval_store as retrieval_fixtures


class ReadStoreTests(unittest.TestCase):
    def setUp(self):
        self.base = retrieval_fixtures.RetrievalStoreTests()
        self.base.store_fixture = self.store_fixture
        self.settings = self.base.settings()

    def connection(self):
        return self.base.connection()

    def read(self, connection, place=None, **options):
        options.setdefault("no_fresh", True)
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.settings, place, **options)

    def seed(self, connection, path, source, members, *, root="code", repository="fixture",
             aliases=(), location_kind="disk"):
        """Persist complete file bytes and independently supplied chunk spans."""
        file_id, file_version, location = uuid4(), uuid4(), uuid4()
        raw = source.encode("utf-8")
        corpus = "documents" if path.endswith(".md") else "code"
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s)",
                           (file_id, repository, root, path, corpus))
        connection.execute("INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,'{}')",
                           (file_version, file_id, sha256(raw).hexdigest(), raw))
        connection.execute("INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,'{}')",
                           (location, file_version, location_kind, location_kind))
        for alias_root, alias_path in aliases:
            connection.execute("INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s)",
                               (file_id, alias_root, alias_path))
        result = {}
        for name, kind, text, extra in members:
            identifier = uuid4()
            chunk_raw = text.encode("utf-8")
            start = raw.index(chunk_raw)
            metadata = {"name": name, "kind": kind, "span": {"start": start,
                        "end": start + len(chunk_raw)}, **extra}
            connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,'{}')",
                               (identifier, repository, file_id, kind))
            version = connection.execute("INSERT INTO public.mycel_chunk_versions "
                "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
                (identifier, sha256(chunk_raw).hexdigest(), chunk_raw, search_text(chunk_raw),
                 Jsonb(metadata))).fetchone()[0]
            connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,'{}')",
                               (uuid4(), version, location, location_kind, location_kind))
            result[name] = str(identifier), version, text
        return result

    @staticmethod
    def generated(connection, *, kind="summary", name="1/7", text="Stored generated text.\n",
                  repository="fixture"):
        identifier = uuid4()
        path = "summaries" if kind == "summary" else "overview"
        raw = text.encode("utf-8")
        connection.execute("INSERT INTO public.mycel_repository_state VALUES (%s,NULL,'[]') ON CONFLICT DO NOTHING",
                           (repository,))
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,NULL,%s,'{}')",
                           (identifier, repository, kind))
        version = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,'{}',%s) RETURNING id",
            (identifier, sha256(raw).hexdigest(), raw, search_text(raw),
             Jsonb({"name": name, "kind": kind, "path": path}))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,NULL,'index','index','{}')",
                           (uuid4(), version))
        return str(identifier), version, SourceAddress(repository, "index", path, name).address

    @proves("MYC-11.1", "MYC-11.5", kind="store")
    def test_whole_retained_code_document_summary_and_overview_text_need_no_vector_or_file(self):
        with self.connection() as connection:
            code_text = "def perform():\n    return 'full indexed text'\n"
            code = self.seed(connection, "perform.py", code_text,
                (("perform", "function", code_text, {}),))["perform"]
            document_text = "# Exact\n" + "Complete body.\n" * 100 + "雪\0final line\n"
            document = self.seed(connection, "note.md", document_text,
                (("Exact", "document", document_text, {"title": "Exact"}),), root="artifact")["Exact"]
            summary = self.generated(connection, text="Summary first\nSummary complete final\n")
            overview = self.generated(connection, kind="overview", name="src/net",
                                      text="# Networking\nWhole overview section.\n")
            expected = ((code[0], "code", code[2]), (document[0], "document", document[2]),
                        (summary[0], "summary", "Summary first\nSummary complete final\n"),
                        (overview[0], "overview", "# Networking\nWhole overview section.\n"))
            before = self.base.contents(connection)
            for identifier, origin, text in expected:
                with self.subTest(origin=origin):
                    reply = self.read(connection, identifier=identifier)
                    self.assertEqual((reply["id"], reply["origin"], reply["text"], reply["cut"]),
                                     (identifier, origin, text, False))
                    self.assertNotIn("file", reply)
                    self.assertTrue(reply["unreadable"])
                    self.assertFalse(reply["dependencyCheck"]["complete"])
            self.assertEqual(self.read(connection, summary[2])["text"], expected[2][2])
            self.assertEqual(self.read(connection, overview[2])["text"], expected[3][2])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))
            self.assertEqual(self.base.contents(connection), before)

    @proves("MYC-11.3", kind="store")
    def test_exact_name_wins_and_unique_bare_method_heading_and_class_header_match(self):
        with self.connection() as connection:
            header = "class Policy:\n    flag = True\n"
            method = "    def allow(self):\n        return self.flag\n"
            other_header = "class Other:\n"
            other_method = "    def reject(self):\n        return False\n"
            members = (("Policy", "class", header, {}),
                ("Policy.allow", "method", method, {"family": "Policy"}),
                ("Other", "class", other_header, {}),
                ("Other.reject", "method", other_method, {"family": "Other"}))
            seeded = self.seed(connection, "policy.py", header + method + other_header + other_method, members)
            for name, selected in (("Policy.allow", "Policy.allow"), ("allow", "Policy.allow"),
                                   ("Policy", "Policy")):
                reply = self.read(connection, "fixture:policy.py#" + name)
                self.assertEqual((reply["id"], reply["text"]), (seeded[selected][0], seeded[selected][2]))
            one, exact = "## Shared\nFirst nested body.\n", "# Shared\nExact heading body.\n"
            unique = "## Unique\nOnly bare heading.\n"
            headings = self.seed(connection, "guide.md", "# Parent\n" + one + unique + exact,
                (("Parent > Shared", "document", one, {"title": "Shared"}),
                 ("Parent > Unique", "document", unique, {"title": "Unique"}),
                 ("Shared", "document", exact, {"title": "Shared"})), root="artifact")
            self.assertEqual(self.read(connection, "fixture:guide.md#Shared")["text"], exact)
            self.assertEqual(self.read(connection, "fixture:guide.md#Unique")["id"],
                             headings["Parent > Unique"][0])

    @proves("MYC-11.4", kind="store")
    def test_missing_ambiguous_disabled_and_unknown_reads_use_the_closed_refusals(self):
        with self.connection() as connection:
            members = tuple((f"Policy{number:02}.run", "method", f"method {number}\n",
                             {"family": f"Policy{number:02}"}) for number in range(25))
            self.seed(connection, "many.py", "".join(member[2] for member in members), members)
            for ref, code in (("fixture:missing.py#Nope", "invalid_input"),
                ("fixture:many.py#absent", "invalid_input"),
                ("disabled:many.py#run", "refused"), ("unknown:many.py#run", "unknown_repository")):
                with self.subTest(ref=ref), self.assertRaises(MycelError) as error:
                    self.read(connection, ref)
                self.assertEqual(error.exception.code, code)
            with self.assertRaises(ReadSelectionError) as error:
                self.read(connection, "fixture:many.py#run")
            refusal = error.exception.to_dict()
            self.assertEqual(refusal["error"]["code"], "invalid_input")
            self.assertEqual(len(refusal["candidates"]), 20)
            self.assertEqual([row["address"] for row in refusal["candidates"]],
                [f"fixture:@code/many.py#Policy{number:02}.run" for number in range(20)])
            self.assertTrue(all(row["root"] == "code" and row["path"] == "many.py"
                                for row in refusal["candidates"]))

    @proves("MYC-11.11", kind="store")
    def test_qualified_roots_percent_names_index_collisions_and_aliases_never_guess_a_file(self):
        with self.connection() as connection:
            code_text, artifact_text = "# Setup\nCheckout document.\n", "# Different\nArtifact document.\n"
            code = self.seed(connection, "README.md", code_text,
                (("Setup", "document", code_text, {"title": "Setup"}),))["Setup"]
            artifact = self.seed(connection, "README.md", artifact_text,
                (("Different", "document", artifact_text, {"title": "Different"}),), root="artifact")["Different"]
            self.assertEqual(self.read(connection, "fixture:@code/README.md#Setup")["id"], code[0])
            self.assertEqual(self.read(connection, "fixture:@artifact/README.md#Different")["id"], artifact[0])
            with self.assertRaises(ReadSelectionError) as error:
                self.read(connection, "fixture:README.md#Setup")
            self.assertEqual(error.exception.code, "invalid_input")
            candidates = error.exception.to_dict()["candidates"]
            self.assertEqual({row["address"] for row in candidates},
                             {"fixture:@code/README.md", "fixture:@artifact/README.md"})
            self.assertEqual({row["root"] for row in candidates}, {"code", "artifact"})
            self.assertEqual(self.read(connection, identifier=code[0])["address"],
                             "fixture:@code/README.md#Setup")
            generated = self.generated(connection)
            physical_text = "# 1/7\nReal file, separate from generated text.\n"
            physical = self.seed(connection, "summaries", physical_text,
                (("1/7", "document", physical_text, {"title": "1/7"}),), root="artifact")["1/7"]
            self.assertEqual(self.read(connection, generated[2])["id"], generated[0])
            self.assertEqual(self.read(connection, "fixture:@artifact/summaries#1%2F7")["id"], physical[0])
            self.assertEqual(self.read(connection, identifier=generated[0])["root"], "index")
            with self.assertRaises(ReadSelectionError) as error:
                self.read(connection, "fixture:summaries#1/7")
            self.assertEqual(error.exception.code, "invalid_input")
            self.assertEqual({row["root"] for row in error.exception.to_dict()["candidates"]},
                             {"artifact", "index"})
            shared_text = "# Limits > Backoff\nCanonical root alias.\n"
            shared = self.seed(connection, "rules.md", shared_text,
                (("Limits > Backoff", "document", shared_text, {"title": "Limits > Backoff"}),),
                root="artifact", aliases=(("code", "docs/rules.md"),))["Limits > Backoff"]
            reply = self.read(connection, "fixture:@code/docs/rules.md#Limits%20%3E%20Backoff")
            self.assertEqual((reply["id"], reply["root"], reply["address"]),
                (shared[0], "artifact", "fixture:@artifact/rules.md#Limits%20%3E%20Backoff"))

    @proves("MYC-11.1", "MYC-11.5", kind="store")
    def test_disk_selection_excludes_branch_and_stash_and_current_exact_bytes_override_text_projection(self):
        with self.connection() as connection:
            current = "# Current\nComplete retained text with 雪\0NUL.\n"
            selected = self.seed(connection, "current.md", current,
                (("Current", "document", current, {"title": "Current"}),), root="artifact")["Current"]
            branch = self.seed(connection, "branch.md", "# Branch\nOld text.\n",
                (("Branch", "document", "# Branch\nOld text.\n", {"title": "Branch"}),),
                root="artifact", location_kind="branch")["Branch"]
            stash = self.seed(connection, "stash.md", "# Stash\nStashed text.\n",
                (("Stash", "document", "# Stash\nStashed text.\n", {"title": "Stash"}),),
                root="artifact", location_kind="stash")["Stash"]
            projection = connection.execute("SELECT text FROM public.mycel_chunk_versions WHERE id=%s",
                                            (selected[1],)).fetchone()[0]
            self.assertNotEqual(projection, current)
            self.assertNotIn("\0", projection)
            self.assertEqual(self.read(connection, identifier=selected[0])["text"], current)
            for identifier in (branch[0], stash[0]):
                with self.assertRaises(MycelError) as error:
                    self.read(connection, identifier=identifier)
                self.assertEqual(error.exception.code, "invalid_input")

    @proves("MYC-11.1", "MYC-11.4", "MYC-11.5", kind="store")
    def test_public_command_returns_one_schema_one_reply_and_serializes_root_ambiguity(self):
        with self.connection() as connection:
            text = "# Heading\nWhole command body.\n"
            selected = self.seed(connection, "README.md", text,
                (("Heading", "document", text, {"title": "Heading"}),))["Heading"]
            self.seed(connection, "README.md", text,
                (("Heading", "document", text, {"title": "Heading"}),), root="artifact")
        config = self.store_fixture.root / "read-command.toml"
        roots = self.settings.values["repos"]["fixture"]
        config.write_text('[store]\naddress=' + json.dumps(self.store_fixture.backend.address(self.store_fixture.database))
            + '\n[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(roots["code_root"])
            + '\nartifact_root=' + json.dumps(roots["artifact_root"]) + '\n')
        with patch.dict("os.environ", {"MYCEL_CONFIG": str(config)}):
            for args in (["read", "fixture:@code/README.md#Heading", "--no-fresh"],
                         ["read", "--id", selected[0], "--no-fresh"],
                         ["read", "--repo", "fixture", "@code/README.md#Heading", "--no-fresh"]):
                output, errors = io.StringIO(), io.StringIO()
                with self.subTest(args=args):
                    self.assertEqual(run(args, stdout=output, stderr=errors), 0)
                    reply = json.loads(output.getvalue())
                    self.assertEqual((reply["schema"], reply["id"], reply["text"]), (1, selected[0], text))
                    self.assertEqual(reply["origin"], "document")
                    self.assertNotIn("repositories", reply)
                    self.assertEqual(errors.getvalue(), "")
            output, errors = io.StringIO(), io.StringIO()
            self.assertEqual(run(["read", "fixture:README.md#Heading", "--no-fresh"],
                                 stdout=output, stderr=errors), 1)
            refusal = json.loads(output.getvalue())
            self.assertEqual(refusal["error"]["code"], "invalid_input")
            self.assertEqual({row["root"] for row in refusal["candidates"]}, {"code", "artifact"})
            self.assertEqual(errors.getvalue(), "")

    @proves("MYC-11.5", "MYC-11.6", kind="store")
    def test_shared_exact_chunk_version_reports_only_faults_owned_by_its_current_disk_location(self):
        disk = '---\nsources: ["other:@artifact/disk.md"]\n---\n# Answer\nSame complete body.\n'
        branch = '---\nsources: ["other:@artifact/branch.md"]\n---\n# Answer\nSame complete body.\n'
        with self.connection() as connection:
            disk_location, file_id, ids, versions = declared_fixtures.seed_document(
                connection, "fixture", "answer.md", disk)
            branch_location, _, _, branch_versions = declared_fixtures.seed_document(
                connection, "fixture", "answer.md", branch, file_id=file_id, chunk_ids=ids,
                kind="branch", location="feature")
            self.assertEqual(versions, branch_versions)
            declared_fixtures.retain(connection, self.settings, disk_location, disk)
            declared_fixtures.retain(connection, self.settings, branch_location, branch)
            records = DeclaredRefStore(connection).recheck(self.settings, repository="fixture")
            self.assertEqual({ref.declaration for ref in records.refs},
                             {"other:@artifact/disk.md", "other:@artifact/branch.md"})
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_ref_faults").fetchone(), (2,))
            before = self.base.contents(connection)
            reply = self.read(connection, identifier=str(ids[0]), deadline=Deadline.after(0))
            self.assertEqual(reply["text"], "# Answer\nSame complete body.\n")
            self.assertEqual({fault["ref"] for fault in reply["dependencyCheck"]["faults"]},
                             {"other:@artifact/disk.md"})
            self.assertFalse(reply["dependencyCheck"]["complete"])
            self.assertEqual(self.base.contents(connection), before)


class ReadFreshnessStoreTests(unittest.TestCase):
    def setUp(self):
        self.base = freshness_fixtures.FreshnessStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

    def read(self, connection, place="fixture:@artifact/driver.md#Driver", **options):
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.base.settings, place, **options)

    @proves("MYC-11.4", "MYC-11.11", kind="store")
    def test_fresh_discovery_refuses_a_new_physical_root_collision_before_an_old_heading_can_win(self):
        checkout = self.base.base.code / "README.md"
        text = "# Original\nWhole checkout document text.\n"
        checkout.write_text(text)
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            selected = SourceResolver.from_store(connection, self.base.settings).resolve(
                "fixture:@code/README.md#Original", purpose="read").selection.members[0].chunk
            collision = self.base.folders["fixture"] / "README.md"
            collision.write_text("# Different\nNew artifact file has no Original heading.\n")
            with self.assertRaises(ReadSelectionError) as error:
                self.read(connection, "fixture:README.md#Original")
            refusal = error.exception.to_dict()
            self.assertEqual(refusal["error"]["code"], "invalid_input")
            self.assertEqual({row["address"] for row in refusal["candidates"]},
                             {"fixture:@code/README.md", "fixture:@artifact/README.md"})
            self.assertEqual({row["root"] for row in refusal["candidates"]}, {"code", "artifact"})
            explicit = self.read(connection, "fixture:@code/README.md#Original")
            self.assertEqual((explicit["id"], explicit["text"]), (selected.identifier, text))
            by_id = read_from_store(connection, self.base.settings, identifier=selected.identifier,
                                    deadline=Deadline.after(30), no_fresh=True)
            self.assertEqual((by_id["address"], by_id["text"]),
                             ("fixture:@code/README.md#Original", text))

    @proves("MYC-11.3", "MYC-11.4", kind="store")
    def test_fresh_discovery_refuses_a_new_duplicate_bare_heading_instead_of_the_old_unique_match(self):
        path = self.base.folders["fixture"] / "headings.md"
        original = "# Parent\n## Shared\nOriginal shared section.\n"
        path.write_text(original)
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            old = self.read(connection, "fixture:@artifact/headings.md#Shared", no_fresh=True)
            path.write_text(original + "# Other\n## Shared\nA newly colliding section.\n")
            with self.assertRaises(ReadSelectionError) as error:
                self.read(connection, "fixture:@artifact/headings.md#Shared")
            refusal = error.exception.to_dict()
            self.assertEqual(refusal["error"]["code"], "invalid_input")
            self.assertEqual({row["address"] for row in refusal["candidates"]},
                {"fixture:@artifact/headings.md#Parent%20%3E%20Shared",
                 "fixture:@artifact/headings.md#Other%20%3E%20Shared"})
            exact = self.read(connection, "fixture:@artifact/headings.md#Parent%20%3E%20Shared")
            self.assertEqual((exact["id"], exact["text"]), (old["id"], old["text"]))

    @proves("MYC-11.1", "MYC-11.4", "MYC-11.5", "MYC-11.6", kind="store")
    def test_fresh_retained_identifier_observes_disk_restoration_and_keeps_absent_branch_text_ineligible(self):
        path = self.base.base.code / "restored.md"
        raw = self.base.document("Restored", "contract:@artifact/contract.md#Contract")
        path.write_bytes(raw)
        self.base.base.commit()
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            member = SourceResolver.from_store(connection, self.base.settings).resolve(
                "fixture:@code/restored.md#Restored", purpose="read").selection.members[0].chunk
            path.unlink()
            self.base.publish(connection, "fixture")
            retained = connection.execute("""SELECT l.kind FROM public.mycel_chunks c
                JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
                JOIN public.mycel_locations l ON l.chunk_version=v.id WHERE c.id=%s""",
                (member.identifier,)).fetchall()
            self.assertTrue(any(row[0] == "branch" for row in retained), retained)
            self.assertFalse(any(row[0] == "disk" for row in retained), retained)
            with patch.object(_Capture, "capture", side_effect=AssertionError("no-fresh captured branch-only id")):
                with self.assertRaises(ReadSelectionError) as error:
                    self.read(connection, None, identifier=member.identifier, no_fresh=True)
                self.assertEqual(error.exception.code, "invalid_input")
            actual, captures = _Capture.capture, []

            def record(capture):
                captures.append(capture.repository.name)
                return actual(capture)

            with patch.object(_Capture, "capture", record):
                with self.assertRaises(ReadSelectionError) as error:
                    self.read(connection, None, identifier=member.identifier)
                self.assertEqual(error.exception.code, "invalid_input")
            self.assertIn("fixture", captures)
            self.base.base.git("restore", "--worktree", "restored.md")
            self.assertEqual(path.read_bytes(), raw)
            with patch.object(_Capture, "capture", side_effect=AssertionError("no-fresh captured restored file")):
                with self.assertRaises(ReadSelectionError) as error:
                    self.read(connection, None, identifier=member.identifier, no_fresh=True)
                self.assertEqual(error.exception.code, "invalid_input")
            self.base.glossary.write_bytes(b"# Glossary\nGoverning source changed before restoration read.\n")
            reply = self.read(connection, None, identifier=member.identifier)
            self.assertEqual((reply["id"], reply["text"]), (member.identifier, member.source.decode()))
            self.assertEqual((reply["root"], reply["origin"], reply["address"]),
                             ("code", "document", "fixture:@code/restored.md#Restored"))
            self.assertEqual(Path(reply["file"]).resolve(), path.resolve())
            self.assertTrue(reply["freshness"]["finished"], reply)
            self.assertTrue(reply["dependencyCheck"]["complete"])
            checks = {row["repository"]: row for row in reply["freshness"]["repositories"]}
            self.assertTrue({"fixture", "contract", "glossary"}.issubset(checks))
            self.assertTrue(all(checks[name]["state"] == "done"
                                for name in ("fixture", "contract", "glossary")))
            self.assertTrue(reply["stale"])

    @proves("MYC-11.6", kind="store")
    def test_recursive_upstreams_are_checked_under_one_deadline_without_returning_other_chunks(self):
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            pins, outside = self.base.pins(connection), self.base.owned(connection, "outside")
            driver, contract = self.base.driver.read_bytes(), self.base.contract.read_bytes()
            identifier, _ = self.base.key(connection, "fixture:@artifact/driver.md#Driver")
            self.base.glossary.write_bytes(b"# Glossary\nChanged governing source.\n")
            self.base.outside.write_bytes(b"# Unrelated\nUnindexed unrelated change.\n")
            captures = []
            actual = _Capture.capture

            def record(capture):
                captures.append(capture.repository.name)
                return actual(capture)

            deadline = Deadline.after(30)
            with patch.object(_Capture, "capture", record), \
                    patch("mycel._embed.embed", side_effect=AssertionError("read invoked embedding")):
                reply = self.read(connection, deadline=deadline)
            self.assertEqual(reply["id"], identifier)
            self.assertEqual(reply["repository"], "fixture")
            self.assertNotIn("results", reply)
            self.assertTrue(reply["freshness"]["checked"])
            self.assertTrue(reply["freshness"]["finished"], reply)
            self.assertTrue(reply["dependencyCheck"]["complete"])
            states = {row["repository"]: row for row in reply["freshness"]["repositories"]}
            self.assertTrue({"fixture", "contract", "glossary"}.issubset(states))
            self.assertTrue(all(states[name]["state"] == "done" for name in ("fixture", "contract", "glossary")))
            self.assertNotIn("outside", captures)
            self.assertNotIn("shared", captures)
            self.assertEqual(self.base.owned(connection, "outside"), outside)
            self.assertEqual(self.base.pins(connection), pins)
            self.assertEqual((self.base.driver.read_bytes(), self.base.contract.read_bytes()), (driver, contract))
            self.assertTrue(reply["stale"])
            reasons = reply["staleReasons"]
            self.assertTrue(any(row["kind"] == "upstream_stale" and
                row["via"][0]["repository"] == "contract" for row in reasons), reasons)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone(), (0,))

    @proves("MYC-11.1", "MYC-11.5", "MYC-11.6", kind="store")
    def test_fresh_read_ingests_changed_exact_text_and_new_qualified_file_before_final_selection(self):
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            changed = b"# Independent\nNew full text for the on-disk version.\n"
            self.base.independent.write_bytes(changed)
            reply = self.read(connection, "fixture:@artifact/independent.md#Independent")
            self.assertEqual(reply["text"], changed.decode())
            self.assertTrue(reply["freshness"]["finished"], reply)
            self.assertTrue(reply["dependencyCheck"]["complete"])
            new_file = self.base.folders["fixture"] / "new.md"
            new_file.write_bytes(b"# New\nNewly discovered exact text.\n")
            reply = self.read(connection, "fixture:@artifact/new.md#New")
            self.assertEqual(reply["text"], new_file.read_text())
            self.assertEqual(Path(reply["file"]).resolve(), new_file.resolve())
            self.assertTrue(reply["freshness"]["finished"], reply)

    @proves("MYC-11.6", kind="store")
    def test_no_fresh_preserves_every_store_row_and_reports_recursive_pending_dependencies(self):
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            before = self.base.contents(connection)
            original = SourceResolver.from_store(connection, self.base.settings).resolve(
                "fixture:@artifact/driver.md#Driver", purpose="read").selection.members[0].chunk.source.decode()
            self.base.glossary.write_bytes(b"# Glossary\nUnchecked source change.\n")
            self.base.driver.write_bytes(b"# Driver\nUnchecked driver edit.\n")
            with patch.object(_Capture, "capture", side_effect=AssertionError("no-fresh captured files")):
                reply = self.read(connection, no_fresh=True)
            self.assertEqual(reply["text"], original)
            self.assertFalse(reply["freshness"]["checked"])
            self.assertFalse(reply["freshness"]["finished"])
            self.assertFalse(reply["dependencyCheck"]["complete"])
            states = {row["repository"]: row for row in reply["freshness"]["repositories"]}
            self.assertTrue({"fixture", "contract", "glossary"}.issubset(states))
            self.assertTrue(all(states[name]["state"] == "pending" for name in ("fixture", "contract", "glossary")))
            self.assertEqual(self.base.contents(connection), before)

    @proves("MYC-11.6", kind="store")
    def test_expired_one_deadline_reads_committed_index_and_lists_pending_work(self):
        with self.base.base.connect() as connection:
            self.base.prepare(connection)
            before = self.base.contents(connection)
            original = SourceResolver.from_store(connection, self.base.settings).resolve(
                "fixture:@artifact/driver.md#Driver", purpose="read").selection.members[0].chunk.source.decode()
            self.base.driver.write_bytes(b"# Driver\nCannot be checked inside the elapsed allowance.\n")
            with patch.object(_Capture, "capture", side_effect=AssertionError("elapsed allowance captured")):
                reply = self.read(connection, deadline=Deadline.after(0))
            self.assertEqual(reply["text"], original)
            self.assertFalse(reply["freshness"]["finished"])
            self.assertFalse(reply["dependencyCheck"]["complete"])
            self.assertTrue(reply["freshness"]["repositories"])
            self.assertTrue(any(row["state"] == "pending" for row in reply["freshness"]["repositories"]))
            self.assertEqual(self.base.contents(connection), before)

    @proves("MYC-11.6", kind="store")
    def test_busy_upstream_keeps_committed_text_and_a_visible_incomplete_dependency_check(self):
        with self.base.base.connect() as connection, self.base.base.connect() as blocker:
            self.base.prepare(connection)
            source_before = self.base.owned(connection, "glossary")
            pins = self.base.pins(connection)
            original = SourceResolver.from_store(connection, self.base.settings).resolve(
                "fixture:@artifact/driver.md#Driver", purpose="read").selection.members[0].chunk.source.decode()
            self.base.glossary.write_bytes(b"# Glossary\nChanged source blocked by another pass.\n")
            with checked_store(blocker), operation_guard(blocker, "glossary", "pass"):
                reply = self.read(connection)
            self.assertEqual(reply["text"], original)
            self.assertFalse(reply["freshness"]["finished"])
            self.assertFalse(reply["dependencyCheck"]["complete"])
            checks = {row["repository"]: row for row in reply["freshness"]["repositories"]}
            self.assertTrue({"fixture", "contract", "glossary"}.issubset(checks))
            self.assertEqual(checks["glossary"]["state"], "busy")
            self.assertTrue(checks["glossary"]["reason"])
            self.assertEqual(self.base.owned(connection, "glossary"), source_before)
            self.assertEqual(self.base.pins(connection), pins)
