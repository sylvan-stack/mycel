"""One bounded TypeSafe Jev attempt and complete independent-review handoff.

The finite classifier owns selection, retries, stage leases and persistence.
This adapter consumes the canonical decision, invokes an explicit fresh guard
before credentials and transmission, and never changes freshness or Drift work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from email.utils import parsedate_to_datetime
import http.client
import json
import math
import re
import ssl
import threading
import time
from types import MappingProxyType

from ._classification_payload import (CHOICE_CRITERIA, INSTRUCTION, LABELS,
                                     DecisionPayload, ReviewerRequest)
from ._credentials import Credentials, CredentialUnavailable, Secret
from ._errors import MycelError
from ._safeguards import InvocationPolicy, require_model_call


ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_HOST = "api.typesafe.ai"
_PATH = "/v1/systemone"
MAX_RESPONSE_BYTES = 1048576
TOLERANCE = Decimal("0.000001")
_TRANSIENT = frozenset({"connection", "timeout", "rate_limited", "unavailable"})
_MESSAGES = {
    "authentication": "The Jev credential was rejected or unavailable.",
    "connection": "The Jev service connection failed.",
    "timeout": "The Jev attempt exceeded its time limit.",
    "rate_limited": "The Jev service rate limit was reached.",
    "unavailable": "The Jev service is temporarily unavailable.",
    "invalid_request": "The Jev service rejected the request.",
    "provider_result_invalid": "The Jev service returned an invalid result.",
    "cancelled": "The Jev attempt was cancelled.",
}


class JevFailure(Exception):
    """Safe typed stage failure; raw provider/OS diagnostics are never retained."""

    def __init__(self, code: str, *, retry_after_seconds: float | None = None):
        if code not in _MESSAGES:
            raise ValueError("Unknown Jev failure code.")
        if retry_after_seconds is not None and (code not in _TRANSIENT
                or type(retry_after_seconds) not in {int, float}
                or not math.isfinite(retry_after_seconds) or retry_after_seconds < 0):
            raise ValueError("A Jev retry delay must be finite and belong to a transient fault.")
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(_MESSAGES[code])

    @property
    def retryable(self) -> bool:
        return self.code in _TRANSIENT

    def as_dict(self) -> dict:
        value = {"code": self.code, "message": str(self), "retryable": self.retryable}
        if self.retry_after_seconds is not None:
            value["retryAfterSeconds"] = self.retry_after_seconds
        return value


@dataclass(frozen=True)
class JevLimits:
    timeout_seconds: float = 10.0
    max_input_bytes: int = 24000

    def __post_init__(self):
        if (type(self.timeout_seconds) not in {int, float} or not math.isfinite(self.timeout_seconds)
                or self.timeout_seconds <= 0 or type(self.max_input_bytes) is not int
                or self.max_input_bytes <= 0):
            raise MycelError("invalid_input", "Jev requires finite positive time and byte budgets.")

    @classmethod
    def from_settings(cls, settings):
        settings.require_valid(require_store=False)
        values = settings.values["drifts"]
        return cls(values["jev_timeout_seconds"], values["max_input_bytes"])


@dataclass(frozen=True)
class JevRequest:
    decision: DecisionPayload = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.decision, DecisionPayload):
            raise MycelError("invalid_input", "Jev requires a complete canonical decision.")

    @property
    def body(self) -> bytes:
        # Preserve Choice insertion order. Canonical decision JSON sorts map
        # keys for identity; applying that encoding to the HTTP envelope would
        # reorder production Choices and change the accepted question.
        return json.dumps({"state": self.decision.as_dict(),
            "model": self.decision.payload["models"]["jev"]["model"],
            "questions": {"dependency": {"type": "choice", "instructions": INSTRUCTION,
                "criteria": dict(zip(LABELS, CHOICE_CRITERIA, strict=True))}}},
            ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class HTTPResult:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


def _invalid():
    raise JevFailure("provider_result_invalid")


def _object(pairs):
    value = {}
    for key, member in pairs:
        if key in value:
            _invalid()
        value[key] = member
    return value


def _json(body: bytes):
    try:
        if type(body) is not bytes or len(body) > MAX_RESPONSE_BYTES:
            _invalid()
        return json.loads(body.decode("utf-8"), parse_float=Decimal,
            parse_constant=lambda _: _invalid(), object_pairs_hook=_object)
    except (UnicodeError, ValueError, TypeError, RecursionError, InvalidOperation):
        _invalid()


def _fraction(value):
    if type(value) not in {Decimal, int}:
        _invalid()
    number = Decimal(value)
    if not number.is_finite() or not 0 <= number <= 1:
        _invalid()
    return Decimal(0) if number == 0 else number


def _distribution(probabilities, confidence, label):
    # Default Decimal precision is 28, which can round a just-outside reply
    # onto the tolerance boundary. All products here terminate: division is
    # only by two. Include every transmitted decimal place plus carry digits.
    # Refuse precision beyond the bounded response arithmetic budget instead
    # of silently rounding an adversarial exponent or returning support.
    precision = max(32, 2 - min(number.as_tuple().exponent
                    for number in (*probabilities.values(), confidence)))
    if precision > MAX_RESPONSE_BYTES:
        _invalid()
    with localcontext() as context:
        context.prec = precision
        context.Emin = -MAX_RESPONSE_BYTES
        context.Emax = MAX_RESPONSE_BYTES
        top = max(probabilities.values())
        if (abs(sum(probabilities.values()) - 1) > TOLERANCE
                or probabilities[label] != top or abs(confidence - (3 * top - 1) / 2) > TOLERANCE):
            _invalid()
    return sum(member == top for member in probabilities.values()) > 1


def _canonical_confidence(probabilities, reported):
    """Derive the exact Choice statistic without changing any probability."""
    precision = max(32, 2 - min(number.as_tuple().exponent
                    for number in (*probabilities.values(), reported)))
    if precision > MAX_RESPONSE_BYTES:
        _invalid()
    with localcontext() as context:
        context.prec = precision
        context.Emin = -MAX_RESPONSE_BYTES
        context.Emax = MAX_RESPONSE_BYTES
        confidence = (3 * max(probabilities.values()) - 1) / 2
    # Keep the response's existing finite fraction invariant. Do not clamp a
    # negative result or renormalize a rounded, nearly uniform distribution.
    return _fraction(confidence)


def _confidence_comparison(reported, canonical):
    precision = max(32, 2 - min(number.as_tuple().exponent for number in (reported, canonical)))
    if precision > MAX_RESPONSE_BYTES:
        _invalid()
    with localcontext() as context:
        context.prec = precision
        context.Emin = -MAX_RESPONSE_BYTES
        context.Emax = MAX_RESPONSE_BYTES
        difference = reported - canonical
    return {"matches": reported == canonical, "reportedMinusCanonical": float(difference)}


@dataclass(frozen=True)
class JevResponse:
    model: str
    label: str
    probabilities: Mapping[str, Decimal]
    confidence: Decimal
    usage: Mapping[str, int]
    tied: bool
    reported_confidence: Decimal | None = None

    def __post_init__(self):
        if (not isinstance(self.model, str) or not re.fullmatch(r"jev-[0-9]+\.[0-9]+\.[0-9]+", self.model)
                or not isinstance(self.label, str) or self.label not in LABELS
                or not isinstance(self.probabilities, Mapping) or set(self.probabilities) != set(LABELS)
                or not isinstance(self.usage, Mapping) or set(self.usage) != {"input_tokens", "output_tokens"}
                or any(type(member) is not int or member < 0 for member in self.usage.values())
                or type(self.tied) is not bool):
            _invalid()
        probabilities = {label: _fraction(self.probabilities[label]) for label in LABELS}
        confidence = _fraction(self.confidence)
        if self.tied != _distribution(probabilities, confidence, self.label):
            _invalid()
        reported = _fraction(confidence if self.reported_confidence is None else self.reported_confidence)
        canonical = _canonical_confidence(probabilities, reported)
        if confidence != canonical:
            _invalid()
        object.__setattr__(self, "probabilities", MappingProxyType(probabilities))
        object.__setattr__(self, "confidence", canonical)
        object.__setattr__(self, "reported_confidence", reported)
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))

    def as_dict(self) -> dict:
        return {"provider": "typesafe", "model": self.model, "label": self.label,
            "probabilities": {label: float(self.probabilities[label]) for label in LABELS},
            "confidence": float(self.confidence), "reportedConfidence": float(self.reported_confidence),
            "confidenceComparison": _confidence_comparison(self.reported_confidence, self.confidence),
            "tied": self.tied, "usage": dict(self.usage)}


def validate_response(result: HTTPResult, *, model: str) -> JevResponse:
    """Use decimal JSON numbers so exact tolerance/floor boundaries stay exact."""
    if not isinstance(result, HTTPResult) or result.status != 200:
        _invalid()
    value = _json(result.body)
    if (not isinstance(value, dict) or set(value) != {"model", "answers", "usage"}
            or value["model"] != model or not isinstance(value["answers"], dict)
            or set(value["answers"]) != {"dependency"}):
        _invalid()
    answer = value["answers"]["dependency"]
    if (not isinstance(answer, dict) or set(answer) != {"type", "choice", "probabilities", "confidence"}
            or answer["type"] != "choice" or not isinstance(answer["choice"], str)
            or answer["choice"] not in LABELS or not isinstance(answer["probabilities"], dict)
            or set(answer["probabilities"]) != set(LABELS)):
        _invalid()
    probabilities = {label: _fraction(answer["probabilities"][label]) for label in LABELS}
    reported = _fraction(answer["confidence"])
    confidence = _canonical_confidence(probabilities, reported)
    tied = _distribution(probabilities, confidence, answer["choice"])
    usage = value["usage"]
    if (not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}
            or any(type(member) is not int or member < 0 for member in usage.values())):
        _invalid()
    return JevResponse(model, answer["choice"], MappingProxyType(probabilities), confidence,
                       MappingProxyType(dict(usage)), tied, reported_confidence=reported)


@dataclass(frozen=True)
class ReviewerHandoff:
    decision: DecisionPayload = field(repr=False)
    reason: str
    status: str
    request: ReviewerRequest | None = field(default=None, repr=False)


@dataclass(frozen=True)
class JevOutcome:
    decision: DecisionPayload = field(repr=False)
    response: JevResponse | None
    status: str
    reason: str | None = None

    @property
    def judgement(self) -> str | None:
        return self.response.label if self.status == "complete" else None

    def as_dict(self) -> dict:
        value = {"inputHash": self.decision.input_hash, "status": self.status,
            "model": self.decision.payload["models"]["jev"]["model"],
            "routing": dict(self.decision.payload["routing"])}
        if self.response is not None:
            value["jev"] = self.response.as_dict()
        if self.judgement is not None:
            value["judgement"] = self.judgement
        if self.reason is not None:
            value["reason"] = self.reason
        return value

    def reviewer_handoff(self, *, timeout_ms: int, max_input_bytes: int = 1048576) -> ReviewerHandoff:
        """Retain the exact complete decision even when review cannot launch."""
        if (self.status != "needs_llm_review" or type(timeout_ms) is not int or timeout_ms < 1
                or type(max_input_bytes) is not int or max_input_bytes < 1):
            raise MycelError("invalid_input", "Only review-routed work has a positive complete reviewer budget.")
        if self.decision.payload["models"]["review"] is None:
            return ReviewerHandoff(self.decision, "reviewer_unconfigured", "needs_llm_review")
        request = ReviewerRequest(self.decision, timeout_ms)
        if len(request.transmitted_bytes) > max_input_bytes:
            return ReviewerHandoff(self.decision, "review_input_too_large", "error")
        return ReviewerHandoff(self.decision, self.reason, "needs_llm_review", request)


def route_response(decision: DecisionPayload, response: JevResponse) -> JevOutcome:
    if response.model != decision.payload["models"]["jev"]["model"]:
        _invalid()
    reason = ("jev_tied" if response.tied else "insufficient_evidence" if response.label == "insufficient_evidence"
              else "jev_low_confidence" if response.confidence < Decimal(decision.payload["routing"]["confidenceFloor"])
              else None)
    return JevOutcome(decision, response, "needs_llm_review" if reason else "complete", reason)


def _check(deadline: float, cancelled: Callable[[], bool]):
    if cancelled():
        raise JevFailure("cancelled")
    if time.monotonic() >= deadline:
        raise JevFailure("timeout")


def _tls_context():
    # Do not honor SSLKEYLOGFILE; the provider key exists only in this boundary.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


def _https_request(body: bytes, key: Secret, *, deadline: float,
                   cancelled: Callable[[], bool]) -> HTTPResult:
    """Fixed HTTPS endpoint, bounded bytes/time, no redirect/proxy/retry channel."""
    _check(deadline, cancelled)
    stopped, done = threading.Event(), threading.Event()
    result, connection, active_socket = [], None, None

    def check():
        _check(deadline, lambda: stopped.is_set())

    def remaining():
        check()
        duration = max(0.001, deadline - time.monotonic())
        if connection is not None:
            connection.timeout = duration
            if active_socket is not None:
                active_socket.settimeout(duration)

    def close():
        if active_socket is not None:
            try:
                active_socket.close()
            except OSError:
                pass
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass

    def work():
        nonlocal connection, active_socket
        try:
            check()
            context = _tls_context()
            check()
            connection = http.client.HTTPSConnection(_HOST,
                timeout=max(0.001, deadline - time.monotonic()), context=context)
            remaining()
            connection.connect()
            # getresponse() may detach connection.sock for Connection: close;
            # HTTPResponse still owns its file and can block in read1. Retain
            # the actual socket so supervision can always interrupt that read.
            active_socket = connection.sock
            remaining()  # A delayed DNS/TLS connection must never send late.
            connection.request("POST", _PATH, body=body, headers={
                "Authorization": "Bearer " + key.reveal(),
                "Content-Type": "application/json", "Accept": "application/json"})
            remaining()
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length) < 0 or int(length) > MAX_RESPONSE_BYTES:
                        _invalid()
                except ValueError:
                    _invalid()
            chunks, size = [], 0
            while True:
                remaining()
                chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    _invalid()
                chunks.append(chunk)
            check()
            result.append(HTTPResult(response.status, b"".join(chunks),
                          {name.lower(): member for name, member in response.getheaders()}))
        except JevFailure as failure:
            result.append(failure)
        except TimeoutError:
            result.append(JevFailure("timeout"))
        except (OSError, http.client.HTTPException):
            result.append(JevFailure("timeout" if time.monotonic() >= deadline else "connection"))
        except Exception:
            result.append(JevFailure("invalid_request"))
        finally:
            try:
                close()
            finally:
                done.set()

    worker = threading.Thread(target=work, name="mycel-jev-request", daemon=True)
    worker.start()
    try:
        while not done.is_set():
            _check(deadline, cancelled)
            done.wait(min(0.05, max(0, deadline - time.monotonic())))
        _check(deadline, cancelled)
        if not result:
            raise JevFailure("invalid_request")
        if isinstance(result[0], JevFailure):
            raise result[0]
        return result[0]
    finally:
        stopped.set()
        if active_socket is not None:
            try:
                active_socket.shutdown(2)
            except OSError:
                pass
        close()
        if active_socket is not None:
            # Shutdown wakes bounded response I/O. Cleanup permits no paid
            # work; a slow DNS worker with no socket checks stopped on return.
            worker.join(timeout=1.0)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = next((value for name, value in headers.items() if name.lower() == "retry-after"), None)
    if not isinstance(value, str):
        return None
    try:
        if value.strip().isdigit():
            seconds = float(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = date.timestamp() - time.time()
    except (ValueError, TypeError, OverflowError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _context_refusal(result: HTTPResult) -> bool:
    # Recognize explicit provider error codes only. A generic 422 or arbitrary
    # diagnostic containing the word "context" is not a size refusal.
    if result.status not in {400, 413, 422}:
        return False
    try:
        value = _json(result.body)
    except JevFailure:
        return False
    if not isinstance(value, dict):
        return False
    error = value.get("error", value)
    return (isinstance(error, dict) and isinstance(error.get("code"), str) and error["code"] in {
        "context_length_exceeded", "max_context_length_exceeded", "input_too_long", "too_many_tokens"})


class JevClient:
    def __init__(self, credentials: Credentials, policy: InvocationPolicy, *,
                 limits: JevLimits | None = None, _transport=None):
        self.credentials, self.policy = credentials, policy
        self.limits = limits or JevLimits()
        self._transport = _transport or _https_request

    def classify(self, decision: DecisionPayload, *, deadline: float,
                 before_call: Callable[[], None], cancelled: Callable[[], bool] = lambda: False,
                 on_call: Callable[[], None] = lambda: None) -> JevOutcome:
        """Run at most one provider call; the caller owns guard/lease and retry.

        ``before_call`` must raise if the exact prepared inputs are no longer
        eligible. It runs before Keychain access and again before transmission.
        The absolute monotonic invocation deadline bounds the entire attempt.
        """
        require_model_call(self.policy, "jev")
        if (type(deadline) not in {int, float} or not math.isfinite(deadline)
                or not callable(before_call) or not callable(on_call)):
            raise MycelError("invalid_input", "Jev requires an absolute finite deadline and a fresh call guard.")
        attempt_deadline = min(deadline, time.monotonic() + self.limits.timeout_seconds)
        _check(attempt_deadline, cancelled)
        request = JevRequest(decision)
        body = request.body
        _check(attempt_deadline, cancelled)
        before_call()
        _check(attempt_deadline, cancelled)
        if len(body) > self.limits.max_input_bytes:
            return JevOutcome(decision, None, "needs_llm_review", "jev_input_too_large")
        try:
            key = self.credentials.require_jev_key(timeout_seconds=attempt_deadline - time.monotonic(),
                                                   cancelled=cancelled)
        except CredentialUnavailable:
            _check(attempt_deadline, cancelled)
            raise JevFailure("authentication") from None
        _check(attempt_deadline, cancelled)
        before_call()
        _check(attempt_deadline, cancelled)
        on_call()
        try:
            result = self._transport(body, key, deadline=attempt_deadline, cancelled=cancelled)
        except JevFailure:
            raise
        except TimeoutError:
            raise JevFailure("timeout") from None
        except (OSError, http.client.HTTPException):
            raise JevFailure("connection") from None
        except Exception:
            raise JevFailure("invalid_request") from None
        _check(attempt_deadline, cancelled)
        if not isinstance(result, HTTPResult) or type(result.status) is not int:
            _invalid()
        if result.status in {401, 403}:
            raise JevFailure("authentication")
        if result.status in {429, 529} or 500 <= result.status <= 599:
            raise JevFailure("rate_limited" if result.status == 429 else "unavailable",
                             retry_after_seconds=_retry_after(result.headers))
        if _context_refusal(result):
            return JevOutcome(decision, None, "needs_llm_review", "jev_context_refused")
        if result.status != 200:
            raise JevFailure("invalid_request")
        response = validate_response(result, model=decision.payload["models"]["jev"]["model"])
        _check(attempt_deadline, cancelled)
        return route_response(decision, response)
