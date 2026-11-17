"""Check Narrator selection with local consolidation and verification stand-ins."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest


_SELECTION_PATH = Path(__file__).resolve().parents[2] / "scripts/narrator/selection.py"
_SELECTION_SPEC = spec_from_file_location("narrator_selection", _SELECTION_PATH)
assert _SELECTION_SPEC is not None and _SELECTION_SPEC.loader is not None
selection = module_from_spec(_SELECTION_SPEC)
_SELECTION_SPEC.loader.exec_module(selection)


def _passages(*excerpts):
    source = "\n\n".join(excerpts)
    request_digest = sha256(source.encode("utf-8")).hexdigest()
    passages = []
    start = 0
    for number, excerpt in enumerate(excerpts, 1):
        end = start + len(excerpt)
        passages.append({
            "request_digest": request_digest,
            "passage_id": f"p{number}",
            "start": start,
            "end": end,
            "text": source[start:end],
        })
        start = end + 2
    return passages


def _proposal(unit_id, prose, rank, citations, *, authority="lab policy", conditions=()):
    candidate_id = f"claim-{unit_id}"
    candidate = {
        "candidate_id": candidate_id,
        "claim": prose,
        "authority": authority,
        "scope": "lab samples",
        "cited_passage_ids": list(citations),
    }
    unit = {
        "unit_id": unit_id,
        "revision": 1,
        "prose": prose,
        "scope": "lab samples",
        "conditions": list(conditions),
        "originating_candidate_ids": [candidate_id],
        "cited_passage_ids": list(citations),
        "consequence_rank": rank,
    }
    return candidate, unit


def _key(unit):
    return {"unit_id": unit["unit_id"], "revision": unit["revision"]}


def _comparison(left, right, *, equivalent=True):
    return {
        "left": _key(left),
        "right": _key(right),
        "equivalent": equivalent,
        "reason": "Same retention period" if equivalent else "Different retention periods",
    }


def _supported(unit, *, consulted=None):
    return {
        **_key(unit),
        "verdict": "supported",
        "affected_part": None,
        "reason": None,
        "evidence_passage_ids": list(unit["cited_passage_ids"] if consulted is None else consulted),
    }


class NarratorSelectionTests(unittest.TestCase):
    def test_supported_regrouping_preserves_late_exception(self):
        passages = _passages(
            "Keep samples for thirty days.",
            "Discard contaminated samples before storage.",
        )
        candidates, proposed = zip(
            _proposal("rejected", "Keep samples for forty days.", 4, ("p1",)),
            _proposal("preferred", "Keep samples for thirty days.", 3, ("p1",)),
            _proposal("alternative", "Retain samples for thirty days.", 2, ("p1",)),
            _proposal("exception", "Discard contaminated samples before storage.", 1, ("p2",),
                      conditions=("contaminated",)),
        )
        rejected, preferred, alternative, exception = proposed
        model_reply = {
            "units": list(proposed),
            "comparisons": [
                _comparison(rejected, preferred),
                _comparison(rejected, alternative, equivalent=False),
                _comparison(preferred, alternative),
            ],
        }
        units, comparisons = selection.parse_consolidation_response(model_reply, candidates)
        initial = selection.select_distinct_units(units, candidates, passages, comparisons)
        self.assertEqual([group["members"] for group in initial["groups"]],
                         [[rejected, preferred], [alternative], [exception]])

        rejected_verdict = {
            **_key(rejected),
            "verdict": "unsupported",
            "affected_part": "forty days",
            "reason": "The policy gives thirty days.",
            "evidence_passage_ids": ["p1"],
        }
        supported = [preferred, alternative, exception]
        verdicts = [rejected_verdict, *(_supported(unit) for unit in supported)]
        frozen_groups = selection.assemble_summary(initial["groups"], verdicts, passages, word_cap=10)
        self.assertEqual(frozen_groups["selected_units"], [preferred, alternative])
        self.assertIn(("exception", 1, "skipped_for_budget"), [
            (item["unit_id"], item["revision"], item["outcome"])
            for item in frozen_groups["dispositions"]
        ])

        regrouped = selection.select_distinct_units(supported, candidates, passages, comparisons)
        summary = selection.assemble_summary(regrouped["groups"], verdicts, passages, word_cap=10)
        self.assertEqual(summary["selected_units"], [preferred, exception])
        self.assertEqual(summary["summary"],
                         "Keep samples for thirty days.\nDiscard contaminated samples before storage.")
        self.assertEqual(summary["word_count"], 10)
        equivalent = next(item for item in summary["dispositions"]
                          if item["outcome"] == "equivalent_not_selected")
        self.assertEqual((equivalent["unit_id"], equivalent["revision"],
                          equivalent["representative_unit_id"], equivalent["representative_revision"]),
                         ("alternative", 1, "preferred", 1))

        revised = alternative | {"revision": 2, "prose": "Store samples for thirty days."}
        current = selection.select_distinct_units([preferred, revised, exception], candidates,
                                                  passages, comparisons)
        self.assertEqual([group["members"] for group in current["groups"]],
                         [[preferred], [revised], [exception]])
        fresh = selection.assemble_summary(current["groups"], [*verdicts, _supported(revised)],
                                           passages, word_cap=10)
        self.assertEqual(fresh["selected_units"], [preferred, revised])

    def test_authority_and_exact_evidence_survive_selection(self):
        passages = _passages(
            "The laboratory board requires a thirty-day hold.",
            "The handling log records tags by batch.",
            "The board starts the hold at intake.",
            "The disposal contractor asks for immediate disposal.",
        )
        candidates, (board, contractor_previous, invalid) = zip(
            _proposal("board", "The board requires 30 days from intake.", 2, ("p1", "p3"),
                      authority="laboratory board"),
            _proposal("contractor", "Contractor requests immediate sample disposal.", 1, ("p4",),
                      authority="disposal contractor"),
            _proposal("uncited", "Destroy all samples upon arrival.", 3, ("p999",)),
        )
        contractor = contractor_previous | {
            "revision": 2, "prose": "The contractor requests immediate disposal.",
        }
        grouped = selection.select_distinct_units(
            [board, contractor, invalid], candidates, passages, [_comparison(board, contractor)]
        )
        self.assertEqual([group["members"] for group in grouped["groups"]],
                         [[invalid], [board], [contractor]])
        self.assertIn(("uncited", 1, "invalid_citation"), [
            (item["unit_id"], item["revision"], item["outcome"])
            for item in grouped["dispositions"]
        ])

        verdicts = [_supported(board), _supported(contractor_previous),
                    _supported(invalid, consulted=["p1"])]
        earlier = selection.assemble_summary(grouped["groups"], verdicts, passages, word_cap=12)
        self.assertEqual(earlier["summary"], "The board requires 30 days from intake.")

        current = selection.assemble_summary(grouped["groups"], [*verdicts, _supported(contractor)],
                                            passages, word_cap=12)
        self.assertEqual(current["summary"],
                         "The board requires 30 days from intake.\n"
                         "The contractor requests immediate disposal.")
        board_selected, contractor_selected = current["selected_units"]
        self.assertEqual(_key(board_selected), {"unit_id": "board", "revision": 1})
        self.assertEqual(_key(contractor_selected), {"unit_id": "contractor", "revision": 2})
        self.assertEqual(board_selected["cited_passage_ids"], ["p1", "p3"])
        self.assertEqual(contractor_selected["cited_passage_ids"], ["p4"])
        self.assertEqual(board_selected["originating_candidate_ids"], ["claim-board"])
        self.assertEqual(contractor_selected["originating_candidate_ids"], ["claim-contractor"])
        self.assertEqual([unit["scope"] for unit in current["selected_units"]],
                         ["lab samples", "lab samples"])

    def test_oversized_member_leaves_room_for_distinct_rule_and_shorter_equivalent(self):
        passages = _passages(
            "Keep the laboratory samples for thirty days.",
            "Seal bags before transport.",
        )
        candidates, (shorter, transport, oversized) = zip(
            _proposal("shorter", "Retain  samples\tfor thirty days.", 1, ("p1",)),
            _proposal("transport", "Seal\tbags  before transport.", 2, ("p2",),
                      conditions=("transport",)),
            _proposal("oversized", "The rule requires that the laboratory samples be held for thirty days.",
                      3, ("p1",)),
        )
        units = [shorter, transport, oversized]
        grouped = selection.select_distinct_units(
            units, candidates, passages, [_comparison(oversized, shorter)]
        )
        verdicts = [_supported(unit) for unit in units]
        exact = selection.assemble_summary(grouped["groups"], verdicts, passages, word_cap=9)
        self.assertEqual([unit["unit_id"] for unit in exact["selected_units"]],
                         ["transport", "shorter"])
        self.assertEqual(exact["summary"],
                         "Seal\tbags  before transport.\nRetain  samples\tfor thirty days.")
        self.assertEqual(exact["word_count"], 9)
        skip, = [item for item in exact["dispositions"] if item["outcome"] == "skipped_for_budget"]
        self.assertEqual(_key(skip), {"unit_id": "oversized", "revision": 1})
        self.assertEqual((skip["required_words"], skip["remaining_words"]), (12, 9))

        no_fit = selection.assemble_summary(grouped["groups"], verdicts, passages, word_cap=3)
        self.assertIsNone(no_fit["summary"])
        self.assertEqual(no_fit["word_count"], 0)
        self.assertEqual(no_fit["selected_units"], [])
        self.assertEqual([
            (item["unit_id"], item["revision"], item["outcome"],
             item["required_words"], item["remaining_words"])
            for item in no_fit["dispositions"]
        ], [
            ("oversized", 1, "skipped_for_budget", 12, 3),
            ("transport", 1, "skipped_for_budget", 4, 3),
            ("shorter", 1, "skipped_for_budget", 5, 3),
        ])

    def test_distinct_rule_fits_before_covered_detail(self):
        passages = _passages(
            "Store sealed samples for thirty days.",
            "Retain sealed freezer samples for thirty days.",
            "Revoke expired credentials before granting access.",
        )
        cover_claim, cover = _proposal("cover", passages[0]["text"], 3, ("p1",),
                                       conditions=("sealed",))
        detail_claim, detail = _proposal("detail", passages[1]["text"], 2, ("p2",),
                                          conditions=("sealed",))
        distinct_claim, distinct = _proposal("distinct", passages[2]["text"], 1, ("p3",))
        detail_claim["scope"] = detail["scope"] = "freezer samples"
        distinct_claim["scope"] = distinct["scope"] = "lab access"
        candidates = [cover_claim, detail_claim, distinct_claim]
        reason = "The sealed-sample policy already governs sealed freezer samples."
        comparison = {
            "left": _key(cover), "right": _key(detail), "equivalent": False,
            "detail": "right", "reason": reason,
        }
        units, comparisons = selection.parse_consolidation_response({
            "units": [cover, detail, distinct], "comparisons": [comparison],
        }, candidates)
        grouped = selection.select_distinct_units(units, candidates, passages, comparisons)
        self.assertEqual([
            [(unit["unit_id"], unit["scope"]) for unit in group["members"]]
            for group in grouped["groups"]
        ], [[("cover", "lab samples")], [("detail", "freezer samples")], [("distinct", "lab access")]])

        other_verdicts = [_supported(detail), _supported(distinct)]
        covered = selection.assemble_summary(grouped["groups"], [_supported(cover), *other_verdicts],
                                            passages, word_cap=13)
        self.assertEqual(covered["summary"],
                         "Store sealed samples for thirty days.\n"
                         "Revoke expired credentials before granting access.")
        self.assertEqual(covered["word_count"], 12)
        self.assertIn({
            "stage": "selection", "unit_id": "detail", "revision": 1, "outcome": "deferred_detail",
            "covering_unit_id": "cover", "covering_revision": 1, "reason": reason,
        }, covered["dispositions"])

        unsupported = {
            **_key(cover), "verdict": "unsupported", "affected_part": "thirty days",
            "reason": "The covering rule did not pass this check.", "evidence_passage_ids": ["p1"],
        }
        uncovered = selection.assemble_summary(grouped["groups"], [unsupported, *other_verdicts],
                                              passages, word_cap=13)
        self.assertEqual(uncovered["summary"],
                         "Retain sealed freezer samples for thirty days.\n"
                         "Revoke expired credentials before granting access.")
        self.assertNotIn("deferred_detail", {item["outcome"] for item in uncovered["dispositions"]})

        replacement = cover | {"revision": 2, "prose": "Hold sealed samples for thirty days."}
        revised_groups = selection.select_distinct_units(
            [replacement, detail, distinct], candidates, passages, comparisons
        )["groups"]
        revised = selection.assemble_summary(revised_groups, [_supported(replacement), *other_verdicts],
                                            passages, word_cap=13)
        self.assertEqual(revised["summary"],
                         "Hold sealed samples for thirty days.\n"
                         "Retain sealed freezer samples for thirty days.")
        self.assertNotIn("deferred_detail", {item["outcome"] for item in revised["dispositions"]})

        # A separate consolidation proposal supplies an exact comparison for the longer cover.
        oversized = cover | {"prose":
            "The laboratory retention policy requires all sealed samples covered by this rule "
            "to be stored for thirty days.",
        }
        long_units, long_comparisons = selection.parse_consolidation_response({
            "units": [oversized, detail, distinct], "comparisons": [comparison],
        }, candidates)
        long_groups = selection.select_distinct_units(long_units, candidates, passages,
                                                     long_comparisons)["groups"]
        fallback = selection.assemble_summary(long_groups, [_supported(oversized), *other_verdicts],
                                             passages, word_cap=13)
        self.assertEqual(fallback["summary"],
                         "Revoke expired credentials before granting access.\n"
                         "Retain sealed freezer samples for thirty days.")
        self.assertEqual(fallback["word_count"], 13)
        self.assertIn(("cover", 1, "skipped_for_budget", 18, 13), [
            (item["unit_id"], item["revision"], item["outcome"],
             item["required_words"], item["remaining_words"])
            for item in fallback["dispositions"] if item["outcome"] == "skipped_for_budget"
        ])
