# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Release operations and executable rollback against a genuine disposable DB."""

import io
import json
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg import sql

from mycel_build._core import digest, json_bytes
from mycel_build._staging import create_stage

try:
    pass
    from .test_build import _frozen_fixture, _wheel_fixture
    from .test_launcher_installation import bundle_fixture
    pass
except ImportError:
    from test_build import _frozen_fixture, _wheel_fixture
    from test_launcher_installation import bundle_fixture


def store_state(connection):
    """Every public table/xmin, sequence and semantic schema definition."""
    tables = connection.execute("SELECT c.relname FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname").fetchall()
    rows = {name: connection.execute(sql.SQL('SELECT to_jsonb(t),xmin::text FROM public.{} t '
        'ORDER BY to_jsonb(t)::text').format(sql.Identifier(name))).fetchall() for name, in tables}
    sequences = connection.execute("SELECT sequencename FROM pg_catalog.pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename").fetchall()
    state = {'rows': rows, 'sequences': {name: connection.execute(
        sql.SQL('SELECT last_value,is_called FROM public.{}').format(sql.Identifier(name))).fetchone()
        for name, in sequences}}
    queries = {
        'relations': "SELECT c.relname,c.relkind,c.relpersistence,c.reloptions,c.relowner "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' ORDER BY c.relname",
        'columns': "SELECT c.relname,a.attnum,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),"
            "a.attnotnull,a.attidentity,a.attgenerated,pg_catalog.pg_get_expr(d.adbin,d.adrelid) "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped "
            "LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
            "WHERE n.nspname='public' ORDER BY c.relname,a.attnum",
        'constraints': "SELECT c.relname,k.conname,pg_catalog.pg_get_constraintdef(k.oid) "
            "FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' ORDER BY c.relname,k.conname",
        'indexes': "SELECT c.relname,pg_catalog.pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready "
            "FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' ORDER BY c.relname,i.indexrelid",
        'extensions': 'SELECT extname,extversion FROM pg_catalog.pg_extension ORDER BY extname',
        'sequenceDefinitions': "SELECT sequencename,sequenceowner,data_type,start_value,min_value,max_value,"
            "increment_by,cycle,cache_size FROM pg_catalog.pg_sequences "
            "WHERE schemaname='public' ORDER BY sequencename",
        'triggers': "SELECT c.relname,t.tgname,pg_catalog.pg_get_triggerdef(t.oid) "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' ORDER BY c.relname,t.tgname",
        'functions': "SELECT p.oid::regprocedure::text,pg_catalog.pg_get_functiondef(p.oid) "
            "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.prokind IN ('f','p','w') ORDER BY p.oid",
    }
    state['schema'] = {name: connection.execute(query).fetchall() for name, query in queries.items()}
    return state


def stage_fixture_build(base):
    """Run real staging with finite local archive/wheel and check stand-ins."""
    source, assets, registry = (Path(base) / name for name in ('source', 'assets', 'registry'))
    assets.mkdir(parents=True)
    archive = assets / 'runtime.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        member = tarfile.TarInfo('python/bin/python3')
        member.size, member.mode = 1, 0o755
        output.addfile(member, io.BytesIO(b'x'))
    wheel = assets / 'fixturedep-1.0-py3-none-any.whl'
    _wheel_fixture(wheel, {'fixturedep/__init__.py': b''})
    row = {'runtime': {'filename': archive.name, 'sha256': digest(archive.read_bytes()), 'licenses': []},
        'dependencies': [{'name': 'fixturedep', 'version': '1.0', 'filename': wheel.name,
            'sha256': digest(wheel.read_bytes()), 'licenses': []}]}
    lock = {'schemaVersion': 1, 'targets': {'macos-arm64': row}}
    frozen = _frozen_fixture()
    frozen['pyproject.toml'] = (b'[project]\nname="mycel"\nversion="2.0.0"\n'
        b'requires-python=">=3.13"\ndependencies=["fixturedep==1.0"]\n')
    frozen['packaging/build-lock.json'] = json_bytes(lock)
    for name, raw in frozen.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    automatic = {'passed': True, 'executed': True, 'checks': [], 'required': 0,
        'passedCount': 0, 'failedCount': 0, 'reason': 'Local finite fixture only.'}

    def bootstrap(_source, _lock, _assets, destination, _target, **options):
        bundle = bundle_fixture(destination.parent, destination.name)
        return json.loads((bundle / 'bundle.json').read_bytes())

    with patch('mycel_build._staging.platform.python_version', return_value='3.14.7'), \
            patch('mycel_build._staging.load_lock', return_value=(lock, row)), \
            patch('mycel_build._launcher.stage_launcher', side_effect=bootstrap), \
            patch('mycel_build._staging.probe_installed', return_value={'passed': True, 'executed': True}), \
            patch('mycel_build._staging.run_automatic', return_value=automatic):
        return create_stage(source, source / 'packaging/build-lock.json', assets, registry, 'macos-arm64')


class LauncherRollbackStoreTests(unittest.TestCase):
    check_kind = "store"


# Archived complete imports; restore needed names in their original scope, not at this file tail.
