"""Check the public Narrator verification and repair boundaries without models."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/narrator/verification.py"
SPEC = spec_from_file_location("mycel_narrator_verification", SCRIPT)
assert SPEC and SPEC.loader
verification = module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


def unit(unit_id, prose, cited_ids, *, revision=1, conditions=()):
    return {
        "unit_id": unit_id,
        "revision": revision,
        "prose": prose,
        "scope": "restore hold",
        "conditions": list(conditions),
        "cited_passage_ids": list(cited_ids),
        "originating_candidate_ids": [f"candidate-{unit_id}"],
        "consequence_rank": 1,
    }


def verdict(unit_id, revision, evidence, *, affected_part=None, reason=None):
    return {
        "unit_id": unit_id,
        "revision": revision,
        "verdict": "unsupported" if affected_part else "supported",
        "evidence_passage_ids": list(evidence),
        "affected_part": affected_part,
        "reason": reason,
    }


def source_request(sections):
    request = "\n".join(sections.values())
    digest = sha256(request.encode("utf-8")).hexdigest()
    passages = []
    for passage_id, text in sections.items():
        start = request.index(text)
        passages.append({
            "request_digest": digest, "passage_id": passage_id,
            "start": start, "end": start + len(text), "text": text,
        })
    return request, digest, [(0, len(request))], passages


def eligible(rejection, consequence, correction_passage_ids):
    return dict(rejection, repair_eligibility={
        "omission_consequence": consequence,
        "correction_passage_ids": correction_passage_ids,
    })


def correction(unit_id, revision, prose, cited_ids, *, conditions=()):
    return {
        "unit_id": unit_id, "revision": revision, "repair": "corrected",
        "prose": prose, "scope": "restore hold", "conditions": list(conditions),
        "cited_passage_ids": list(cited_ids),
    }


class NarratorVerificationTests(unittest.TestCase):
    def test_exact_nonadjacent_passages_require_a_current_verdict(self):
        request = "Objet: épreuve\nRule: hold.\nGap\nException: audit.\nOutro"
        digest = sha256(request.encode("utf-8")).hexdigest()
        rule = {"start": 15, "end": 26, "text": "Rule: hold."}
        exception = {"start": 31, "end": 48, "text": "Exception: audit."}
        exact_rule = dict(rule, passage_id="rule", request_digest=digest)
        exact_exception = dict(exception, passage_id="exception", request_digest=digest)
        decoy = {
            "start": 7, "end": 14, "text": "épreuve", "passage_id": "decoy", "request_digest": digest,
        }
        proposal = unit(
            "hold", "Hold unless an audit permits release.", ["rule", "decoy", "exception"], revision=3,
        )
        unsupported = unit("decoy-only", "Release is mandatory.", ["decoy"])
        expected = dict(proposal, revision=4, cited_passage_ids=["rule", "exception"])

        for judged_revision in (3, 4):
            with self.subTest(judged_revision=judged_revision):
                def judge(_instructions, payload):
                    self.assertEqual(payload["units"], [{
                        "unit_id": "hold",
                        "revision": 4,
                        "prose": "Hold unless an audit permits release.",
                        "scope": "restore hold",
                        "conditions": [],
                        "cited_passage_ids": ["rule", "exception"],
                    }])
                    self.assertEqual(payload["source_context"], [rule, exception])
                    self.assertEqual(payload["passages"], [exact_rule, exact_exception])
                    return [verdict("hold", judged_revision, ["rule", "exception"])]

                checked, verdicts, dispositions = verification.verify_units(
                    request, digest, [(31, 48), (15, 26)],
                    [exact_exception, decoy, exact_rule], [proposal, unsupported], judge=judge,
                )

                self.assertEqual(checked, [expected])
                unsupported_verdict = next(row for row in verdicts if row["unit_id"] == "decoy-only")
                self.assertEqual(unsupported_verdict["verdict"], "unsupported")
                self.assertEqual(unsupported_verdict["evidence_passage_ids"], [])
                supported = [row for row in verdicts if row["verdict"] == "supported"]
                exclusions = {
                    (row["unit_id"], row["revision"], row["outcome"]): row for row in dispositions
                }
                removed = exclusions[("hold", 4, "invalid_citation")]
                self.assertEqual(
                    (removed["passage_id"], removed["citation_position"], removed["previous_revision"]),
                    ("decoy", 2, 3),
                )
                if judged_revision == 3:
                    self.assertEqual(supported, [])
                    self.assertIn(("hold", 4, "missing_verdict"), exclusions)
                else:
                    self.assertEqual(supported, [verdict("hold", 4, ["rule", "exception"])])

    def test_repair_handoff_contains_only_fresh_supported_revisions(self):
        request = source_request({
            "approval": "Approved correction can lift the restore hold 24 hours after approval.",
            "audit": "That correction applies only to a generated child with a complete audit record.",
            "override": "A manual override expires 48 hours after issue unless a recorded extension applies.",
            "logging": "Operators log every override.",
            "causality": "Shorter holds coincided with fewer retries. The cause remains unresolved.",
        })
        original = unit("logging", "Operators log every override.", ["logging"], revision=2)
        overclaim = unit("correction", "Only correction lifts the hold 24 hours after ingestion.", ["approval"])
        override = unit("override", "Manual overrides never expire.", ["override"])
        causal = unit("causal", "Shorter holds caused fewer retries.", ["causality"])
        correction_rejection = eligible(
            verdict("correction", 1, ["approval", "audit"],
                    affected_part="Only correction lifts the hold 24 hours after ingestion",
                    reason="The source permits correction without making it exclusive and starts the clock at approval."),
            "An operator might lift a hold too early or deny another authorized path.", ["approval", "audit"],
        )
        override_rejection = eligible(
            verdict("override", 1, ["override"], affected_part="never expire",
                    reason="Manual overrides expire unless a recorded extension applies."),
            "An operator might rely on an expired override.", ["override"],
        )
        causal_rejection = verdict(
            "causal", 1, ["causality"], affected_part="caused", reason="The causal claim is unresolved.",
        )
        original_support = verdict("logging", 2, ["logging"])
        initial = verification.verify_units(
            *request, [original, overclaim, override, causal], assess_repair=True,
            judge=lambda _instructions, _payload: [
                original_support, correction_rejection, override_rejection, causal_rejection,
            ],
        )

        repaired_prose = (
            "An approved correction can lift the restore hold 24 hours after approval "
            "for a generated child with a complete audit record."
        )
        conditions = ["generated child", "complete audit record", "24 hours after approval"]
        incomplete_prose = "A manual override expires 48 hours after issue."
        fresh_support = verdict("correction", 2, ["approval", "audit"])
        fresh_rejection = verdict(
            "override", 2, ["override"], affected_part="expires 48 hours after issue",
            reason="The prose omits the recorded-extension exception.",
        )
        calls = []

        def admit():
            calls.append("admit")
            return True

        def repair(_instructions, payload):
            calls.append("repair")
            self.assertEqual(payload["rejections"], [correction_rejection, override_rejection])
            self.assertEqual([row["unit_id"] for row in payload["units"]], ["correction", "override"])
            return [
                correction("correction", 1, repaired_prose, ["approval", "audit"], conditions=conditions),
                correction("override", 1, incomplete_prose, ["override"]),
            ]

        def recheck(_instructions, payload):
            calls.append("recheck")
            self.assertEqual([
                (row["unit_id"], row["revision"], row["prose"], row["conditions"], row["cited_passage_ids"])
                for row in payload["units"]
            ], [
                ("correction", 2, repaired_prose, conditions, ["approval", "audit"]),
                ("override", 2, incomplete_prose, [], ["override"]),
            ])
            return [fresh_support, fresh_rejection, verdict("override", 1, ["override"])]

        supported, verdicts, dispositions = verification.repair_units(
            *request, initial, admit=admit, repair=repair, recheck=recheck,
        )

        self.assertEqual(calls, ["admit", "repair", "recheck"])
        self.assertEqual(supported, [original, dict(
            overclaim, revision=2, prose=repaired_prose, conditions=conditions,
            cited_passage_ids=["approval", "audit"],
        )])
        self.assertEqual(verdicts, [
            original_support, correction_rejection, override_rejection, causal_rejection,
            fresh_support, fresh_rejection,
        ])
        self.assertEqual([
            (row["unit_id"], row["revision"], row["outcome"], row["previous_revision"])
            for row in dispositions if row["stage"] == "repair"
        ], [("correction", 2, "repaired", 1), ("override", 2, "repair_unsupported", 1)])

    def test_repair_budget_preserves_the_original_verified_subset(self):
        request = source_request({
            "logging": "Every restore attempt is logged.",
            "child": "A generated child can be restored only after its audit record is complete.",
        })
        original = unit("logging", "Every restore attempt is logged.", ["logging"], revision=2)
        unsafe = unit("child", "Restore generated children without waiting for an audit record.", ["child"])
        support = verdict("logging", 2, ["logging"])
        rejection = eligible(
            verdict("child", 1, ["child"], affected_part="without waiting for an audit record",
                    reason="The audit record must be complete before restoration."),
            "An operator might restore a child before the audit is complete.", ["child"],
        )
        repaired_prose = "Restore a generated child only after its audit record is complete."
        initial = verification.verify_units(
            *request, [original, unsafe], assess_repair=True,
            judge=lambda _instructions, _payload: [support, rejection],
        )

        for stage, expected_calls, expected_revision, previous_revision in (
            ("admit", ["admit"], 1, None),
            ("repair", ["admit", "repair"], 1, None),
            ("recheck", ["admit", "repair", "recheck"], 2, 1),
        ):
            with self.subTest(stage=stage):
                calls = []

                def admit():
                    calls.append("admit")
                    return stage != "admit"

                def repair(_instructions, _payload):
                    calls.append("repair")
                    if stage == "repair":
                        raise verification.RepairBudgetExhausted
                    return [correction("child", 1, repaired_prose, ["child"])]

                def recheck(_instructions, payload):
                    calls.append("recheck")
                    fresh, = payload["units"]
                    self.assertEqual((fresh["unit_id"], fresh["revision"], fresh["prose"]),
                                     ("child", 2, repaired_prose))
                    raise verification.RepairBudgetExhausted

                supported, verdicts, dispositions = verification.repair_units(
                    *request, initial, admit=admit, repair=repair, recheck=recheck,
                )

                self.assertEqual(calls, expected_calls)
                self.assertEqual(supported, [original])
                self.assertEqual(verdicts, [support, rejection])
                self.assertEqual([
                    (row["unit_id"], row["revision"], row["outcome"], row.get("previous_revision"))
                    for row in dispositions if row["stage"] == "repair"
                ], [("child", expected_revision, "budget_exhausted", previous_revision)])
