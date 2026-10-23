"""Independent fixtures for accepted ranking constants and ordering rules."""

from dataclasses import replace
import json
import math
from pathlib import Path
import random
import tempfile
import unittest

from mycel._errors import MycelError
from mycel._ranking import (DocumentCitation, RankingGraph, classify_route,
                            rank_repository)
from mycel._retrieval import Candidate, RetrievalChunk
from mycel._retrieval_store import RepositoryCandidates
from mycel._settings import load_settings


def chunk(identifier, *, cosine=None, repository="orchard", path=None,
          name="step", root="code", origin="code", kind="function", **values):
    vectors = () if cosine is None else ((cosine, math.sqrt(max(0.0, 1 - cosine ** 2))),)
    values.setdefault("fully_embedded", cosine is not None)
    values.setdefault("part_vectors", vectors)
    return RetrievalChunk(identifier, 1, repository, root, path or identifier + ".py",
                          name, kind, origin, "", **values)


def document(identifier, cosine=None, **values):
    values.setdefault("root", "artifact")
    values.setdefault("path", identifier + ".md")
    return chunk(identifier, cosine=cosine, origin="documents", kind="section", **values)


def candidates(chunks, *, meaning=(), wording=()):
    return RepositoryCandidates("orchard", tuple(chunks), tuple(meaning), tuple(wording),
                                sum(not item.fully_embedded for item in chunks))


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.settings = self.load()

    def load(self, *, orchard_patterns="", handbook_patterns=""):
        source = f'''[store]
address = "postgresql://mycel@localhost/mycel"
[repos.orchard]
enabled = true
code_root = {json.dumps(str(self.home / "orchard"))}
artifact_root = {json.dumps(str(self.home / "orchard-docs"))}
{orchard_patterns}
[repos.handbook]
enabled = true
artifact_root = {json.dumps(str(self.home / "handbook"))}
{handbook_patterns}
[search]
shared_documents = [{{repo="handbook", paths=["visible"]}}]
'''
        path = self.home / "settings.toml"
        path.write_text(source)
        settings = load_settings(path=path, home=self.home)
        settings.require_valid()
        return settings

    def rank(self, query, inputs, graph=RankingGraph(), vector=(1.0, 0.0), **options):
        return rank_repository(self.settings, query, inputs, graph, vector, **options)

    def by_id(self, reply):
        return {entry.chunk.identifier: entry for entry in reply.results}

    def test_route_shapes_and_plain_word_are_fixed(self):
        for query in ("payments", "renewSession", "auth/session.ts#renew", "a_b",
                      "áccent", "支払", "123", ".", "/", "-", "  payments\n"):
            with self.subTest(query=query):
                self.assertEqual(classify_route(query), "identifier")
        for query in ("how does renewal decide", "two\nwords", "a?", "a:b", "a+b",
                      "a@b", "😀", "café!", "a\tb"):
            with self.subTest(query=query):
                self.assertEqual(classify_route(query), "question")
        for query in ("", " \t\n", None, 10):
            with self.subTest(query=query), self.assertRaises(MycelError) as raised:
                classify_route(query)
            self.assertEqual(raised.exception.code, "invalid_input")

    def test_equal_weight_rrf_one_based_ranks_and_ties(self):
        a, b, c, d = (chunk(name, cosine=0.8) for name in ("a", "b", "c", "d"))
        inputs = candidates((d, c, b, a, a),
            meaning=(Candidate(a, 0.8), Candidate(a, 0.8), Candidate(b, 0.8), Candidate(c, 0.8)),
            wording=(Candidate(b, 100), Candidate(a, 90), Candidate(d, 80)))
        reply = self.rank("payments", inputs)
        self.assertEqual([item.chunk.identifier for item in reply.results], ["a", "b", "c", "d"])
        results = self.by_id(reply)
        for identifier in ("a", "b"):
            self.assertAlmostEqual(results[identifier].score, 1 / 61 + 1 / 62, places=15)
        self.assertEqual((results["a"].meaning_rank, results["a"].wording_rank), (1, 2))
        self.assertEqual((results["b"].meaning_rank, results["b"].wording_rank), (2, 1))
        self.assertAlmostEqual(results["c"].score, 1 / 63, places=15)
        only_a = candidates((a,), meaning=(Candidate(a, 0.8),), wording=(Candidate(a, 90),))
        self.assertAlmostEqual(self.rank("payments", only_a).results[0].score, 2 / 61, places=15)
        self.assertTrue(all(entry.via is None for entry in reply.results))

    def test_score_ties_use_every_canonical_field_and_never_insertion_order(self):
        a = chunk("a", cosine=0.7, path="same.py", root="artifact", name="first")
        b = chunk("b", cosine=0.7, path="same.py", name="first")
        c = chunk("c", cosine=0.7, path="same.py", name="second")
        d = chunk("d", cosine=0.7, path="z.py", name="first")
        expected = ("a", "b", "c", "d")
        for seed in range(5):
            rows = [d, c, b, a]
            random.Random(seed).shuffle(rows)
            # Equal question cosines leave the full canonical tuple to decide.
            inputs = candidates(rows, meaning=tuple(Candidate(row, 0.7) for row in rows))
            self.assertEqual(tuple(item.chunk.identifier for item in
                self.rank("how do payments work", inputs).results), expected)
            # A one-arm identifier has distinct original ranks. Swapped rank
            # pairs give equal RRF scores independent of candidate row order.
            inputs = candidates(rows, meaning=(Candidate(d, .7), Candidate(c, .7),
                Candidate(b, .7), Candidate(a, .7)), wording=(Candidate(a, 4),
                Candidate(b, 3), Candidate(c, 2), Candidate(d, 1)))
            reply = self.rank("payments", inputs)
            self.assertEqual(tuple(item.chunk.identifier for item in reply.results), ("a", "d", "b", "c"))

    def test_question_signed_cosines_and_wording_tail_tier(self):
        positive, zero, negative = (chunk(name, cosine=value)
            for name, value in (("positive", .4), ("zero", 0), ("negative", -.7)))
        test = chunk("test", path="test_rescue.py")
        ordinary = chunk("ordinary")
        inputs = candidates((negative, zero, positive, test, ordinary),
            meaning=(Candidate(positive, .4), Candidate(zero, 0), Candidate(negative, -.7)),
            wording=(Candidate(test, 100), Candidate(ordinary, 94)))
        reply = self.rank("how do payments work", inputs)
        self.assertEqual([entry.chunk.identifier for entry in reply.results],
                         ["positive", "zero", "negative", "ordinary", "test"])
        self.assertEqual([entry.score_tier for entry in reply.results],
                         ["scored"] * 3 + ["wording_tail"] * 2)
        self.assertEqual(reply.results[-1].wording_rank, 1)
        self.assertAlmostEqual(reply.results[-1].score, 93)
        self.assertEqual(reply.results[2].score, -.7)
        self.assertEqual(reply.route, "question")
        self.assertTrue(reply.meaning_used)
        self.assertEqual(reply.without_vector, 2)
        # Negative document cues still deliver code. A wording-only direct
        # occurrence does not add .05, and its large BM25 cannot erase the
        # separate scored tier when a bridge supplies the same identity.
        bridge_only = chunk("negative-bridge", cosine=-.9)
        negative_doc = document("negative-doc", -.5)
        graph = RankingGraph((negative_doc,), (DocumentCitation(negative_doc, (bridge_only,)),))
        bridged = self.rank("how do payments work", candidates((bridge_only, ordinary),
            wording=(Candidate(bridge_only, 100), Candidate(ordinary, 90))), graph)
        self.assertEqual([entry.chunk.identifier for entry in bridged.results], ["negative-bridge", "ordinary"])
        self.assertAlmostEqual(bridged.results[0].score, -.46, places=14)
        self.assertEqual(bridged.results[0].score_tier, "scored")
        self.assertEqual(bridged.results[0].via, negative_doc)

    def test_once_only_bridge_agreement_before_weights(self):
        direct = chunk("direct", cosine=.8, path="test_direct.py")
        bridged = chunk("bridged", cosine=.7)
        word_bridged = chunk("word-bridged", cosine=.6)
        best, next_best = document("best", .9), document("next", .89)
        graph = RankingGraph((next_best, best), (
            DocumentCitation(best, (direct, direct, bridged, word_bridged)),
            DocumentCitation(best, (direct,)),
            DocumentCitation(next_best, (direct, bridged, word_bridged))))
        inputs = candidates((direct, bridged, word_bridged),
            meaning=(Candidate(direct, .8),), wording=(Candidate(word_bridged, 100),))
        results = self.by_id(self.rank("how do payments work", inputs, graph))
        self.assertEqual(set(results), {"direct", "bridged", "word-bridged"})
        self.assertAlmostEqual(results["direct"].score, .81654, places=14)
        self.assertEqual(results["direct"].raw_direct_cosine, .8)
        self.assertAlmostEqual(results["direct"].raw_bridge_cosine, .9)
        for identifier in results:
            self.assertEqual(results[identifier].via, best)
            self.assertEqual(results[identifier].documented_in, (best, next_best))
        for identifier in ("bridged", "word-bridged"):
            self.assertAlmostEqual(results[identifier].score, .828, places=14)
            self.assertIsNone(results[identifier].raw_direct_cosine)
            self.assertEqual(results[identifier].score_tier, "scored")
        # Stronger direct matches still report the delivering section and get
        # exactly one .05; multipart/repeated-citation order cannot alter it.
        stronger = replace(direct, part_vectors=((.95, math.sqrt(1 - .95 ** 2)),) * 30)
        graph = RankingGraph((best,), (DocumentCitation(best, (stronger,) * 30),))
        reply = self.rank("how do payments work", candidates((stronger,),
            meaning=(Candidate(stronger, .95),)), graph)
        self.assertAlmostEqual(reply.results[0].score, .93, places=14)
        self.assertEqual(reply.results[0].via, best)

    def test_bridge_full_pools_caps_and_citer_order_are_independent_of_arms(self):
        direct = tuple(chunk(f"direct-{i:02}", cosine=.99) for i in range(25))
        destinations = tuple(chunk(f"cited-{i}", cosine=.7 - i * .1) for i in range(4))
        incomplete = chunk("incomplete", cosine=1, fully_embedded=False)
        other = chunk("foreign", repository="handbook", cosine=1)
        docs = tuple(document(f"doc-{i}", .9 - i * .01) for i in range(9))
        special = chunk("ninth-only", cosine=.8)
        shared = document("shared", 1, repository="handbook", path="visible/shared.md")
        private = document("private", 1, repository="handbook", path="private.md")
        graph = RankingGraph((*reversed(docs), shared, private), tuple(
            DocumentCitation(doc, (*destinations, destinations[0], incomplete, other))
            for doc in docs[:8]) + (DocumentCitation(docs[8], (special,)),
            DocumentCitation(shared, (special,)), DocumentCitation(private, (destinations[0],))))
        rows = (*direct, *destinations, incomplete, special)
        inputs = candidates(rows, meaning=tuple(Candidate(row, .99) for row in direct[:20]))
        results = self.by_id(self.rank("how do payments work", inputs, graph, k=100))
        self.assertEqual(set(results), {row.identifier for row in direct[:20]} |
                         {row.identifier for row in destinations[:3]})
        first = results[destinations[0].identifier]
        self.assertEqual(first.via, docs[0])
        self.assertEqual(first.documented_in, (docs[0], docs[1]))
        # Reverse evidence can include visible shared documents without making
        # them cues; own-document evidence remains usable for code-only.
        graph = RankingGraph((*docs, shared, private), (*graph.citations,
            DocumentCitation(shared, (destinations[0],))))
        mixed = self.by_id(self.rank("how do payments work", inputs, graph, k=100))
        self.assertEqual(mixed[destinations[0].identifier].documented_in, (shared, docs[0]))
        code_only = self.by_id(self.rank("how do payments work", inputs, graph, k=100, only="code"))
        self.assertEqual(code_only[destinations[0].identifier].documented_in, (docs[0], docs[1]))
        self.assertTrue(all(entry.chunk.origin == "code" for entry in code_only.values()))

    def test_all_entry_families_and_trigger_lifts(self):
        code = chunk("test", cosine=.8, path="__tests__/billing.test.ts", kind="module")
        generated = chunk("generated", cosine=.8, path="gql/types.ts", kind="file")
        both = chunk("both", cosine=.8, path="src/test_mixed.py", kind="style")
        # A configured overlap proves independent factors multiply only once.
        self.settings = self.load(orchard_patterns='generated_patterns = ["mixed", "gql/types"]')
        inputs = candidates((code, generated, both), meaning=tuple(Candidate(item, .8)
                           for item in (code, generated, both)))
        scores = {"test": .8 * .93 * .9, "generated": .8 * .93 * .9,
                  "both": .8 * .93 * .93 * .9}
        results = self.by_id(self.rank("how do payments work", inputs))
        for identifier, expected in scores.items():
            self.assertAlmostEqual(results[identifier].score, expected, places=14)
        for query in ("TEST", "tests", "Spec", "specs", "e2e", "MOCK", "mocks", "fixture", "fixtures"):
            with self.subTest(query=query):
                result = self.rank("how do " + query + " work", inputs)
                self.assertAlmostEqual(self.by_id(result)["test"].score, .8 * .9)
        for query in ("type", "TYPES", "schema", "schemas", "graphql", "gql", "codegen", "generated"):
            with self.subTest(query=query):
                result = self.rank("how do " + query + " work", inputs)
                self.assertAlmostEqual(self.by_id(result)["generated"].score, .8 * .9)
        both_lifted = self.by_id(self.rank("how do tests and schemas work", inputs))
        self.assertAlmostEqual(both_lifted["both"].score, .8 * .9)
        near_words = self.by_id(self.rank("contest spectacle mocked typeless schematics", inputs))
        self.assertAlmostEqual(near_words["both"].score, scores["both"])
        # The identifier route keeps generated factor=1 and uses its own test
        # and structural factors without changing the RRF constant.
        identifier = self.by_id(self.rank("payments", inputs))
        self.assertAlmostEqual(identifier["test"].score, 1 / 61 * .85 * .75)
        self.assertAlmostEqual(identifier["generated"].score, 1 / 62 * .75)
        self.assertAlmostEqual(identifier["both"].score, 1 / 63 * .85 * .75)
        lifted = self.by_id(self.rank("tests", inputs))
        self.assertAlmostEqual(lifted["test"].score, 1 / 61 * .75)

    def test_weighting_applies_to_bridge_and_wording_only_sources(self):
        test_bridge = chunk("test-bridge", cosine=.8, path="test_bridge.py", kind="module")
        generated_bridge = chunk("gen-bridge", cosine=.7, path="gql/types.ts", kind="style")
        test_word = chunk("test-word", path="run_test.go", kind="file")
        gen_word = chunk("gen-word", path="billing.generated.ts", kind="markup")
        doc = document("doc", .9)
        graph = RankingGraph((doc,), (DocumentCitation(doc, (test_bridge, generated_bridge)),))
        inputs = candidates((test_bridge, generated_bridge, test_word, gen_word),
            wording=(Candidate(test_word, 10), Candidate(gen_word, 9)))
        results = self.by_id(self.rank("how do payments work", inputs, graph))
        self.assertAlmostEqual(results["test-bridge"].score, .9 * .92 * .93 * .9)
        self.assertAlmostEqual(results["gen-bridge"].score, .9 * .92 * .93 * .9)
        self.assertAlmostEqual(results["test-word"].score, 10 * .93 * .9)
        self.assertAlmostEqual(results["gen-word"].score, 9 * .93 * .9)
        lifted = self.by_id(self.rank("how do tests and generated schemas work", inputs, graph))
        self.assertAlmostEqual(lifted["test-bridge"].score, .9 * .92 * .9)
        self.assertAlmostEqual(lifted["gen-word"].score, 9 * .9)
        lexical_only = self.by_id(self.rank("payments", inputs, vector=None))
        self.assertEqual(set(lexical_only), {"test-word", "gen-word"})
        self.assertAlmostEqual(lexical_only["test-word"].score, 1 / 61 * .85 * .75)
        self.assertAlmostEqual(lexical_only["gen-word"].score, 1 / 62 * .75)

    def test_repository_patterns_override_packaged_defaults(self):
        test = chunk("test", cosine=.8, path="conftest.py")
        custom = chunk("custom", cosine=.8, path="checks/billing.py")
        shared = document("shared", .9, repository="handbook", path="visible/checks.md")
        self.settings = self.load(orchard_patterns='test_patterns = ["^checks/"]\ngenerated_patterns = []',
                                 handbook_patterns='test_patterns = ["checks"]\ngenerated_patterns = []')
        inputs = candidates((test, custom, shared), meaning=(Candidate(test, .8),
            Candidate(custom, .8), Candidate(shared, .9)))
        results = self.by_id(self.rank("how do payments work", inputs))
        self.assertAlmostEqual(results["test"].score, .8)
        self.assertAlmostEqual(results["custom"].score, .8 * .93)
        self.assertAlmostEqual(results["shared"].score, .9 * .93)
        self.settings = self.load(orchard_patterns='test_patterns = []\ngenerated_patterns = []')
        self.assertAlmostEqual(self.by_id(self.rank("how do payments work", inputs))["custom"].score, .8)
        self.settings = self.load(orchard_patterns='test_patterns = ["["]')
        with self.assertRaises(MycelError) as raised:
            self.rank("how do payments work", inputs)
        self.assertEqual(raised.exception.code, "invalid_input")

    def test_mixed_document_margin_both_routes_arms_and_caps(self):
        code = chunk("code", cosine=.8, path="test_code.py", kind="module")
        below, boundary, above = (document(name, value) for name, value in
                                  (("below", .829), ("boundary", .83), ("above", .95)))
        last = document("last", .94)
        router = document("router", 1, root="code", path="nested/README.md")
        index = document("index", 1, path="INDEX.md")
        docs = (router, index, below, boundary, above, last)
        graph = RankingGraph(docs, (DocumentCitation(above, (code,)),))
        for query in ("payments", "how do payments work"):
            for arm in ("meaning", "wording"):
                with self.subTest(query=query, arm=arm):
                    arms = {"meaning": (Candidate(code, .8),)}
                    hits = tuple(Candidate(doc, value) for doc, value in
                                 zip(docs, (1, 1, .829, .83, .95, .94)))
                    arms[arm] = (*arms.get(arm, ()), *hits)
                    inputs = candidates((code, *docs), **arms)
                    reply = self.rank(query, inputs, graph, k=100)
                    doc_entries = [entry for entry in reply.results if entry.chunk.origin == "documents"]
                    self.assertEqual(len(doc_entries), 2)
                    self.assertEqual([entry.chunk for entry in doc_entries],
                                     [boundary, above] if query == "payments" else [above, last])
                    self.assertNotIn(below, [entry.chunk for entry in doc_entries])
                    self.assertNotIn(router, [entry.chunk for entry in doc_entries])
                    self.assertNotIn(index, [entry.chunk for entry in doc_entries])
                    boundary_only = candidates((code, boundary), meaning=(Candidate(code, .8),),
                        **({"wording": (Candidate(boundary, 3),)} if arm == "wording" else {}))
                    if arm == "meaning":
                        boundary_only = replace(boundary_only,
                            meaning=(Candidate(code, .8), Candidate(boundary, .83)))
                    admitted = self.rank(query, boundary_only)
                    self.assertIn(boundary, [entry.chunk for entry in admitted.results])
        # A high-code bar outside the capped meaning arm still excludes docs.
        hidden_code = chunk("outside-arm", cosine=.99)
        inputs = candidates((code, hidden_code, above), meaning=(Candidate(code, .8),),
                            wording=(Candidate(above, 100),))
        self.assertNotIn(above, [entry.chunk for entry in self.rank("payments", inputs).results])

    def test_mixed_document_negative_no_code_and_no_vector_policies(self):
        code = chunk("code", cosine=-.8)
        boundary = document("boundary", -.77)
        below = document("below", -.771)
        inputs = candidates((code, boundary, below), meaning=(Candidate(code, -.8),),
                            wording=(Candidate(boundary, 2), Candidate(below, 1)))
        self.assertEqual(set(self.by_id(self.rank("how do payments work", inputs))), {"code", "boundary"})
        incomplete = chunk("incomplete")
        negative_doc = document("negative", -.99)
        inputs = candidates((incomplete, negative_doc), wording=(Candidate(incomplete, 1), Candidate(negative_doc, 2)))
        self.assertIn("negative", self.by_id(self.rank("payments", inputs)))
        without = self.rank("payments", inputs, vector=None)
        self.assertEqual(set(self.by_id(without)), {"incomplete"})
        self.assertFalse(without.meaning_used)
        docs = tuple(document(str(i), .1) for i in range(4))
        router = document("router", path="README.md")
        inputs = candidates((router, *docs), wording=tuple(Candidate(item, 10 - i)
                            for i, item in enumerate((router, *docs))))
        for query in ("payments", "how do payments work"):
            reply = self.rank(query, inputs, vector=None, only="docs", k=100)
            self.assertEqual([entry.chunk for entry in reply.results], [router, *docs])
        # Docs-only cannot deliver cited code or add code-document annotations.
        target = chunk("target", cosine=1)
        graph = RankingGraph(docs, (DocumentCitation(docs[0], (target,)),))
        reply = self.rank("how do payments work", candidates((*docs, target),
            meaning=(Candidate(docs[0], .1),)), graph, only="docs")
        self.assertEqual([entry.chunk for entry in reply.results], [docs[0]])
        self.assertIsNone(reply.results[0].via)

    def test_input_validation_and_conflicting_snapshot_rows_refuse(self):
        code = chunk("code", cosine=.8)
        inputs = candidates((code,), meaning=(Candidate(code, .8),))
        for query, options in ((" ", {}), ("payments", {"k": 0}),
                               ("payments", {"only": "everything"})):
            with self.subTest(query=query, options=options), self.assertRaises(MycelError):
                self.rank(query, inputs, **options)
        with self.assertRaises(MycelError) as raised:
            self.rank("payments", candidates((code,), meaning=(Candidate(replace(code, name="other"), .8),)))
        self.assertEqual(raised.exception.code, "store_format")
        with self.assertRaises(MycelError):
            self.rank("payments", inputs, vector=(0, 0))
        with self.assertRaises(MycelError):
            self.rank("payments", candidates((replace(code, part_vectors=()),),
                wording=(Candidate(replace(code, part_vectors=()), 2),)))


if __name__ == "__main__":
    unittest.main()
