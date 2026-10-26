"""Mycel's private PostgreSQL format; only explicit initialization performs DDL.

Inspection starts with PostgreSQL catalogues. Unrelated legacy-product tables
are never read, repaired, migrated or removed. Format 2 explicitly migrates the
known format-1 verification ownership only after validating all retained data.
Format 3 (19 October 2026, MYC-17) admits the chunk kinds ``req`` and ``dec``,
the requirement and decision entities keyed by their row's UUID; its step
changes no table and validates the format-2 structure before the number rises,
so that an older Build, which would read those chunks as code, refuses the store.

Feature modules own ingest, embedding, evidence retention and activity behavior.
These tables provide their shared persistence boundary without claiming those
operations are implemented. No settings, address, password or repository is
seeded here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

import psycopg

from ._errors import ErrorCode, MycelError
from ._locks import structure_guard


STORE_FORMAT = 4
REQUIRED_EXTENSIONS = frozenset({"pg_search", "vector"})
_ALLOWED_EXTENSIONS = REQUIRED_EXTENSIONS | {"plpgsql"}
_DIMENSIONS = frozenset({256, 512, 1024, 2048})
BM25_INDEX = "mycel_chunk_versions_bm25"
VECTOR_INDEX = "mycel_vectors_hnsw"

# Delimit every hex byte first: replacement cannot hit an odd-nibble `00`.
# Every pass is bounded by input length; a suffix lookahead would repeatedly
# scan the remaining bytes for dense NUL input. Only BM25 text replaces NUL.
_TEXT_PROJECTION_SQL = ("convert_from(decode(replace(replace(regexp_replace(encode(source_bytes, 'hex'::text), "
                        "'(..)'::text, '\\1:'::text, 'g'::text), '00:'::text, 'efbfbd:'::text), "
                        "':'::text, ''::text), 'hex'::text), 'UTF8'::name)")


def exact_bytes(value) -> bytes:
    """Read an authoritative BYTEA value without coercing unrelated types."""
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise MycelError("store_format", "The store has incompatible exact UTF-8 bytes.")
    return bytes(value)


def exact_text(value) -> str:
    try:
        return exact_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError:
        raise MycelError("store_format", "The store has incompatible exact UTF-8 bytes.") from None


def search_text(source: bytes) -> str:
    """A lossy BM25 field only; never evidence, public text or model input."""
    return exact_text(source).replace("\0", "\ufffd")


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool = False
    extra: str = ""

    def declaration(self, dimensions: int) -> str:
        kind = self.type.replace("$dimensions", str(dimensions))
        return f"{self.name} {kind}{'' if self.nullable else ' NOT NULL'} {self.extra}".strip()


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    table: str
    target: tuple[str, ...]
    delete: str = "CASCADE"


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    primary: tuple[str, ...]
    unique: tuple[tuple[str, ...], ...] = ()
    foreign: tuple[ForeignKey, ...] = ()
    checks: tuple[str, ...] = ()

    def sql(self, dimensions: int) -> str:
        entries = [column.declaration(dimensions) for column in self.columns]
        entries.append(f"PRIMARY KEY ({', '.join(self.primary)})")
        entries.extend(f"UNIQUE ({', '.join(columns)})" for columns in self.unique)
        entries.extend(f"FOREIGN KEY ({', '.join(key.columns)}) REFERENCES public.{key.table} "
                       f"({', '.join(key.target)}) ON DELETE {key.delete}" for key in self.foreign)
        entries.extend(f"CONSTRAINT {self.name}_check_{number} CHECK ({check})"
                       for number, check in enumerate(self.checks, 1))
        return f"CREATE TABLE public.{self.name} (\n  " + ",\n  ".join(entries) + "\n)"


def _c(name: str, kind: str, nullable: bool = False, extra: str = "") -> Column:
    return Column(name, kind, nullable, extra)


def _fk(column: str | tuple[str, ...], table: str, target: str | tuple[str, ...] = "id",
        delete: str = "CASCADE") -> ForeignKey:
    return ForeignKey((column,) if isinstance(column, str) else column, table,
                      (target,) if isinstance(target, str) else target, delete)


# Order is dependency order. JSON fields hold subject-specific, versioned state,
# never configuration snapshots or arbitrary invocation caches.
TABLES = (
    Table("mycel_store", (_c("singleton", "boolean"), _c("format", "integer"),
          _c("dimensions", "integer"), _c("index_generation", "uuid")), ("singleton",),
          checks=("singleton", "format >= 1", "dimensions = ANY (ARRAY[256, 512, 1024, 2048])")),
    Table("mycel_lock_keys", (_c("key", "bigint", extra="GENERATED ALWAYS AS IDENTITY"),
          _c("namespace", "text"), _c("identity", "text")), ("key",),
          unique=(("namespace", "identity"),), checks=("key > 0",)),
    Table("mycel_invocations", (_c("id", "uuid"), _c("liveness_key", "bigint"),
          _c("backend_pid", "integer"), _c("backend_start", "timestamp with time zone"),
          _c("index_generation", "uuid")), ("id",), unique=(("liveness_key",),),
          foreign=(_fk("liveness_key", "mycel_lock_keys", "key", "RESTRICT"),)),
    # A pass run in steps keeps how far it got in `pass_progress` (SYL-286).
    Table("mycel_repository_state", (_c("repository", "text"),
          _c("last_pass_at", "timestamp with time zone", True), _c("read_locations", "jsonb"),
          _c("pass_progress", "jsonb", True)), ("repository",)),
    # Address ownership belongs to a location. Retained branches and retargeted
    # disk roots can hold different physical files at the same portable place.
    Table("mycel_files", (_c("id", "uuid"), _c("repository", "text"), _c("root", "text"),
          _c("path", "text"), _c("corpus", "text")), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),)),
    Table("mycel_file_aliases", (_c("file_id", "uuid"), _c("root", "text"), _c("path", "text")),
          ("file_id", "root", "path"), foreign=(_fk("file_id", "mycel_files"),)),
    Table("mycel_file_versions", (_c("id", "uuid"), _c("file_id", "uuid"),
          _c("snapshot_hash", "text"), _c("source_bytes", "bytea"), _c("metadata", "jsonb")),
          ("id",), unique=(("file_id", "snapshot_hash"),),
          foreign=(_fk("file_id", "mycel_files"),),
          checks=("snapshot_hash = encode(sha256(source_bytes), 'hex'::text)",)),
    Table("mycel_file_locations", (_c("id", "uuid"), _c("file_version", "uuid"),
          _c("kind", "text"), _c("location", "text"), _c("metadata", "jsonb")), ("id",),
          unique=(("file_version", "kind", "location"),),
          foreign=(_fk("file_version", "mycel_file_versions"),),
          checks=("kind = ANY (ARRAY['disk'::text, 'branch'::text, 'stash'::text])",)),
    Table("mycel_chunks", (_c("id", "uuid"), _c("repository", "text"),
          _c("file_id", "uuid", True), _c("kind", "text"), _c("metadata", "jsonb")), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("file_id", "mycel_files"))),
    Table("mycel_chunk_versions", (_c("id", "bigint", extra="GENERATED ALWAYS AS IDENTITY"),
          _c("chunk_id", "uuid"), _c("snapshot_hash", "text"), _c("source_bytes", "bytea"), _c("text", "text"),
          _c("comparison", "jsonb"), _c("metadata", "jsonb")), ("id",),
          unique=(("chunk_id", "snapshot_hash"),), foreign=(_fk("chunk_id", "mycel_chunks"),),
          checks=("snapshot_hash = encode(sha256(source_bytes), 'hex'::text)",
                  "text = " + _TEXT_PROJECTION_SQL)),
    Table("mycel_locations", (_c("id", "uuid"), _c("chunk_version", "bigint"),
          _c("file_location", "uuid", True), _c("kind", "text"), _c("location", "text"),
          _c("metadata", "jsonb")), ("id",),
          foreign=(_fk("chunk_version", "mycel_chunk_versions"),
                   _fk("file_location", "mycel_file_locations")),
          checks=("kind = ANY (ARRAY['disk'::text, 'branch'::text, 'stash'::text, 'index'::text])",)),
    Table("mycel_embedding_plans", (_c("id", "uuid"), _c("chunk_version", "bigint"),
          _c("model", "text"), _c("dimensions", "integer"), _c("plan_hash", "text"),
          _c("place_line", "text"), _c("provenance", "jsonb"), _c("failure", "jsonb", True)),
          ("id",), unique=(("chunk_version", "model", "dimensions"),),
          foreign=(_fk("chunk_version", "mycel_chunk_versions"),)),
    Table("mycel_embedding_parts", (_c("plan_id", "uuid"), _c("part_order", "integer"),
          _c("byte_start", "bigint"), _c("byte_end", "bigint"), _c("input_bytes", "bytea"),
          _c("submitted_tokens", "integer"), _c("planning_tokens", "integer"),
          _c("failure", "jsonb", True)), ("plan_id", "part_order"),
          foreign=(_fk("plan_id", "mycel_embedding_plans"),),
          checks=("part_order >= 0", "byte_start >= 0 AND byte_end >= byte_start",
                  "submitted_tokens >= 0 AND planning_tokens >= 0")),
    Table("mycel_vectors", (_c("plan_id", "uuid"), _c("part_order", "integer"),
          _c("model", "text"), _c("dimensions", "integer"),
          _c("embedding", "vector($dimensions)")), ("plan_id", "part_order"),
          foreign=(_fk(("plan_id", "part_order"), "mycel_embedding_parts", ("plan_id", "part_order")),)),
    # Returned results survive a nonblocking publication conflict. There is no
    # deletable version/part foreign key: publication alone decides which exact
    # versions still exist. Receipts are private, never searchable coverage.
    Table("mycel_embedding_receipts", (_c("id", "uuid"), _c("repository", "text"),
          _c("model", "text"), _c("dimensions", "integer"), _c("payload", "bytea"),
          _c("created_at", "timestamp with time zone", extra="DEFAULT clock_timestamp()")),
          ("id",), checks=("dimensions = ANY (ARRAY[256, 512, 1024, 2048])",)),
    Table("mycel_snapshots", (_c("repository", "text"), _c("hash", "text"),
          _c("bytes", "bytea"), _c("metadata", "jsonb")), ("repository", "hash"),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),),
          checks=("hash = encode(sha256(bytes), 'hex'::text)",)),
    Table("mycel_manifests", (_c("repository", "text"), _c("hash", "text"),
          _c("kind", "text"), _c("bytes", "bytea"), _c("metadata", "jsonb")),
          ("repository", "hash"), foreign=(_fk("repository", "mycel_repository_state", "repository"),),
          checks=("hash = encode(sha256(bytes), 'hex'::text)",)),
    Table("mycel_evidence_owners", (_c("id", "uuid"), _c("repository", "text"),
          _c("kind", "text"), _c("identity", "text"), _c("invocation", "uuid", True)),
          ("id",), unique=(("id", "repository"), ("repository", "kind", "identity")),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("invocation", "mycel_invocations", delete="RESTRICT"))),
    Table("mycel_evidence_references", (_c("owner", "uuid"), _c("repository", "text"),
          _c("snapshot_hash", "text", True), _c("manifest_hash", "text", True),
          _c("ordinal", "integer")), ("owner", "ordinal"),
          foreign=(_fk(("owner", "repository"), "mycel_evidence_owners", ("id", "repository")),
                   _fk(("repository", "snapshot_hash"), "mycel_snapshots", ("repository", "hash"), "RESTRICT"),
                   _fk(("repository", "manifest_hash"), "mycel_manifests", ("repository", "hash"), "RESTRICT")),
          checks=("(snapshot_hash IS NULL) <> (manifest_hash IS NULL)",)),
    Table("mycel_dependencies", (_c("id", "uuid"), _c("repository", "text"),
          _c("dependant_version", "bigint"), _c("declaration", "text"), _c("source_place", "text"),
          _c("kind", "text"), _c("state", "jsonb"), _c("baseline_owner", "uuid", True)), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("dependant_version", "mycel_chunk_versions"),
                   _fk("baseline_owner", "mycel_evidence_owners", delete="RESTRICT"))),
    Table("mycel_edges", (_c("dependency", "uuid"), _c("source_version", "bigint")),
          ("dependency", "source_version"), foreign=(_fk("dependency", "mycel_dependencies"),
                   _fk("source_version", "mycel_chunk_versions"))),
    Table("mycel_relations", (_c("id", "uuid"), _c("repository", "text"),
          _c("left_version", "bigint"), _c("right_place", "text"), _c("state", "jsonb"),
          _c("baseline_owner", "uuid", True)), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("left_version", "mycel_chunk_versions"),
                   _fk("baseline_owner", "mycel_evidence_owners", delete="RESTRICT"))),
    Table("mycel_ref_faults", (_c("id", "uuid"), _c("repository", "text"),
          _c("chunk_version", "bigint"), _c("declaration", "text"), _c("fault", "jsonb")), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("chunk_version", "mycel_chunk_versions"))),
    Table("mycel_stale_reasons", (_c("id", "uuid"), _c("repository", "text"),
          _c("chunk_version", "bigint"), _c("dependency", "uuid", True), _c("reason", "jsonb")),
          ("id",), foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("chunk_version", "mycel_chunk_versions"), _fk("dependency", "mycel_dependencies"))),
    Table("mycel_drifts", (_c("id", "uuid"), _c("repository", "text"),
          _c("dependant_version", "bigint", True), _c("opened_at", "timestamp with time zone"),
          _c("closed_at", "timestamp with time zone", True), _c("state", "jsonb"),
          _c("evidence_owner", "uuid")), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("dependant_version", "mycel_chunk_versions", delete="SET NULL"),
                   _fk("evidence_owner", "mycel_evidence_owners", delete="RESTRICT"))),
    Table("mycel_classification_work", (_c("id", "uuid"), _c("repository", "text"),
          _c("dependency", "uuid"), _c("quiet_until", "timestamp with time zone", True),
          _c("state", "jsonb"), _c("evidence_owner", "uuid", True)), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("dependency", "mycel_dependencies"),
                   _fk("evidence_owner", "mycel_evidence_owners", delete="RESTRICT"))),
    Table("mycel_verifications", (_c("id", "uuid"), _c("repository", "text"),
          _c("chunk_id", "uuid"), _c("recorded_at", "timestamp with time zone"),
          _c("record", "jsonb"), _c("evidence_owner", "uuid")), ("id",),
          foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("chunk_id", "mycel_chunks"),
                   _fk("evidence_owner", "mycel_evidence_owners", delete="RESTRICT"))),
    Table("mycel_generated_state", (_c("chunk_id", "uuid"), _c("repository", "text"),
          _c("kind", "text"), _c("state", "jsonb")), ("chunk_id",),
          foreign=(_fk("chunk_id", "mycel_chunks"),
                   _fk("repository", "mycel_repository_state", "repository"))),
    Table("mycel_activity", (_c("id", "bigint", extra="GENERATED ALWAYS AS IDENTITY"),
          _c("repository", "text", True), _c("invocation", "uuid"), _c("index_generation", "uuid"),
          _c("kind", "text"), _c("trigger", "text"), _c("build", "integer"),
          _c("started_at", "timestamp with time zone"), _c("ended_at", "timestamp with time zone", True),
          _c("outcome", "text", True), _c("counts", "jsonb"), _c("error", "jsonb", True)),
          ("id",), foreign=(_fk("repository", "mycel_repository_state", "repository"),
                   _fk("invocation", "mycel_invocations", delete="RESTRICT")),
          checks=("outcome IS NULL OR outcome = ANY (ARRAY['done'::text, 'refused'::text, 'failed'::text, 'stopped'::text])",)),
    Table("mycel_activity_files", (_c("activity", "bigint"), _c("ordinal", "integer"),
          _c("root", "text"), _c("path", "text"), _c("location", "text"),
          _c("change", "text")), ("activity", "ordinal"), foreign=(_fk("activity", "mycel_activity"),)),
    Table("mycel_identity_decisions", (_c("activity", "bigint"), _c("ordinal", "integer"),
          _c("root", "text"), _c("path", "text"), _c("location", "text"),
          _c("chunk_id", "uuid"), _c("decision", "text"), _c("old_name", "text", True),
          _c("new_name", "text", True)), ("activity", "ordinal"),
          foreign=(_fk("activity", "mycel_activity"),)),
    # Activity keeps references only. Its pruning must neither own nor delete
    # the separately retained classification evidence and judgement bundles.
    Table("mycel_activity_classifications", (_c("activity", "bigint"), _c("ordinal", "integer"),
          _c("bundle", "text"), _c("dependant", "text"), _c("outcome", "text")),
          ("activity", "ordinal"), foreign=(_fk("activity", "mycel_activity"),)),
)
_TABLE_MAP = MappingProxyType({table.name: table for table in TABLES})
_SEQUENCES = frozenset(f"{table.name}_{column.name}_seq" for table in TABLES for column in table.columns
                       if "IDENTITY" in column.extra)


@dataclass(frozen=True)
class StoreInspection:
    state: str
    format: int | None = None
    dimensions: int | None = None
    index_generation: str | None = None
    reason: str | None = None
    extensions: tuple[str, ...] = ()

    def diagnostic(self) -> dict[str, Any]:
        result = {"state": self.state, "format": self.format, "dimensions": self.dimensions,
                  "indexGeneration": self.index_generation}
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class InitResult:
    before: StoreInspection
    after: StoreInspection
    changed: bool
    vectors_removed: int = 0

    def reply(self, address: str) -> dict[str, Any]:
        """The caller supplies the validated, password-free configured address."""
        return {"store": address, "format": {"before": self.before.format, "after": self.after.format},
                "dimensions": {"before": self.before.dimensions, "after": self.after.dimensions},
                "indexGeneration": self.after.index_generation, "changed": self.changed,
                "vectorsRemoved": self.vectors_removed}


@dataclass(frozen=True)
class Migration:
    """One future format step, validated before its version is committed."""

    apply: Callable[[Any], None]
    validate: Callable[[Any], None]


# The predecessors are exact and bounded: no older inspection grants permission
# to reinterpret arbitrary records or accept a damaged catalogue. Formats 2 and
# 3 share one structure; format 4 adds the repository's step progress.
_FORMAT_3_TABLES = tuple(Table("mycel_repository_state", (_c("repository", "text"),
    _c("last_pass_at", "timestamp with time zone", True), _c("read_locations", "jsonb")), ("repository",))
    if table.name == "mycel_repository_state" else table for table in TABLES)
_FORMAT_1_TABLES = tuple(Table("mycel_verifications", (
    _c("id", "uuid"), _c("repository", "text"), _c("chunk_version", "bigint"),
    _c("recorded_at", "timestamp with time zone"), _c("record", "jsonb"),
    _c("evidence_owner", "uuid")), ("id",), foreign=(
        _fk("repository", "mycel_repository_state", "repository"),
        _fk("chunk_version", "mycel_chunk_versions"),
        _fk("evidence_owner", "mycel_evidence_owners", delete="RESTRICT")))
    if table.name == "mycel_verifications" else table for table in _FORMAT_3_TABLES)

_RELATIONS_SQL = """SELECT n.nspname, c.relname, c.relkind
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
AND n.nspname NOT LIKE 'pg_temp_%' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d
 WHERE d.classid = 'pg_catalog.pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
