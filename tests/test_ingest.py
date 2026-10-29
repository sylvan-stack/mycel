# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Public complete ingest against the gate's real disposable PostgreSQL."""
import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run
from mycel._settings import load_settings

try:
    from . import test_located_reconciliation as fixtures
    pass
except ImportError:
    import test_located_reconciliation as fixtures


class IngestUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class IngestStoreFixture(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize()

    def invoke(self, *args, build=1):
        output, diagnostic = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}), \
                patch('mycel._build_identity.current_build', return_value=build):
            status = run(['ingest', *args], stdout=output, stderr=diagnostic)
        self.assertEqual(diagnostic.getvalue(), '')
        return status, json.loads(output.getvalue())

    def add_repository(self, name, source, *, enabled=True):
        folder = self.base.base / name
        folder.mkdir()
        (folder / 'answer.md').write_bytes(source)
        self.base.config.write_text(self.base.config.read_text() + '\n[repos.' + name + ']\nenabled=' +
            str(enabled).lower() + '\nartifact_root=' + json.dumps(str(folder)) + '\n')
        self.base.settings = load_settings(path=self.base.config, home=self.base.base)
        return folder

    def state(self, connection):
        # Last successful observation time is allowed to advance on a quiet
        # repeat. Every actual feature/audit row, including xmin, stays exact.
        return {table: rows for table, rows in self.base.state(connection).items()
                if table != 'mycel_repository_state'}

    def physical(self):
        return {str(path.relative_to(self.base.code)): (path.read_bytes(), path.stat().st_mtime_ns,
                                                      path.stat().st_mode)
                for path in self.base.code.rglob('*') if path.is_file()}


class IngestStoreTests(IngestStoreFixture):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class IngestPublishesItsCaptureStoreTests(IngestStoreFixture):
    """A pass publishes the capture it read (MYC-1.37, MYC-D64)."""
    check_kind = "store"


    def disk_sources(self, connection):
        rows = connection.execute("""SELECT v.source_bytes FROM public.mycel_file_versions v
            JOIN public.mycel_file_locations l ON l.file_version=v.id WHERE l.kind='disk'""").fetchall()
        return sorted(bytes(row[0]) for row in rows)


class IngestStepUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class IngestStepStoreTests(unittest.TestCase):
    """One small step of a pass keeps its work for the next (SYL-286)."""
    check_kind = "store"

    setUp = IngestStoreTests.setUp
    invoke = IngestStoreTests.invoke

    def disk_text(self, connection):
        rows = connection.execute("""SELECT l.metadata->>'path',v.source_bytes FROM public.mycel_file_locations l
            JOIN public.mycel_file_versions v ON v.id=l.file_version WHERE l.kind='disk'""").fetchall()
        return {path: bytes(source) for path, source in rows}

    def edited_notes(self, count=3):
        for number in range(count):
            (self.base.artifact / f'note{number}.md').write_bytes(b'# Note\nFirst.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        for number in range(count):
            (self.base.artifact / f'note{number}.md').write_bytes(b'# Note\nSecond.\n')

    def second(self, connection):
        return sorted(path for path, source in self.disk_text(connection).items() if source == b'# Note\nSecond.\n')

    def progress(self):
        with self.base.connect() as connection:
            return connection.execute("SELECT pass_progress,last_pass_at FROM public.mycel_repository_state "
                                      "WHERE repository='fixture'").fetchone()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
