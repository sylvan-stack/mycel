"""Offline acceptance of pinned counts and complete original-text coverage."""

from dataclasses import FrozenInstanceError, replace
import hashlib
from importlib import resources
import json
from pathlib import Path
import random
import socket
import tempfile
import unittest
from unittest.mock import patch

from mycel._coverage import proves
from mycel._embedding_plan import (
    PlanningError, code_place_line, document_place_line, load_tokenizer,
    plan_batches, plan_chunk, plan_query, validate_plan,
)
from mycel._errors import MycelError


OWNED = ("MYC-3.2", "MYC-3.3", "MYC-3.16", "MYC-3.18", "MYC-3.19", "MYC-3.20")


class EmbeddingPlanTests(unittest.TestCase):
    @proves("MYC-3.2", "MYC-3.16")
    def test_document_preamble_and_empty_heading_can_be_planned_without_invented_context(self):
        for heading in ((), "", ("",), ("", "Child")):
            place = document_place_line("notes.md", heading)
            plan = plan_chunk("repo", "preamble", "v1", "  preamble text\n", kind="document",
                              place_line=place, tokenizer=self.tokenizer)
            self.assert_complete(plan, self.tokenizer)
        self.assertEqual(document_place_line("notes.md", ()), "notes.md › ")

    @proves("MYC-3.19", "MYC-3.18")
    def test_retained_library_counting_context_and_recorded_counts_must_be_verifiable(self):
        plan = self.chunk("complete text\n")
        for mutation in ({"tokenizers_library_sha256": "0" * 64}, {"tokenizers_version": "0.0.0"},
                         {"document_prompt": "changed prompt"}, {"query_prompt": "changed query prompt"}):
            with self.subTest(mutation=mutation), self.assertRaises(PlanningError):
                plan_batches([replace(plan, provenance=replace(plan.provenance, **mutation))], tokenizer=self.tokenizer)
        for mutation in ({"submitted_tokens": 0}, {"planning_tokens": True}, {"start_byte": False}):
            with self.subTest(mutation=mutation), self.assertRaises(PlanningError):
                validate_plan(replace(plan, parts=(replace(plan.parts[0], **mutation),)), self.tokenizer)

    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def small_tokenizer(self, *, input_cap=20, batch_cap=30, batch_inputs=3):
        return replace(self.tokenizer, catalog=replace(self.tokenizer.catalog,
                       input_token_cap=input_cap, batch_token_cap=batch_cap, batch_input_cap=batch_inputs))

    def chunk(self, text, *, kind="code", tokenizer=None, repository="repo", chunk="chunk", version="v1",
              place="p — f (function)"):
        return plan_chunk(repository, chunk, version, text, kind=kind, place_line=place,
                          tokenizer=tokenizer or self.tokenizer)

    def assert_complete(self, plan, tokenizer):
        self.assertEqual("".join(part.text for part in plan.parts), plan.text)
        raw = plan.text.encode("utf-8")
        self.assertEqual(plan.text_sha256, hashlib.sha256(raw).hexdigest())
        offset = 0
        for order, part in enumerate(plan.parts):
            self.assertEqual((part.order, part.start_byte), (order, offset))
            body = raw[part.start_byte:part.end_byte].decode("utf-8")
            self.assertEqual(body, part.text)
            self.assertEqual(part.input_text, plan.place_line + "\n" + body)
            self.assertEqual((part.submitted_tokens, part.planning_tokens),
                             tokenizer.counts(part.input_text, "document"))
            self.assertLessEqual(max(part.submitted_tokens, part.planning_tokens), tokenizer.catalog.input_token_cap)
            offset = part.end_byte
        self.assertEqual(offset, len(raw))
        validate_plan(plan, tokenizer)

    @proves("MYC-3.19")
    def test_packaged_asset_matches_official_revision_digest_and_known_counts(self):
        catalog = self.tokenizer.catalog
        self.assertEqual(catalog.tokenizer_repository, "voyageai/voyage-code-4")
        self.assertEqual(catalog.tokenizer_revision, "ac780b405e54ff8b3aff681270e0e03840fed2f3")
        raw = resources.files("mycel").joinpath("data", catalog.tokenizer_file).read_bytes()
        self.assertEqual(len(raw), 7031645)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539")
        self.assertEqual(catalog.tokenizers_version, "0.23.2")
        self.assertEqual(self.tokenizer.count("hello world"), 2)
        self.assertEqual(self.tokenizer.count("a 😀 e\u0301 雪\r\n"), 7)
        self.assertEqual(self.tokenizer.count(""), 0)
        self.assertEqual(self.tokenizer.counts("hello world", "query"), (2, 10))
        self.assertRegex(self.tokenizer.library_sha256, r"^[0-9a-f]{64}$")

    @proves("MYC-3.19", "MYC-3.18")
    def test_loader_and_counts_work_with_network_and_hub_downloads_forbidden(self):
        with patch.object(socket, "socket", side_effect=AssertionError("No runtime network")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("No runtime download")), \
                patch("tokenizers.Tokenizer.from_pretrained", side_effect=AssertionError("No Hub download")):
            local = load_tokenizer()
            self.assertEqual(local.count("hello world"), 2)
            plan = self.chunk("body\n", tokenizer=local)
            self.assert_complete(plan, local)
            self.assertEqual(plan_batches([plan], tokenizer=local)[0].inputs[0].input_text,
                             plan.parts[0].input_text)

    @proves("MYC-3.19", "MYC-3.18")
    def test_missing_tampered_asset_and_wrong_library_version_fail_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokenizer.json"
            with self.assertRaisesRegex(PlanningError, "unavailable"):
                load_tokenizer(asset_path=path)
            path.write_text('{"unknown":"content"}')
            with self.assertRaisesRegex(PlanningError, "pinned digest"):
                load_tokenizer(asset_path=path)
        with patch("tokenizers.__version__", "0.0.0"):
            with self.assertRaisesRegex(PlanningError, "exact version"):
                load_tokenizer()
        with self.assertRaises(MycelError) as failure:
            load_tokenizer("unknown-model")
        self.assertEqual(failure.exception.code, "settings")

    @proves("MYC-3.19")
    def test_catalog_is_immutable_validated_and_requires_supported_dimensions(self):
        with self.assertRaises(FrozenInstanceError):
            self.tokenizer.catalog.input_token_cap = 1
        bad = json.loads(resources.files("mycel").joinpath("data/embedding-models.json").read_text())
        bad["models"]["voyage-code-4"]["input_token_cap"] = 99999
        with patch("mycel._embedding_plan._catalog_bytes", return_value=json.dumps(bad).encode()):
            with self.assertRaises(PlanningError):
                load_tokenizer()
        for dimensions in (0, 999, True, "1024"):
            with self.subTest(dimensions=dimensions), self.assertRaises(MycelError) as failure:
                plan_query("query", tokenizer=self.tokenizer, dimensions=dimensions)
            self.assertEqual(failure.exception.code, "settings")
        for dimensions in (256, 512, 1024, 2048):
            self.assertEqual(plan_query("query", tokenizer=self.tokenizer, dimensions=dimensions).dimensions, dimensions)

    @proves("MYC-3.19", "MYC-3.18")
    def test_counts_never_pad_or_truncate_and_planning_adds_only_the_provider_prompt(self):
        local = self.tokenizer
        self.assertIsNone(local._tokenizer.padding)
        self.assertIsNone(local._tokenizer.truncation)
        text = "x " * 34000
        self.assertGreater(local.count(text), 32000)
        submitted, planning = local.counts("exact input", "document")
        self.assertEqual(submitted, local.count("exact input"))
        self.assertEqual(planning, local.count("Represent the document for retrieval: exact input"))
        self.assertGreater(planning, submitted)
        with self.assertRaisesRegex(PlanningError, "cannot be truncated"):
            plan_query(text, tokenizer=local)

    @proves("MYC-3.2", "MYC-3.16")
    def test_code_and_document_place_lines_repeat_without_changing_body(self):
        code = code_place_line("src/雪.py", "charge", "function")
        document = document_place_line("docs/notes.md", ["Notes", "A › B"])
        self.assertEqual(code, "src/雪.py — charge (function)")
        self.assertEqual(document, "docs/notes.md › Notes › A › B")
        body = "  # untouched\r\n雪 e\u0301 😀\n\tfinal  "
        for kind, place in (("code", code), ("document", document)):
            plan = self.chunk(body, kind=kind, place=place)
            self.assert_complete(plan, self.tokenizer)
            self.assertEqual(plan.parts[0].input_text, place + "\n" + body)
            self.assertNotIn(self.tokenizer.catalog.document_prompt, plan.parts[0].input_text)
        for bad in ("bad\nline", "bad\rline", "", "bad\0line"):
            with self.assertRaises(PlanningError):
                code_place_line("path", bad, "function")

    @proves("MYC-3.3", "MYC-3.18")
    def test_query_is_exact_complete_and_refused_without_splitting_or_truncation(self):
        text = "exact Query? \t\n"
        plan = plan_query(text, tokenizer=self.tokenizer)
        self.assertEqual(plan.text, text)
        self.assertEqual((plan.submitted_tokens, plan.planning_tokens), (4, 12))
        self.assertEqual(plan.input_type, "query")
        self.assertFalse(plan.truncation)
        too_small = self.small_tokenizer(input_cap=11)
        with self.assertRaisesRegex(PlanningError, "complete query"):
            plan_query(text, tokenizer=too_small)
        self.assertEqual(text, "exact Query? \t\n")

    @proves("MYC-3.16", "MYC-3.20", "MYC-3.2")
    def test_golden_code_ranges_prefer_line_endings_and_keep_final_whitespace(self):
        local = self.small_tokenizer()
        body = "first = 1\nsecond = 2\r\nthird = 3\rfourth = 4\n  tail"
        plan = self.chunk(body, tokenizer=local)
        self.assertEqual([(p.start_byte, p.end_byte) for p in plan.parts], [(0, 10), (10, 22), (22, 32), (32, 49)])
        self.assertEqual([p.planning_tokens for p in plan.parts], [17, 17, 17, 20])
        self.assert_complete(plan, local)

    @proves("MYC-3.16", "MYC-3.20")
    def test_golden_document_ranges_use_original_text_after_normalization(self):
        local = self.small_tokenizer()
        body = "# Head\n\nOne paragraph with snow 雪.\n \t\r\nSecond paragraph e\u0301 😀 tail."
        plan = self.chunk(body, kind="document", tokenizer=local)
        self.assertEqual([(p.start_byte, p.end_byte) for p in plan.parts], [(0, 8), (8, 37), (37, 72)])
        self.assertEqual(plan.parts[0].text, "# Head\n\n")
        self.assert_complete(plan, local)
        self.assertIn("e\u0301", "".join(p.text for p in plan.parts))

    @proves("MYC-3.16", "MYC-3.20", "MYC-3.18")
    def test_golden_multibyte_ranges_remeasure_tokens_spanning_unicode_characters(self):
        local = self.small_tokenizer()
        body = "😀雪é" * 20
        plan = self.chunk(body, tokenizer=local)
        self.assertEqual([(p.start_byte, p.end_byte) for p in plan.parts],
                         [(0, 25), (25, 49), (49, 72), (72, 97), (97, 121), (121, 144), (144, 169), (169, 180)])
        self.assert_complete(plan, local)
        self.assertEqual(len({(p.start_byte, p.end_byte) for p in plan.parts}), len(plan.parts))

    @proves("MYC-3.16", "MYC-3.18", "MYC-3.20")
    def test_long_body_uses_real_catalog_caps_and_keeps_the_entire_tail(self):
        body = "x " * 34000 + "FINAL 雪😀\t "
        self.assertGreater(self.tokenizer.count(body), self.tokenizer.catalog.input_token_cap)
        plan = self.chunk(body)
        self.assertGreater(len(plan.parts), 1)
        self.assert_complete(plan, self.tokenizer)
        self.assertTrue(plan.parts[-1].text.endswith("FINAL 雪😀\t "))
        batches = plan_batches([plan], tokenizer=self.tokenizer)
        self.assertGreater(len(batches), 1)
        for batch in batches:
            self.assertLessEqual(batch.planning_tokens, 31744)
            self.assertLessEqual(len(batch.inputs), 64)

    @proves("MYC-3.16", "MYC-3.20")
    def test_varied_original_unicode_always_reconstructs_deterministically(self):
        randomizer = random.Random(115)
        alphabet = ["é", "e\u0301", "雪", "😀", "👩\u200d💻", "\t", " ", "\r\n", "\n", "\r", "alpha"]
        body = "".join(randomizer.choice(alphabet) for _ in range(160)) + "\u0301final\t "
        for kind in ("code", "document"):
            for cap in (20, 23, 50):
                with self.subTest(kind=kind, cap=cap):
                    local = self.small_tokenizer(input_cap=cap, batch_cap=100)
                    plan = self.chunk(body, kind=kind, tokenizer=local)
                    self.assert_complete(plan, local)
                    repeated = self.chunk(body, kind=kind, tokenizer=local)
                    self.assertEqual(plan, repeated)
                    self.assertEqual(plan.plan_sha256, repeated.plan_sha256)

    @proves("MYC-3.2", "MYC-3.16", "MYC-3.18")
    def test_empty_body_has_one_place_only_part_and_impossible_context_fails(self):
        plan = self.chunk("")
        self.assertEqual(len(plan.parts), 1)
        self.assertEqual((plan.parts[0].start_byte, plan.parts[0].end_byte), (0, 0))
        self.assertEqual(plan.parts[0].input_text, "p — f (function)\n")
        self.assert_complete(plan, self.tokenizer)
        local = self.small_tokenizer(input_cap=2)
        for body in ("", "😀", "full source remains"):
            with self.subTest(body=body), self.assertRaisesRegex(PlanningError, "cannot fit"):
                self.chunk(body, tokenizer=local)

    @proves("MYC-3.19", "MYC-3.20")
    def test_saved_metadata_records_complete_counting_and_version_provenance(self):
        plan = self.chunk("exact source\n")
        data = plan.to_dict()
        provenance = data["provenance"]
        self.assertEqual(data["chunk_version"], "v1")
        self.assertEqual(data["text_sha256"], hashlib.sha256(b"exact source\n").hexdigest())
        self.assertEqual(provenance["planner_version"], 1)
        self.assertEqual(provenance["input_token_cap"], 31744)
        self.assertEqual(provenance["batch_token_cap"], 31744)
        self.assertEqual(provenance["batch_input_cap"], 64)
        self.assertEqual(provenance["provider_input_cap"], 1000)
        self.assertEqual(provenance["provider_context_tokens"], 32000)
        self.assertEqual(provenance["repository_in_flight_cap"], 1)
        self.assertEqual(provenance["tokenizers_library_sha256"], self.tokenizer.library_sha256)
        self.assertEqual(provenance["tokenizers_version"], "0.23.2")
        self.assertFalse(provenance["padding"])
        self.assertFalse(provenance["truncation"])
        self.assertEqual(len(provenance["catalog_sha256"]), 64)
        self.assertEqual(set(data["parts"][0]), {"order", "start_byte", "end_byte", "submitted_tokens", "planning_tokens"})
        self.assertEqual(json.loads(json.dumps(data)), data)

    @proves("MYC-3.18", "MYC-3.20")
    def test_batches_sort_identity_and_end_before_either_cap_or_repository_changes(self):
        local = self.small_tokenizer(input_cap=20, batch_cap=100, batch_inputs=3)
        plans = [self.chunk("x", tokenizer=local, chunk="b", version="v2"),
                 self.chunk("x", tokenizer=local, repository="other", chunk="z"),
                 self.chunk("x", tokenizer=local, chunk="a", version="v2"),
                 self.chunk("x", tokenizer=local, chunk="a", version="v1"),
                 self.chunk("x", tokenizer=local, chunk="c")]
        batches = plan_batches(reversed(plans), tokenizer=local)
        self.assertEqual([[i.chunk_id + "/" + i.chunk_version for i in b.inputs] for b in batches],
                         [["z/v1"], ["a/v1", "a/v2", "b/v2"], ["c/v1"]])
        tight = replace(local, catalog=replace(local.catalog, batch_token_cap=27))
        batches = plan_batches(plans, tokenizer=tight)
        for batch in batches:
            self.assertLessEqual(batch.planning_tokens, 27)
            self.assertLessEqual(len(batch.inputs), 3)
            self.assertEqual(batch.planning_tokens, sum(i.planning_tokens for i in batch.inputs))
            self.assertEqual(batch.submitted_tokens, sum(i.submitted_tokens for i in batch.inputs))
            self.assertEqual(batch.input_type, "document")
            self.assertEqual(batch.output_dtype, "float")
            self.assertFalse(batch.truncation)
        self.assertEqual(plan_batches(plans, tokenizer=tight), plan_batches(reversed(plans), tokenizer=tight))

    @proves("MYC-3.18", "MYC-3.20", "MYC-3.19")
    def test_retained_plan_verification_refuses_lost_text_changed_context_unknown_pins(self):
        local = self.small_tokenizer()
        plan = self.chunk("😀雪é" * 20, tokenizer=local)
        corruptions = [replace(plan, parts=plan.parts[:-1]),
                       replace(plan, place_line="changed location"),
                       replace(plan, text_sha256="0" * 64),
                       replace(plan, parts=(replace(plan.parts[0], end_byte=1),) + plan.parts[1:]),
                       replace(plan, provenance=replace(plan.provenance, tokenizer_revision="0" * 40)),
                       replace(plan, provenance=replace(plan.provenance, truncation=True))]
        for corrupted in corruptions:
            with self.subTest(corrupted=corrupted.plan_sha256), self.assertRaises(PlanningError):
                plan_batches([corrupted], tokenizer=local)
        smaller = self.small_tokenizer(input_cap=19)
        with self.assertRaisesRegex(PlanningError, "verified limit"):
            validate_plan(plan, smaller)
        with self.assertRaisesRegex(PlanningError, "duplicate"):
            plan_batches([plan, plan], tokenizer=local)

    @proves("MYC-3.18", "MYC-3.20")
    def test_batch_counts_remeasure_exact_saved_inputs_and_empty_batch_is_empty(self):
        plan = self.chunk("source")
        forged_counts = replace(plan, parts=(replace(plan.parts[0], submitted_tokens=0, planning_tokens=0),))
        with self.assertRaises(PlanningError):
            plan_batches([forged_counts], tokenizer=self.tokenizer)
        batches = plan_batches([plan], tokenizer=self.tokenizer)
        self.assertEqual((batches[0].submitted_tokens, batches[0].planning_tokens),
                         self.tokenizer.counts(plan.parts[0].input_text, "document"))
        self.assertEqual(plan_batches([], tokenizer=self.tokenizer), ())

    @proves("MYC-3.16", "MYC-3.18")
    def test_invalid_unicode_and_mismatched_model_fail_without_a_provider(self):
        for text in ("broken\ud800", b"bytes"):
            with self.subTest(text=repr(text)), self.assertRaises(PlanningError):
                self.chunk(text)
        with self.assertRaises(MycelError) as failure:
            plan_query("x", model="other-model", tokenizer=self.tokenizer)
        self.assertEqual(failure.exception.code, "settings")


if __name__ == "__main__":
    unittest.main()
