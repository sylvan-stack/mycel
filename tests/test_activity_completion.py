# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Complete injected mutation accounting on configured disposable stores."""

import unittest

from psycopg.types.json import Jsonb

from mycel import _activity as activity


class ActivityCompletionStoreTests(unittest.TestCase):
    check_kind = "store"

    def connect(self):
        return self.store_fixture.backend.connection(self.store_fixture.database)

    def seed(self, connection):
        connection.execute("INSERT INTO public.mycel_repository_state(repository,read_locations) "
                           "VALUES ('fixture','{}'),('unchanged','{}')")

    def write(self, counts, **details):
        def callback(connection):
            connection.execute("UPDATE public.mycel_repository_state SET read_locations=%s "
                               "WHERE repository='fixture'", (Jsonb(counts),))
            return activity.AppliedMutation(True, counts, **details)
        return callback

    def rows(self, connection):
        return connection.execute('SELECT id,repository,kind,outcome,counts '
                                  'FROM public.mycel_activity ORDER BY id').fetchall()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
