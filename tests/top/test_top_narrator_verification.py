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
