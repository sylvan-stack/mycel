"""Requirement and decision rows as entities of their own (MYC-17)."""

from hashlib import sha256
from pathlib import Path
import unittest
from uuid import uuid4

from mycel._capture import _parse_value, _restore_parse_value
from mycel._errors import MycelError
from mycel._markdown import EntityRow, comparison_hash, split_markdown


REQ_A = "11111111-2222-4333-8444-555555555555"
REQ_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DEC_A = "0f2c1b4e-8a9d-4c3e-9b7a-1d2e3f4a5b6c"
CHAT = "c3d4e5f6-0718-4293-a4b5-c6d7e8f90a1b"

FIXTURE = f"""---
role: authored
spec: FIX-1
status: accepted
---
# Fixture · 1 Cellar

## Requirements

| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |
| FIX-1.2 <!-- {REQ_B} --> | log every \\| bottle | New | store |

## Decisions

| ID | Question | Proposed default | Outcome | Discussion |
|---|---|---|---|---|
| FIX-D1 <!-- {DEC_A} --> | Which cellar? | The old one | Decided 19 October 2026 by the owner: the old one | [cht:{CHAT}:Q2VsbGFy] and [cellar:cht:{CHAT}:Q2VsbGFy] |
| FIX-D2 <!-- 9c0d1e2f-3a4b-4c5d-8e6f-7a8b9c0d1e2f --> | Which bottles? | All of them | Proposed: all of them | |

## Prose

| Decision | Recorded outcome |
|---|---|
| FIX-D1 · Which cellar? | the old one |

```markdown
| FIX-1.9 <!-- 99999999-2222-4333-8444-555555555555 --> | an example inside a fence | New | unit |
```
"""


