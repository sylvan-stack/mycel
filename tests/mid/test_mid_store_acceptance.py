"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_store_acceptance as _support
from test_store_acceptance import (store)


class ProductStoreTests(_support.ProductStoreTests):


# TEST-TIER-BEGIN tests/test_store_acceptance.py::ProductStoreTests.test_migration_step_rolls_back_ddl_and_format_while_preserving_generation
    def test_migration_step_rolls_back_ddl_and_format_while_preserving_generation(self):
        with self.connection() as connection:
            before = store.require_store(connection)
            def fail(current):
                current.execute("CREATE TABLE public.mycel_migration_probe (value text)")
                current.execute("UPDATE public.mycel_store SET format=%s", (store.STORE_FORMAT + 1,))
                raise RuntimeError("deliberate public fixture migration failure")
            with self.assertRaises(RuntimeError):
                store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 1, before.index_generation,
                               {store.STORE_FORMAT: store.Migration(fail, lambda current: None)})
            self.assertEqual(connection.execute(
                "SELECT to_regclass('public.mycel_migration_probe')").fetchone(), (None,))
            after = store.require_store(connection)
            self.assertEqual((after.format, after.index_generation), (store.STORE_FORMAT, before.index_generation))
            self.error("store_format", lambda: store._migrate(connection, store.STORE_FORMAT, store.STORE_FORMAT + 1, before.index_generation, {}))
# TEST-TIER-END tests/test_store_acceptance.py::ProductStoreTests.test_migration_step_rolls_back_ddl_and_format_while_preserving_generation
