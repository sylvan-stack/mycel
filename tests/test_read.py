"""Exact-read unit proofs over independently retained source selections."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._freshness import (ChunkRequirement, DependencyFault, FreshnessResult,
                             FreshnessScope, RepositoryStatus)
from mycel._read import read_chunk, select_chunk
from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress


def chunk(name, text, *, kind="function", title=None, family=None, span=None, number=1):
    raw = text.encode("utf-8")
    return ResolvedChunk(str(uuid4()), number, name, kind, raw, sha256(raw).hexdigest(),
                         span, title, family)


def file(path, text, members, *, root="code", repository="fixture", aliases=()):
    raw = text.encode("utf-8")
    primary = SourceAddress(repository, root, path)
    return ResolvedFile(str(uuid4()), repository, primary, aliases or (primary,), raw,
                        sha256(raw).hexdigest(), tuple(members))


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mycel_exact_read_")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.code, self.artifact = self.home / "code", self.home / "artifact"
        self.code.mkdir()
        self.artifact.mkdir()
        config = self.home / "settings.toml"
        config.write_text('[store]\naddress="postgresql://mycel@localhost/mycel"\n'
            '[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(self.code))
            + '\nartifact_root=' + json.dumps(str(self.artifact))
            + '\n[repos.disabled]\nenabled=false\n', encoding="utf-8")
        self.settings = load_settings(path=config, home=self.home)
        self.settings.require_valid()

    def resolver(self, *files, index=()):
        return SourceResolver(self.settings, tuple(files), index=tuple(index))

    @proves("MYC-11.2")
    def test_qualified_and_legacy_places_and_result_identifier_select_one_exact_chunk(self):
        method = chunk("Policy.allow", "    def allow(self):\n        return True\n",
                       kind="method", family="Policy")
        retained = file("src/rètry.py", method.source.decode(), (method,))
        generated = chunk("1/7", "A complete generated summary.\n", kind="summary", number=2)
        generated_place = SourceAddress("fixture", "index", "summaries", "1/7")
        resolver = self.resolver(retained, index=((generated_place, generated),))
        for place in ("fixture:@code/src/r%C3%A8try.py#Policy.allow",
                      "fixture:@code/src/rètry.py#Policy.allow",
                      "fixture:src/rètry.py#Policy.allow"):
            with self.subTest(place=place):
                selected = select_chunk(resolver, place)
                self.assertEqual(selected.chunk, method)
                self.assertEqual(selected.place.address, "fixture:@code/src/r%C3%A8try.py#Policy.allow")
        by_id = select_chunk(resolver, identifier=method.identifier)
        self.assertEqual((by_id.chunk, by_id.file), (method, retained))
        self.assertEqual(read_chunk(resolver, identifier=generated.identifier)["address"],
                         "fixture:@index/summaries#1%2F7")
        self.assertEqual(select_chunk(resolver, "fixture:@index/summaries#1%2F7").chunk,
                         generated)
        for options in ({}, {"place": retained.primary.address, "identifier": method.identifier},
                        {"identifier": ""}, {"identifier": "missing"}):
            with self.subTest(options=options), self.assertRaises(MycelError) as error:
                select_chunk(resolver, **options)
            self.assertEqual(error.exception.code, "invalid_input")

    @proves("MYC-11.7")
    def test_reply_keeps_checkout_markdown_document_origin_exact_lines_and_canonical_root(self):
        prefix = "# Intro\nIntro text.\n"
        text = "## Limits > Backoff\n雪 and a complete body.\n"
        member = chunk("Intro > Limits > Backoff", text, kind="document", title="Limits > Backoff",
                       span=(len(prefix.encode()), len((prefix + text).encode())))
        retained = file("README.md", prefix + text, (member,))
        (self.code / "README.md").write_text(prefix + text, encoding="utf-8")
        reply = read_chunk(self.resolver(retained), "fixture:@code/README.md#Limits > Backoff")
        self.assertEqual({key: reply[key] for key in ("schema", "id", "repository", "origin", "root",
            "path", "address", "name", "kind", "lines", "text", "cut")},
            {"schema": 1, "id": member.identifier, "repository": "fixture", "origin": "document",
             "root": "code", "path": "README.md",
             "address": "fixture:@code/README.md#Intro%20%3E%20Limits%20%3E%20Backoff",
             "name": member.name, "kind": "document", "lines": {"start": 3, "end": 4},
             "text": text, "cut": False})
        self.assertEqual(reply["file"], str(self.code / "README.md"))
        self.assertNotIn("context", reply)
        self.assertFalse(reply["stale"])
        self.assertFalse(reply["dependencyCheck"]["complete"])
        self.assertFalse(reply["freshness"]["checked"])
        self.assertFalse(reply["freshness"]["finished"])

    @proves("MYC-11.7")
    def test_original_source_and_intermediate_paths_faults_and_heartwood_survive_reply(self):
        text = "---\nstatus: heartwood\nimplemented: true\n---\n# Stable\nBody.\n"
        member = chunk("Stable", text, kind="document", title="Stable")
        retained = file("stable.md", text, (member,), root="artifact")
        (self.artifact / "stable.md").write_text(text, encoding="utf-8")
        reason = {"kind": "upstream_stale", "source": {
            "repository": "glossary", "address": "glossary:@artifact/terms.md#Term"},
            "via": [{"repository": "contract", "address": "contract:@artifact/contract.md#Contract"}]}
        fault = {"ref": "missing:@artifact/guide.md#Guide", "reason": "unregistered_repository"}
        reply = read_chunk(self.resolver(retained), identifier=member.identifier,
                           metadata={"origin": "document", "staleReasons": [reason],
                                     "heartwood": True, "faults": [fault]})
        self.assertTrue(reply["stale"])
        self.assertTrue(reply["heartwood"])
        self.assertEqual(reply["staleReasons"], [reason])
        self.assertEqual(reply["dependencyCheck"]["faults"], [fault])
        self.assertFalse(reply["dependencyCheck"]["complete"])
        inferred = read_chunk(self.resolver(retained), identifier=member.identifier)
        self.assertTrue(inferred["heartwood"])

    @proves("MYC-11.7")
    def test_pending_source_or_ref_fault_cannot_make_an_unmarked_chunk_verified_current(self):
        member = chunk("step", "def step(): pass\n")
        retained = file("step.py", member.source.decode(), (member,))
        requirement = ChunkRequirement("fixture", (member.identifier, member.version),
                                       ("fixture", "upstream"))
        scope = FreshnessScope(("fixture",))
        complete = FreshnessResult(scope, (RepositoryStatus("fixture", "done"),
            RepositoryStatus("upstream", "done")), (), True, True, (), (requirement,))
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, freshness=complete)
        self.assertFalse(reply["stale"])
        self.assertTrue(reply["dependencyCheck"]["complete"])
        pending = replace(complete, repositories=(RepositoryStatus("fixture", "done"),
            RepositoryStatus("upstream", "pending", "Still required.")), finished=False,
            incomplete_repositories=("upstream",))
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, freshness=pending)
        self.assertFalse(reply["stale"])
        self.assertFalse(reply["dependencyCheck"]["complete"])
        self.assertFalse(reply["freshness"]["finished"])
        fault = DependencyFault("fixture", "upstream:@artifact/missing.md", "missing_file",
                                (member.identifier, member.version))
        faulty = replace(complete, faults=(fault,),
                         chunk_requirements=(replace(requirement, faults=(fault,)),))
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, freshness=faulty)
        self.assertFalse(reply["dependencyCheck"]["complete"])
        self.assertTrue(reply["dependencyCheck"]["faults"])

    @proves("MYC-11.8")
    def test_context_comes_from_the_file_while_the_chunk_text_stays_exactly_indexed(self):
        before = [f"# before {number}\n" for number in range(60)]
        body = "def selected():\n    return 'indexed version'\n"
        after = [f"# after {number}\n" for number in range(60)]
        original = "".join(before) + body + "".join(after)
        start = len("".join(before).encode())
        member = chunk("selected", body, span=(start, start + len(body.encode())))
        retained = file("context.py", original, (member,))
        current_before = [line.replace("before", "disk-before") for line in before]
        current_after = [line.replace("after", "disk-after") for line in after]
        (self.code / "context.py").write_text("".join(current_before) + body + "".join(current_after))
        resolver = self.resolver(retained)
        self.assertNotIn("context", read_chunk(resolver, identifier=member.identifier))
        self.assertEqual(read_chunk(resolver, identifier=member.identifier, context=0)["context"],
                         {"before": "", "after": ""})
        reply = read_chunk(resolver, identifier=member.identifier, context=2)
        self.assertEqual(reply["text"], body)
        self.assertEqual(reply["context"], {"before": "".join(current_before[-2:]),
                                           "after": "".join(current_after[:2])})
        reply = read_chunk(resolver, identifier=member.identifier, context=50)
        self.assertEqual(reply["context"], {"before": "".join(current_before[-50:]),
                                           "after": "".join(current_after[:50])})
        for value in (-1, 51, True, 1.5, "2"):
            with self.subTest(value=value), self.assertRaises(MycelError) as error:
                read_chunk(resolver, identifier=member.identifier, context=value)
            self.assertEqual(error.exception.code, "invalid_input")

    @proves("MYC-11.8")
    def test_context_stops_at_file_boundaries(self):
        body = "def first():\n    return 1\n"
        after = "# only one following line\n"
        member = chunk("first", body, span=(0, len(body.encode())))
        retained = file("short.py", body + after, (member,))
        (self.code / "short.py").write_text(body + after)
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, context=50)
        self.assertEqual(reply["context"], {"before": "", "after": after})

    @proves("MYC-11.7", "MYC-11.8")
    def test_context_does_not_read_a_symlink_that_escapes_the_selected_configured_root(self):
        body = "def selected():\n    return 'indexed'\n"
        original = "# retained prefix\n" + body + "# retained suffix\n"
        start = len("# retained prefix\n".encode())
        member = chunk("selected", body, span=(start, start + len(body.encode())))
        retained = file("escape.py", original, (member,))
        outside = self.home / "outside.py"
        outside.write_text("# outside secret prefix\n" + body + "# outside secret suffix\n")
        (self.code / "escape.py").symlink_to(outside)
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, context=50)
        self.assertEqual(reply["text"], body)
        self.assertEqual(reply["context"], {"before": "", "after": ""})
        self.assertNotIn("file", reply)
        self.assertTrue(reply["unreadable"])
        self.assertNotIn("outside secret", json.dumps(reply))

    @proves("MYC-11.9")
    def test_five_mib_cut_is_measured_in_utf8_bytes_without_a_partial_character(self):
        limit = 5 * 1024 * 1024
        for text, expected, cut in (("a" * limit, "a" * limit, False),
            ("a" * (limit - 1) + "雪tail", "a" * (limit - 1), True),
            ("雪" * (limit // 3 + 1), "雪" * (limit // 3), True)):
            with self.subTest(byte_count=len(text.encode())):
                member = chunk("1/1", text, kind="summary")
                place = SourceAddress("fixture", "index", "summaries", member.name)
                reply = read_chunk(self.resolver(index=((place, member),)), identifier=member.identifier)
                self.assertEqual(reply["text"], expected)
                self.assertEqual(reply["cut"], cut)
                self.assertLessEqual(len(reply["text"].encode("utf-8")), limit)

    @proves("MYC-11.2")
    def test_identifier_and_qualified_alias_use_the_actual_primary_binding(self):
        member = chunk("Section", "# Section\nBody.\n", kind="document", title="Section")
        shared = file("guide.md", member.source.decode(), (member,), root="artifact",
            aliases=(SourceAddress("fixture", "artifact", "guide.md"),
                     SourceAddress("fixture", "code", "docs/guide.md")))
        resolver = self.resolver(shared)
        reply = read_chunk(resolver, "fixture:@code/docs/guide.md#Section")
        self.assertEqual(reply["id"], member.identifier)
        self.assertEqual(reply["address"], "fixture:@artifact/guide.md#Section")
        self.assertEqual(read_chunk(resolver, identifier=member.identifier)["root"], "artifact")
