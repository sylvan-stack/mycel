# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Offline acceptance of pinned counts and complete original-text coverage."""
from dataclasses import FrozenInstanceError, replace
from importlib import resources
import json
from pathlib import Path
import random
import socket
import tempfile
from unittest.mock import patch

from mycel._embedding_plan import (
    PlanningError, code_place_line, document_place_line, load_tokenizer,
    plan_batches, plan_chunk, plan_query, validate_plan,
)
from mycel._errors import MycelError


import hashlib
import unittest
from dataclasses import replace

from mycel._embedding_plan import (
    load_tokenizer,
    plan_chunk,
    validate_plan,
)

OWNED = ("MYC-3.2", "MYC-3.3", "MYC-3.16", "MYC-3.18", "MYC-3.19", "MYC-3.20")


class EmbeddingPlanTests(unittest.TestCase):


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


# Archived complete imports; restore needed names in their original scope, not at this file tail.
