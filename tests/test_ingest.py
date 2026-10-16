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
from mycel._coverage import proves
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
    @proves('MYC-0.6')
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

    @proves('MYC-1.20', 'MYC-1.22', 'MYC-1.30', kind='store')
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

    @proves('MYC-1.21', 'MYC-1.22', kind='store')
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

    @proves('MYC-1.20', 'MYC-1.22', kind='store')
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

    @proves('MYC-1.23', kind='store')
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

    @proves('MYC-1.23', kind='store')
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

    @proves('MYC-1.23', kind='store')
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

    @proves('MYC-1.21', 'MYC-1.23', kind='store')
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

    @proves('MYC-1.22', 'MYC-1.23', kind='store')
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

    @proves('MYC-1.22', 'MYC-1.23', kind='store')
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

    @proves('MYC-1.23', kind='store')
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
