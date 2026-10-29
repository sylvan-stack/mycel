# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Requirement and decision rows as entities of their own (MYC-17)."""

import unittest

REQ_A = "11111111-2222-4333-8444-555555555555"
REQ_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DEC_A = "0f2c1b4e-8a9d-4c3e-9b7a-1d2e3f4a5b6c"
CHAT = "c3d4e5f6-0718-4293-a4b5-c6d7e8f90a1b"

FIXTURE = f"""---
role: authored
spec: FIX-1
status: accepted
---
# Fixture · 1 Cellar

## Requirements

| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |
| FIX-1.2 <!-- {REQ_B} --> | log every \\| bottle | New | store |

## Decisions

| ID | Question | Proposed default | Outcome | Discussion |
|---|---|---|---|---|
| FIX-D1 <!-- {DEC_A} --> | Which cellar? | The old one | Decided 19 October 2026 by the owner: the old one | [cht:{CHAT}:Q2VsbGFy] and [cellar:cht:{CHAT}:Q2VsbGFy] |
| FIX-D2 <!-- 9c0d1e2f-3a4b-4c5d-8e6f-7a8b9c0d1e2f --> | Which bottles? | All of them | Proposed: all of them | |

## Prose

| Decision | Recorded outcome |
|---|---|
| FIX-D1 · Which cellar? | the old one |

```markdown
| FIX-1.9 <!-- 99999999-2222-4333-8444-555555555555 --> | an example inside a fence | New | unit |
```
"""


class EntityRowTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class EntityUriTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class DiscussionSettingsTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


try:
    from . import test_located_reconciliation as located_fixtures
except ImportError:
    import test_located_reconciliation as located_fixtures

import io
import json
import os
from unittest.mock import patch

from mycel._cli import run
from mycel._freshness import Deadline
from mycel._read_store import read_from_store

SPEC = f"""---
role: authored
spec: FIX-1
status: accepted
---
# Fixture · 1 Cellar

## Requirements

| ID | Mycel must… | From v1 | Verified by |
|---|---|---|---|
| FIX-1.1 <!-- {REQ_A} --> | keep the cellar cool | Kept | unit |
| FIX-1.2 <!-- {REQ_B} --> | log every bottle | New | store |

## Decisions

| ID | Question | Proposed default | Outcome | Discussion |
|---|---|---|---|---|
| FIX-D1 <!-- {DEC_A} --> | Which cellar? | The old one | Decided 19 October 2026 by the owner: the old one | [cht:{CHAT}:Q2VsbGFy] |
"""

NOTE = """# Note

## Why the old cellar

Because the owner decided so.

<!-- sources:
fixture:@artifact/spec.md#FIX-D1
-->
"""

LAYOUT = """CREATE TABLE chats (id uuid PRIMARY KEY, title text, created_at timestamptz NOT NULL);
CREATE TABLE exchanges (id uuid PRIMARY KEY, chat_id uuid NOT NULL REFERENCES chats (id), number integer NOT NULL,
  state text NOT NULL, replaced_by uuid, UNIQUE (chat_id, number));
CREATE TABLE messages (exchange_id uuid NOT NULL REFERENCES exchanges (id), position integer NOT NULL,
  role text NOT NULL, text text NOT NULL, PRIMARY KEY (exchange_id, position));
INSERT INTO chats VALUES (%s, 'Cellar', now());
INSERT INTO exchanges VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 1, 'completed', NULL);
INSERT INTO exchanges VALUES ('8f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 2, 'completed', '9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b');
INSERT INTO exchanges VALUES ('9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', %s, 3, 'completed', NULL);
INSERT INTO messages VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Which cellar?');
INSERT INTO messages VALUES ('7f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 3, 'assistant', 'The old one.');
INSERT INTO messages VALUES ('8f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Replaced message');
INSERT INTO messages VALUES ('9f3a2c1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b', 0, 'user', 'Agreed.');
"""


class EntityStoreTests(unittest.TestCase):
    """Entity rows through the real pass, the resolver and the read."""
    check_kind = "store"


    def setUp(self):
        self.base = located_fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()
        (self.base.artifact / "spec.md").write_text(SPEC, encoding="utf-8")
        self.base.commit()

    def ingest(self):
        output, diagnostic = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(self.base.config)}), \
                patch("mycel._build_identity.current_build", return_value=1), \
                patch("mycel._credentials.Credentials.require_embedding_key"), \
                patch("mycel._embed.VoyageClient"):
            status = run(["ingest", "--repo", "fixture"], stdout=output, stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(), "")
        reply = json.loads(output.getvalue())
        self.assertEqual(status, 0, reply)
        return reply

    def read(self, connection, place=None, **options):
        options.setdefault("no_fresh", True)
        options.setdefault("deadline", Deadline.after(30))
        return read_from_store(connection, self.base.settings, place, **options)

    def entity_rows(self, connection):
        return connection.execute("""SELECT c.id::text, c.kind, f.path, v.id, l.id IS NOT NULL
            FROM public.mycel_chunks c JOIN public.mycel_files f ON f.id = c.file_id
            JOIN public.mycel_chunk_versions v ON v.chunk_id = c.id
            JOIN public.mycel_locations l ON l.chunk_version = v.id AND l.kind='disk'
            WHERE c.kind IN ('req', 'dec') ORDER BY c.id, v.id""").fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
