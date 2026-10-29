"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_refs as _support
from test_refs import (Jsonb ,Path ,contextmanager ,invoke ,patch ,retain ,seed_document ,tempfile)


class RefsStoreTests(_support.RefsStoreTests):


# TEST-TIER-BEGIN tests/test_refs.py::RefsStoreTests.test_all_repository_reports_share_one_database_enforced_readonly_snapshot
    def test_all_repository_reports_share_one_database_enforced_readonly_snapshot(self):
        text = "# Answer\n<!-- sources:\nunknown:path\n-->\n"
        with tempfile.TemporaryDirectory() as directory:
            config, settings = self.configured(Path(directory), {"one": {"enabled": True}, "two": {"enabled": True}})
            with self.store_fixture.backend.connection(self.store_fixture.database) as peer:
                for name in ("one", "two"):
                    location, _, _, _ = seed_document(peer, name, "answer.md", text)
                    retain(peer, settings, location, text)
                from mycel._locks import snapshot_transaction
                from mycel._refs import _report
                snapshots = []

                @contextmanager
                def observe(connection):
                    with snapshot_transaction(connection):
                        snapshots.append(connection.execute(
                            "SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation')").fetchone())
                        yield

                advanced = False
                def advance_after_first_row(row):
                    nonlocal advanced
                    result = _report(row)
                    if not advanced:
                        advanced = True
                        peer.execute("UPDATE public.mycel_dependencies SET state=state || %s WHERE repository='two'",
                                     (Jsonb({"resolution": {"state": "invalid", "fault": "unregistered_repository"}}),))
                    return result

                with patch("mycel._refs.snapshot_transaction", observe), \
                        patch("mycel._refs._report", advance_after_first_row):
                    status, reply, stderr = invoke(config, ("refs", "--repo", "one", "--repo", "two"))
                self.assertEqual((status, stderr), (0, ""))
                self.assertEqual(snapshots, [("on", "repeatable read")])
                self.assertEqual([entry["result"]["refs"][0]["resolutionFault"] for entry in reply["repositories"]],
                                 ["not_checked", "not_checked"])
                status, newer, stderr = invoke(config, ("refs", "--repo", "two"))
                self.assertEqual(newer["repositories"][0]["result"]["refs"][0]["resolutionFault"], "unregistered_repository")
# TEST-TIER-END tests/test_refs.py::RefsStoreTests.test_all_repository_reports_share_one_database_enforced_readonly_snapshot