class EntityRowTests(unittest.TestCase):
    def test_rows_with_a_uuid_become_entities_with_their_metadata_beside_unchanged_sections(self):
        document = split_markdown(FIXTURE)
        self.assertEqual([chunk.name for chunk in document.chunks],
                         ["Fixture · 1 Cellar", "Fixture · 1 Cellar > Requirements", "Fixture · 1 Cellar > Decisions",
                          "Fixture · 1 Cellar > Prose"])
        self.assertEqual("".join(chunk.text for chunk in document.chunks).encode(), document.source[document.frontmatter_span.byte_end:])
        self.assertEqual(document.diagnostics, ())
        self.assertEqual([(row.kind, row.id, row.uuid) for row in document.entities],
                         [("req", "FIX-1.1", REQ_A), ("req", "FIX-1.2", REQ_B), ("dec", "FIX-D1", DEC_A),
                          ("dec", "FIX-D2", "9c0d1e2f-3a4b-4c5d-8e6f-7a8b9c0d1e2f")])
        first, second, decided, open_ = document.entities
        self.assertEqual((first.title, first.status, first.verified_by, first.from_v1, first.discussion),
                         ("keep the cellar cool", "accepted", "unit", "Kept", ()))
        self.assertEqual((second.title, second.verified_by, second.from_v1), ("log every | bottle", "store", "New"))
        self.assertEqual((first.section, first.position, first.line), ("Fixture · 1 Cellar > Requirements", 1, 12))
        self.assertEqual(second.position, 2)
        self.assertEqual(first.text, f"| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |\n")
        self.assertEqual(first.snapshot_hash, sha256(first.text.encode()).hexdigest())
        self.assertEqual(first.content_hash, comparison_hash(first.text))
        self.assertEqual((decided.title, decided.status, decided.decided_at, decided.decided_by),
                         ("Which cellar?", "decided", "19 October 2026", "the owner"))
        self.assertEqual(decided.discussion, (f"[cht:{CHAT}:Q2VsbGFy]", f"[cellar:cht:{CHAT}:Q2VsbGFy]"))
        self.assertEqual((open_.status, open_.decided_at, open_.decided_by, open_.discussion), ("open", None, None, ()))
        self.assertEqual(decided.metadata(), {"kind": "dec", "uuid": DEC_A, "id": "FIX-D1", "title": "Which cellar?",
            "status": "decided", "decidedBy": "the owner", "decidedAt": "19 October 2026",
            "discussion": [f"[cht:{CHAT}:Q2VsbGFy]", f"[cellar:cht:{CHAT}:Q2VsbGFy]"]})
        self.assertEqual(first.metadata(), {"kind": "req", "uuid": REQ_A, "id": "FIX-1.1", "title": "keep the cellar cool",
            "status": "accepted", "verifiedBy": "unit", "fromV1": "Kept"})
        restored = _restore_parse_value(_parse_value(document))
        self.assertEqual(restored.entities, document.entities)
        self.assertIsInstance(restored.entities[0], EntityRow)

    def test_missing_and_repeated_uuids_are_faults_and_no_entity(self):
        source = FIXTURE.replace(f"| FIX-1.2 <!-- {REQ_B} --> |", "| FIX-1.2 |")
        source = source.replace("| FIX-D2 <!-- 9c0d1e2f-3a4b-4c5d-8e6f-7a8b9c0d1e2f --> |", f"| FIX-D2 <!-- {DEC_A} --> |")
        document = split_markdown(source)
        self.assertEqual([row.id for row in document.entities], ["FIX-1.1"])
        self.assertEqual([(item.code, item.line) for item in document.diagnostics],
                         [("entity_missing_uuid", 13), ("entity_repeated_uuid", 19), ("entity_repeated_uuid", 20)])
        self.assertIn("FIX-1.2", document.diagnostics[0].message)
        self.assertIn(DEC_A, document.diagnostics[1].message)
        self.assertEqual(len(document.chunks), 4)
        self.assertEqual("".join(chunk.text for chunk in document.chunks).encode(), document.source[document.frontmatter_span.byte_end:])

    def test_an_edit_to_a_neighbouring_row_leaves_the_entity_its_text_and_hashes(self):
        before = split_markdown(FIXTURE)
        after = split_markdown(FIXTURE.replace("keep the cellar cool", "keep the cellar cold"))
        self.assertNotEqual(before.chunks[1].content_hash, after.chunks[1].content_hash)
        self.assertEqual(before.entities[1], after.entities[1])
        self.assertNotEqual(before.entities[0].snapshot_hash, after.entities[0].snapshot_hash)
        self.assertEqual(before.entities[0].uuid, after.entities[0].uuid)
        moved = split_markdown(FIXTURE.replace(
            f"| FIX-1.2 <!-- {REQ_B} --> | log every \\| bottle | New | store |\n", "").replace(
            "## Prose\n", f"## Moved\n\n| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n"
            f"| FIX-1.2 <!-- {REQ_B} --> | log every \\| bottle | New | store |\n\n## Prose\n"))
        row = next(item for item in moved.entities if item.uuid == REQ_B)
        self.assertEqual((row.section, row.position, row.text), ("Fixture · 1 Cellar > Moved", 1, before.entities[1].text))

    def test_prose_cells_fenced_rows_and_headerless_lines_are_not_entities(self):
        document = split_markdown(FIXTURE)
        self.assertNotIn("FIX-1.9", [row.id for row in document.entities])
        self.assertEqual([item.code for item in document.diagnostics], [])
        loose = split_markdown("# Loose\n\n| FIX-1.3 <!-- 11111111-2222-4333-8444-555555555555 --> | no header |\n")
        self.assertEqual(loose.entities, ())
        self.assertEqual(loose.diagnostics, ())


