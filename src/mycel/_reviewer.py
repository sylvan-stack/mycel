"""One bounded protocol-1 reviewer attempt, without credentials or retries.

The finite classifier owns retry decisions, eligibility, evidence leases and
application. This module launches only an inspected command, supplies complete
independent evidence, and returns validated replies or safe typed failures.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import time
from types import MappingProxyType

from ._classification_payload import LABELS, DecisionPayload, ReviewCommandIdentity, ReviewerRequest
from ._errors import MycelError
from ._jev import ReviewerHandoff
from ._safeguards import (ChildProcessFailure, CompletedChild, InvocationPolicy,
                         require_model_call, run_resolved_reviewer)


_TRANSIENT = frozenset({"connection", "timeout", "rate_limited", "unavailable"})
_ADAPTER_CODES = _TRANSIENT | {"authentication", "input_too_large", "invalid_request",
    "provider_result_invalid", "unsupported_protocol", "internal"}
_MESSAGES = {
    "authentication": "The reviewer credential was rejected or unavailable.",
    "connection": "The reviewer service connection failed.",
    "timeout": "The reviewer attempt exceeded its time limit.",
    "rate_limited": "The reviewer service rate limit was reached.",
    "unavailable": "The reviewer service is temporarily unavailable.",
    "input_too_large": "The reviewer provider could not accept the complete input.",
    "invalid_request": "The reviewer provider rejected the request.",
    "provider_result_invalid": "The reviewer provider returned an invalid result.",
    "unsupported_protocol": "The reviewer adapter does not support the requested protocol.",
    "internal": "The reviewer adapter reported an internal failure.",
    "protocol": "The reviewer adapter returned an invalid protocol reply.",
    "transport": "The reviewer process failed to complete the protocol exchange.",
    "stdout_limit": "The reviewer exceeded its standard output limit.",
    "stderr_limit": "The reviewer exceeded its diagnostic output limit.",
    "input_incomplete": "The reviewer did not consume its complete request.",
    "review_command_unavailable": "The configured reviewer command is unavailable.",
    "review_input_too_large": "The complete reviewer request exceeds its byte budget.",
    "reviewer_unconfigured": "The independent reviewer is not configured.",
    "obsolete": "The reviewer command identity changed before launch.",
    "cancelled": "The reviewer attempt was cancelled.",
}
_IDENTITY = frozenset({"protocol", "inputHash", "provider", "model", "adapterRevision", "commandHash"})


def _finite_number(value) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


class ReviewerFailure(Exception):
    """A safe parent-owned diagnostic; no adapter messages or stderr survive."""

    def __init__(self, code: str, *, retry_after_seconds: float | None = None,
                 returncode: int | None = None, elapsed_seconds: float | None = None):
        if code not in _MESSAGES:
            raise ValueError("Unknown reviewer failure code.")
        if retry_after_seconds is not None and (code not in _TRANSIENT
                or not _finite_number(retry_after_seconds) or retry_after_seconds < 0):
            raise ValueError("A reviewer retry delay must be finite and belong to a transient fault.")
        self.code, self.retry_after_seconds = code, retry_after_seconds
        self.returncode, self.elapsed_seconds = returncode, elapsed_seconds
        super().__init__(_MESSAGES[code])

    @property
    def retryable(self) -> bool:
        return self.code in _TRANSIENT

    def as_dict(self) -> dict:
        value = {"code": self.code, "message": str(self), "retryable": self.retryable}
        if self.retry_after_seconds is not None:
            value["retryAfterSeconds"] = self.retry_after_seconds
        if self.returncode is not None:
            value["signal" if self.returncode < 0 else "exit"] = abs(self.returncode)
        if self.elapsed_seconds is not None:
            value["elapsedSeconds"] = self.elapsed_seconds
        return value


@dataclass(frozen=True)
class ReviewerLimits:
    timeout_seconds: float = 120.0
    max_input_bytes: int = 1048576

    def __post_init__(self):
        if (not _finite_number(self.timeout_seconds)
                or self.timeout_seconds <= 0 or type(self.max_input_bytes) is not int
                or self.max_input_bytes <= 0):
            raise MycelError("invalid_input", "Review requires finite positive time and byte budgets.")

    @classmethod
    def from_settings(cls, settings):
        settings.require_valid(require_store=False)
        values = settings.values["drifts"]
        return cls(values["review_timeout_seconds"], values["review_max_input_bytes"])


@dataclass(frozen=True)
class ReviewerSuccess:
    request: ReviewerRequest = field(repr=False)
    judgement: str
    rationale: str
    evidence: tuple[str, ...]
    usage: Mapping[str, int] | None = None
    elapsed_seconds: float = 0.0
    confidence_score: float | None = None

    def as_dict(self) -> dict:
        value = {key: self.request.payload[key] for key in _IDENTITY}
        value.update(judgement=self.judgement, rationale=self.rationale, evidence=list(self.evidence))
        if self.confidence_score is not None:
            value["confidenceScore"] = self.confidence_score
        if self.usage is not None:
            value["usage"] = dict(self.usage)
        return value


def _invalid(child: CompletedChild | None = None):
    raise ReviewerFailure("protocol", returncode=child.returncode if child else None,
                          elapsed_seconds=child.elapsed_seconds if child else None) from None


def _text(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _invalid()
        value[key] = item
    return value


def validate_response(child: CompletedChild, request: ReviewerRequest) -> ReviewerSuccess:
    """Validate strict JSON and its exit envelope; error diagnostics are discarded."""
    if not isinstance(child, CompletedChild) or not isinstance(request, ReviewerRequest):
        raise MycelError("invalid_input", "Review validation requires a completed child and typed request.")
    if type(child.returncode) is not int or child.returncode not in {0, 1}:
        raise ReviewerFailure("transport", returncode=child.returncode if type(child.returncode) is int else None,
                              elapsed_seconds=child.elapsed_seconds)
    if type(child.stdout) is not bytes or len(child.stdout) > 1048576:
        _invalid(child)
    try:
        source = child.stdout.decode("utf-8", errors="strict")
        value = json.loads(source, object_pairs_hook=_object,
                           parse_constant=lambda _: _invalid())
    except (ValueError, UnicodeError, RecursionError, ReviewerFailure):
        _invalid(child)
    if type(value) is not dict or not _IDENTITY <= value.keys():
        _invalid(child)
    if type(value["protocol"]) is not int or value["protocol"] != 1:
        _invalid(child)
    for key in _IDENTITY - {"protocol"}:
        if not isinstance(value[key], str) or value[key] != request.payload[key]:
            _invalid(child)
    if "error" in value:
        if set(value) != _IDENTITY | {"error"} or child.returncode != 1:
            _invalid(child)
        error = value["error"]
        if (type(error) is not dict or not {"code", "message"} <= error.keys()
                or error.keys() - {"code", "message", "retryAfterSeconds"}
                or not isinstance(error["code"], str) or error["code"] not in _ADAPTER_CODES
                or not _text(error["message"])):
            _invalid(child)
        delay = error.get("retryAfterSeconds")
        if "retryAfterSeconds" in error and (error["code"] not in _TRANSIENT
                or not _finite_number(delay) or delay < 0):
            _invalid(child)
        raise ReviewerFailure(error["code"], retry_after_seconds=delay,
                              returncode=child.returncode, elapsed_seconds=child.elapsed_seconds)
    if (child.returncode != 0 or not {"judgement", "rationale", "evidence"} <= value.keys()
            or value.keys() - _IDENTITY - {"judgement", "rationale", "evidence", "usage"} -
                ({"confidenceScore"} if request.decision.payload["questionVersion"] in {"mycel-origin-v1", "mycel-audit-conformance-v1", "mycel-audit-consistency-v1", "mycel-audit-ambiguity-v1"} else set())
            or not isinstance(value["judgement"], str) or value["judgement"] not in request.decision.payload["labels"]
            or not _text(value["rationale"])):
        _invalid(child)
    origin = request.decision.payload["questionVersion"] in {"mycel-origin-v1", "mycel-audit-conformance-v1", "mycel-audit-consistency-v1", "mycel-audit-ambiguity-v1"}
    score = value.get("confidenceScore")
    if origin and (not _finite_number(score) or not 0 <= score <= 1):
        _invalid(child)
    citations = value["evidence"]
    if (type(citations) is not list or not citations or any(not isinstance(item, str) for item in citations)
            or len(set(citations)) != len(citations)
            or not set(citations) <= set(request.decision.evidence_locators)):
        _invalid(child)
    usage = value.get("usage")
    if "usage" in value and (type(usage) is not dict or usage.keys() - {"inputTokens", "outputTokens"}
            or any(type(number) is not int or number < 0 for number in usage.values())):
        _invalid(child)
    return ReviewerSuccess(request, value["judgement"], value["rationale"].strip(), tuple(citations),
                           MappingProxyType(usage) if usage is not None else None, child.elapsed_seconds, score if origin else None)


def _check(deadline: float, cancelled: Callable[[], bool]):
    if cancelled():
        raise ReviewerFailure("cancelled")
    if time.monotonic() >= deadline:
        raise ReviewerFailure("timeout")


class ReviewerClient:
    def __init__(self, policy: InvocationPolicy, command: ReviewCommandIdentity, *,
                 home: Path | None = None, limits: ReviewerLimits | None = None):
        if not isinstance(command, ReviewCommandIdentity):
            raise MycelError("invalid_input", "Review requires an inspected command identity.")
        self.policy, self.command = policy, command
        self.home, self.limits = (home or Path.home()).resolve(), limits or ReviewerLimits()

    def classify(self, decision: DecisionPayload | ReviewerHandoff, *, deadline: float,
                 before_call: Callable[[], None],
                 cancelled: Callable[[], bool] = lambda: False,
                 on_call: Callable[[], None] = lambda: None) -> ReviewerSuccess:
        """Make one launch, with complete evidence and a required fresh guard.

        ``before_call`` rechecks the parent's frozen configuration and complete
        eligible inputs. The caller must independently recheck those identities
        and the executable before applying a returned result. Retry/backoff is
        exclusively the finite parent's responsibility.
        """
        require_model_call(self.policy, "reviewer")
        if (not _finite_number(deadline)
                or not callable(before_call) or not callable(cancelled) or not callable(on_call)):
            raise MycelError("invalid_input", "Review requires a finite deadline and fresh call guard.")
        command, home, limits, policy = self.command, self.home, self.limits, self.policy
        attempt_deadline = min(deadline, time.monotonic() + limits.timeout_seconds)
        _check(attempt_deadline, cancelled)
        if isinstance(decision, ReviewerHandoff):
            decision = decision.decision
        if not isinstance(decision, DecisionPayload):
            raise MycelError("invalid_input", "Review requires a complete typed decision payload.")
        review = decision.payload["models"]["review"]
        if review is None:
            raise ReviewerFailure("reviewer_unconfigured")
        if (review["commandHash"] != command.command_hash
                or review["adapterRevision"] != command.payload["adapterRevision"]):
            raise ReviewerFailure("obsolete")
        if not command.available:
            raise ReviewerFailure("review_command_unavailable")
        budget_at = time.monotonic()
        timeout_ms = math.floor((attempt_deadline - budget_at) * 1000)
        if timeout_ms < 1:
            raise ReviewerFailure("timeout")
        attempt_deadline = budget_at + timeout_ms / 1000
        request = ReviewerRequest(decision, timeout_ms)
        transmitted = request.transmitted_bytes
        _check(attempt_deadline, cancelled)
        if len(transmitted) > limits.max_input_bytes:
            raise ReviewerFailure("review_input_too_large")

        def guard():
            _check(attempt_deadline, cancelled)
            before_call()
            _check(attempt_deadline, cancelled)
            if (self.command != command or self.home != home or self.limits != limits or self.policy != policy):
                raise ReviewerFailure("obsolete")
            current = ReviewCommandIdentity.inspect(command.payload["argv"],
                        command.payload["adapterRevision"], home)
            _check(attempt_deadline, cancelled)
            if current != command:
                raise ReviewerFailure("obsolete")
            if math.floor((attempt_deadline - time.monotonic()) * 1000) < 1:
                raise ReviewerFailure("timeout")
            on_call()

        try:
            child = run_resolved_reviewer(policy, command.payload["argv"], transmitted,
                timeout_seconds=timeout_ms / 1000, home=home, before_spawn=guard,
                cancelled=cancelled, absolute_deadline=attempt_deadline)
        except ChildProcessFailure as error:
            code = "review_command_unavailable" if error.reason == "unavailable" else error.reason
            raise ReviewerFailure(code if code in _MESSAGES else "transport") from None
        except OSError:
            raise ReviewerFailure("transport") from None
        except KeyboardInterrupt:
            raise
        _check(attempt_deadline, cancelled)
        try:
            result = validate_response(child, request)
        except ReviewerFailure:
            _check(attempt_deadline, cancelled)
            raise
        _check(attempt_deadline, cancelled)
        return result
