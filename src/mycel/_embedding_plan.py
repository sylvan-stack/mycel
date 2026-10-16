"""Offline, lossless plans measured with the Build's pinned Voyage tokenizer.

This module plans inputs only. It opens no provider connection, writes no store,
and never acquires a credential. Text offsets always refer to the original UTF-8
body, including characters changed by the tokenizer's NFC normalizer.
"""

from bisect import bisect_right
from dataclasses import asdict, dataclass, field
import hashlib
from importlib import resources
import json
from pathlib import Path
import re
from typing import Iterable

from ._errors import ErrorCode, MycelError


class PlanningError(MycelError):
    """A local failure that leaves the complete source text untouched."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.REFUSED, message)


@dataclass(frozen=True)
class ModelCatalog:
    model: str
    dimensions: tuple[int, ...]
    default_dimensions: int
    tokenizer_repository: str
    tokenizer_revision: str
    tokenizer_file: str
    tokenizer_sha256: str
    tokenizers_version: str
    planner_version: int
    provider_context_tokens: int
    input_token_cap: int
    batch_token_cap: int
    batch_input_cap: int
    provider_input_cap: int
    repository_in_flight_cap: int
    query_prompt: str
    document_prompt: str
    counting_rule: str
    catalog_sha256: str


def _catalog_bytes() -> bytes:
    return resources.files("mycel").joinpath("data/embedding-models.json").read_bytes()


def _catalog(model: str) -> ModelCatalog:
    try:
        raw = _catalog_bytes()
        data = json.loads(raw)
        if data["schema_version"] != 1:
            raise ValueError("unsupported catalog")
        entry = data["models"][model]
        fields = dict(entry)
        fields["dimensions"] = tuple(fields["dimensions"])
        catalog = ModelCatalog(model=model, catalog_sha256=hashlib.sha256(raw).hexdigest(), **fields)
        positive = ("default_dimensions", "planner_version", "provider_context_tokens", "input_token_cap",
                    "batch_token_cap", "batch_input_cap", "provider_input_cap", "repository_in_flight_cap")
        if any(type(getattr(catalog, name)) is not int or getattr(catalog, name) < 1 for name in positive):
            raise ValueError("invalid limit")
        if (not catalog.dimensions or any(type(n) is not int or n < 1 for n in catalog.dimensions)
                or catalog.default_dimensions not in catalog.dimensions
                or catalog.planner_version != 1
                or catalog.input_token_cap > catalog.provider_context_tokens
                or catalog.input_token_cap > catalog.batch_token_cap
                or catalog.batch_input_cap > catalog.provider_input_cap
                or catalog.repository_in_flight_cap != 1
                or not re.fullmatch(r"[0-9a-f]{40}", catalog.tokenizer_revision)
                or not re.fullmatch(r"[0-9a-f]{64}", catalog.tokenizer_sha256)
                or Path(catalog.tokenizer_file).name != catalog.tokenizer_file
                or not catalog.tokenizer_file.endswith(".json")
                or not catalog.query_prompt or not catalog.document_prompt
                or catalog.counting_rule != "submitted-exact; planning-prompt-plus-exact-v1"):
            raise ValueError("invalid catalog")
        return catalog
    except KeyError as exc:
        if str(exc) == repr(model):
            raise MycelError(ErrorCode.SETTINGS, "The embedding model has no packaged tokenizer catalog.") from None
        raise PlanningError("The packaged embedding model catalog is invalid.") from None
    except (OSError, TypeError, ValueError):
        raise PlanningError("The packaged embedding model catalog is unavailable or invalid.") from None


def _library_digest(package) -> str:
    """Hash the installed Python/native implementation, independent of its path."""
    root = Path(package.__file__).parent
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file()
                   and "__pycache__" not in path.parts
                   and (path.suffix == ".py" or path.suffix in {".so", ".pyd", ".dll", ".dylib"}))
    if not files:
        raise PlanningError("The pinned tokenizer library cannot be verified locally.")
    try:
        for path in files:
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(path.read_bytes() + b"\0")
    except OSError:
        raise PlanningError("The pinned tokenizer library cannot be verified locally.") from None
    return digest.hexdigest()


@dataclass(frozen=True)
class ModelTokenizer:
    catalog: ModelCatalog
    library_sha256: str
    _tokenizer: object = field(repr=False, compare=False)

    def _encode(self, text: str):
        _utf8(text)
        try:
            return self._tokenizer.encode(text)
        except Exception:
            raise PlanningError("The complete embedding input cannot be tokenized reliably.") from None

    def count(self, text: str) -> int:
        return len(self._encode(text))

    def counts(self, text: str, input_type: str) -> tuple[int, int]:
        prompt = self.catalog.document_prompt if input_type == "document" else self.catalog.query_prompt
        if input_type not in {"document", "query"}:
            raise PlanningError("The embedding input type is invalid.")
        return self.count(text), self.count(prompt + text)


def load_tokenizer(model: str = "voyage-code-4", *, asset_path: Path | None = None) -> ModelTokenizer:
    """Verify local files and instantiate the official tokenizer without a Hub API.

    ``asset_path`` is an internal check seam for missing/tampered file checks; it
    is not a settings field. Its bytes must still match the immutable catalog.
    """
    catalog = _catalog(model)
    try:
        import tokenizers
    except ImportError:
        raise PlanningError("The pinned tokenizer library is missing from this Build.") from None
    if tokenizers.__version__ != catalog.tokenizers_version:
        raise PlanningError("The installed tokenizer library does not match this Build's exact version.")
    try:
        raw = (asset_path.read_bytes() if asset_path is not None
               else resources.files("mycel").joinpath("data", catalog.tokenizer_file).read_bytes())
    except OSError:
        raise PlanningError("The packaged tokenizer file is unavailable.") from None
    if hashlib.sha256(raw).hexdigest() != catalog.tokenizer_sha256:
        raise PlanningError("The packaged tokenizer file does not match its pinned digest.")
    try:
        tokenizer = tokenizers.Tokenizer.from_str(raw.decode("utf-8"))
        tokenizer.no_padding()
        tokenizer.no_truncation()
    except Exception:
        raise PlanningError("The verified tokenizer file cannot be loaded reliably.") from None
    return ModelTokenizer(catalog, _library_digest(tokenizers), tokenizer)


def _utf8(text: str) -> bytes:
    if type(text) is not str:
        raise PlanningError("Embedding text must be a complete Unicode string.")
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise PlanningError("Embedding text cannot be represented as valid UTF-8.") from None


def _place_component(text: str) -> str:
    _utf8(text)
    if not text or "\n" in text or "\r" in text or "\0" in text:
        raise PlanningError("The embedding place line requires non-empty single-line components.")
    return text


def code_place_line(path: str, symbol: str, kind: str) -> str:
    return f"{_place_component(path)} — {_place_component(symbol)} ({_place_component(kind)})"


def document_place_line(path: str, heading_path: str | Iterable[str]) -> str:
    def heading(text: str) -> str:
        _utf8(text)
        if "\n" in text or "\r" in text or "\0" in text:
            raise PlanningError("The document heading path must have single-line components.")
        return text
    headings = heading(heading_path) if isinstance(heading_path, str) else " › ".join(heading(h) for h in heading_path)
    # A preamble and an empty-title heading are valid document sections.
    return f"{_place_component(path)} › {headings}"


@dataclass(frozen=True)
class PlanProvenance:
    tokenizer_repository: str
    tokenizer_revision: str
    tokenizer_file: str
    tokenizer_sha256: str
    tokenizers_version: str
    tokenizers_library_sha256: str
    catalog_sha256: str
    planner_version: int
    counting_rule: str
    provider_context_tokens: int
    input_token_cap: int
    batch_token_cap: int
    batch_input_cap: int
    provider_input_cap: int
    repository_in_flight_cap: int
    document_prompt: str
    query_prompt: str
    padding: bool = False
    truncation: bool = False


def _provenance(tokenizer: ModelTokenizer) -> PlanProvenance:
    names = PlanProvenance.__dataclass_fields__
    values = {name: getattr(tokenizer.catalog, name) for name in names if hasattr(tokenizer.catalog, name)}
    return PlanProvenance(**values, tokenizers_library_sha256=tokenizer.library_sha256)


@dataclass(frozen=True)
class EmbeddingPart:
    order: int
    start_byte: int
    end_byte: int
    submitted_tokens: int
    planning_tokens: int
    text: str = field(repr=False)
    input_text: str = field(repr=False)


@dataclass(frozen=True)
class EmbeddingPlan:
    repository: str
    chunk_id: str
    chunk_version: str
    text_sha256: str
    model: str
    dimensions: int
    kind: str
    place_line: str
    provenance: PlanProvenance
    parts: tuple[EmbeddingPart, ...]
    text: str = field(repr=False)

    def to_dict(self) -> dict:
        """Store metadata; source text remains the chunk version's own record."""
        data = asdict(self)
        data.pop("text")
        data["parts"] = list(data["parts"])
        for part in data["parts"]:
            part.pop("text")
            part.pop("input_text")
        return data

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False).encode("utf-8")).hexdigest()