class EntityUriTests(unittest.TestCase):
    def test_entity_uris_parse_format_and_resolve_by_uuid_with_the_kind_tag_as_a_check(self):
        from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
        from mycel._settings import SettingsSnapshot, _freeze
        from mycel._source_refs import SourceAddress, format_entity_uri, parse_entity_uri
        uri = format_entity_uri("req", REQ_A.upper(), "keep the cellar cool", "fixture")
        self.assertEqual(uri, f"[fixture:req:{REQ_A}:a2VlcCB0aGUgY2VsbGFyIGNvb2w=]")
        parsed = parse_entity_uri(uri)
        self.assertEqual((parsed.repository, parsed.kind, parsed.uuid, parsed.title), ("fixture", "req", REQ_A, "keep the cellar cool"))
        self.assertEqual(parse_entity_uri(f"[req:{REQ_A}:]").repository, None)
        self.assertEqual(parse_entity_uri(f"[any:dec:{DEC_A}:Q2VsbGFy]").repository, None)
        self.assertEqual(parse_entity_uri(f"[req:{REQ_A}:]").text, f"[req:{REQ_A}:]")
        for value in ("fixture:@artifact/spec.md#FIX-1.1", f"[req:{REQ_A}]", f"[toolong:{REQ_A}:]", "[req:not-a-uuid:]", ""):
            self.assertIsNone(parse_entity_uri(value), value)
        with self.assertRaises(ValueError):
            format_entity_uri("row", REQ_A, "x")
        row = f"| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |\n".encode()
        section = b"## Requirements\n\n| ID |\n|---|\n" + row
        source = b"# Cellar\n\n" + section
        def chunk(identifier, name, kind, raw, start, entity=None):
            comparison = {"kind": "code_text", "revision": "exact-sha256-v1", "hash": sha256(raw).hexdigest()}
            return ResolvedChunk(identifier, 1, name, kind, raw, sha256(raw).hexdigest(), (start, start + len(raw)),
                                 None, None, _freeze(comparison), None, None, entity)
        entity = {"kind": "req", "uuid": REQ_A, "id": "FIX-1.1", "title": "keep the cellar cool"}
        members = (chunk("c0000000-0000-4000-8000-000000000001", "Cellar", "document", source, 0),
                   chunk(REQ_A, "FIX-1.1", "req", row, len(source) - len(row), entity))
        file = ResolvedFile("f0000000-0000-4000-8000-000000000001", "fixture",
                            SourceAddress("fixture", "artifact", "spec.md"), (SourceAddress("fixture", "artifact", "spec.md"),),
                            source, sha256(source).hexdigest(), members)
        settings = SettingsSnapshot(Path("/dev/null"), _freeze({"repos": {"fixture": {"enabled": True}}}), True, True)
        resolver = SourceResolver(settings, (file,))
        for declaration in (uri, f"[req:{REQ_A}:]", f"[any:req:{REQ_A}:]"):
            result = resolver.resolve(declaration, purpose="read")
            self.assertEqual(result.state, "resolved", declaration)
            self.assertEqual((result.selection.kind, result.selection.place.address, result.selection.members[0].chunk.identifier),
                             ("req", "fixture:@artifact/spec.md#FIX-1.1", REQ_A))
            self.assertEqual(result.selection.members[0].chunk.entity, _freeze(entity))
        self.assertEqual(resolver.resolve("fixture:@artifact/spec.md#FIX-1.1").selection.members[0].chunk.identifier, REQ_A)
        self.assertEqual((resolver.resolve(f"[dec:{REQ_A}:]").state, resolver.resolve(f"[dec:{REQ_A}:]").fault),
                         ("invalid", "entity_kind_mismatch"))
        self.assertEqual((resolver.resolve(f"[req:{DEC_A}:]").state, resolver.resolve(f"[req:{DEC_A}:]").fault),
                         ("unresolved", "missing_entity"))
        self.assertEqual(resolver.resolve(f"[cht:{CHAT}:]").fault, "ineligible_entity")


class DiscussionSettingsTests(unittest.TestCase):
    def test_discussions_table_knows_only_a_password_free_address_and_its_keychain_item(self):
        import tempfile
        from mycel._credentials import _ACCOUNTS, Credentials
        from mycel._safeguards import InvocationPolicy
        from mycel._settings import load_settings
        self.assertEqual(_ACCOUNTS["discussions"], "discussions-password")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[store]\naddress="postgresql://fixture@localhost/private?sslmode=disable"\n')
            without = load_settings(path=path, home=Path(directory))
            self.assertTrue(without.valid)
            self.assertIsNone(Credentials(without, InvocationPolicy("read")).discussion_target())
            path.write_text(path.read_text() + '[discussions]\naddress="postgresql://arbol@localhost/arbol?sslmode=disable"\n')
            with_address = load_settings(path=path, home=Path(directory))
            self.assertTrue(with_address.valid)
            target = Credentials(with_address, InvocationPolicy("read")).discussion_target()
            self.assertEqual(target.address, "postgresql://arbol@localhost/arbol?sslmode=disable")
            self.assertIsNone(target.password)
            path.write_text(path.read_text() + 'timeout=5\n')
            unknown = load_settings(path=path, home=Path(directory))
            self.assertFalse(unknown.valid)
            self.assertIn("discussions.timeout", unknown.report()["unknownKeys"])
            path.write_text('[store]\naddress="postgresql://fixture@localhost/private?sslmode=disable"\n'
                            '[discussions]\naddress="postgresql://arbol:secret@localhost/arbol"\n')
            with_password = load_settings(path=path, home=Path(directory))
            self.assertFalse(with_password.valid)
            self.assertEqual([fault["key"] for fault in with_password.report()["faults"]], ["discussions.address"])


