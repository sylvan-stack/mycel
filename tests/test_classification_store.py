# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Canonical complete requests through configured disposable real stores."""
import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from mycel._classification_store import ClassificationStore
from mycel._settings import load_settings

try:
    from . import test_drift_lifecycle as fixtures
except ImportError:
    import test_drift_lifecycle as fixtures


# A day ahead of the real clock: the passes of these checks observe at the real
# time, which must not follow the fixture's time; files a day older are trusted.
NOW = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
AT = NOW.isoformat()


class ClassificationStoreFixture(unittest.TestCase):
    """Shared fixture helpers; no inherited automatic methods."""
    def setUp(self):
        self.fixture = fixtures.DriftLifecycleStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def old_files(self):
        for root in (self.base.artifact, self.fixture.fixture.downstream):
            for path in root.rglob('*'):
                if path.is_file():
                    stamp = (NOW - timedelta(days=1)).timestamp()
                    os.utime(path, (stamp, stamp))

    def prepare(self, connection, *, at=AT):
        self.fixture.prepare(connection)
        self.fixture.change(connection, 1)
        self.old_files()
        drift = self.fixture.one(connection)
        source = self.fixture.reason(drift)
        result = ClassificationStore(connection).prepare(self.base.settings, drift['id'], source['id'], at=at)
        return result

    def stage_check(self, connection, prepared, stage='jev', *, at=AT):
        return ClassificationStore(connection).check(self.base.settings, prepared, stage=stage, at=at)

    def write_reviewer(self):
        command = self.base.base / 'review-adapter'
        command.write_bytes(b'#!/bin/sh\nexit 0\n')
        command.chmod(0o700)
        self.base.config.write_text(self.base.config.read_text() + '\n[drifts]\nreview_command=' +
            json.dumps([str(command), '--literal', '$HOME/*.json']) +
            '\nreview_provider="fixture-provider"\nreview_model="fixture-model-v1"\nreview_revision="fixture-adapter-v1"\n')
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        return command


class ClassificationEvidenceStoreTests(ClassificationStoreFixture):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
