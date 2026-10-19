"""Requirement and decision rows as chunks of their own, keyed by their UUID (MYC-17).

The pass publishes the entity rows of a captured document beside the section
chunks, in the same file transaction: one chunk per row, its identifier the
row's UUID, its exact version and its disk location. Nothing here deletes a
chunk row; collection keeps entity rows so that a withdrawn id stays reserved.
"""

from __future__ import annotations

import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from ._evidence import canonical_json, exact_comparison
from ._markdown import MarkdownDocument
from ._store import ENTITY_KINDS, search_text


def entity_details(row) -> dict:
    """The located metadata of one entity row: what the resolver and reads see."""
    return {"name": row.id, "kind": row.kind, "title": row.title,
            "span": {"start": row.byte_start, "end": row.byte_end},
            "section": row.section, "position": row.position, "entity": row.metadata()}


def publish_entities(connection, repository: str, file_id, location, captured) -> tuple[tuple[str, int], ...]:
    """Write the entity rows of one captured document for its disk location.

    Runs inside the file's transaction after its section chunks. A row that
    already exists in another file moves here: its chunk row is updated, its
    old locations were removed by that file's own rewrite. The exact version
    is reused when the row's text is unchanged, as for any chunk.
    """
    parsed = captured.parsed
    if not isinstance(parsed, MarkdownDocument) or not parsed.entities:
        return ()
    persisted = []
    for row in parsed.entities:
        if row.kind not in ENTITY_KINDS:
            continue
        raw = row.text.encode("utf-8")
        comparison = exact_comparison(raw, "code_text").as_dict()
        details = entity_details(row)
        connection.execute("INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE "
                           "SET repository=EXCLUDED.repository,file_id=EXCLUDED.file_id,kind=EXCLUDED.kind",
                           (row.uuid, repository, file_id, row.kind, Jsonb({})))
        exact = connection.execute("INSERT INTO public.mycel_chunk_versions "
            "(chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(chunk_id,snapshot_hash) DO UPDATE SET metadata=mycel_chunk_versions.metadata RETURNING id",
            (row.uuid, row.snapshot_hash, raw, search_text(raw),
             Jsonb(json.loads(canonical_json(comparison))), Jsonb(details))).fetchone()[0]
        connection.execute("INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)",
                           (uuid4(), exact, location, "disk", "disk", Jsonb(details)))
        persisted.append((row.uuid, exact))
    return tuple(persisted)
