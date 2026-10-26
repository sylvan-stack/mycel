"""Public complete ingest against the gate's real disposable PostgreSQL."""
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from mycel._activity import MutationActivity, activity_state
from mycel._capture import capture_repository
from mycel._cli import Invocation, parse, run
from mycel._errors import MycelError
from mycel._ingest import _cumulative, ingest
from mycel._locks import operation_guard
from mycel._settings import load_settings
from mycel._voyage import HTTPResult

try:
    from . import test_located_reconciliation as fixtures
    from .fixtures import EmbeddingStandIn
except ImportError:
    import test_located_reconciliation as fixtures
    from fixtures import EmbeddingStandIn


class IngestUnitTests(unittest.TestCase):
    def test_explicit_ingest_options_and_cumulative_reply_preview(self):
        self.assertEqual(parse(['ingest', '--repo', 'a', '--embed', '--confirm-empty']).arguments,
                         ('--embed', '--confirm-empty'))
        for arguments in (['ingest', 'sync'], ['ingest', '--dry-run'], ['activity', '--entry', '0'],
                          ['activity', '--entry', '1', '--all']):
            with self.assertRaises(MycelError):
                parse(arguments)
        prior = {'refsChecked': 2, 'stale': 3, 'dependencyPending': ['b']}
        self.assertEqual(_cumulative(prior, {'refsChecked': 4, 'stale': 1, 'dependencyPending': ['c']}),
                         {'refsChecked': 6, 'stale': 1, 'dependencyPending': ['c']})
        self.assertEqual(prior, {'refsChecked': 2, 'stale': 3, 'dependencyPending': ['b']})