try:
    from . import test_located_reconciliation as located_fixtures
except ImportError:
    import test_located_reconciliation as located_fixtures

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from mycel._cli import run
from mycel._freshness import Deadline
from mycel._read_store import read_from_store
from mycel._settings import load_settings
from mycel import _store as store


SPEC = f"""---
role: authored
spec: FIX-1
status: accepted
---
# Fixture · 1 Cellar

## Requirements

| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |
| FIX-1.2 <!-- {REQ_B} --> | log every bottle | New | store |

## Decisions

| ID | Question | Proposed default | Outcome | Discussion |
|---|---|---|---|---|
| FIX-D1 <!-- {DEC_A} --> | Which cellar? | The old one | Decided 19 October 2026 by the owner: the old one | [cht:{CHAT}:Q2VsbGFy] |
"""

NOTE = """# Note

## Why the old cellar

Because the owner decided so.

<!-- sources:
fixture:@artifact/spec.md#FIX-D1
-->
"""

LAYOUT = """CREATE TABLE chats (id uuid PRIMARY KEY, title text, created_at timestamptz NOT NULL);
CREATE TABLE exchanges (id uuid PRIMARY KEY, chat_id uuid NOT NULL REFERENCES chats (id), number integer NOT NULL,
  state text NOT NULL, replaced_by uuid, UNIQUE (chat_id, number));
CREATE TABLE messages (exchange_id uuid NOT NULL REFERENCES exchanges (id), position integer NOT NULL,
  role text NOT NULL, text text NOT NULL, PRIMARY KEY (exchange_id, position));
INSERT INTO chats VALUES (%s, 'Cellar', now());
INSERT INTO exchanges VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 1, 'completed', NULL);
INSERT INTO exchanges VALUES ('8f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 2, 'completed', '9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b');
INSERT INTO exchanges VALUES ('9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 3, 'completed', NULL);
INSERT INTO messages VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Which cellar?');
INSERT INTO messages VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 3, 'assistant', 'The old one.');
INSERT INTO messages VALUES ('8f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Replaced message');
INSERT INTO messages VALUES ('9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Agreed.');
"""


