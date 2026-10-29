# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Origin Coverage over real captures and a disposable PostgreSQL store."""
import unittest

try:
    from . import test_justify as fixtures
except ImportError:
    import test_justify as fixtures


class OriginsInputTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


class OriginsStoreTests(unittest.TestCase):
    check_kind = "store"

    setUp=fixtures.UriMutationStoreTests.setUp
    ingest=fixtures.UriMutationStoreTests.ingest
    invoke=fixtures.UriMutationStoreTests.invoke

    def report(self,repository='fixture',settings=None,**options):
        from mycel._locks import snapshot_transaction
        from mycel._origins import origins_in_transaction
        from mycel._store import checked_store
        with self.base.connect() as connection,checked_store(connection),snapshot_transaction(connection):
            return origins_in_transaction(connection,settings or self.secondary,repository,**options)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
