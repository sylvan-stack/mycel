# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Local protocol and app-server stand-ins; never access a model or credentials."""
import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from mycel import _classification_payload as payload

try:
    from .test_reviewer import context_fixture
except ImportError:
    from test_reviewer import context_fixture


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/review_with_codex.py"
SPEC = importlib.util.spec_from_file_location("mycel_codex_review_adapter", SCRIPT)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
CATALOG = "/fictional/model-catalog.json"


def complete_request():
    command = payload.ReviewCommandIdentity({"argv": ["/fictional/python", "-I", "-B", "/fictional/adapter.py"],
        "executableSha256": "a" * 64, "adapterRevision": "fictional-codex-v1", "protocol": 1,
        "instructionVersion": "mycel-review-v1", "environmentVersion": "mycel-review-env-v1"})
    original = context_fixture(command)
    body = original.as_dict()
    body["models"]["review"] = dict(command.model_identity(adapter.PROVIDER, adapter.MODEL))
    decision = payload.DecisionPayload(body)
    return json.loads(payload.ReviewerRequest(decision, 120000).canonical_bytes), command


def configured():
    result = {}
    with patch.object(Path, "home", return_value=Path("/fictional")), \
            patch.object(Path, "open", side_effect=FileNotFoundError):
        # The only file-dependent settings are MCP table headers. Supply a
        # local in-memory empty configuration, never the owner's settings.
        from io import StringIO
        with patch.object(Path, "open", return_value=StringIO("")):
            for key, value in adapter.overrides(CATALOG).items():
                target = result
                parts = key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = deepcopy(value)
    return result


def selected_thread():
    return {"model": adapter.MODEL, "modelProvider": adapter.PROVIDER, "reasoningEffort": adapter.EFFORT,
            "instructionSources": [], "approvalPolicy": "never", "sandbox": {"type": "readOnly"},
            "thread": {"id": "fictional-thread", "ephemeral": True}}


class ScriptedServer:
    def __init__(self, request, *, events=None):
        self.request, self.events = request, events
        self.calls, self.sent = [], []
        self.on_notification = lambda message: None
        self.config = configured()
        self.catalog = CATALOG
        self.selected = selected_thread()
        self.account = {"requiresOpenaiAuth": True, "account": {"type": "chatgpt"}}

    def send(self, value):
        self.sent.append(value)

    def call(self, method, params):
        self.calls.append((method, deepcopy(params)))
        if method == "initialize":
            return {}
        if method == "config/read":
            return {"config": self.config, "origins": {"tools.update_plan.enabled": {},
                    "tools.experimental_request_user_input.enabled": {}, "model_catalog_json": {}}}
        if method == "account/read":
            return self.account
        if method == "thread/start":
            return self.selected
        if method != "turn/start":
            raise AssertionError("Unexpected fixture RPC")
        answer = {"judgement": "needs_review", "rationale": "The changed permission contradicts the guide.",
                  "evidence": [self.request["evidenceLocators"][0]]}
        common = {"threadId": "fictional-thread", "turnId": "fictional-turn"}
        events = [
            {"method": "item/completed", "params": {**common, "item": {"type": "agentMessage", "id": "answer",
                "phase": "final_answer", "text": json.dumps(answer)}}},
            {"method": "rawResponse/completed", "params": {**common, "responseId": "fictional-response",
                "usage": {"inputTokens": 123, "outputTokens": 7}}},
            {"method": "turn/completed", "params": {"threadId": "fictional-thread",
                "turn": {"id": "fictional-turn", "status": "completed", "error": None}}},
        ]
        if self.events is not None:
            events = self.events(deepcopy(events))
        for event in events:
            self.on_notification(event)
        return {"turn": {"id": "fictional-turn"}}


class CodexReviewerAdapterTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