class IngestStoreTests(unittest.TestCase):
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

    def test_unchanged_empty_policy_is_batched_but_role_repairs_and_new_refs_run(self):
        from mycel._dependency_application import DependencyApplicationStore
        from mycel._relations import RelationApplicationStore
        guide = self.base.artifact / 'guide.md'
        guide.write_text(''.join(f'# Part {number}\nBody {number}.\n' for number in range(30)))
        (self.base.code / 'answer.py').write_text('def answer():\n    return 42\n')
        self.base.commit()
        with patch.object(DependencyApplicationStore, 'apply_in_transaction',
                          side_effect=AssertionError('An empty new scope can initialize its role together')), \
                patch.object(RelationApplicationStore, 'apply_in_transaction',
                           side_effect=AssertionError('An empty new scope needs no relation executor')):
            status, first = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, first)
        self.assertGreater(first['repositories']['fixture']['rolesChanged'], 0)
        with self.base.connect() as connection:
            before = self.state(connection)
        with patch.object(DependencyApplicationStore, 'apply_in_transaction',
                          side_effect=AssertionError('An empty unchanged scope needs no chunk executor')), \
                patch.object(RelationApplicationStore, 'apply_in_transaction',
                           side_effect=AssertionError('An empty unchanged scope needs no relation executor')):
            status, quiet = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, quiet)
        self.assertFalse(quiet['repositories']['fixture']['changed'])
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)
            connection.execute("UPDATE public.mycel_locations SET metadata=jsonb_set(metadata,'{role}', '\"derived\"') WHERE file_location IS NOT NULL")
            connection.commit()
        status, repaired = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, repaired)
        self.assertTrue(repaired['repositories']['fixture']['changed'])
        self.assertGreater(repaired['repositories']['fixture']['rolesChanged'], 0)
        guide.write_text('---\nsources: ["fixture:@code/answer.py#answer"]\n---\n' + guide.read_text())
        status, declared = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, declared)
        self.assertGreater(declared['repositories']['fixture']['pinsCaptured'], 0)

    def test_late_empty_policy_mutation_refuses_and_rolls_back(self):
        from mycel._overview_store import OverviewStore
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            before = self.state(connection)
        original = OverviewStore.reconcile_in_transaction
        def change_role(store, repository):
            changed = original(store, repository)
            store.connection.execute("UPDATE public.mycel_locations SET metadata=jsonb_set(metadata,'{role}', '\"derived\"') WHERE file_location IS NOT NULL")
            return changed
        with patch.object(OverviewStore, 'reconcile_in_transaction', change_role):
            status, refused = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, refused)
        self.assertEqual(refused['repositories'][0]['error']['code'], 'invalid_input')
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)

    def test_empty_scope_mutation_during_active_policy_refuses(self):
        from mycel._relations import RelationApplicationStore
        (self.base.artifact / 'derived.md').write_text(
            '---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Derived\nBody.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            before = self.state(connection)
        original = RelationApplicationStore.apply_in_transaction
        def mutate(store, *args, **kwargs):
            observed = original(store, *args, **kwargs)
            store.connection.execute("""UPDATE public.mycel_locations l
                SET metadata=jsonb_set(l.metadata,'{role}','"derived"')
                FROM public.mycel_file_locations f WHERE f.id=l.file_location
                AND f.metadata->>'path'='guide.md'""")
            return observed
        with patch.object(RelationApplicationStore, 'apply_in_transaction', mutate):
            status, refused = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, refused)
        self.assertEqual(refused['repositories'][0]['error']['code'], 'invalid_input')
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)

    def test_edited_chunks_keep_prior_asserted_sources_and_relations(self):
        from mycel._derive import DeriveStore
        from mycel._relate import RelateStore
        guide = self.base.artifact / 'guide.md'
        code = self.base.code / 'answer.py'
        code.write_text('def answer():\n    return 42\n')
        (self.base.artifact / 'source.md').write_text('# Source\nStable source.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            for dependant in ('fixture:@artifact/guide.md#Guide', 'fixture:@code/answer.py#answer'):
                for store in (DeriveStore(connection), RelateStore(connection)):
                    store.apply(self.base.settings, dependant, 'fixture:@artifact/source.md#Source',
                                settings_home=self.base.base, build=1)
        for normalized in (True, False):
            guide.write_bytes(b'# Guide\n' + (b'Original   body.\n' if normalized else b'Substantive new body.\n'))
            code.write_bytes(b'def answer():\n    ' + (b'return   42\n' if normalized else b'return 43\n'))
            status, reply = self.invoke('--repo', 'fixture')
            self.assertEqual(status, 0, reply)
            result = reply['repositories']['fixture']
            self.assertGreater(result['pinsInherited' if normalized else 'pinsCaptured'], 0)
            self.assertGreater(result['relationPinsInherited' if normalized else 'relationPinsCaptured'], 0)
            with self.base.connect() as connection:
                for table, column, predicate in (
                        ('mycel_dependencies', 'dependant_version', "p.kind='asserted'"),
                        ('mycel_relations', 'left_version', "p.state->>'ownership'='asserted'")):
                    rows = connection.execute(f"""SELECT p.baseline_owner FROM public.{table} p
                        JOIN public.mycel_locations l ON l.chunk_version=p.{column}
                        AND l.file_location::text=p.state->'declarationLocation'->>'file'
                        WHERE l.kind='disk' AND {predicate}""").fetchall()
                    self.assertEqual(len(rows), 2)
                    self.assertTrue(all(row[0] is not None for row in rows))

    def test_restored_historical_chunk_inherits_assertions_absent_from_current_file(self):
        from mycel._derive import DeriveStore
        from mycel._relate import RelateStore
        guide = self.base.artifact / 'guide.md'
        original = guide.read_bytes()
        guide.write_bytes(original + b'# Tail\nRetained body.\n')
        (self.base.artifact / 'source.md').write_text('# Source\nStable source.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            for store in (DeriveStore(connection), RelateStore(connection)):
                store.apply(self.base.settings, 'fixture:@artifact/guide.md#Tail',
                            'fixture:@artifact/source.md#Source', settings_home=self.base.base, build=1)
        guide.write_bytes(original)
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        guide.write_bytes(original + b'# Tail\nRetained   body.\n')
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertGreater(reply['repositories']['fixture']['pinsInherited'], 0)
        self.assertGreater(reply['repositories']['fixture']['relationPinsInherited'], 0)

    def test_complete_disk_local_branches_stash_and_exact_quiet_activity(self):
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'# Guide\nOriginal body.\n# Fixed\nStable section.\n')
        self.base.commit()
        self.base.git('branch', 'other')
        self.base.git('update-ref', 'refs/remotes/origin/remote-only', 'HEAD')
        guide.write_bytes(b'# Guide\nStashed body.\n# Fixed\nStable section.\n')
        (self.base.artifact / 'stashed.md').write_bytes(b'# Stashed\nUntracked stash.\n')
        self.base.git('stash', 'push', '--include-untracked', '--message', 'Fixture stash')
        guide.write_bytes(b'# Guide\nDirty on-disk body.\n# Fixed\nStable section.\n')
        (self.base.code / 'dirty.py').write_bytes(b'def dirty():\n    return 2\n')
        before = self.physical()
        with patch('mycel._credentials.Credentials.require_embedding_key') as credential, \
                patch('mycel._embed.VoyageClient') as provider:
            status, reply = self.invoke('--repo', 'fixture')
            credential.assert_not_called()
            provider.assert_not_called()
        self.assertEqual(status, 0, reply)
        self.assertTrue(reply['repositories']['fixture']['ran'])
        self.assertGreater(reply['repositories']['fixture']['pending'], 0)
        self.assertEqual(self.physical(), before)
        with self.base.connect() as connection:
            locations = connection.execute('SELECT read_locations,last_pass_at FROM '
                'public.mycel_repository_state WHERE repository=%s', ('fixture',)).fetchone()
            self.assertEqual([item['location']['kind'] for item in locations[0]],
                             ['disk', 'branch', 'branch', 'stash'])
            self.assertFalse(any('remote-only' in item['location']['identity'] for item in locations[0]))
            self.assertIsNotNone(locations[1])
            self.assertTrue(connection.execute("SELECT 1 FROM public.mycel_file_locations WHERE kind='stash' "
                "AND metadata->>'path'='stashed.md'").fetchone())
            entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
            details = activity_state(connection, entry)
            self.assertEqual(details['counts'], reply['repositories']['fixture'])
            self.assertTrue({'new', 'edited'}.issubset({item['decision'] for item in details['decisions']}))
        guide.write_bytes(guide.read_bytes().replace(b'Dirty on-disk body.', b'Further on-disk edit.'))
        status, edited = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, edited)
        before = self.physical()
        with self.base.connect() as connection:
            entry = connection.execute('SELECT max(id) FROM public.mycel_activity').fetchone()[0]
            self.assertEqual({item['decision'] for item in activity_state(connection, entry)['decisions']},
                             {'edited', 'unchanged'})
            before_store = self.state(connection)
        status, repeated = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, repeated)
        self.assertFalse(repeated['repositories']['fixture']['changed'])
        self.assertEqual(self.physical(), before)
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before_store)

    def test_failed_complete_capture_and_late_audit_leave_retryable_file_and_no_deletion(self):
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'# Guide\nChanged body.\n')
        with self.base.connect() as connection:
            before = self.state(connection)
        from mycel._located_reconciliation import LocatedCaptureStore
        original = LocatedCaptureStore.capture
        def incomplete(store, settings, repository):
            result = original(store, settings, repository)
            return replace(result, locations=(replace(result.disk, complete=False), *result.locations[1:]))
        with patch.object(LocatedCaptureStore, 'capture', incomplete):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, reply)
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)
        with patch.object(MutationActivity, '_details', side_effect=MycelError('internal', 'Fixture audit failure.')):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, reply)
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertEqual(reply['repositories']['fixture']['chunks']['edited'], 1)
        guide.unlink()
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, reply)
        status, reply = self.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 0, reply)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_file_locations WHERE kind='disk'").fetchone()[0], 0)
            self.assertGreater(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions').fetchone()[0], 0)
        self.base.git('rm', 'docs/guide.md')
        self.base.git('commit', '--message', 'Fixture final removal')
        self.base.artifact.mkdir(exist_ok=True)
        status, reply = self.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 0, reply)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_files').fetchone()[0], 0)

    def test_every_document_and_code_identity_decision_is_public_and_transaction_bound(self):
        guide = self.base.artifact / 'guide.md'
        code = self.base.code / 'symbols.py'
        guide.write_bytes(b'# Named\nRename body.\n# Stable\nStable body.\n# Edited\nOriginal body.\n# Gone\nRemoved body.\n')
        code.write_bytes(b'def named():\n    return 1\n\ndef stable():\n    return 2\n\ndef edited():\n    return 3\n\ndef gone():\n    return 4\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        guide.write_bytes(b'# Renamed\nRename body.\n# Stable\nStable body.\n# Edited\nChanged body.\n# Added\nNew body.\n')
        code.write_bytes(b'def renamed():\n    return 1\n\ndef stable():\n    return 2\n\ndef edited():\n    return 30\n\ndef added():\n    return 5\n')
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        with self.base.connect() as connection:
            identifier = connection.execute('SELECT max(id) FROM public.mycel_activity').fetchone()[0]
            decisions = activity_state(connection, identifier)['decisions']
            for path in ('guide.md', 'symbols.py'):
                self.assertEqual({item['decision'] for item in decisions if item['path'] == path},
                                 {'unchanged', 'edited', 'renamed', 'new', 'removed'})
            self.assertTrue(all(item['previousName'] for item in decisions if item['decision'] == 'renamed'))
            before = self.state(connection)
        output, diagnostic = StringIO(), StringIO()
        with patch.dict(os.environ, {'MYCEL_CONFIG': str(self.base.config)}):
            status = run(['activity', '--entry', str(identifier)], stdout=output, stderr=diagnostic)
        self.assertEqual((status, diagnostic.getvalue()), (0, ''))
        reported = json.loads(output.getvalue())
        self.assertEqual(len(reported['entries'][0]['decisions']), len(decisions))
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)

    def test_busy_selected_affected_and_disjoint_owners_have_exact_pending_and_retry(self):
        downstream = self.add_repository('downstream',
            b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Answer\nStable answer.\n')
        unrelated = self.add_repository('unrelated', b'# Answer\nUnrelated.\n')
        status, reply = self.invoke('--repo', 'fixture', '--repo', 'downstream', '--repo', 'unrelated')
        self.assertEqual(status, 0, reply)
        (self.base.artifact / 'guide.md').write_bytes(b'# Guide\nSource edit.\n')
        with self.base.connect() as connection:
            old_dependant = connection.execute("SELECT to_jsonb(d),xmin::text FROM public.mycel_dependencies d "
                "WHERE repository='downstream' ORDER BY id").fetchall()
        with self.base.connect() as other, operation_guard(other, 'downstream', 'pass'):
            status, reply = self.invoke('--repo', 'fixture', '--repo', 'downstream')
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT to_jsonb(d),xmin::text FROM public.mycel_dependencies d "
                "WHERE repository='downstream' ORDER BY id").fetchall(), old_dependant)
        self.assertEqual(status, 1, reply)
        self.assertTrue(reply['repositories']['fixture']['ran'])
        self.assertEqual(reply['repositories']['fixture']['dependencyPending'], ['downstream'])
        self.assertFalse(reply['repositories']['downstream']['ran'])
        self.assertEqual((downstream / 'answer.md').read_bytes(),
            b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Answer\nStable answer.\n')
        with self.base.connect() as other, operation_guard(other, 'unrelated', 'pass'):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertFalse(reply['repositories']['fixture']['changed'])
        self.assertGreater(reply['repositories']['fixture']['dependencyRepositories']['downstream']['stale'], 0)
        with self.base.connect() as connection:
            self.assertTrue(connection.execute("SELECT 1 FROM public.mycel_stale_reasons WHERE repository='downstream' "
                "AND reason->>'kind'='source_changed'").fetchone())

    def test_named_repeated_cwd_organization_and_all_scopes_with_local_faults(self):
        other = self.add_repository('other', b'# Answer\nOther document.\n')
        self.base.config.write_text(self.base.config.read_text() + 'code_root=' + json.dumps(str(other)) + '\n')
        self.base.git('init', '--initial-branch=fixture-main', cwd=other)
        self.base.commit(cwd=other)
        self.add_repository('disabled', b'# Answer\nDisabled document.\n', enabled=False)
        self.base.config.write_text(self.base.config.read_text() + '\n[organizations.Group]\nroot=' +
                                   json.dumps(str(self.base.base)) + '\n')
        status, reply = self.invoke('--repo', 'fixture', '--repo', 'fixture', '--repo', 'unknown', '--repo', 'disabled')
        self.assertEqual(status, 1, reply)
        self.assertEqual(set(reply['repositories']), {'fixture', 'unknown', 'disabled'})
        self.assertTrue(reply['repositories']['fixture']['ran'])
        self.assertFalse(reply['repositories']['unknown']['ran'])
        self.assertFalse(reply['repositories']['disabled']['ran'])
        with patch('pathlib.Path.cwd', return_value=other):
            status, reply = self.invoke()
        self.assertEqual(status, 0, reply)
        self.assertEqual(set(reply['repositories']), {'other'})
        status, reply = self.invoke('--repo', 'Group')
        self.assertEqual(status, 0, reply)
        self.assertEqual(set(reply['repositories']), {'fixture', 'other'})
        status, reply = self.invoke('--all')
        self.assertEqual(status, 0, reply)
        self.assertEqual(set(reply['repositories']), {'fixture', 'other'})
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_files WHERE repository='disabled'").fetchone()[0], 0)

    def test_busy_required_source_refuses_selected_publication_without_half_file(self):
        self.add_repository('source', b'# Answer\nRequired source.\n')
        (self.base.artifact / 'guide.md').write_bytes(
            b'---\nsources: ["source:@artifact/answer.md#Answer"]\n---\n# Guide\nDerived document.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'source', '--repo', 'fixture')[0], 0)
        (self.base.artifact / 'guide.md').write_bytes(
            (self.base.artifact / 'guide.md').read_bytes().replace(b'Derived document.', b'Edited derived document.'))
        with self.base.connect() as connection:
            before = self.state(connection)
        with self.base.connect() as other, operation_guard(other, 'source', 'pass'):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, reply)
        self.assertEqual(reply['repositories'][0]['error']['code'], 'busy')
        with self.base.connect() as connection:
            self.assertEqual(self.state(connection), before)

    def test_disabled_foreign_edge_owner_gets_collection_guard_and_exact_activity(self):
        self.add_repository('downstream',
            b'---\nsources: ["fixture:@artifact/guide.md#Guide"]\n---\n# Answer\nRetained answer.\n')
        self.assertEqual(self.invoke('--repo', 'fixture', '--repo', 'downstream')[0], 0)
        self.base.config.write_text(self.base.config.read_text().replace('[repos.downstream]\nenabled=true',
                                                                      '[repos.downstream]\nenabled=false'))
        self.base.git('rm', 'docs/guide.md')
        self.base.git('commit', '--message', 'Fixture final source removal')
        self.base.artifact.mkdir(exist_ok=True)
        with self.base.connect() as other, operation_guard(other, 'downstream', 'pass'):
            status, reply = self.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 1, reply)
        self.assertEqual(reply['repositories']['fixture']['collectionPending'], ['downstream'])
        status, reply = self.invoke('--repo', 'fixture', '--confirm-empty')
        self.assertEqual(status, 0, reply)
        self.assertGreater(reply['repositories']['fixture']['dependencyRepositories']['downstream']['sourceEdgesCollected'], 0)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE repository='fixture'").fetchone()[0], 0)
            self.assertGreater(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE repository='downstream'").fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_edges').fetchone()[0], 0)
            self.assertTrue(connection.execute("SELECT 1 FROM public.mycel_activity WHERE repository='downstream' "
                "AND counts ? 'sourceEdgesCollected'").fetchone())

    def test_final_activity_close_failure_retains_committed_ingest_reply(self):
        with patch.object(MutationActivity, 'finish', side_effect=MycelError('internal', 'Fixture closing failure.')):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 1, reply)
        self.assertTrue(reply['repositories']['fixture']['ran'])
        self.assertEqual(reply['countsState'], 'committed_prefix')
        with self.base.connect() as connection:
            self.assertGreater(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone()[0], 0)
            entry = connection.execute('SELECT id FROM public.mycel_activity').fetchone()[0]
            self.assertEqual(activity_state(connection, entry)['outcome'], 'unfinished')

    def test_guard_cleanup_failure_and_interrupt_keep_acknowledged_publication(self):
        from mycel._ingest import _publication_guards
        for fault in (MycelError('internal', 'Fixture guard cleanup failure.'), KeyboardInterrupt()):
            @contextmanager
            def failed_cleanup(*args):
                with _publication_guards(*args) as guards:
                    yield guards
                raise fault
            with patch('mycel._ingest._publication_guards', failed_cleanup):
                status, reply = self.invoke('--repo', 'fixture')
            self.assertEqual(status, 2 if isinstance(fault, KeyboardInterrupt) else 1, reply)
            self.assertTrue(reply['repositories']['fixture']['ran'])
            with self.base.connect() as connection:
                self.assertGreater(connection.execute('SELECT count(*) FROM public.mycel_chunks').fetchone()[0], 0)

    def test_optional_embedding_uses_ingest_policy_only_after_scoped_publication(self):
        self.add_repository('unrelated', b'# Answer\nUnselected text.\n')
        policies, attempts = [], []
        from mycel._embedding_plan import load_tokenizer
        tokenizer = load_tokenizer()
        fixture = EmbeddingStandIn(tokenizer.counts)
        def transport(body, key, **kwargs):
            with self.base.connect() as connection, operation_guard(connection, 'fixture', 'pass'):
                attempts.append(connection.execute("SELECT count(*) FROM public.mycel_chunks WHERE repository='fixture'").fetchone()[0])
            raw = json.loads(body)
            response = fixture.embed(raw['input'], model=raw['model'], dimensions=raw['output_dimension'],
                                     input_type=raw['input_type'], truncation=raw['truncation'])
            return HTTPResult(200, json.dumps(response).encode())
        from mycel._credentials import Secret
        from mycel._voyage import VoyageClient
        def client(credentials, policy, **kwargs):
            policies.append(policy)
            return VoyageClient(credentials, policy, _transport=transport, **kwargs)
        with patch('mycel._embed.VoyageClient', side_effect=client), \
                patch('mycel._credentials.Credentials.require_embedding_key', return_value=Secret('fixture-key')):
            status, reply = self.invoke('--repo', 'fixture', '--embed')
        self.assertEqual(status, 0, reply)
        self.assertTrue(all(policy.command == 'ingest' and policy.embed for policy in policies))
        self.assertTrue(attempts and all(count > 0 for count in attempts))
        self.assertEqual(reply['repositories']['fixture']['pending'], 0)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_files WHERE repository='unrelated'").fetchone()[0], 0)


