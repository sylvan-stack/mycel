"""Offline all-path mechanical reasoning and configured disposable-store proofs."""
from contextlib import ExitStack
import json
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._capture import capture_repository
from mycel._errors import MycelError
from mycel._located_dependencies import LocatedDependencyProducer
from mycel._located_reconciliation import LocatedCaptureStore
from mycel._locks import operation_guard
from mycel._settings import load_settings
from mycel._source_refs import SourceAddress
from mycel._staleness import StaleEdge, StaleNode, StaleReason, compare_dependency, plan_staleness
from mycel._store import checked_store

try:
    from . import test_located_reconciliation as fixtures
except ImportError:
    import test_located_reconciliation as fixtures


class StalenessUnitTests(unittest.TestCase):
    def test_hash_and_membership_decisions_are_pure_and_use_complete_selection(self):
        import test_reconciliation as values
        from mycel._evidence import CaptureLocation, capture_baseline
        from mycel._resolver import SourceResolver
        dep = values.document('owner', 'answer.md', '# Answer\nClaim.\n')
        old = values.code('class Worker:\n    def first(self):\n        return 1\n')
        ref = 'source:@code/code.py#Worker'
        resolver = SourceResolver(values.settings(), (dep, old))
        selected = resolver.resolve(ref)
        baseline = capture_baseline('owner', values.member(dep), dep, selected.selection,
            kind='declared', declaration=ref, captured_at='2026-10-09T00:00:00Z', location=CaptureLocation('disk')).manifest.payload
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            self.assertEqual(compare_dependency(baseline, selected, selected.selection.place, 'declared'), ())
            added = values.code('class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
            changed = SourceResolver(values.settings(), (dep, added)).resolve(ref)
            self.assertEqual([reason.kind for reason in compare_dependency(baseline, changed,
                selected.selection.place, 'asserted')], ['source_changed'])
            removed = values.code('class Worker:\n    pass\n')
            changed = SourceResolver(values.settings(), (dep, removed)).resolve(ref)
            self.assertEqual({reason.kind for reason in compare_dependency(baseline, changed,
                selected.selection.place, 'declared')}, {'source_changed', 'source_removed'})
            missing = SourceResolver(values.settings(), (dep,)).resolve(ref)
            self.assertEqual(compare_dependency(baseline, missing, selected.selection.place,
                'declared')[0].kind, 'source_removed')
            whole = values.document('source', 'source.md', '---\nrole: authored\n---\n# Source\nSame body.\n')
            selected = SourceResolver(values.settings(), (dep, whole)).resolve('source:@artifact/source.md')
            baseline = capture_baseline('owner', values.member(dep), dep, selected.selection,
                kind='declared', declaration=selected.declaration, captured_at='2026-10-09T00:00:00Z',
                location=CaptureLocation('disk')).manifest.payload
            changed_file = values.document('source', 'source.md', '---\nrole: derived\n---\n# Source\nSame body.\n')
            changed = SourceResolver(values.settings(), (dep, changed_file)).resolve(selected.declaration)
            self.assertEqual(compare_dependency(baseline, changed, selected.selection.place, 'declared')[0].kind,
                             'source_changed')

    def test_offline_iterative_all_path_planning_and_cycle_refusal(self):
        def node(number, exempt=False):
            return StaleNode(str(number), number + 1,
                SourceAddress('fictional', 'artifact', str(number) + '.md', 'Heading'), exempt)
        nodes = tuple(node(number) for number in range(1100))
        edges = tuple(StaleEdge(str(number), str(number + 1), str(number), 'declared') for number in range(1099))
        direct = {'0': (('origin', StaleReason('source_changed', nodes[0].place, 'asserted')),)}
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            result = plan_staleness(nodes, edges, direct)
        self.assertEqual(len(result['1099'][0][1].via), 1099)
        self.assertEqual(result['1099'][0][1].source, nodes[0].place)
        with self.assertRaises(MycelError):
            plan_staleness(nodes[:2], (StaleEdge('0', '1', 'x', 'declared'),
                StaleEdge('1', '0', 'y', 'declared')), direct)
        blocked = plan_staleness((node(0), node(1, True), node(2)),
            (StaleEdge('0', '1', 'x', 'declared'), StaleEdge('1', '2', 'y', 'declared')), direct)
        self.assertEqual(blocked['1'], ())
        self.assertEqual(blocked['2'], ())
        mixed = plan_staleness(nodes[:2], edges[:1],
            {'0': direct['0'], '1': (('local', StaleReason('source_removed', nodes[1].place, 'declared')),)})
        self.assertEqual([reason.kind for _, reason in mixed['1']], ['source_removed', 'upstream_stale'])


class MechanicalStalenessStoreTests(unittest.TestCase):
    check_kind = "store"

    def setUp(self):
        self.base = fixtures.LocatedReconciliationStoreTests()
        self.base.store_fixture = self.store_fixture
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.initialize(b'# Guide\nRepository guide.\n')
        self.source = self.base.artifact / 'source.md'
        self.source.write_bytes(b'# Source\nOriginal source body.\n')
        self.code = self.base.code / 'worker.py'
        self.code.write_bytes(b'def work():\n    return 1\n')
        self.base.commit()
        self.roots = {}
        for owner in ('left', 'right', 'tail', 'unrelated'):
            root = self.base.base / owner
            root.mkdir()
            self.roots[owner] = root
            self.base.config.write_text(self.base.config.read_text() + '\n[repos.' + owner + ']\nenabled=true\n'
                + 'artifact_root=' + json.dumps(str(root)) + '\n')
        self.write('left', 'Left', ('fixture:@artifact/source.md#Source',))
        self.write('right', 'Right', ('fixture:@artifact/source.md#Source',))
        self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'right:@artifact/answer.md#Right'))
        self.write('unrelated', 'Other', ())
        self.reload()

    def reload(self):
        self.settings = load_settings(path=self.base.config, home=self.base.base)

    def write(self, owner, title, sources, *, metadata='', body='Unchanged claim.'):
        raw = '---\nrole: authored\n' + metadata + 'sources: ' + json.dumps(list(sources)) + '\n---\n'
        (self.roots[owner] / 'answer.md').write_text(raw + '# ' + title + '\n' + body + '\n')

    def guards(self, connection):
        held = ExitStack()
        held.enter_context(checked_store(connection))
        for owner in sorted(self.settings.values['repos']):
            held.enter_context(operation_guard(connection, owner, 'pass'))
        return held

    def publish(self, connection, owner='fixture', *, producer=True, activity=None, reply_counts=None):
        manifest = capture_repository(self.settings, owner)
        handoff = LocatedDependencyProducer(self.settings, captured_at='2026-10-09T21:00:00Z',
            settings_home=self.base.base, collection_manifest=manifest) if producer else None
        with self.guards(connection) if producer else checked_store(connection):
            return LocatedCaptureStore(connection).apply(self.settings, manifest, batch_handoff=handoff,
                activity=activity, reply_counts=reply_counts)

    def prepare(self, connection):
        for owner in ('fixture', 'left', 'right', 'tail', 'unrelated'):
            self.publish(connection, owner)
        self.assertEqual(self.reasons(connection), [])

    def reasons(self, connection, owner=None):
        return connection.execute("""SELECT r.id,r.repository,r.chunk_version,r.dependency,r.reason,xmin::text
            FROM public.mycel_stale_reasons r WHERE (%s::text IS NULL OR r.repository=%s)
            ORDER BY r.repository,(r.reason->>'kind'='upstream_stale'),r.reason::text""", (owner, owner)).fetchall()

    def pins(self, connection):
        return connection.execute('SELECT id,repository,dependant_version,baseline_owner FROM public.mycel_dependencies '
                                  'ORDER BY id').fetchall()

    def unrelated_state(self, connection):
        return {table: connection.execute(f"SELECT to_jsonb(t),xmin::text FROM public.{table} t "
            "WHERE repository='unrelated' ORDER BY to_jsonb(t)::text").fetchall()
            for table in ('mycel_dependencies', 'mycel_chunks', 'mycel_stale_reasons', 'mycel_activity')}

    def test_complete_same_pass_hash_reasons_diamond_paths_and_unrelated_rows(self):
        self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'right:@artifact/answer.md#Right',
                                   'fixture:@code/worker.py#work'))
        unrelated_source = self.roots['unrelated'] / 'anchor.md'
        unrelated_source.write_text('# Anchor\nIndependent original source.\n')
        self.write('unrelated', 'Other', ('unrelated:@artifact/anchor.md#Anchor',))
        with self.base.connect() as connection:
            self.prepare(connection)
            pins, unrelated = self.pins(connection), self.unrelated_state(connection)
            unrelated_source.write_text('# Anchor\nUnindexed edit in an independent component.\n')
            self.source.write_bytes(b'# Source\nChanged governing document.\n')
            self.code.write_bytes(b'def work():\n    return 2\n')
            result = self.publish(connection)
            self.assertEqual(self.pins(connection), pins)
            tail = self.reasons(connection, 'tail')
            self.assertEqual(len(tail), 3)
            self.assertEqual(tail[0][4]['kind'], 'source_changed')
            self.assertEqual(tail[0][4]['source']['address'], 'fixture:@code/worker.py#work')
            indirect = [row[4] for row in tail if row[4]['kind'] == 'upstream_stale']
            self.assertEqual({tuple(place['repository'] for place in reason['via']) for reason in indirect},
                             {('left',), ('right',)})
            self.assertTrue(all(reason['source']['address'] == 'fixture:@artifact/source.md#Source' for reason in indirect))
            self.assertEqual(self.unrelated_state(connection), unrelated)
            self.assertEqual(result.counts['dependencyRepositories']['tail']['stale'], 1)
            self.assertEqual(result.counts['stalePending'], [])
            connection.execute("UPDATE public.mycel_stale_reasons SET reason=reason || "
                "'{\"classification\":{\"bundle\":\"fictional-retained-link\"}}'::jsonb WHERE repository='tail'")
            stable = self.reasons(connection)
            self.assertFalse(self.publish(connection).changed)
            self.assertEqual(self.reasons(connection), stable)
            self.code.write_bytes(b'def work():\n    return 1\n')
            self.publish(connection)
            self.assertEqual(len(self.reasons(connection, 'tail')), 2)
            self.assertTrue(all(row[4]['kind'] == 'upstream_stale' for row in self.reasons(connection, 'tail')))
            self.source.write_bytes(b'# Source\nOriginal source body.\n')
            self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            self.assertEqual(self.pins(connection), pins)

    def test_disk_absence_and_restoration_clear_direct_and_every_indirect_reason(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            pins = self.pins(connection)
            self.source.unlink()  # Its committed local branch still retains the source.
            self.publish(connection)
            reasons = self.reasons(connection)
            self.assertEqual(len(reasons), 4)
            self.assertEqual({row[4]['kind'] for row in self.reasons(connection, 'left')}, {'source_removed'})
            self.assertTrue(all(row[4]['source']['address'] == 'fixture:@artifact/source.md#Source' for row in reasons))
            self.source.write_bytes(b'# Source\nOriginal source body.\n')
            self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            self.assertEqual(self.pins(connection), pins)

    def test_heartwood_and_external_generated_stop_propagation_but_their_bytes_still_compare(self):
        self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
        self.write('right', 'Right', ('fixture:@artifact/source.md#Source',), metadata='generated: true\n')
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged blocked source.\n')
            self.publish(connection)
            self.assertEqual(self.reasons(connection), [])
            path = self.roots['left'] / 'answer.md'
            path.write_text(path.read_text().replace('Unchanged claim.', 'Changed Heartwood record.'))
            self.publish(connection, 'left')
            reasons = self.reasons(connection, 'tail')
            self.assertEqual(len(reasons), 1)
            self.assertEqual(reasons[0][4]['kind'], 'source_changed')
            self.assertEqual(reasons[0][4]['source']['repository'], 'left')
            self.assertEqual(self.reasons(connection, 'left'), [])

    def test_generic_frontmatter_exemption_changes_clear_and_restore_only_applicable_paths(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            pins = self.pins(connection)
            self.source.write_bytes(b'# Source\nChanged before exemptions.\n')
            self.publish(connection)
            self.assertEqual(len(self.reasons(connection)), 4)
            self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
            self.publish(connection, 'left', producer=False)
            self.assertEqual(self.reasons(connection, 'left'), [])
            tail = self.reasons(connection, 'tail')
            self.assertEqual(len(tail), 1)
            self.assertEqual(tail[0][4]['via'][0]['repository'], 'right')
            self.write('right', 'Right', ('fixture:@artifact/source.md#Source',), metadata='generated: true\n')
            self.publish(connection, 'right', producer=False)
            self.assertEqual(self.reasons(connection), [])
            self.write('left', 'Left', ('fixture:@artifact/source.md#Source',))
            self.publish(connection, 'left', producer=False)
            self.assertEqual(len(self.reasons(connection, 'left')), 1)
            self.assertEqual(len(self.reasons(connection, 'tail')), 1)
            self.assertEqual(self.reasons(connection, 'tail')[0][4]['via'][0]['repository'], 'left')
            self.assertEqual(self.pins(connection), pins)

    def test_document_to_code_move_cannot_carry_its_old_document_exemption(self):
        from mycel._derive import DeriveStore
        from mycel._resolver import SourceResolver
        document = self.base.artifact / 'generated.md'
        document.write_bytes(b'---\ngenerated: true\n---\n# Historical\nOriginal generated text.\n')
        self.base.commit()
        with self.base.connect() as connection:
            self.prepare(connection)
            previous = next(file for file in SourceResolver.from_store(connection, self.settings).files
                            if file.primary.path == 'generated.md')
            document.rename(self.base.artifact / 'generated.py')
            self.base.commit()
            self.publish(connection, producer=False)
            current = next(file for file in SourceResolver.from_store(connection, self.settings).files
                           if file.primary.path == 'generated.py')
            self.assertEqual(current.identifier, previous.identifier)
            self.assertTrue(all(chunk.kind != 'document' for chunk in current.chunks))
            metadata = connection.execute("""SELECT l.metadata FROM public.mycel_file_locations l
                JOIN public.mycel_file_versions v ON v.id=l.file_version
                WHERE v.file_id=%s AND l.kind='disk'""", (current.identifier,)).fetchone()[0]
            self.assertIs(metadata['documentDeclarations']['metadata']['generated'], True)
            dependant = SourceResolver._members(current, current.chunks)[0].place.address
            DeriveStore(connection).apply(self.settings, dependant, 'fixture:@artifact/source.md#Source',
                captured_at='2026-10-09T21:00:00Z')
            self.source.write_bytes(b'# Source\nChanged source of current code.\n')
            self.publish(connection)
            reasons = self.reasons(connection, 'fixture')
            self.assertEqual(len(reasons), 1)
            self.assertEqual(reasons[0][4]['kind'], 'source_changed')

    def test_busy_owner_stays_pending_while_guarded_descendants_apply_and_retry(self):
        with self.base.connect() as connection, self.base.connect() as busy:
            self.prepare(connection)
            pins = self.pins(connection)
            self.source.write_bytes(b'# Source\nChanged with a busy intermediate.\n')
            with checked_store(busy), operation_guard(busy, 'left', 'pass'):
                result = self.publish(connection, producer=False)
                self.assertEqual(self.reasons(connection, 'left'), [])
                self.assertEqual(len(self.reasons(connection, 'tail')), 2)
                self.assertEqual({item['chunk']['repository'] for item in result.counts['stalePending']}, {'left'})
                self.assertEqual({item['reason'] for item in result.counts['stalePending']}, {'busy'})
            retried = self.publish(connection, producer=False)
            self.assertEqual(retried.counts['stalePending'], [])
            self.assertEqual(len(self.reasons(connection, 'left')), 1)
            self.assertEqual(self.pins(connection), pins)
            unrelated = self.unrelated_state(connection)
            with checked_store(busy), operation_guard(busy, 'unrelated', 'pass'):
                repeated = self.publish(connection, producer=False)
            self.assertEqual(repeated.counts['stalePending'], [])
            self.assertNotIn('unrelated', repeated.counts.get('dependencyRepositories', {}))
            self.assertEqual(self.unrelated_state(connection), unrelated)

    def test_final_busy_peer_dependency_change_refuses_all_prospective_marks(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            before = self.reasons(connection)
            old_source = connection.execute("SELECT v.snapshot_hash FROM public.mycel_file_versions v "
                "JOIN public.mycel_file_locations l ON l.file_version=v.id JOIN public.mycel_files f ON f.id=v.file_id "
                "WHERE f.repository='fixture' AND l.kind='disk' AND l.metadata->>'path'='source.md'").fetchone()
            self.source.write_bytes(b'# Source\nChanged before peer guard.\n')
            def mutate(owner, counts):
                if owner == 'fixture':
                    peer.execute("UPDATE public.mycel_dependencies SET state=state || '{\"peerObservation\":true}'::jsonb "
                                 "WHERE repository='left'")
                return counts
            with checked_store(peer), operation_guard(peer, 'left', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, producer=False, reply_counts=mutate)
                self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), before)
            self.assertEqual(connection.execute("SELECT v.snapshot_hash FROM public.mycel_file_versions v "
                "JOIN public.mycel_file_locations l ON l.file_version=v.id JOIN public.mycel_files f ON f.id=v.file_id "
                "WHERE f.repository='fixture' AND l.kind='disk' AND l.metadata->>'path'='source.md'").fetchone(), old_source)

    def test_disjoint_busy_owner_can_commit_metadata_during_source_publication(self):
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged with disjoint concurrent work.\n')
            def mutate(owner, counts):
                if owner == 'fixture':
                    peer.execute("""UPDATE public.mycel_locations SET metadata=metadata || '{"peerObservation":true}'::jsonb
                        WHERE chunk_version IN (SELECT v.id FROM public.mycel_chunk_versions v
                            JOIN public.mycel_chunks c ON c.id=v.chunk_id WHERE c.repository='unrelated')""")
                return counts
            with checked_store(peer), operation_guard(peer, 'unrelated', 'pass'):
                result = self.publish(connection, producer=False, reply_counts=mutate)
            self.assertEqual(result.counts['stalePending'], [])
            self.assertEqual(len(self.reasons(connection)), 4)
            self.assertEqual(connection.execute("""SELECT count(*) FROM public.mycel_locations
                WHERE metadata->>'peerObservation'='true'""").fetchone(), (1,))

    def test_new_downstream_pin_during_source_deletion_invalidates_and_then_retries(self):
        from psycopg.types.json import Jsonb
        from mycel._derive import DeriveStore
        with self.base.connect() as connection, self.base.connect() as peer:
            self.prepare(connection)
            DeriveStore(connection).apply(self.settings, 'unrelated:@artifact/answer.md#Other',
                'fixture:@artifact/source.md#Source', captured_at='2026-10-09T21:00:00Z')
            row = connection.execute("SELECT * FROM public.mycel_dependencies WHERE repository='unrelated'").fetchone()
            connection.execute('DELETE FROM public.mycel_dependencies WHERE id=%s', (row[0],))
            self.source.unlink()
            inserted = False
            def publish_new_pin(owner, counts):
                nonlocal inserted
                if owner == 'fixture' and not inserted:
                    peer.execute('INSERT INTO public.mycel_dependencies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                                 (*row[:6], Jsonb(row[6]), row[7]))
                    inserted = True
                return counts
            with checked_store(peer), operation_guard(peer, 'unrelated', 'pass'):
                with self.assertRaises(MycelError) as caught:
                    self.publish(connection, producer=False, reply_counts=publish_new_pin)
                self.assertEqual(caught.exception.code, 'invalid_input')
            self.assertEqual(self.reasons(connection), [])
            retry = self.publish(connection, producer=False)
            self.assertEqual(retry.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection, 'unrelated')[0][4]['kind'], 'source_removed')

    def test_native_activity_contains_exact_downstream_detection_and_audit_failure_rolls_back(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged with activity.\n')
            with MutationActivity(connection, build=1).session() as audit:
                result = self.publish(connection, activity=audit)
                final = {('fixture', 'ingest'): result.counts,
                         **{(owner, 'ingest'): counts for owner, counts in result.counts['dependencyRepositories'].items()}}
                audit.finish('done', counts=final)
            entries = connection.execute('SELECT id,repository FROM public.mycel_activity ORDER BY repository').fetchall()
            self.assertEqual({owner for _, owner in entries}, {'fixture', 'left', 'right', 'tail'})
            for identifier, owner in entries:
                state = activity_state(connection, identifier)
                self.assertEqual(state['counts'], final[(owner, 'ingest')])
                if owner != 'fixture':
                    self.assertEqual(state['files'], [])
                    self.assertEqual(state['decisions'], [])
            stable = self.reasons(connection)
            self.source.write_bytes(b'# Source\nOriginal source body.\n')
            with MutationActivity(connection, build=1).session() as audit:
                with patch.object(audit, 'record_in_transaction', side_effect=MycelError('internal', 'Fictional audit failure')):
                    with self.assertRaises(MycelError):
                        self.publish(connection, activity=audit)
            self.assertEqual(self.reasons(connection), stable)

    def test_final_root_audit_and_baseline_reader_file_mutations_refuse_publication(self):
        from mycel._evidence import EvidenceStore
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged with late foreign mutation.\n')
            left = self.roots['left'] / 'answer.md'
            original = left.read_bytes()
            with MutationActivity(connection, build=1).session() as audit:
                native = audit.record_in_transaction
                def record(owner, kind, mutation):
                    value = native(owner, kind, mutation)
                    if owner == 'fixture':
                        left.write_bytes(original + b'Late root-audit mutation.\n')
                    return value
                with patch.object(audit, 'record_in_transaction', side_effect=record):
                    with self.assertRaises(MycelError):
                        self.publish(connection, producer=False, activity=audit)
            self.assertEqual(self.reasons(connection), [])
            left.write_bytes(original)
            native = EvidenceStore._read_baseline
            def read(store, owner, identifier, **kwargs):
                value = native(store, owner, identifier, **kwargs)
                if owner == 'left':
                    left.write_bytes(original + b'Late baseline-reader mutation.\n')
                return value
            with patch.object(EvidenceStore, '_read_baseline', read):
                with self.assertRaises(MycelError):
                    self.publish(connection, producer=False)
            self.assertEqual(self.reasons(connection), [])

    def test_corrupt_baseline_and_foreign_uningested_bytes_keep_marks_pending_with_exact_counts(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged before missing evidence.\n')
            self.publish(connection)
            before = self.reasons(connection)
            connection.execute("""UPDATE public.mycel_snapshots SET metadata=metadata || '{"bytes":0}'::jsonb
                WHERE repository='left'""")
            result = self.publish(connection, producer=False)
            self.assertEqual(self.reasons(connection), before)
            self.assertEqual(result.counts['dependencyRepositories']['left']['staleReasons'], 1)
            self.assertEqual(result.counts['dependencyRepositories']['tail']['staleReasons'], 2)
            self.assertEqual({item['reason'] for item in result.counts['stalePending']},
                             {'snapshot_corrupt', 'upstream_unchecked'})
            right = self.roots['right'] / 'answer.md'
            right.write_bytes(right.read_bytes() + b'Unindexed foreign edit.\n')
            result = self.publish(connection, producer=False)
            self.assertIn('changed_since_ingest', {item['reason'] for item in result.counts['stalePending']})
            self.assertEqual(self.reasons(connection), before)

    def test_fault_on_exempt_intermediate_does_not_block_an_independent_downstream_reason(self):
        self.write('left', 'Left', ('fixture:@artifact/source.md#Source',), metadata='status: heartwood\n')
        self.write('tail', 'Tail', ('left:@artifact/answer.md#Left', 'fixture:@code/worker.py#work'))
        with self.base.connect() as connection:
            self.prepare(connection)
            connection.execute("""UPDATE public.mycel_snapshots SET metadata=metadata || '{"bytes":0}'::jsonb
                WHERE repository='left'""")
            self.code.write_bytes(b'def work():\n    return 2\n')
            result = self.publish(connection, producer=False)
            self.assertEqual(result.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection, 'left'), [])
            self.assertEqual(len(self.reasons(connection, 'tail')), 1)
            self.assertEqual(self.reasons(connection, 'tail')[0][4]['source']['address'], 'fixture:@code/worker.py#work')

    def test_current_class_members_expand_prelocks_and_retries_after_generic_publication(self):
        self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
        self.write('left', 'Left', ('fixture:@code/worker.py#Worker',))
        with self.base.connect() as connection:
            self.prepare(connection)
            self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
            result = self.publish(connection, producer=False)
            self.assertEqual(result.counts['stalePending'], [])
            self.assertEqual(self.reasons(connection, 'left')[0][4]['kind'], 'source_changed')
            self.code.write_bytes(b'class Worker:\n    def second(self):\n        return 2\n')
            result = self.publish(connection, producer=False)
            self.assertEqual(result.counts['stalePending'], [])
            self.assertEqual({row[4]['kind'] for row in self.reasons(connection, 'left')},
                             {'source_changed', 'source_removed'})
            self.assertEqual(next(row[4]['source']['name'] for row in self.reasons(connection, 'left')
                if row[4]['kind'] == 'source_removed'), 'Worker.first')

    def test_disabled_source_deactivates_stale_authority_without_a_removed_or_missing_baseline_claim(self):
        with self.base.connect() as connection:
            self.prepare(connection)
            self.source.write_bytes(b'# Source\nChanged before disabling.\n')
            self.publish(connection)
            self.base.config.write_text(self.base.config.read_text().replace('[repos.fixture]\nenabled=true',
                                                                          '[repos.fixture]\nenabled=false'))
            self.reload()
            result = self.publish(connection, 'left')
            self.assertEqual(self.reasons(connection, 'left'), [])
            tail = self.reasons(connection, 'tail')
            self.assertEqual(tail, [])
            self.assertEqual(result.counts['stalePending'], [])

    def test_shared_disk_branch_version_selects_only_its_disk_owned_pin(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'---\nsources: ["fixture:@artifact/source.md#Source"]\n---\n# Guide\nRepository guide.\n')
        self.base.commit()
        with self.base.connect() as connection:
            self.prepare(connection)
            deps = connection.execute("""SELECT id,dependant_version,baseline_owner,state->'declarationLocation'->>'kind'
                FROM public.mycel_dependencies WHERE repository='fixture' ORDER BY id""").fetchall()
            self.assertEqual({row[3] for row in deps}, {'disk', 'branch'})
            self.assertEqual(len({row[1] for row in deps}), 1)
            self.assertEqual(len({row[2] for row in deps}), 2)
            self.source.write_bytes(b'# Source\nDisk-only source change.\n')
            self.publish(connection)
            current = self.reasons(connection, 'fixture')
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0][3], next(row[0] for row in deps if row[3] == 'disk'))

    def test_declared_asserted_reasons_keep_both_kinds_and_new_family_members_supply_prelocks(self):
        from mycel._derive import DeriveStore
        self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n')
        self.write('left', 'Left', ('fixture:@code/worker.py#Worker',))
        with self.base.connect() as connection:
            self.prepare(connection)
            DeriveStore(connection).apply(self.settings, 'right:@artifact/answer.md#Right',
                'fixture:@artifact/source.md#Source', captured_at='2026-10-09T21:00:00Z')
            self.source.write_bytes(b'# Source\nBoth independent edge kinds change.\n')
            self.publish(connection)
            self.assertEqual({row[4]['edge'] for row in self.reasons(connection, 'right')}, {'declared', 'asserted'})
            self.code.write_bytes(b'class Worker:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
            self.publish(connection, producer=False)
            DeriveStore(connection).apply(self.settings, 'fixture:@code/worker.py#Worker.second',
                'right:@artifact/answer.md#Right', captured_at='2026-10-09T21:00:00Z')
            right = self.roots['right'] / 'answer.md'
            right.write_text(right.read_text().replace('Unchanged claim.', 'Changed source for the new member.'))
            result = self.publish(connection, 'right', producer=False)
            self.assertEqual(result.counts['stalePending'], [])
            reasons = self.reasons(connection, 'left')
            self.assertTrue(any(row[4]['kind'] == 'upstream_stale' and row[4]['source']['repository'] == 'right'
                and row[4]['via'][0]['name'] == 'Worker.second' for row in reasons))