ORDER BY n.nspname, c.relname"""
_COLUMNS_SQL = """SELECT n.nspname, c.relname, a.attname,
pg_catalog.format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, a.attidentity
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum"""
_CONSTRAINTS_SQL = """SELECT n.nspname, c.relname, k.contype,
ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY x(num, ord)
 JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = x.num ORDER BY x.ord),
tn.nspname, tc.relname,
ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY x(num, ord)
 JOIN pg_catalog.pg_attribute a ON a.attrelid = tc.oid AND a.attnum = x.num ORDER BY x.ord),
k.confdeltype, k.convalidated
FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_class tc ON tc.oid = k.confrelid
LEFT JOIN pg_catalog.pg_namespace tn ON tn.oid = tc.relnamespace
WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND k.contype IN ('p', 'u', 'f')"""
_INDEXES_SQL = """SELECT n.nspname, i.relname, tn.nspname, t.relname, am.amname,
x.indisvalid, x.indisready, pg_catalog.pg_get_indexdef(i.oid), i.reloptions
FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid
JOIN pg_catalog.pg_namespace n ON n.oid = i.relnamespace
JOIN pg_catalog.pg_class t ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace tn ON tn.oid = t.relnamespace
JOIN pg_catalog.pg_am am ON am.oid = i.relam
WHERE n.nspname = 'public' AND i.relname = ANY(%s)"""
_CHECKS_SQL = """SELECT n.nspname, c.relname, k.conname,
pg_catalog.pg_get_expr(k.conbin, k.conrelid), k.convalidated
FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND k.contype = 'c'"""


def _dimensions(value: Any) -> int:
    if type(value) is not int or value not in _DIMENSIONS:
        raise MycelError(ErrorCode.SETTINGS, "The store dimensions must be a supported model dimension.")
    return value


@contextmanager
def _transaction(connection, *, readonly: bool = False) -> Iterator[None]:
    # Native connections enter here in autocommit mode. A transaction/savepoint
    # preserves the caller's connection and rolls back every failed DDL step.
    with connection.transaction():
        if readonly:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path = pg_catalog, public")
        connection.execute("SET LOCAL lock_timeout = '1ms'")
        connection.execute("SET LOCAL statement_timeout = '5000ms'")
        yield


def _normalized(sql: str) -> str:
    # PostgreSQL's deparser adds parentheses around cast operands and omits
    # quotes around simple extension reloption strings. Compare the released
    # expression tokens rather than that presentation detail.
    return re.sub(r"[\s()'\"]+", "", sql.replace("public.", "")).lower().rstrip(";")


def _normalized_check(expression: str) -> str:
    # Preserve string literals: a forged case-sensitive constant is a different
    # constraint even when PostgreSQL's presentation adds parentheses/casts.
    return "".join(part if number % 2 else re.sub(r'[\s()"]+', '', part).lower()
                   for number, part in enumerate(re.split(r"('(?:''|[^'])*')", expression)))


def _expected_checks(tables=TABLES) -> set[tuple[str, str, str, bool]]:
    return {(table.name, f"{table.name}_check_{number}", _normalized_check(check), True)
            for table in tables for number, check in enumerate(table.checks, 1)}


def _bm25_sql() -> str:
    # ParadeDB v0.24.1's released expression/tokenizer API, not a historical
    # paradedb.create_bm25 procedure. See its tagged create_index.sql benchmark.
    return (f"CREATE INDEX {BM25_INDEX} ON public.mycel_chunk_versions USING bm25 "
            "(id, (text::pdb.unicode_words)) WITH (key_field = 'id')")


def _vector_sql(dimensions: int) -> str:
    # pgvector's vector HNSW limit is 2,000 dimensions. At 2,048 the index casts
    # to halfvec, but the stored vector remains full float precision. Retrieval
    # must use the expression for candidates, then rerank with full vectors.
    column = "embedding vector_cosine_ops" if dimensions <= 2000 else \
             f"(embedding::halfvec({dimensions})) halfvec_cosine_ops"
    return f"CREATE INDEX {VECTOR_INDEX} ON public.mycel_vectors USING hnsw ({column})"


def _expected_columns(dimensions: int, tables=TABLES) -> dict[str, dict[str, tuple[str, bool, str]]]:
    return {table.name: {column.name: (column.type.replace("$dimensions", str(dimensions)),
                                     column.nullable, "a" if "IDENTITY" in column.extra else "")
                         for column in table.columns} for table in tables}


def _expected_constraints(tables=TABLES) -> set[tuple[Any, ...]]:
    result = set()
    actions = {"CASCADE": "c", "RESTRICT": "r", "SET NULL": "n"}
    for table in tables:
        result.add((table.name, "p", table.primary, None, None, (), " ", True))
        result.update((table.name, "u", columns, None, None, (), " ", True) for columns in table.unique)
        result.update((table.name, "f", key.columns, "public", key.table, key.target,
                       actions[key.delete], True) for key in table.foreign)
    return result


def _shape_fault(connection, dimensions: int, definitions=TABLES) -> str | None:
    tables = [table.name for table in definitions]
    actual: dict[str, dict[str, tuple[str, bool, str]]] = {}
    for namespace, table, name, kind, nullable, identity in connection.execute(_COLUMNS_SQL, (tables,)).fetchall():
        actual.setdefault(table, {})[name] = (kind, nullable, identity)
    if actual != _expected_columns(dimensions, definitions):
        return "The index has missing or incompatible columns."
    constraints = {(table, kind, tuple(columns), target_namespace, target_table, tuple(target_columns),
                    action, valid) for namespace, table, kind, columns, target_namespace, target_table,
                    target_columns, action, valid in connection.execute(_CONSTRAINTS_SQL, (tables,)).fetchall()}
    if constraints != _expected_constraints(definitions):
        return "The index has missing or incompatible integrity constraints."
    checks = {(table, name, _normalized_check(expression), valid)
              for namespace, table, name, expression, valid in connection.execute(_CHECKS_SQL, (tables,)).fetchall()}
    if checks != _expected_checks(definitions):
        return "The index has missing, invalid or incompatible check constraints."
    indexes = {row[1]: row for row in connection.execute(_INDEXES_SQL, ([BM25_INDEX, VECTOR_INDEX],)).fetchall()}
    for name, table, method, expected in ((BM25_INDEX, "mycel_chunk_versions", "bm25", _bm25_sql()),
                                        (VECTOR_INDEX, "mycel_vectors", "hnsw", _vector_sql(dimensions))):
        row = indexes.get(name)
        if row is None or row[:1] != ("public",) or row[2:7] != ("public", table, method, True, True) \
                or _normalized(row[7]) != _normalized(expected):
            return "The index has a missing, invalid or incompatible search index."
    return None


def _migrate_verification_lifetime(connection) -> None:
    """Validate every old binding before replacing exact-row ownership."""
    metadata = connection.execute("SELECT singleton, format, dimensions, index_generation "
                                  "FROM public.mycel_store").fetchall()
    if len(metadata) != 1 or metadata[0][0] is not True or metadata[0][1] != 1:
        raise MycelError("store_format", "The verification migration requires store format 1.")
    relations = connection.execute(_RELATIONS_SQL).fetchall()
    if ({name for namespace, name, kind in relations if namespace == "public" and kind == "r"}
            != set(_TABLE_MAP) or any(namespace != "public" or kind not in {"r", "S"}
                                     for namespace, _, kind in relations)
            or {name for _, name, kind in relations if kind == "S"} != _SEQUENCES
            or _shape_fault(connection, metadata[0][2], _FORMAT_1_TABLES) is not None):
        raise MycelError("store_format", "The verification migration found an incompatible predecessor catalogue.")
    from ._verification_reader import validate_verification_record
    from ._evidence import EvidenceError
    rows = connection.execute("""SELECT r.id,r.repository,c.id,r.recorded_at,r.record,r.evidence_owner,
        v.id,c.id,c.repository,v.snapshot_hash,v.source_bytes,v.comparison
        FROM public.mycel_verifications r
        LEFT JOIN public.mycel_chunk_versions v ON v.id=r.chunk_version
        LEFT JOIN public.mycel_chunks c ON c.id=v.chunk_id ORDER BY r.id""").fetchall()
    for row in rows:
        if row[2] is None:
            raise MycelError("store_format", "A verification has no exact predecessor version.")
        try:
            validate_verification_record(connection, row[:6], legacy_version=row[6:])
        except EvidenceError:
            raise MycelError("store_format", "A predecessor verification has unavailable or corrupt evidence.") from None
    connection.execute("ALTER TABLE public.mycel_verifications ADD COLUMN chunk_id uuid")
    connection.execute("""UPDATE public.mycel_verifications r SET chunk_id=v.chunk_id
        FROM public.mycel_chunk_versions v WHERE v.id=r.chunk_version""")
    connection.execute("ALTER TABLE public.mycel_verifications ALTER COLUMN chunk_id SET NOT NULL")
    connection.execute("""ALTER TABLE public.mycel_verifications ADD FOREIGN KEY (chunk_id)
        REFERENCES public.mycel_chunks (id) ON DELETE CASCADE""")
    connection.execute("ALTER TABLE public.mycel_verifications DROP COLUMN chunk_version")


def _validate_verification_lifetime(connection) -> None:
    dimensions = connection.execute("SELECT dimensions FROM public.mycel_store").fetchone()[0]
    fault = _shape_fault(connection, dimensions, _FORMAT_3_TABLES)
    if fault is not None:
        raise MycelError("store_format", fault)
    from ._verification_reader import validate_verification_record
    from ._evidence import EvidenceError
    rows = connection.execute("""SELECT id,repository,chunk_id,recorded_at,record,evidence_owner
        FROM public.mycel_verifications ORDER BY id""").fetchall()
    for row in rows:
        try:
            validate_verification_record(connection, row)
        except EvidenceError:
            raise MycelError("store_format", "A migrated verification has unavailable or corrupt evidence.") from None


ENTITY_KINDS = frozenset({"req", "dec"})


def _migrate_entity_kinds(connection) -> None:
    """Format 2 to 3: the structure is unchanged; only the reading rules are new."""
    metadata = connection.execute("SELECT singleton, format FROM public.mycel_store").fetchall()
    if len(metadata) != 1 or metadata[0][0] is not True or metadata[0][1] != 2:
        raise MycelError("store_format", "The entity migration requires store format 2.")
    dimensions = connection.execute("SELECT dimensions FROM public.mycel_store").fetchone()[0]
    fault = _shape_fault(connection, dimensions, _FORMAT_3_TABLES)
    if fault is not None:
        raise MycelError("store_format", "The entity migration found an incompatible predecessor catalogue.")
    kinds = connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE kind = ANY(%s)",
                               (sorted(ENTITY_KINDS),)).fetchone()[0]
    if kinds:
        raise MycelError("store_format", "A format 2 store cannot already hold entity chunks.")


def _validate_entity_kinds(connection) -> None:
    dimensions = connection.execute("SELECT dimensions FROM public.mycel_store").fetchone()[0]
    fault = _shape_fault(connection, dimensions, _FORMAT_3_TABLES)
    if fault is not None:
        raise MycelError("store_format", fault)


def _migrate_pass_progress(connection) -> None:
    """Format 3 to 4: an empty step progress column; no record is reinterpreted."""
    metadata = connection.execute("SELECT singleton, format, dimensions FROM public.mycel_store").fetchall()
    if len(metadata) != 1 or metadata[0][0] is not True or metadata[0][1] != 3:
        raise MycelError("store_format", "The step progress migration requires store format 3.")
    if _shape_fault(connection, metadata[0][2], _FORMAT_3_TABLES) is not None:
        raise MycelError("store_format", "The step progress migration found an incompatible predecessor catalogue.")
    connection.execute("ALTER TABLE public.mycel_repository_state ADD COLUMN pass_progress jsonb")


def _validate_pass_progress(connection) -> None:
    dimensions = connection.execute("SELECT dimensions FROM public.mycel_store").fetchone()[0]
    fault = _shape_fault(connection, dimensions)
    if fault is not None:
        raise MycelError("store_format", fault)


MIGRATIONS: Mapping[int, Migration] = MappingProxyType({
    1: Migration(_migrate_verification_lifetime, _validate_verification_lifetime),
    2: Migration(_migrate_entity_kinds, _validate_entity_kinds),
    3: Migration(_migrate_pass_progress, _validate_pass_progress),
})


def _inspect(connection, build_format: int = STORE_FORMAT) -> StoreInspection:
    extensions = tuple(row[0] for row in connection.execute(
        "SELECT extname FROM pg_catalog.pg_extension ORDER BY extname").fetchall())
    relations = connection.execute(_RELATIONS_SQL).fetchall()
    foreign = [(namespace, name) for namespace, name, kind in relations
               if namespace != "public" or (kind == "r" and name not in _TABLE_MAP)
               or (kind == "S" and name not in _SEQUENCES) or kind not in {"r", "S"}]
    foreign_extensions = set(extensions) - _ALLOWED_EXTENSIONS
    # Future Mycel formats may add relations this Build cannot understand.
    # Their correctly typed format record can diagnose "newer"; no unknown
    # table is read or accepted. Unrelated/v1 names stop at catalogues alone.
    future_relations = bool(foreign) and all(namespace == "public" and name.startswith("mycel_")
                                            and name not in _TABLE_MAP and name not in _SEQUENCES
                                            for namespace, name in foreign)
    if foreign_extensions or (foreign and not future_relations):
        return StoreInspection("foreign", reason="The database contains objects that do not belong to Mycel.",
                               extensions=extensions)
    if not relations:
        return StoreInspection("empty", extensions=extensions)
    relation_names = {name for namespace, name, kind in relations if kind == "r"}
    if "mycel_store" not in relation_names:
        return StoreInspection("damaged", reason="The index format record is missing.", extensions=extensions)
    # Only a correctly typed metadata table is eligible for a data read.
    metadata_columns = {name: (kind, nullable, identity)
                        for namespace, table, name, kind, nullable, identity in connection.execute(
                            _COLUMNS_SQL, (["mycel_store"],)).fetchall()}
    if metadata_columns != _expected_columns(1024)["mycel_store"]:
        return StoreInspection("damaged", reason="The index format record has an incompatible shape.",
                               extensions=extensions)
    try:
        rows = connection.execute("SELECT singleton, format, dimensions, index_generation FROM public.mycel_store").fetchall()
        if len(rows) != 1:
            raise ValueError()
        singleton, number, dimensions, generation = rows[0]
        if singleton is not True or type(number) is not int or number < 1 or type(dimensions) is not int \
                or dimensions not in _DIMENSIONS:
            raise ValueError()
        generation = str(UUID(str(generation)))
    except (psycopg.Error, ValueError, TypeError, AttributeError):
        return StoreInspection("damaged", reason="The index format record is unreadable or invalid.",
                               extensions=extensions)
    state = "older" if number < build_format else "newer" if number > build_format else "current"
    result = StoreInspection(state, number, dimensions, generation, extensions=extensions)
    if foreign and state != "newer":
        return StoreInspection("foreign", reason="The database contains objects that do not belong to Mycel.",
                               extensions=extensions)
    if state != "current":
        return result
    if relation_names != set(_TABLE_MAP) or {name for _, name, kind in relations if kind == "S"} != _SEQUENCES:
        return StoreInspection("damaged", number, dimensions, generation,
                               "The index has missing structural records.", extensions)
    if not REQUIRED_EXTENSIONS.issubset(extensions):
        return StoreInspection("damaged", number, dimensions, generation,
                               "The index is missing required pg_search or vector extensions.", extensions)
    fault = _shape_fault(connection, dimensions)
    return result if fault is None else StoreInspection("damaged", number, dimensions, generation, fault, extensions)


def inspect_store(connection) -> StoreInspection:
    """Read a consistent diagnostic, including empty, foreign and newer stores."""
    try:
        with _transaction(connection, readonly=True):
            return _inspect(connection)
    except psycopg.Error:
        raise MycelError(ErrorCode.STORE_UNAVAILABLE, "The index store could not be inspected.") from None


def require_store(connection, *, dimensions: int | None = None, operation: str = "read") -> StoreInspection:
    """Validate without DDL. Hold structure_guard around the whole operation.

    Retrieval accepts a dimension mismatch and chooses wording-only search;
    callers compare the returned dimension and explain that fallback. Embed
    refuses it before acquiring any provider credential.
    """
    if dimensions is not None:
        _dimensions(dimensions)
    inspection = inspect_store(connection)
    if inspection.state != "current":
        found = "none" if inspection.format is None else str(inspection.format)
        reason = inspection.reason or f"The store format is {found}; this Build reads format {STORE_FORMAT}."
        raise MycelError(ErrorCode.STORE_FORMAT, reason)
    if operation == "embed" and dimensions is not None and dimensions != inspection.dimensions:
        raise MycelError(ErrorCode.STORE_FORMAT,
                         f"The store has {inspection.dimensions} dimensions; settings request {dimensions}. Run mycel init.")
    return inspection


@contextmanager
def checked_store(connection, *, dimensions: int | None = None, operation: str = "read") -> Iterator[StoreInspection]:
    """Keep the nonblocking shared structure lock until the operation ends."""
    with structure_guard(connection):
        yield require_store(connection, dimensions=dimensions, operation=operation)


def _initialization_refusal(inspection: StoreInspection, build_format: int) -> None:
    if inspection.state == "foreign":
        raise MycelError(ErrorCode.REFUSED, inspection.reason)
    if inspection.state in {"newer", "damaged"}:
        reason = inspection.reason or f"The store format is {inspection.format}; this Build reads format {build_format}."
        raise MycelError(ErrorCode.STORE_FORMAT, reason)


def _create(connection, dimensions: int) -> str:
    available = {row[0] for row in connection.execute(
        "SELECT name FROM pg_catalog.pg_available_extensions").fetchall()}
    missing = sorted(REQUIRED_EXTENSIONS - available)
    if missing:
        raise MycelError(ErrorCode.REFUSED, "The server is missing required extensions: " + ", ".join(missing) + ".")
    generation = str(uuid4())
    for extension in sorted(REQUIRED_EXTENSIONS):
        connection.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
    for table in TABLES:
        connection.execute(table.sql(dimensions))
    connection.execute(_bm25_sql())
    connection.execute(_vector_sql(dimensions))
    connection.execute("INSERT INTO public.mycel_store (singleton, format, dimensions, index_generation) "
                       "VALUES (true, %s, %s, %s)", (STORE_FORMAT, dimensions, UUID(generation)))
    return generation


def _migrate(connection, start: int, finish: int, generation: str, migrations: Mapping[int, Migration]) -> None:
    # Reject a missing path before committing any prefix of that path.
    if any(number not in migrations for number in range(start, finish)):
        raise MycelError(ErrorCode.STORE_FORMAT,
                         f"No complete migration path exists from store format {start} to {finish}.")
    for number in range(start, finish):
        step = migrations[number]
        with _transaction(connection):
            step.apply(connection)
            step.validate(connection)
            rows = connection.execute("SELECT index_generation FROM public.mycel_store").fetchall()
            if rows != [(UUID(generation),)] and rows != [(generation,)]:
                raise MycelError(ErrorCode.INTERNAL, "A migration changed the index generation.")
            connection.execute("UPDATE public.mycel_store SET format = %s WHERE singleton = true", (number + 1,))


def _change_dimensions(connection, dimensions: int) -> int:
    count = connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0]
    connection.execute("DELETE FROM public.mycel_vectors")
    connection.execute("DELETE FROM public.mycel_embedding_receipts")
    connection.execute(f"DROP INDEX public.{VECTOR_INDEX}")
    connection.execute(f"ALTER TABLE public.mycel_vectors ALTER COLUMN embedding TYPE vector({dimensions})")
    connection.execute(_vector_sql(dimensions))
    connection.execute("UPDATE public.mycel_store SET dimensions = %s WHERE singleton = true", (dimensions,))
    return count


def initialize_store(connection, *, dimensions: int, build: int | None = None,
                     address: str | None = None) -> InitResult:
    """Make/change the schema explicitly; a compatible store is a true no-op.

    Installed commands supply their immutable Build identity and exact reply
    address. Unnumbered development/fixture callers keep the schema-only API.
    """
    dimensions = _dimensions(dimensions)
    if build is not None and (type(build) is not int or build <= 0 or not isinstance(address, str)):
        raise MycelError("internal", "Initialization requires a valid Build and reply address.")
    try:
        # A no-op is compatible with ordinary shared operations, but must still
        # refuse an active exclusive initialization immediately.
        with structure_guard(connection):
            before = inspect_store(connection)
            _initialization_refusal(before, STORE_FORMAT)
            if before.state == "current" and before.dimensions == dimensions:
                return InitResult(before, before, False)
        with structure_guard(connection, exclusive=True):
            # Recheck after obtaining the session lock: another initializer may
            # have completed between our diagnostic snapshot and lock attempt.
            before = inspect_store(connection)
            _initialization_refusal(before, STORE_FORMAT)
            if before.state == "current" and before.dimensions == dimensions:
                return InitResult(before, before, False)
            if before.state == "empty":
                with ExitStack() as guards:
                    with _transaction(connection):
                        _create(connection, dimensions)
                        after = _inspect(connection)
                        if after.state != "current":
                            raise MycelError(ErrorCode.INTERNAL, "The new store failed its structural validation.")
                        result = InitResult(before, after, True)
                        if build is not None:
                            from ._locks import bootstrap_invocation_guard
                            from ._activity import record_initialization, _audit_failure
                            try:
                                invocation = guards.enter_context(bootstrap_invocation_guard(connection))
                            except (psycopg.Error, MycelError):
                                raise _audit_failure() from None
                            record_initialization(connection, invocation, build=build, counts=result.reply(address))
                return result
            removed = 0
            with ExitStack() as guards:
                invocation = None
                if build is not None:
                    from ._locks import invocation_guard
                    invocation = guards.enter_context(invocation_guard(connection))
                with _transaction(connection):
                    if before.state == "older":
                        _migrate(connection, before.format, STORE_FORMAT, before.index_generation, MIGRATIONS)
                    current = _inspect(connection)
                    if current.state != "current":
                        raise MycelError(ErrorCode.STORE_FORMAT, "The migrated store has an incompatible structure.")
                    if current.dimensions != dimensions:
                        removed = _change_dimensions(connection, dimensions)
                    after = _inspect(connection)
                    if after.state != "current" or after.index_generation != before.index_generation:
                        raise MycelError(ErrorCode.INTERNAL, "The changed store failed its structural validation.")
                    result = InitResult(before, after, True, removed)
                    if invocation is not None:
                        from ._activity import record_initialization
                        record_initialization(connection, invocation, build=build, counts=result.reply(address))
            return result
    except psycopg.errors.LockNotAvailable:
        raise MycelError(ErrorCode.BUSY, "The index structure is in use by another invocation.") from None
    except psycopg.OperationalError:
        raise MycelError(ErrorCode.STORE_UNAVAILABLE, "The index store connection was lost.") from None
    except psycopg.Error:
        raise MycelError(ErrorCode.REFUSED, "The server refused the required index structure change.") from None