def _dimensions(tokenizer: ModelTokenizer, dimensions: int | None) -> int:
    dimension = tokenizer.catalog.default_dimensions if dimensions is None else dimensions
    if type(dimension) is not int or dimension not in tokenizer.catalog.dimensions:
        raise MycelError(ErrorCode.SETTINGS, "The embedding dimensions are not supported by the packaged model.")
    return dimension


def _boundaries(text: str, kind: str) -> list[int]:
    boundaries = []
    previous = 0
    for ending in re.finditer(r"\r\n|\r|\n", text):
        if kind == "code" or not text[previous:ending.start()].strip(" \t"):
            boundaries.append(ending.end())
        previous = ending.end()
    return boundaries


def plan_chunk(repository: str, chunk_id: str, chunk_version: str, text: str, *, place_line: str,
               kind: str, model: str = "voyage-code-4", dimensions: int | None = None,
               tokenizer: ModelTokenizer | None = None) -> EmbeddingPlan:
    tokenizer = tokenizer or load_tokenizer(model)
    if model != tokenizer.catalog.model:
        raise MycelError(ErrorCode.SETTINGS, "The embedding model and packaged tokenizer do not match.")
    dimensions = _dimensions(tokenizer, dimensions)
    for identity in (repository, chunk_id, chunk_version):
        _place_component(identity)
    _place_component(place_line)
    if kind not in {"document", "code"}:
        raise PlanningError("A chunk plan requires document or code boundary rules.")
    encoded_body = _utf8(text)
    byte_offsets = [0]
    for character in text:
        byte_offsets.append(byte_offsets[-1] + len(character.encode("utf-8")))
    boundaries = _boundaries(text, kind)
    prefix = place_line + "\n"
    counting_prefix = tokenizer.catalog.document_prompt + prefix
    cap = tokenizer.catalog.input_token_cap
    parts = []
    start = 0
    while start < len(text) or not parts:
        remaining = text[start:]
        whole = prefix + remaining
        submitted, planning = tokenizer.counts(whole, "document")
        end = len(text)
        if max(submitted, planning) > cap:
            encoding = tokenizer._encode(counting_prefix + remaining)
            covered = max((offset[1] for offset in encoding.offsets[:cap]), default=0)
            tentative = min(len(text), start + max(0, covered - len(counting_prefix)))
            end = start
            latest = bisect_right(boundaries, tentative)
            for candidate in reversed(boundaries[:latest]):
                if candidate <= start:
                    break
                counts = tokenizer.counts(prefix + text[start:candidate], "document")
                if max(counts) <= cap:
                    end, (submitted, planning) = candidate, counts
                    break
            if end == start:
                for candidate in range(tentative, start, -1):
                    counts = tokenizer.counts(prefix + text[start:candidate], "document")
                    if max(counts) <= cap:
                        end, (submitted, planning) = candidate, counts
                        break
            if end == start:
                raise PlanningError("A complete place line and the next source character cannot fit the embedding limit.")
        body = text[start:end]
        complete_input = prefix + body
        submitted, planning = tokenizer.counts(complete_input, "document")
        if max(submitted, planning) > cap:
            raise PlanningError("The complete embedding part exceeds its verified input limit.")
        parts.append(EmbeddingPart(len(parts), byte_offsets[start], byte_offsets[end], submitted, planning,
                                   body, complete_input))
        start = end
    return EmbeddingPlan(repository, chunk_id, chunk_version, hashlib.sha256(encoded_body).hexdigest(),
                         model, dimensions, kind, place_line, _provenance(tokenizer), tuple(parts), text)


