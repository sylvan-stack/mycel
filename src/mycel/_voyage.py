"""Bounded Voyage transport and offline-testable embedding orchestration.

Only the fixed in-process HTTPS transport sees the private key. Persistence is
an internal guarded callback, supplied by the store feature; this module does
not claim that a callback alone implements PostgreSQL commit guards.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
import http.client
import json
import math
import re
import ssl
import threading
import time

from ._credentials import Credentials, Secret
from ._embedding_plan import EmbeddingBatch, ModelTokenizer, PlanningError, QueryPlan, load_tokenizer
from ._errors import MycelError
from ._safeguards import InvocationPolicy, require_model_call


_HOST = "api.voyageai.com"
_PATH = "/v1/embeddings"
REQUEST_DEADLINE_SECONDS = 60.0
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
_TRANSIENT = frozenset({"connection", "deadline", "rate_limit", "server"})
_MESSAGES = {
    "connection": "The embedding service connection failed.",
    "deadline": "The embedding service request exceeded its deadline.",
    "rate_limit": "The embedding service rate limit was reached.",
    "server": "The embedding service returned a temporary server failure.",
    "authentication": "The embedding credential was rejected or unavailable.",
    "authorization": "The embedding service refused authorization.",
    "missing_model": "The embedding service could not provide the selected model.",
    "content": "The embedding service rejected this complete input.",
    "invalid_response": "The embedding service returned an invalid response.",
    "response_limit": "The embedding service response exceeded the local byte limit.",
    "provider": "The embedding service refused the request.",
    "cancelled": "Embedding was stopped by the caller.",
}


class ProviderFailure(Exception):
    def __init__(self, kind: str, *, retry_after: float | None = None):
        self.kind = kind if kind in _MESSAGES else "provider"
        self.retry_after = retry_after
        super().__init__(_MESSAGES[self.kind])

    def to_dict(self) -> dict:
        return {"kind": self.kind, "message": str(self)}


class EmbeddingGuardFailure(MycelError):
    """An invocation input changed after earlier batches may have committed."""


@dataclass(frozen=True)
class HTTPResult:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


def _cancel_check(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise ProviderFailure("cancelled")


def _tls_context() -> ssl.SSLContext:
    # Match Python's verified client defaults without its SSLKEYLOGFILE
    # side effect. Authentication traffic never creates a TLS secret log.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


def _https_request(body: bytes, key: Secret, *, deadline: float, cancelled: Callable[[], bool]) -> HTTPResult:
    """Use one fixed TLS connection; redirects and ambient proxy settings do not apply.

    Supervision bounds the caller even when TLS setup or OS DNS is slow. A
    worker finishing after cancellation checks the stop event before connecting
    or transmitting and closes its connection. No retry happens here.
    """
    _cancel_check(cancelled)
    stopped = threading.Event()
    done = threading.Event()
    result = []
    connection = None

    def check():
        if stopped.is_set():
            raise ProviderFailure("cancelled")
        if time.monotonic() >= deadline:
            raise ProviderFailure("deadline")

    def remaining():
        check()
        duration = max(0.001, deadline - time.monotonic())
        if connection is not None:
            connection.timeout = duration
            if connection.sock is not None:
                connection.sock.settimeout(duration)

    def close():
        active = connection
        if active is not None:
            try:
                active.close()
            except (OSError, http.client.HTTPException):
                pass

    def work():
        nonlocal connection
        try:
            check()
            context = _tls_context()
            check()  # TLS certificate loading also belongs to the deadline.
            connection = http.client.HTTPSConnection(_HOST,
                         timeout=max(0.001, deadline - time.monotonic()), context=context)
            remaining()
            connection.connect()
            remaining()  # In particular, do not send after a slow DNS lookup.
            connection.request("POST", _PATH, body=body,
                               headers={"Authorization": "Bearer " + key.reveal(),
                                        "Content-Type": "application/json", "Accept": "application/json"})
            remaining()
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length) > MAX_RESPONSE_BYTES or int(length) < 0:
                        raise ProviderFailure("response_limit")
                except ValueError:
                    raise ProviderFailure("invalid_response") from None
            chunks = []
            size = 0
            while True:
                remaining()
                chunk = response.read1(min(64 * 1024, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ProviderFailure("response_limit")
                chunks.append(chunk)
            check()
            result.append(HTTPResult(response.status, b"".join(chunks),
                                     {name.lower(): value for name, value in response.getheaders()}))
        except ProviderFailure as failure:
            result.append(failure)
        except (TimeoutError, OSError, http.client.HTTPException):
            result.append(ProviderFailure("deadline" if time.monotonic() >= deadline else "connection"))
        except Exception:
            result.append(ProviderFailure("provider"))
        finally:
            try:
                close()
            finally:
                done.set()

    worker = threading.Thread(target=work, name="mycel-voyage-request", daemon=True)
    worker.start()
    try:
        while not done.is_set():
            _cancel_check(cancelled)
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise ProviderFailure("deadline")
            done.wait(min(0.05, remaining_time))
        _cancel_check(cancelled)
        if time.monotonic() >= deadline:
            raise ProviderFailure("deadline")
        if not result:
            raise ProviderFailure("provider")
        value = result[0]
        if isinstance(value, ProviderFailure):
            raise value
        return value
    finally:
        stopped.set()
        # Close active sockets on caller interruption or deadline, even if the
        # worker is between response reads. Its finally also closes late DNS.
        active_socket = connection.sock if connection is not None else None
        if active_socket is not None:
            try:
                active_socket.shutdown(2)
            except OSError:
                pass
        close()


def _wait(seconds: float, cancelled: Callable[[], bool]) -> None:
    end = time.monotonic() + seconds
    while True:
        _cancel_check(cancelled)
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        threading.Event().wait(min(0.05, remaining))


def _retry_after(headers: Mapping[str, str], now: float) -> float | None:
    value = next((value for name, value in headers.items() if name.lower() == "retry-after"), None)
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"[0-9]+", value.strip()):
        digits = value.strip().lstrip("0")
        seconds = 60.0 if len(digits) > 2 else float(digits or "0")
    else:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = date.timestamp() - now
        except (TypeError, ValueError, OverflowError):
            return None
    return min(60.0, max(0.0, seconds)) if math.isfinite(seconds) and seconds >= 0 else None


def _client_error_kind(result: HTTPResult) -> str:
    """Classify known request faults without copying arbitrary provider text."""
    try:
        body = _load_json(result.body)
    except ProviderFailure:
        return "provider"
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if error.get("param") == "model" or (isinstance(code, str) and code in {"model_not_found", "invalid_model", "unsupported_model"}):
            return "missing_model"
    detail = body.get("detail", body.get("message", ""))
    if isinstance(error, dict):
        detail = error.get("message", detail)
    if not isinstance(detail, str):
        return "provider"
    wording = detail.casefold()
    if "model" in wording and any(term in wording for term in
                                  ("invalid", "not found", "does not exist", "not supported", "unsupported", "unavailable")):
        return "missing_model"
    if any(term in wording for term in ("context length", "token limit", "number of tokens", "batch size", "too many tokens")):
        return "content"
    return "provider"


def _load_json(body: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("nonfinite JSON value")

    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ProviderFailure("invalid_response") from None


@dataclass(frozen=True)
class ValidatedResponse:
    vectors: tuple[tuple[float, ...], ...] = field(repr=False)
    provider_tokens: int
    requests: int


def _validate_response(result: HTTPResult, *, model: str, dimensions: int, input_count: int) -> ValidatedResponse:
    body = _load_json(result.body)
    data = body.get("data")
    usage = body.get("usage")
    if (body.get("model", model) != model or not isinstance(data, list) or len(data) != input_count
            or not isinstance(usage, dict) or type(usage.get("total_tokens")) is not int
            or usage["total_tokens"] < 0):
        raise ProviderFailure("invalid_response")
    vectors = [None] * input_count
    for row in data:
        if not isinstance(row, dict):
            raise ProviderFailure("invalid_response")
        index, vector = row.get("index"), row.get("embedding")
        if (type(index) is not int or not 0 <= index < input_count or vectors[index] is not None
                or not isinstance(vector, list) or len(vector) != dimensions):
            raise ProviderFailure("invalid_response")
        if any(type(number) not in {int, float} for number in vector):
            raise ProviderFailure("invalid_response")
        try:
            numeric = tuple(float(number) for number in vector)
        except (OverflowError, ValueError):
            raise ProviderFailure("invalid_response") from None
        if any(not math.isfinite(number) for number in numeric):
            raise ProviderFailure("invalid_response")
        vectors[index] = numeric
    if any(vector is None for vector in vectors):
        raise ProviderFailure("invalid_response")
    return ValidatedResponse(tuple(vectors), usage["total_tokens"], 0)


@dataclass(frozen=True)
class PartIdentity:
    repository: str
    chunk_id: str
    chunk_version: str
    part_order: int


@dataclass(frozen=True)
class VectorWrite:
    part: PartIdentity
    model: str
    dimensions: int
    vector: tuple[float, ...] = field(repr=False)


@dataclass(frozen=True)
class PartFailure:
    part: PartIdentity
    kind: str
    message: str


@dataclass(frozen=True)
class CommitReceipt:
    """The guarded transaction partitions supplied parts by exact retention.

    The store callback must commit every still-retained version atomically and
    return deleted only for versions removed meanwhile. There is no callback
    for an unvalidated provider response.
    """
    retained: tuple[PartIdentity, ...]
    deleted: tuple[PartIdentity, ...] = ()
    deferred: tuple[PartIdentity, ...] = ()


def _receipt(receipt: CommitReceipt, supplied: Sequence[PartIdentity]) -> tuple[int, int, int]:
    groups = ((receipt.retained, receipt.deleted, receipt.deferred)
              if isinstance(receipt, CommitReceipt) else ())
    if (not groups or any(not isinstance(group, tuple) or any(not isinstance(part, PartIdentity) for part in group)
                          or len(set(group)) != len(group) for group in groups)
            or sum(len(group) for group in groups) != len(set().union(*groups))
            or set().union(*groups) != set(supplied)):
        raise MycelError("internal", "The guarded embedding commit returned invalid retention accounting.")
    return len(receipt.retained), len(receipt.deleted), len(receipt.deferred)


@dataclass(frozen=True)
class EmbeddingProgress:
    repository: str
    embedded_parts: int
    failed_parts: int
    discarded_parts: int
    submitted_inputs: int
    requests: int
    provider_tokens: int
    stopping_reason: str | None = None
    stopping_kind: str | None = None
    deferred_parts: int = 0

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class VoyageClient:
    def __init__(self, credentials: Credentials, policy: InvocationPolicy, *,
                 tokenizer: ModelTokenizer | None = None, attempts: int = 5,
                 cancelled: Callable[[], bool] | None = None,
                 before_send: Callable[[], None] | None = None,
                 _transport: Callable[..., HTTPResult] | None = None,
                 _waiter: Callable[[float, Callable[[], bool]], None] | None = None,
                 _monotonic: Callable[[], float] = time.monotonic,
                 _wall_clock: Callable[[], float] = time.time):
        if type(attempts) is not int or attempts < 1:
            raise MycelError("settings", "Embedding attempts must be a positive integer.")
        self._credentials = credentials
        self._policy = policy
        self._tokenizer = tokenizer or load_tokenizer()
        self._attempts = attempts
        self._cancelled = cancelled or (lambda: False)
        self._before_send = before_send or (lambda: None)
        self._transport = _transport or _https_request
        self._waiter = _waiter or _wait
        self._monotonic = _monotonic
        self._wall_clock = _wall_clock
        self._requests = 0
        self._submitted = 0

    def _body(self, inputs: Sequence[str], model: str, dimensions: int, input_type: str) -> bytes:
        catalog = self._tokenizer.catalog
        if (model != catalog.model or type(dimensions) is not int or dimensions not in catalog.dimensions
                or input_type not in {"query", "document"} or not inputs
                or len(inputs) > catalog.batch_input_cap):
            raise PlanningError("The embedding request does not match the packaged model contract.")
        counts = [self._tokenizer.counts(text, input_type) for text in inputs]
        if (any(max(count) > catalog.input_token_cap for count in counts)
                or sum(count[0] for count in counts) > catalog.batch_token_cap
                or sum(count[1] for count in counts) > catalog.batch_token_cap):
            raise PlanningError("The complete embedding request exceeds its verified local limits.")
        body = json.dumps({"input": list(inputs), "model": model, "output_dimension": dimensions,
                           "output_dtype": "float", "input_type": input_type, "truncation": False},
                          ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise PlanningError("The complete embedding request exceeds the local byte limit.")
        return body

    def _request(self, inputs: Sequence[str], model: str, dimensions: int, input_type: str) -> ValidatedResponse:
        require_model_call(self._policy, "embedding")
        body = self._body(inputs, model, dimensions, input_type)
        _cancel_check(self._cancelled)
        self._before_send()
        try:
            key = self._credentials.require_embedding_key()
        except MycelError:
            raise ProviderFailure("authentication") from None
        if "\r" in key.reveal() or "\n" in key.reveal():
            raise ProviderFailure("authentication")
        first_request = self._requests
        for attempt in range(self._attempts):
            _cancel_check(self._cancelled)
            self._before_send()
            deadline = self._monotonic() + REQUEST_DEADLINE_SECONDS
            self._requests += 1
            self._submitted += len(inputs)
            try:
                result = self._transport(body, key, deadline=deadline, cancelled=self._cancelled)
                _cancel_check(self._cancelled)
                if self._monotonic() >= deadline:
                    raise ProviderFailure("deadline")
                if not isinstance(result, HTTPResult) or type(result.status) is not int:
                    raise ProviderFailure("invalid_response")
                if not isinstance(result.body, bytes) or len(result.body) > MAX_RESPONSE_BYTES:
                    raise ProviderFailure("response_limit")
                status = result.status
                if (not isinstance(result.headers, Mapping)
                        or any(not isinstance(name, str) or not isinstance(value, str)
                               for name, value in result.headers.items())):
                    raise ProviderFailure("invalid_response")
                retry = _retry_after(result.headers, self._wall_clock())
                kind = ("deadline" if status == 408 else "rate_limit" if status == 429 else
                        "server" if 500 <= status <= 599 else "authentication" if status == 401 else
                        "authorization" if status == 403 else "missing_model" if status == 404 else
                        "content" if status in {413, 422} else
                        _client_error_kind(result) if status == 400 else "provider")
                if status != 200:
                    raise ProviderFailure(kind, retry_after=retry)
                validated = _validate_response(result, model=model, dimensions=dimensions, input_count=len(inputs))
                return ValidatedResponse(validated.vectors, validated.provider_tokens, self._requests - first_request)
            except (TimeoutError, ConnectionError, OSError):
                failure = ProviderFailure("connection")
            except ProviderFailure as error:
                failure = error
            if failure.kind not in _TRANSIENT or attempt + 1 == self._attempts:
                raise failure
            pause = min(30.0, 2.0 ** min(attempt, 5))
            if failure.retry_after is not None:
                pause = max(pause, min(60.0, failure.retry_after))
            self._waiter(pause, self._cancelled)
        raise ProviderFailure("provider")

    def query(self, plan: QueryPlan) -> ValidatedResponse:
        return self._request((plan.text,), plan.model, plan.dimensions, "query")

    def embed_repository(self, repository: str, batches: Sequence[EmbeddingBatch], *,
                         commit: Callable[[tuple[VectorWrite, ...]], CommitReceipt],
                         record_failures: Callable[[tuple[PartFailure, ...]], CommitReceipt]) -> EmbeddingProgress:
        """Process saved inputs; callbacks supply future store commit guards."""
        if any(batch.repository != repository or any(item.repository != repository for item in batch.inputs)
               for batch in batches):
            raise MycelError("invalid_input", "An embedding pass requires one repository's saved batches.")
        embedded = failed = discarded = deferred = usage = 0
        before_requests, before_submitted = self._requests, self._submitted
        stopping = None

        def send(batch, inputs):
            nonlocal embedded, failed, discarded, deferred, usage
            identities = tuple(PartIdentity(item.repository, item.chunk_id, item.chunk_version, item.part_order)
                               for item in inputs)
            try:
                response = self._request(tuple(item.input_text for item in inputs), batch.model, batch.dimensions, "document")
            except ProviderFailure as error:
                if error.kind != "content":
                    raise
                if len(inputs) > 1:
                    middle = len(inputs) // 2
                    send(batch, inputs[:middle])
                    send(batch, inputs[middle:])
                else:
                    failure = PartFailure(identities[0], error.kind, str(error))
                    retained, deleted, staged = _receipt(record_failures((failure,)), identities)
                    failed += retained
                    discarded += deleted
                    deferred += staged
                    if staged:
                        raise MycelError("busy", "Returned embedding results are saved for later publication.")
                return
            # Once a complete response is validated, save its paid results
            # before observing cancellation between batches.
            writes = tuple(VectorWrite(identity, batch.model, batch.dimensions, vector)
                           for identity, vector in zip(identities, response.vectors))
            usage += response.provider_tokens
            retained, deleted, staged = _receipt(commit(writes), identities)
            embedded += retained
            discarded += deleted
            deferred += staged
            if staged:
                raise MycelError("busy", "Returned embedding results are saved for later publication.")

        try:
            for batch in batches:
                _cancel_check(self._cancelled)
                send(batch, batch.inputs)
        except ProviderFailure as failure:
            stopping = failure
        except KeyboardInterrupt:
            stopping = ProviderFailure("cancelled")
        except MycelError as error:
            if (not isinstance(error, EmbeddingGuardFailure)
                    and error.code not in {"busy", "store_unavailable", "store_format"}):
                raise
            stopping = error
        return EmbeddingProgress(repository, embedded, failed, discarded,
                                 self._submitted - before_submitted, self._requests - before_requests, usage,
                                 str(stopping) if stopping else None,
                                 (stopping.kind if isinstance(stopping, ProviderFailure) else stopping.code.value)
                                 if stopping else None, deferred)
