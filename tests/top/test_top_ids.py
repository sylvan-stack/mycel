"""Check the durable identifier contract on disposable PostgreSQL stores."""

import io
import json

from test_store_acceptance import ProductStoreTests

from mycel._cli import run
from mycel._collection import CollectionStore
from mycel._locks import (
    atomic_transaction,
    identifier_allocation_guard,
    operation_guard,
    removal_guard,
)
from mycel._store import inspect_store


class IdentifierStoreTests(ProductStoreTests):
    def command(self, *arguments, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        status = run(arguments, stdout=stdout, stderr=stderr)
        reply = json.loads(stdout.getvalue())
        self.assertEqual(status, int(error is not None), (reply, stderr.getvalue()))
        if error is not None:
            self.assertEqual(reply["error"]["code"], error)
        return reply

    def test_allocation_refuses_contention_and_lists_only_committed_issues(self):
        self.command(
            "ids", "next", "syl", "--for", "Wrong series", error="invalid_input"
        )
        self.command("ids", "next", "SYL", "--for", "  ", error="invalid_input")
        self.assertEqual(
            self.command("ids", "list", "SYL"), {"series": "SYL", "ids": []}
        )
        first = {"id": "SYL-341", "for": "Fixture purpose"}
        self.assertEqual(
            self.command("ids", "next", "SYL", "--for", first["for"]),
            {"id": first["id"]},
        )

        with self.connection() as peer, identifier_allocation_guard(peer):
            self.command(
                "ids", "next", "SYL", "--for", "Contending purpose", error="busy"
            )
            with peer.transaction(force_rollback=True):
                peer.execute(
                    "INSERT INTO public.mycel_issued_identifiers VALUES ('SYL', 342, 'Uncommitted')"
                )
                self.assertEqual(
                    self.command("ids", "list", "SYL"),
                    {"series": "SYL", "ids": [first]},
                )

        self.assertEqual(
            self.command("ids", "next", "SYL", "--for", first["for"]), {"id": "SYL-342"}
        )
        self.assertEqual(
            self.command("ids", "list", "SYL"),
            {
                "series": "SYL",
                "ids": [first, {**first, "id": "SYL-342"}],
            },
        )
        with self.connection() as observer:
            self.assertEqual(
                observer.execute(
                    "SELECT number, purpose FROM public.mycel_issued_identifiers ORDER BY number"
                ).fetchall(),
                [(341, first["for"]), (342, first["for"])],
            )

    def test_init_migrates_format_five_without_tying_issues_to_repository_lifetime(
        self,
    ):
        with self.connection() as connection:
            generation = inspect_store(connection).index_generation
            with connection.transaction():
                connection.execute("DROP TABLE public.mycel_issued_identifiers")
                connection.execute("UPDATE public.mycel_store SET format = 5")
                connection.execute(
                    "INSERT INTO public.mycel_repository_state VALUES ('fixture', NULL, '{}')"
                )
            self.assertEqual(inspect_store(connection).format, 5)
            self.command("ids", "list", "SYL", error="store_format")
            self.command(
                "ids", "next", "SYL", "--for", "Before init", error="store_format"
            )
            self.assertEqual(
                connection.execute(
                    "SELECT to_regclass('public.mycel_issued_identifiers')"
                ).fetchone(),
                (None,),
            )

            self.command("init")
            migrated = inspect_store(connection)
            self.assertEqual(
                (migrated.state, migrated.format, migrated.index_generation),
                ("current", 6, generation),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT repository FROM public.mycel_repository_state"
                ).fetchall(),
                [("fixture",)],
            )

            self.assertEqual(
                self.command("ids", "next", "SYL", "--for", "Fixture issue"),
                {"id": "SYL-341"},
            )
            with (
                removal_guard(connection, "fixture"),
                operation_guard(connection, "fixture", "pass"),
                atomic_transaction(connection),
            ):
                removal = CollectionStore(connection).remove_repository_in_transaction(
                    "fixture",
                    guarded_repositories=("fixture",),
                )
                self.assertEqual(removal["repositories"], 1)
            self.assertEqual(
                self.command("ids", "list", "SYL"),
                {
                    "series": "SYL",
                    "ids": [{"id": "SYL-341", "for": "Fixture issue"}],
                },
            )