@dataclass(frozen=True)
class QueryPlan:
    text: str
    model: str
    dimensions: int
    submitted_tokens: int
    planning_tokens: int
    provenance: PlanProvenance
    input_type: str = "query"
    truncation: bool = False


def plan_query(text: str, *, model: str = "voyage-code-4", dimensions: int | None = None,
               tokenizer: ModelTokenizer | None = None) -> QueryPlan:
    tokenizer = tokenizer or load_tokenizer(model)
    if model != tokenizer.catalog.model:
        raise MycelError(ErrorCode.SETTINGS, "The embedding model and packaged tokenizer do not match.")
    dimension = _dimensions(tokenizer, dimensions)
    submitted, planning = tokenizer.counts(text, "query")
    if max(submitted, planning) > tokenizer.catalog.input_token_cap:
        raise PlanningError("The complete query exceeds the embedding input limit; it cannot be truncated.")
    return QueryPlan(text, model, dimension, submitted, planning, _provenance(tokenizer))


@dataclass(frozen=True)
class BatchInput:
    repository: str
    chunk_id: str
    chunk_version: str
    part_order: int
    input_text: str
    submitted_tokens: int
    planning_tokens: int


@dataclass(frozen=True)
class EmbeddingBatch:
    repository: str
    model: str
    dimensions: int
    inputs: tuple[BatchInput, ...]
    submitted_tokens: int
    planning_tokens: int
    input_type: str = "document"
    output_dtype: str = "float"
    truncation: bool = False


