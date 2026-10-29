"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_embedding_plan as _support
from test_embedding_plan import (load_tokenizer ,patch ,plan_batches ,random ,socket)


class EmbeddingPlanTests(_support.EmbeddingPlanTests):


# TEST-TIER-BEGIN tests/test_embedding_plan.py::EmbeddingPlanTests.test_loader_and_counts_work_with_network_and_hub_downloads_forbidden
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
# TEST-TIER-END tests/test_embedding_plan.py::EmbeddingPlanTests.test_loader_and_counts_work_with_network_and_hub_downloads_forbidden


# TEST-TIER-BEGIN tests/test_embedding_plan.py::EmbeddingPlanTests.test_varied_original_unicode_always_reconstructs_deterministically
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
# TEST-TIER-END tests/test_embedding_plan.py::EmbeddingPlanTests.test_varied_original_unicode_always_reconstructs_deterministically
