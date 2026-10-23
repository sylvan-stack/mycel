"""Configured-store stale repair proofs with deterministic local services."""

from dataclasses import replace
import os
import signal
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity
from mycel._cli import Invocation
from mycel._coverage import proves
from mycel._errors import MycelError
from mycel._generated import generated_capture
from mycel._locks import operation_guard, removal_guard
from mycel._summary_regenerate import regenerate_summaries
from mycel._summary_store import StoreSummaries
from mycel._summary_writer import WriterResult

try:
    from . import test_summary_build as builds
except ImportError:
    import test_summary_build as builds


class SequentialWriter:
    def __init__(self, *, fail_at=None, interrupt_at=None, callback=None):
        self.requests, self.fail_at, self.interrupt_at, self.callback = [], fail_at, interrupt_at, callback

    def write_many(self, requests):
        self.requests.extend(requests)
        number = len(self.requests)
        if self.callback:
            self.callback(number, requests)
        if number == self.interrupt_at:
            raise KeyboardInterrupt
        if number == self.fail_at:
            return (WriterResult(None, "nonzero_exit", 2),)
        return (WriterResult(f" Whole regenerated response {number}.\r\n\0end. ".encode(), None, 1),)


class SummaryRegenerationStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.fixture = builds.SummaryBuildStoreTests()
        self.fixture.store_fixture = self.store_fixture
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base

    def regenerate(self, connection, *, writer=None, client=None, before_publish=None, tokenizer=None):
        return regenerate_summaries(Invocation("summaries", repositories=("fixture",), arguments=("regenerate",),
            settings=self.base.settings), _store=(connection, None), _writer=writer or SequentialWriter(),
            _client=client or builds.LocalEmbedding(), _tokenizer=tokenizer or self.fixture.tokenizer,
            _before_publish=before_publish)

    def prepare(self, connection, *, tree=False, independent=False):
        self.fixture.prepare(connection, count=24 if tree else 12)
        if tree:
            groupings = 0

            def group(nodes):
                nonlocal groupings
                groupings += 1
                return (tuple(nodes),) if groupings == 2 else tuple(tuple(nodes[i:i+2]) for i in range(0, len(nodes), 2))

            with patch("mycel._summary_build.group_summary_nodes", side_effect=group):
                self.fixture.build(connection)
        elif independent:
            with patch("mycel._summary_build.group_summary_nodes",
                    side_effect=lambda nodes: tuple(tuple(nodes[i:i+4]) for i in range(0, len(nodes), 4))):
                self.fixture.build(connection)
        else:
            self.fixture.build(connection)

    def snapshot(self, connection):
        with StoreSummaries(connection, self.base.settings).snapshot(("fixture",)) as snapshot:
            return snapshot._summaries, snapshot.status(), snapshot.regeneration_plan()

    def current(self, connection):
        return {str(row[0]): row for row in connection.execute("SELECT c.id,v.id,v.source_bytes,l.location,g.state "
            "FROM public.mycel_chunks c JOIN public.mycel_generated_state g ON g.chunk_id=c.id "
            "JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id JOIN public.mycel_locations l ON l.chunk_version=v.id "
            "WHERE c.kind='summary' AND l.kind='index' ORDER BY l.location").fetchall()}

    def change(self, connection, summary, *, text="Changed current section.\n"):
        pin = next(pin for pin in summary.state.members if pin.place.root == "artifact")
        path = self.base.artifact / pin.place.path
        source = path.read_text()
        path.write_text(source.splitlines()[0] + "\n" + text)
        self.base.apply(connection)
        return path

    def generated(self, connection, version):
        return connection.execute("SELECT d.id,d.repository,d.dependant_version,d.declaration,d.source_place,d.kind,"
            "d.state,d.baseline_owner,r.manifest_hash FROM public.mycel_dependencies d "
            "JOIN public.mycel_evidence_references r ON r.owner=d.baseline_owner AND r.ordinal=0 "
            "WHERE d.kind='generated' AND d.dependant_version=%s ORDER BY d.id", (version,)).fetchall()

    def no_leases(self, connection):
        self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE invocation IS NOT NULL").fetchone(), (0,))

    @proves("MYC-8.17", "MYC-8.27", kind="store")
    def test_only_stale_nodes_retain_places_and_exact_membership_with_lower_response_feeding_parent(self):
        with self.base.connect() as connection, self.base.connect() as reader:
            self.prepare(connection, tree=True)
            summaries, _, _ = self.snapshot(connection)
            leaf, parent = summaries[0], summaries[-1]
            self.change(connection, leaf)
            (self.base.artifact / "new.md").write_text("# New\nA section added since the build.\n")
            self.base.apply(connection)
            old = self.current(connection)
            observations = []

            def during(number, requests):
                visible = self.current(reader)
                observations.append(visible)
                if number == 1:
                    self.assertEqual(visible, old)
                else:
                    self.assertIn(b"Whole regenerated response 1", requests[0])
                    self.assertNotEqual(visible[leaf.member.chunk.identifier][1], old[leaf.member.chunk.identifier][1])
                    self.assertEqual(visible[parent.member.chunk.identifier], old[parent.member.chunk.identifier])

            writer = SequentialWriter(callback=during)
            result = self.regenerate(connection, writer=writer)
            self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 2, 0))
            self.assertFalse(result.value["replaced"])
            self.assertEqual((result.value["failed"], result.value["blocked"], result.value["cut"]), ([], [], []))
            current = self.current(connection)
            self.assertEqual(set(current), set(old))
            for summary in summaries:
                identifier = summary.member.chunk.identifier
                self.assertEqual(current[identifier][3], old[identifier][3])
                self.assertEqual([item["chunkId"] for item in current[identifier][4]["members"]],
                                 [pin.chunk_id for pin in summary.state.members])
                if summary not in (leaf, parent):
                    self.assertEqual(current[identifier], old[identifier])
            for summary in (leaf, parent):
                row = current[summary.member.chunk.identifier]
                self.assertNotEqual(row[1], summary.member.chunk.version)
                pins = self.generated(connection, row[1])
                self.assertEqual(len(pins), len(summary.state.members))
                for pin in pins:
                    capture, member = generated_capture(connection, pin)
                    self.assertEqual(capture.manifest.payload["response"]["hash"],
                        connection.execute("SELECT snapshot_hash FROM public.mycel_chunk_versions WHERE id=%s", (row[1],)).fetchone()[0])
                    self.assertEqual(connection.execute("SELECT source_version FROM public.mycel_edges WHERE dependency=%s", (pin[0],)).fetchone(), (member["version"],))
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p ON p.id=v.plan_id WHERE p.chunk_version=%s", (row[1],)).fetchone(), (1,))
            self.assertTrue(all(level["stale"] == 0 for level in self.snapshot(connection)[1]["levels"]))
            self.no_leases(connection)

    @proves("MYC-8.17", "MYC-8.18", "MYC-8.27", kind="store")
    def test_failed_leaf_remains_stale_parent_is_blocked_and_independent_successes_remain(self):
        with self.base.connect() as connection:
            self.prepare(connection, tree=True)
            summaries, _, _ = self.snapshot(connection)
            self.change(connection, summaries[0])
            self.change(connection, summaries[1])
            old = self.current(connection)
            writer = SequentialWriter(fail_at=1)
            result = self.regenerate(connection, writer=writer)
            self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (1, 1, "failed"))
            self.assertEqual(result.value["failed"], [{"summary": summaries[0].member.place.address, "reason": "nonzero_exit"}])
            self.assertEqual(result.value["blocked"][0]["summary"]["address"], summaries[-1].member.place.address)
            self.assertEqual(result.value["blocked"][0]["reason"], "stale_member")
            self.assertEqual(len(writer.requests), 2)
            now = self.current(connection)
            self.assertEqual(now[summaries[0].member.chunk.identifier], old[summaries[0].member.chunk.identifier])
            self.assertEqual(now[summaries[-1].member.chunk.identifier], old[summaries[-1].member.chunk.identifier])
            self.assertNotEqual(now[summaries[1].member.chunk.identifier][1], old[summaries[1].member.chunk.identifier][1])
            self.no_leases(connection)

    @proves("MYC-8.18", "MYC-8.27", kind="store")
    def test_missing_members_are_dropped_and_memberless_nodes_deleted_with_owned_evidence_cleanup(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summaries, _, _ = self.snapshot(connection)
            first, second = summaries[:2]
            removed = first.state.members + second.state.members[:1]
            for pin in removed:
                (self.base.artifact / pin.place.path).unlink()
            self.base.commit()
            self.base.apply(connection)
            owners = [row[7] for row in self.generated(connection, first.member.chunk.version)]
            original = self.current(connection)
            writer = SequentialWriter()
            result = self.regenerate(connection, writer=writer)
            self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 1))
            self.assertEqual(len(writer.requests), 1)
            now = self.current(connection)
            self.assertNotIn(first.member.chunk.identifier, now)
            self.assertEqual([pin["chunkId"] for pin in now[second.member.chunk.identifier][4]["members"]],
                             [pin.chunk_id for pin in second.state.members[1:]])
            self.assertEqual(now[summaries[2].member.chunk.identifier], original[summaries[2].member.chunk.identifier])
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_evidence_owners WHERE id=ANY(%s::uuid[])", (owners,)).fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE dependant_version=%s", (first.member.chunk.version,)).fetchone(), (0,))
            self.no_leases(connection)

    @proves("MYC-8.18", "MYC-8.27", kind="store")
    def test_embedding_failure_and_exact_input_change_preserve_stale_original(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            summary = self.snapshot(connection)[0][0]
            path = self.change(connection, summary)
            old = self.current(connection)
            result = self.regenerate(connection, client=builds.LocalEmbedding(fail=True))
            self.assertEqual(result.value["failed"], [{"summary": summary.member.place.address, "reason": "embedding_failed"}])
            self.assertEqual(self.current(connection), old)
            original = path.read_bytes()
            result = self.regenerate(connection, before_publish=lambda: path.write_bytes(b"# Changed\nLate edit.\n"))
            self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
            self.assertEqual(self.current(connection), old)
            path.write_bytes(original)
            self.assertEqual(self.snapshot(connection)[1]["levels"][0]["stale"], 1)
            self.no_leases(connection)

    @proves("MYC-8.17", "MYC-8.27", kind="store")
    def test_fixed_membership_that_grew_past_request_budget_is_blocked_without_calls_or_new_places(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            summary = self.snapshot(connection)[0][0]
            self.change(connection, summary, text="x" * 49_000)
            old = self.current(connection)
            plan = self.snapshot(connection)[2]
            detail = plan["work"][0]
            self.assertEqual(detail["action"], "write")
            self.assertGreater(detail["boundedRequestsForCurrentText"], 1)
            self.assertEqual((detail["requestFits"], detail["requiresBuild"]), (False, True))
            writer = SequentialWriter(callback=lambda *_: self.fail("oversized fixed group called writer"))
            client = builds.LocalEmbedding(lambda _: self.fail("oversized fixed group called embedding"))
            result = self.regenerate(connection, writer=writer, client=client)
            self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (1, 0, "inputs_changed"))
            self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
            self.assertEqual(self.current(connection), old)
            self.no_leases(connection)

    @proves("MYC-8.17", "MYC-8.27", "MYC-8.28", kind="store")
    def test_single_surviving_oversized_member_keeps_place_reports_cut_and_publishes_all_vector_parts(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summary = self.snapshot(connection)[0][0]
            for pin in summary.state.members[1:]:
                (self.base.artifact / pin.place.path).unlink()
            pin = summary.state.members[0]
            path = self.base.artifact / pin.place.path
            path.write_text(path.read_text().splitlines()[0] + "\n" + "雪🙂" * 26_000)
            self.base.commit()
            self.base.apply(connection)
            tokenizer = replace(self.fixture.tokenizer,
                                catalog=replace(self.fixture.tokenizer.catalog, input_token_cap=60))
            writer = builds.LocalWriter(response=("Whole response line.\n" * 80).encode())
            result = self.regenerate(connection, writer=writer, tokenizer=tokenizer)
            self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 0))
            self.assertEqual(result.value["cut"][0]["address"], pin.place.address)
            self.assertEqual(len(writer.requests[0].decode()), 48_000)
            self.assertIn(b"[Mycel: source text cut at request limit]", writer.requests[0])
            row = self.current(connection)[summary.member.chunk.identifier]
            self.assertEqual(row[3], summary.member.place.address)
            self.assertEqual([item["chunkId"] for item in row[4]["members"]], [pin.chunk_id])
            capture, member = generated_capture(connection, self.generated(connection, row[1])[0])
            self.assertTrue(member["cut"])
            self.assertGreater(member["source"]["bytes"], member["sent"]["bytes"])
            vectors = connection.execute("SELECT count(*) FROM public.mycel_vectors v JOIN public.mycel_embedding_plans p "
                "ON p.id=v.plan_id WHERE p.chunk_version=%s", (row[1],)).fetchone()[0]
            self.assertGreater(vectors, 1)
            self.no_leases(connection)

    @proves("MYC-8.18", "MYC-8.27", kind="store")
    def test_member_restored_during_memberless_deletion_preserves_stale_original(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summary = self.snapshot(connection)[0][0]
            sources = [(self.base.artifact / pin.place.path, (self.base.artifact / pin.place.path).read_bytes())
                       for pin in summary.state.members]
            for path, _ in sources:
                path.unlink()
            self.base.commit()
            self.base.apply(connection)
            old = self.current(connection)
            result = self.regenerate(connection, before_publish=lambda: sources[0][0].write_bytes(sources[0][1]))
            self.assertEqual((result.status, result.value["deleted"], result.value["written"]), (1, 0, 0))
            self.assertEqual(result.value["blocked"][0]["reason"], "inputs_changed")
            self.assertEqual(self.current(connection), old)
            self.no_leases(connection)

    @proves("MYC-8.17", "MYC-8.27", "MYC-8.28", kind="store")
    def test_recreated_original_document_place_rejoins_new_identity_in_both_plan_and_actual_regeneration(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summary = self.snapshot(connection)[0][0]
            pin = summary.state.members[0]
            path = self.base.artifact / pin.place.path
            original = path.read_text()
            path.unlink()
            self.base.commit()
            self.base.apply(connection)
            path.write_text(original.splitlines()[0] + "\nRecreated current source at the retained place.\n")
            self.base.commit()
            self.base.apply(connection)
            from mycel._resolver import SourceResolver
            replacement = SourceResolver.from_store(connection, self.base.settings).resolve(pin.place.address,
                purpose="read").selection.members[0]
            self.assertNotEqual(replacement.chunk.identifier, pin.chunk_id)
            _, _, plan = self.snapshot(connection)
            detail = next(item for item in plan["work"] if item["summary"]["address"] == summary.member.place.address)
            self.assertEqual(detail["action"], "write")
            self.assertEqual(detail["missingMembers"], [])
            self.assertIn(replacement.chunk.identifier, [item["current"]["chunkId"] for item in detail["members"]])
            result = self.regenerate(connection)
            self.assertEqual((result.status, result.value["written"], result.value["deleted"]), (0, 1, 0))
            row = self.current(connection)[summary.member.chunk.identifier]
            retained = row[4]["members"]
            self.assertIn(replacement.chunk.identifier, [item["chunkId"] for item in retained])
            self.assertNotIn(pin.chunk_id, [item["chunkId"] for item in retained])
            self.assertEqual({item["place"] for item in retained}, {item.place.address for item in summary.state.members})
            self.assertEqual(self.snapshot(connection)[1]["levels"][0]["stale"], 0)
            self.no_leases(connection)

    @proves("MYC-8.27", "MYC-8.29", kind="store")
    def test_interruption_retains_acknowledged_success_and_releases_unpublished_request_evidence(self):
        with self.base.connect() as connection:
            self.prepare(connection, independent=True)
            summaries, _, _ = self.snapshot(connection)
            self.change(connection, summaries[0])
            self.change(connection, summaries[1])
            old = self.current(connection)
            result = self.regenerate(connection, writer=SequentialWriter(interrupt_at=2))
            self.assertEqual((result.status, result.value["written"], result.value["deleted"], result.value["stopped"]), (2, 1, 0, "interrupted"))
            current = self.current(connection)
            self.assertNotEqual(current[summaries[0].member.chunk.identifier][1], old[summaries[0].member.chunk.identifier][1])
            self.assertEqual(current[summaries[1].member.chunk.identifier], old[summaries[1].member.chunk.identifier])
            self.no_leases(connection)

    @proves("MYC-8.27", "MYC-8.28", "MYC-8.29", kind="store")
    def test_final_audit_failure_returns_acknowledged_counts_and_truthful_activity(self):
        with self.base.connect() as connection, removal_guard(connection, "fixture"):
            self.prepare(connection, independent=True)
            summaries, _, _ = self.snapshot(connection)
            self.change(connection, summaries[0])
            self.change(connection, summaries[1])
            with patch("mycel._summary_regenerate.current_build", return_value=1), \
                    patch.object(MutationActivity, "finish", side_effect=MycelError("store_unavailable", "Final audit unavailable.")):
                result = self.regenerate(connection)
            self.assertEqual((result.status, result.value["written"], result.value["countsState"]), (1, 2, "committed_prefix"))
            self.assertEqual(result.value["error"]["code"], "store_unavailable")
            counts = connection.execute("SELECT counts FROM public.mycel_activity WHERE kind='summaries_regenerate'").fetchone()[0]
            self.assertEqual(counts["written"], 2)
            self.no_leases(connection)

    @proves("MYC-8.27", "MYC-8.28", "MYC-8.29", kind="store")
    def test_signal_after_publication_acknowledgement_preserves_success_and_complete_interrupted_activity(self):
        with self.base.connect() as connection, removal_guard(connection, "fixture"):
            self.prepare(connection, independent=True)
            summaries, _, _ = self.snapshot(connection)
            self.change(connection, summaries[0])
            self.change(connection, summaries[1])
            old = self.current(connection)
            record = MutationActivity.record_in_transaction

            def signal_after_record(activity, repository, kind, result):
                record(activity, repository, kind, result)
                if kind == "summaries_regenerate":
                    os.kill(os.getpid(), signal.SIGINT)

            with patch("mycel._summary_regenerate.current_build", return_value=1), \
                    patch.object(MutationActivity, "record_in_transaction", signal_after_record):
                result = self.regenerate(connection)
            self.assertEqual((result.status, result.value["written"], result.value["stopped"]), (2, 1, "interrupted"))
            current = self.current(connection)
            self.assertNotEqual(current[summaries[0].member.chunk.identifier][1], old[summaries[0].member.chunk.identifier][1])
            self.assertEqual(current[summaries[1].member.chunk.identifier], old[summaries[1].member.chunk.identifier])
            outcome, counts = connection.execute("SELECT outcome,counts FROM public.mycel_activity "
                "WHERE kind='summaries_regenerate'").fetchone()
            self.assertEqual((outcome, counts), ("stopped", result.value))
            self.no_leases(connection)

    @proves("MYC-8.17", "MYC-8.29", kind="store")
    def test_no_stale_work_makes_no_service_calls_and_mutation_lock_is_nonblocking(self):
        with self.base.connect() as connection, self.base.connect() as competing:
            self.prepare(connection)
            old = self.current(connection)
            writer = SequentialWriter(callback=lambda *_: self.fail("fresh summaries called writer"))
            client = builds.LocalEmbedding(lambda _: self.fail("fresh summaries called embedding"))
            result = self.regenerate(connection, writer=writer, client=client)
            self.assertEqual(result.value, {"repository": "fixture", "written": 0, "deleted": 0, "replaced": False,
                "failed": [], "blocked": [], "cut": []})
            with operation_guard(competing, "fixture", "summaries"):
                with self.assertRaises(MycelError) as error:
                    self.regenerate(connection)
                self.assertEqual(error.exception.code, "busy")
            self.assertEqual(self.current(connection), old)