def validate_plan(plan: EmbeddingPlan, tokenizer: ModelTokenizer) -> None:
    """Remeasure retained exact inputs under this Build before any submission."""
    if plan.model != tokenizer.catalog.model:
        raise PlanningError("The retained plan uses a different embedding model.")
    for name in ("tokenizer_repository", "tokenizer_revision", "tokenizer_file", "tokenizer_sha256"):
        if getattr(plan.provenance, name) != getattr(tokenizer.catalog, name):
            raise PlanningError("The retained plan's recorded tokenizer cannot be verified by this Build.")
    if (plan.provenance.tokenizers_version != tokenizer.catalog.tokenizers_version
            or plan.provenance.tokenizers_library_sha256 != tokenizer.library_sha256
            or plan.provenance.document_prompt != tokenizer.catalog.document_prompt
            or plan.provenance.query_prompt != tokenizer.catalog.query_prompt):
        raise PlanningError("The retained plan's tokenizer library or counting context cannot be verified by this Build.")
    if (plan.provenance.planner_version != 1 or plan.provenance.padding or plan.provenance.truncation
            or plan.provenance.counting_rule != tokenizer.catalog.counting_rule):
        raise PlanningError("The retained plan's counting and planner provenance cannot be verified.")
    _place_component(plan.place_line)
    for identity in (plan.repository, plan.chunk_id, plan.chunk_version):
        _place_component(identity)
    if plan.kind not in {"document", "code"}:
        raise PlanningError("The retained plan's logical chunk kind is invalid.")
    _dimensions(tokenizer, plan.dimensions)
    raw = _utf8(plan.text)
    if hashlib.sha256(raw).hexdigest() != plan.text_sha256 or not plan.parts:
        raise PlanningError("The retained plan does not match the complete chunk version.")
    offset = 0
    if not raw and len(plan.parts) != 1:
        raise PlanningError("An empty chunk must retain exactly one embedding part.")
    for order, part in enumerate(plan.parts):
        if any(type(value) is not int or value < 0 for value in
               (part.order, part.start_byte, part.end_byte, part.submitted_tokens, part.planning_tokens)):
            raise PlanningError("The retained plan's ranges or token counts are invalid.")
        body = _utf8(part.text)
        if (part.order != order or part.start_byte != offset or part.end_byte != offset + len(body)
                or (raw and not body)
                or raw[part.start_byte:part.end_byte] != body
                or part.input_text != plan.place_line + "\n" + part.text):
            raise PlanningError("The retained plan's original-text ranges or saved inputs are invalid.")
        submitted, planning = tokenizer.counts(part.input_text, "document")
        if (part.submitted_tokens, part.planning_tokens) != (submitted, planning):
            raise PlanningError("The retained plan's token counts do not match its exact inputs.")
        if max(submitted, planning) > tokenizer.catalog.input_token_cap:
            raise PlanningError("A retained embedding input exceeds this Build's verified limit.")
        offset = part.end_byte
    if offset != len(raw):
        raise PlanningError("The retained embedding plan does not cover the complete chunk version.")


def plan_batches(plans: Iterable[EmbeddingPlan], *, tokenizer: ModelTokenizer | None = None) -> tuple[EmbeddingBatch, ...]:
    """Greedy repository/identity/version/part ordering, with final local counts."""
    tokenizer = tokenizer or load_tokenizer()
    ordered = sorted(plans, key=lambda p: (p.repository, p.chunk_id, p.chunk_version))
    seen = set()
    batches = []
    inputs = []
    key = None
    submitted_total = planning_total = 0

    def finish():
        if inputs:
            batches.append(EmbeddingBatch(*key, tuple(inputs), submitted_total, planning_total))

    for plan in ordered:
        identity = (plan.repository, plan.chunk_id, plan.chunk_version)
        if identity in seen:
            raise PlanningError("A batch plan contains a duplicate chunk version.")
        seen.add(identity)
        validate_plan(plan, tokenizer)
        next_key = (plan.repository, plan.model, plan.dimensions)
        for part in plan.parts:
            submitted, planning = tokenizer.counts(part.input_text, "document")
            cap = tokenizer.catalog.batch_token_cap
            if inputs and (key != next_key or len(inputs) >= tokenizer.catalog.batch_input_cap
                           or planning_total + planning > cap or submitted_total + submitted > cap):
                finish()
                inputs = []
                submitted_total = planning_total = 0
            key = next_key
            inputs.append(BatchInput(*identity, part.order, part.input_text, submitted, planning))
            submitted_total += submitted
            planning_total += planning
    finish()
    return tuple(batches)