class EntityStoreTests(unittest.TestCase):
    """Entity rows through the real pass, the resolver and the read."""
    check_kind = "store"


    def setUp(self):
        self.base = located_fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()
        (self.base.artifact / "spec.md").write_text(SPEC, encoding="utf-8")
        self.base.commit()

    def ingest(self):
        output, diagnostic = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(self.base.config)}), \
                patch("mycel._build_identity.current_build", return_value=1), \
                patch("mycel._credentials.Credentials.require_embedding_key"), \
                patch("mycel._embed.VoyageClient"):
            status = run(["ingest", "--repo", "fixture"], stdout=output, stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(), "")
        reply = json.loads(output.getvalue())
        self.assertEqual(status, 0, reply)
        return reply

    def read(self, connection, place=None, **options):
        options.setdefault("no_fresh", True)
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.base.settings, place, **options)

    def entity_rows(self, connection):
        return connection.execute("""SELECT c.id::text, c.kind, f.path, v.id, l.id IS NOT NULL
            FROM public.mycel_chunks c JOIN public.mycel_files f ON f.id = c.file_id
            JOIN public.mycel_chunk_versions v ON v.chunk_id = c.id
            JOIN public.mycel_locations l ON l.chunk_version = v.id AND l.kind='disk'
            WHERE c.kind IN ('req', 'dec') ORDER BY c.id, v.id""").fetchall()

    def test_pass_publishes_entity_rows_keyed_by_uuid_and_keeps_them_through_edits_and_moves(self):
        self.ingest()
        with self.base.connect() as connection:
            rows = self.entity_rows(connection)
            self.assertEqual([(row[0], row[1], row[2], row[4]) for row in rows],
                             [(DEC_A, "dec", "spec.md", True), (REQ_A, "req", "spec.md", True), (REQ_B, "req", "spec.md", True)])
            versions = {row[0]: row[3] for row in rows}
            sections = connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind='document'").fetchone()[0]
            self.assertEqual(sections, 4)  # the guide and the three sections of the specification
        # An edit to a neighbouring row leaves the entity, its version and its location.
        spec = self.base.artifact / "spec.md"
        spec.write_text(SPEC.replace("keep the cellar cool", "keep the cellar cold"), encoding="utf-8")
        self.ingest()
        with self.base.connect() as connection:
            rows = self.entity_rows(connection)
            # The disk row has a new exact version; main still retains its old version.
            self.assertEqual([(row[0], row[4]) for row in rows], [(DEC_A, True), (REQ_A, True), (REQ_B, True)])
            self.assertEqual([row for row in rows if row[0] == REQ_B][0][3], versions[REQ_B])
            self.assertNotEqual([row for row in rows if row[0] == REQ_A][0][3], versions[REQ_A])
            self.assertGreater(connection.execute("SELECT count(*) FROM public.mycel_locations "
                "WHERE chunk_version=%s AND kind='branch'", (versions[REQ_A],)).fetchone()[0], 0)
        # A move of the row to another file changes a location, not the entity.
        moved = SPEC.replace(f"| FIX-1.2 <!-- {REQ_B} --> | log every bottle | New | store |\n", "")
        spec.write_text(moved.replace("keep the cellar cool", "keep the cellar cold"), encoding="utf-8")
        (self.base.artifact / "more.md").write_text(
            f"# More\n\n| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n"
            f"| FIX-1.2 <!-- {REQ_B} --> | log every bottle | New | store |\n", encoding="utf-8")
        self.ingest()
        with self.base.connect() as connection:
            rows = [row for row in self.entity_rows(connection) if row[0] == REQ_B]
            self.assertEqual([(row[2], row[3], row[4]) for row in rows], [("more.md", versions[REQ_B], True)])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind IN ('req','dec')").fetchone()[0], 3)
            reply = self.read(connection, f"[req:{REQ_B}:bG9n]")
            self.assertEqual((reply["path"], reply["name"], reply["origin"], reply["kind"]), ("more.md", "FIX-1.2", "document", "req"))
        # A row that leaves every location keeps its entity row.
        (self.base.artifact / "more.md").unlink()
        self.base.commit()  # advance the only local branch past the removed row too
        self.ingest()
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT kind FROM public.mycel_chunks WHERE id::text=%s", (REQ_B,)).fetchone(), ("req",))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunk_versions WHERE chunk_id::text=%s", (REQ_B,)).fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind IN ('req','dec')").fetchone()[0], 3)

    def test_read_by_entity_uri_address_and_human_id_with_the_kind_tag_as_a_check(self):
        self.ingest()
        with self.base.connect() as connection:
            by_uri = self.read(connection, f"[req:{REQ_A}:a2VlcCB0aGUgY2VsbGFyIGNvb2w]")
            with_code = self.read(connection, f"[fixture:req:{REQ_A}:]")
            by_address = self.read(connection, "fixture:@artifact/spec.md#FIX-1.1")
            by_human_id = self.read(connection, "fixture:spec.md#FIX-1.1")
            by_identifier = self.read(connection, identifier=REQ_A)
            for reply in (with_code, by_address, by_human_id, by_identifier):
                self.assertEqual((reply["id"], reply["text"], reply["entity"]), (by_uri["id"], by_uri["text"], by_uri["entity"]))
            self.assertEqual(by_uri["id"], REQ_A)
            self.assertEqual(by_uri["text"], f"| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |\n")
            self.assertEqual(by_uri["entity"], {"kind": "req", "uuid": REQ_A, "id": "FIX-1.1", "title": "keep the cellar cool",
                "status": "accepted", "verifiedBy": "unit", "fromV1": "Kept",
                "uri": f"[fixture:req:{REQ_A}:a2VlcCB0aGUgY2VsbGFyIGNvb2w=]"})
            self.assertEqual((by_uri["origin"], by_uri["kind"], by_uri["lines"]), ("document", "req", {"start": 12, "end": 12}))
            for place, message in ((f"[dec:{REQ_A}:]", "kind tag"), (f"[cht:{CHAT}:]", "no chunk"),
                                   (f"[req:{CHAT}:]", "No current indexed")):
                with self.assertRaises(MycelError) as error:
                    self.read(connection, place)
                self.assertEqual(error.exception.code.value, "invalid_input")
                self.assertIn(message, error.exception.message)

    def test_a_decision_shows_its_chats_from_a_stand_in_database_and_an_edit_marks_dependants_stale(self):
        (self.base.artifact / "note.md").write_text(NOTE, encoding="utf-8")
        self.ingest()
        with self.base.connect() as connection:
            unavailable = self.read(connection, f"[dec:{DEC_A}:]")
            self.assertEqual(unavailable["entity"]["discussion"], [{"uri": f"[cht:{CHAT}:Q2VsbGFy]", "available": False,
                "reason": "The settings name no discussions.address."}])
        backend = self.store_fixture.backend
        database = "mycel_check_" + uuid4().hex
        backend.create_database(database)
        self.addCleanup(backend.drop_database, database)
        with backend.connection(database) as arbol:
            for statement in LAYOUT.strip().split(";\n"):
                statement = statement.strip()
                if statement:
                    arbol.execute(statement, (CHAT,) * statement.count("%s"))
            arbol.commit() if hasattr(arbol, "commit") else None
        self.base.config.write_text(self.base.config.read_text() + "\n[discussions]\naddress=" +
                                    json.dumps(backend.address(database)) + "\n")
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        from mycel._credentials import Credentials
        original = Credentials._keychain

        def stand_in_keychain(self, purpose, **options):
            # The stand-in database lives on the check server, so its password
            # is the store's; the real `discussions-password` item is never read.
            return original(self, "store" if purpose == "discussions" else purpose, **options)

        with self.base.connect() as connection:
            with patch("mycel._credentials.Credentials._keychain", stand_in_keychain):
                shown = self.read(connection, f"[dec:{DEC_A}:]")
            self.assertEqual(shown["entity"]["discussion"], [{"uri": f"[cht:{CHAT}:Q2VsbGFy]", "available": True,
                "title": "Cellar", "messages": [{"role": "user", "text": "Which cellar?"},
                {"role": "assistant", "text": "The old one."}, {"role": "user", "text": "Agreed."}]}])
            self.assertEqual(shown["entity"]["status"], "decided")
            note = self.read(connection, "fixture:@artifact/note.md#Why the old cellar")
            self.assertFalse(note["stale"], note)
        # The chat changes: nothing becomes stale.
        with backend.connection(database) as arbol:
            arbol.execute("UPDATE messages SET text='Changed' WHERE role='assistant'")
            arbol.commit() if hasattr(arbol, "commit") else None
        self.ingest()
        with self.base.connect() as connection:
            self.assertFalse(self.read(connection, "fixture:@artifact/note.md#Why the old cellar")["stale"])
            self.assertFalse(self.read(connection, f"[dec:{DEC_A}:]")["stale"])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies").fetchone()[0], 1)
        # The decision row is edited: what rests on it is stale.
        spec = self.base.artifact / "spec.md"
        spec.write_text(SPEC.replace("Decided 19 October 2026 by the owner: the old one",
                                     "Decided 19 October 2026 by the owner: the old one, cleaned"), encoding="utf-8")
        self.ingest()
        with self.base.connect() as connection:
            note = self.read(connection, "fixture:@artifact/note.md#Why the old cellar")
            self.assertTrue(note["stale"], note)
            self.assertIn("source_changed", json.dumps(note["staleReasons"]))

    def test_init_brings_a_format_2_store_forward_in_one_step_and_info_reports_the_format(self):
        with self.base.connect() as connection:
            before = store.require_store(connection)
            self.assertEqual(before.format, 4)
            # Formats 2 and 3 share one structure; format 4 adds step progress.
            connection.execute("ALTER TABLE public.mycel_repository_state DROP COLUMN pass_progress")
            connection.execute("UPDATE public.mycel_store SET format=2")
            connection.commit() if hasattr(connection, "commit") else None
            self.assertEqual(store.inspect_store(connection).state, "older")
            result = store.initialize_store(connection, dimensions=before.dimensions)
            self.assertTrue(result.changed)
            self.assertEqual((result.before.format, result.after.format), (2, 4))
            self.assertEqual(result.after.index_generation, before.index_generation)
            self.assertEqual(store.require_store(connection).format, 4)
        output, diagnostic = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(self.base.config)}):
            status = run(["info"], stdout=output, stderr=diagnostic)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["store"]["format"], 4)