class IngestPublishesItsCaptureStoreTests(IngestStoreTests):
    """A pass publishes the capture it read (MYC-1.37, MYC-D64)."""
    check_kind = "store"


    def disk_sources(self, connection):
        rows = connection.execute("""SELECT v.source_bytes FROM public.mycel_file_versions v
            JOIN public.mycel_file_locations l ON l.file_version=v.id WHERE l.kind='disk'""").fetchall()
        return sorted(bytes(row[0]) for row in rows)

    def test_file_changed_during_pass_is_saved_as_captured_named_and_taken_by_the_next_pass(self):
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'# Guide\nFirst edit.\n')
        from mycel import _located_reconciliation
        original = _located_reconciliation._observe
        calls = 0

        def racing(repository, addresses, source):
            # Right after the pass has observed the file it read, another agent
            # replaces it, as a `git pull` does, with new bytes and a new inode,
            # and adds a branch: every later step of the pass sees the change.
            nonlocal calls
            calls += 1
            physical = original(repository, addresses, source)
            if calls == 1:
                replacement = guide.with_name('guide.md.new')
                replacement.write_bytes(b'# Guide\nSecond edit, during the pass.\n')
                os.replace(replacement, guide)
                self.base.git('branch', 'added-during-pass')
            return physical

        with patch.object(_located_reconciliation, '_observe', racing):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertGreaterEqual(calls, 1)
        self.assertEqual(status, 0, reply)
        fixture = reply['repositories']['fixture']
        self.assertEqual(fixture['changedDuringPass'], ['branch refs/heads/added-during-pass', 'fixture:@artifact/guide.md'])
        self.assertEqual(fixture['chunks']['edited'], 1)
        self.assertNotIn('error', fixture)
        with self.base.connect() as connection:
            self.assertEqual(self.disk_sources(connection), [b'# Guide\nFirst edit.\n'])
            self.assertFalse(connection.execute("SELECT 1 FROM public.mycel_file_locations WHERE kind='branch' "
                "AND location LIKE '%added-during-pass%'").fetchone())
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        fixture = reply['repositories']['fixture']
        self.assertNotIn('changedDuringPass', fixture)
        # The disk edit and the new branch, which holds the committed text,
        # are both taken up now; the disk version is the second edit.
        self.assertTrue(fixture['changed'])
        self.assertGreaterEqual(fixture['chunks']['edited'], 1)
        with self.base.connect() as connection:
            self.assertEqual(self.disk_sources(connection), [b'# Guide\nSecond edit, during the pass.\n'])
            self.assertTrue(connection.execute("SELECT 1 FROM public.mycel_file_locations WHERE kind='branch' "
                "AND location LIKE '%added-during-pass%'").fetchone())
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertFalse(reply['repositories']['fixture']['changed'])

    def test_pass_takes_a_foreign_source_from_the_index_and_its_own_pass_marks_the_dependant_stale(self):
        foreign = self.add_repository('foreign', b'# Source\nForeign source.\n')
        guide = self.base.artifact / 'guide.md'
        guide.write_bytes(b'---\nsources: ["foreign:@artifact/answer.md#Source"]\n---\n# Guide\nRests on the foreign source.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'foreign')[0], 0)
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertEqual(reply['repositories']['fixture']['stale'], 0)
        # The foreign source is edited on disk and not ingested; the dependant
        # is edited too, so its pass has to pin the source again. It pins the
        # indexed source and completes: the foreign disk is its own pass's.
        (foreign / 'answer.md').write_bytes(b'# Source\nEdited on disk, not ingested.\n')
        guide.write_bytes(guide.read_bytes().replace(b'Rests on', b'Still rests on'))
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        fixture = reply['repositories']['fixture']
        self.assertNotIn('error', fixture)
        self.assertEqual(fixture['chunks']['edited'], 1)
        self.assertEqual(fixture['stale'], 0)
        self.assertNotIn('changedDuringPass', fixture)
        status, reply = self.invoke('--repo', 'foreign')
        self.assertEqual(status, 0, reply)
        self.assertEqual(reply['repositories']['foreign']['chunks']['edited'], 1)
        self.assertEqual(reply['repositories']['foreign']['dependencyRepositories']['fixture']['stale'], 1)

    def test_pass_reads_each_location_catalog_once_for_its_dependency_run(self):
        for number in range(6):
            (self.base.artifact / f'note{number}.md').write_bytes(
                b'# Note\nFirst.\n# Detail\nSecond.\n# More\nThird.\n')
        self.base.commit()
        from mycel._resolver import SourceResolver
        original = SourceResolver.from_store.__func__
        reads = []

        def counting(cls, connection, settings, **kwargs):
            if kwargs.get('_in_transaction') and not kwargs.get('_read_transaction'):
                reads.append((kwargs.get('kind'), kwargs.get('location')))
            return original(cls, connection, settings, **kwargs)

        with patch.object(SourceResolver, 'from_store', classmethod(counting)):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        chunks = sum(reply['repositories']['fixture']['chunks'].values())
        self.assertGreaterEqual(chunks, 18)
        # One catalog per location for the run, plus the few the batch and the
        # detector read; never one per chunk.
        self.assertLess(len(reads), chunks)
        self.assertLessEqual(len(reads), 2 * len({location for location in reads}) + 4)


class IngestStepUnitTests(unittest.TestCase):
    def test_sources_come_before_their_dependants_and_a_cycle_keeps_capture_order(self):
        from types import SimpleNamespace
        from mycel._located_reconciliation import _sources_first
        files = tuple(SimpleNamespace(primary=SimpleNamespace(root='code', path=path))
                      for path in ('a.py', 'b.md', 'c.py', 'd.py', 'e.py'))
        edges = frozenset({(('code', 'b.md'), ('code', 'a.py')), (('code', 'd.py'), ('code', 'e.py')),
                           (('code', 'e.py'), ('code', 'd.py')), (('code', 'x.py'), ('code', 'c.py'))})
        self.assertEqual([file.primary.path for file in _sources_first(files, edges)],
                         ['b.md', 'c.py', 'a.py', 'd.py', 'e.py'])
        self.assertEqual(parse(['ingest', '--repo', 'a', '--files', '3']).arguments, ('--files', '3'))
        for arguments in (['ingest', '--files', '0'], ['ingest', '--files', 'x'], ['ingest', '--files']):
            with self.assertRaises((MycelError, SystemExit)):
                parse(arguments)


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

    def test_steps_handle_a_bounded_share_keep_it_and_retire_removed_files_once_none_changed_remains(self):
        (self.base.artifact / 'old.md').write_bytes(b'# Old\nRemoved on disk.\n')
        self.edited_notes()
        (self.base.artifact / 'old.md').unlink()
        replies = []
        while not replies or not replies[-1]['complete']:
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
            self.assertEqual(status, 0, reply)
            fixture = reply['repositories']['fixture']
            replies.append(fixture)
            with self.base.connect() as connection:
                self.assertEqual('old.md' in self.disk_text(connection), bool(fixture['remaining']['files']))
            self.assertEqual(self.progress()[0] is None, fixture['complete'] or bool(fixture['remaining']['files']))
        writing = [reply for reply in replies if reply['files']['changed']]
        refreshing = replies[len(writing):]
        # Each step writes one changed file and the next finds one fewer.
        self.assertEqual([reply['remaining']['files'] for reply in writing], list(range(len(writing) - 1, -1, -1)))
        self.assertGreaterEqual(len(writing), 3)
        self.assertEqual([reply['files']['removed'] for reply in writing], [0] * (len(writing) - 1) + [1])
        # Then each step refreshes one unchanged file, resuming after the last.
        self.assertTrue(refreshing)
        self.assertEqual([reply['remaining'] for reply in refreshing],
                         [{'files': 0, 'refresh': left} for left in range(len(refreshing) - 1, -1, -1)])
        self.assertEqual(writing[-1]['remaining']['refresh'], len(refreshing))
        self.assertTrue(all(reply['classificationCheck']['reason'] == 'step' for reply in replies))
        self.assertIsNotNone(self.progress()[1])
        with self.base.connect() as connection:
            self.assertEqual(len(self.second(connection)), 3)
        status, reply = self.invoke('--repo', 'fixture', '--files', '1000')
        self.assertEqual(status, 0, reply)
        fixture = reply['repositories']['fixture']
        self.assertEqual((fixture['changed'], fixture['remaining'], fixture['complete']),
                         (False, {'files': 0, 'refresh': 0}, True))

    def test_a_new_file_updates_the_file_count_of_its_neighbours_without_making_them_changed(self):
        self.edited_notes(2)
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        (self.base.artifact / 'added.md').write_bytes(b'# Added\nNew.\n')
        status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 0, reply)
        fixture = reply['repositories']['fixture']
        self.assertEqual((fixture['files']['changed'], fixture['remaining']['files']), (1, 0))
        with self.base.connect() as connection:
            counts = [row[0] for row in connection.execute("""SELECT l.metadata->'captureFileCount'
                FROM public.mycel_file_locations l JOIN public.mycel_file_versions v ON v.id=l.file_version
                JOIN public.mycel_files f ON f.id=v.file_id WHERE f.repository='fixture' AND l.kind='disk'""")]
        self.assertEqual(set(counts), {len(counts)})

    def test_the_refresh_resumes_after_its_last_file_and_starts_again_after_a_change(self):
        for number in range(4):
            (self.base.artifact / f'note{number}.md').write_bytes(b'# Note\nFirst.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        (self.base.artifact / 'note0.md').write_bytes(b'# Note\nSecond.\n')
        status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 0, reply)
        unchanged = reply['repositories']['fixture']['remaining']['refresh']
        self.assertGreaterEqual(unchanged, 4)
        self.assertIsNotNone(self.progress()[0])
        from mycel import _ingest
        for left in (unchanged - 1, unchanged - 2):
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
            self.assertEqual((status, reply['repositories']['fixture']['remaining']), (0, {'files': 0, 'refresh': left}))
            # An interrupted step keeps the place the last step reached.
            with patch.object(_ingest._CompleteProducer, '__call__', side_effect=KeyboardInterrupt):
                self.assertEqual(self.invoke('--repo', 'fixture', '--files', '1')[0], 2)
        self.assertEqual(len(self.progress()[0]['refreshedThrough']), 3)
        (self.base.artifact / 'note0.md').write_bytes(b'# Note\nThird.\n')
        status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual((status, reply['repositories']['fixture']['remaining']), (0, {'files': 0, 'refresh': unchanged}))
        status, reply = self.invoke('--repo', 'fixture', '--files', '2')
        self.assertEqual((status, reply['repositories']['fixture']['remaining']),
                         (0, {'files': 0, 'refresh': unchanged - 2}))
        status, reply = self.invoke('--repo', 'fixture', '--files', '1000')
        self.assertEqual((status, reply['repositories']['fixture']['complete']), (0, True))
        self.assertIsNone(self.progress()[0])

    def test_an_interrupted_step_loses_only_itself(self):
        self.edited_notes()
        self.assertEqual(self.invoke('--repo', 'fixture', '--files', '1')[0], 0)
        from mycel import _ingest
        with patch.object(_ingest._CompleteProducer, '__call__', side_effect=KeyboardInterrupt):
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 2, reply)
        with self.base.connect() as connection:
            self.assertEqual(len(self.second(connection)), 1)
        status, reply = self.invoke('--repo', 'fixture', '--files', '1')
        self.assertEqual(status, 0, reply)
        self.assertEqual(reply['repositories']['fixture']['remaining'], {'files': 1, 'refresh': 0})
        with self.base.connect() as connection:
            self.assertEqual(len(self.second(connection)), 2)

    def test_a_series_takes_sources_first_and_leaves_no_stale_mark_a_single_pass_would_not(self):
        from mycel._derive import DeriveStore
        code = self.base.code / 'answer.py'
        code.write_text('def answer():\n    return 42\n')
        (self.base.artifact / 'source.md').write_text('# Source\nStable source.\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            DeriveStore(connection).apply(self.base.settings, 'fixture:@code/answer.py#answer',
                                          'fixture:@artifact/source.md#Source', settings_home=self.base.base, build=1)
        code.write_text('def answer():\n    return 43\n')
        (self.base.artifact / 'source.md').write_text('# Source\nEdited source.\n')
        replies = []
        while not replies or not replies[-1]['complete']:
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
            self.assertEqual(status, 0, reply)
            replies.append(reply['repositories']['fixture'])
        self.assertEqual([reply['files']['changed'] for reply in replies[:3]], [1, 1, 0])
        self.assertTrue(all(reply['stale'] == 0 for reply in replies))
        with self.base.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_stale_reasons').fetchone()[0], 0)

    def test_a_file_moved_during_a_series_keeps_its_identity(self):
        (self.base.artifact / 'moved.md').write_bytes(b'# Moved\nKept body.\n')
        self.edited_notes(2)
        with self.base.connect() as connection:
            before = self.base.resolve(connection, 'fixture:@artifact/moved.md#Moved').selection.members[0].chunk.identifier
        os.rename(self.base.artifact / 'moved.md', self.base.artifact / 'zmoved.md')
        writing = 0
        while True:
            status, reply = self.invoke('--repo', 'fixture', '--files', '1')
            self.assertEqual(status, 0, reply)
            writing += bool(reply['repositories']['fixture']['files']['changed'])
            if reply['repositories']['fixture']['complete']:
                break
        self.assertEqual(writing, 3)
        with self.base.connect() as connection:
            after = self.base.resolve(connection, 'fixture:@artifact/zmoved.md#Moved').selection.members[0].chunk.identifier
            self.assertNotIn('moved.md', self.disk_text(connection))
        self.assertEqual(after, before)

    def test_unchanged_origin_link_dependants_are_not_reapplied_and_still_go_stale(self):
        from mycel._dependency_application import DependencyApplicationStore
        from mycel._justify import JustifyStore
        from mycel._source_refs import format_entity_uri
        requirement = '6b2f8c1e-3a4d-4e5f-9a6b-7c8d9e0f1a2b'
        spec = self.base.artifact / 'spec.md'
        spec.write_text('---\nstatus: accepted\n---\n# Spec\n\n## Requirements\n\n'
                        '| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n'
                        f'| FIX-1.1 <!-- {requirement} --> | keep the answer | New | unit |\n')
        (self.base.code / 'answer.py').write_text('def answer():\n    return 42\n')
        self.base.commit()
        self.assertEqual(self.invoke('--repo', 'fixture')[0], 0)
        with self.base.connect() as connection:
            JustifyStore(connection).apply(self.base.settings, 'fixture:@code/answer.py#answer',
                                           format_entity_uri('req', requirement, 'keep the answer'), by='owner', build=1)
        original = DependencyApplicationStore.apply_in_transaction
        applied = []

        def counting(store, settings, file_location, version, **kwargs):
            applied.append((file_location, version))
            return original(store, settings, file_location, version, **kwargs)

        with patch.object(DependencyApplicationStore, 'apply_in_transaction', counting):
            status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertGreaterEqual(reply['repositories']['fixture'].get('originScopesSettled', 0), 1)
        with self.base.connect() as connection:
            scope = connection.execute("""SELECT l.file_location::text,l.chunk_version FROM public.mycel_dependencies d
                JOIN public.mycel_locations l ON l.chunk_version=d.dependant_version
                WHERE d.state ? 'originLink' AND l.kind='disk'""").fetchone()
        self.assertNotIn((scope[0], scope[1]), [(str(location), version) for location, version in applied])
        spec.write_text(spec.read_text().replace('keep the answer', 'keep the answer exact'))
        status, reply = self.invoke('--repo', 'fixture')
        self.assertEqual(status, 0, reply)
        self.assertGreaterEqual(reply['repositories']['fixture']['stale'], 1)
