"""Execute frozen automatic checks using the sealed installed product.

The check workspace is disposable development material. Its product path is a
link to the installed package, never a second importable product source copy.
Only closed, sanitized check outcomes cross back into the retained registry.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import ipaddress
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit

from ._core import BuildError, TARGETS, digest, file_manifest, json_bytes
from ._process import run_group, _defer_cleanup_signals
from ._qualification import automatic_contract


_RUNNER = r'''
import contextlib, importlib, io, json, pathlib, platform, sys, sysconfig, unittest
root = pathlib.Path(sys.argv[1])
program = pathlib.Path(sys.argv[2]).resolve()
configuration = json.loads((root / 'gate-config.json').read_text())
if (not sys.flags.isolated or not sys.dont_write_bytecode or platform.python_version() != '3.14.7'
        or sysconfig.get_config_var('Py_GIL_DISABLED')):
    raise RuntimeError('installed automatic gate interpreter differs from its pin')
# Source-reading tests see the same installed bytes as imports. Builder-only
# fixtures remain available from the frozen development inputs beside them.
sys.path[:0] = [str(root / 'src'), str(root), str(root / 'tests')]
from mycel._coverage import KINDS, iter_checks, run_checks
from mycel_build._automatic_backend import InstalledFixtureBackend
from mycel._build_identity import current_build
if current_build() != configuration['build']:
    raise RuntimeError('installed automatic gate Build identity differs')
backend = (InstalledFixtureBackend(configuration['storeAddress'],
    _ownership_journal=pathlib.Path(configuration['ownershipJournal']))
    if configuration['storeAddress'] else None)
native = backend
suite = unittest.defaultTestLoader.discover(str(root / 'tests' / 'top'), top_level_dir=str(root / 'tests'))
observed = []
for check in iter_checks(suite):
    kind = getattr(check, 'check_kind', 'unit')
    if kind not in KINDS:
        raise RuntimeError('a discovered check has an unknown kind')
    if kind in {'unit', 'store'}:
        observed.append({'name': check.id(), 'kind': kind})
if sorted(observed, key=lambda row: row['name']) != configuration['declarations']:
    raise RuntimeError('discovered automatic checks differ from independent frozen inventory')
# Check details can contain exceptions, SQL and arbitrary fixture output. They
# stay in memory and are never emitted or retained by the development tool.
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        if native is not None:
            try:
                native.preflight()
            except Exception:
                backend = None
        report = run_checks(suite, store_backend=backend, workers=configuration['workers'],
                            tests_directory=root / 'tests')
    finally:
        if native is not None:
            from mycel_build._process import _defer_cleanup_signals
            with _defer_cleanup_signals():
                native.recover_owned_databases()
for name, module in tuple(sys.modules.items()):
    if name == 'mycel' or name.startswith('mycel.'):
        origin = getattr(module, '__file__', None)
        if origin is None or not pathlib.Path(origin).resolve().is_relative_to(program):
            raise RuntimeError('automatic gate imported product outside the installed Build')
checks = [{'name': check.name, 'kind': check.kind,
           'status': check.status, 'passed': check.status == 'passed',
           'detail': None if check.status == 'passed' else 'The named automatic check did not pass.'}
          for check in report.checks]
print(json.dumps({'passed': report.passed, 'executed': True, 'checks': checks,
                  'gateErrorCount': len(report.errors), 'inventorySha256': configuration['inventorySha256'],
                  'gateErrors': ['The automatic gate reported an error.'] * len(report.errors),
                  'python': platform.python_version(), 'machine': platform.machine(),
                  'isolated': bool(sys.flags.isolated), 'dontWriteBytecode': sys.dont_write_bytecode,
                  'installedProductImports': True, 'build': current_build()}))
'''


_RECOVER = r'''
import json, pathlib, platform, sys, sysconfig
root = pathlib.Path(sys.argv[1])
program = pathlib.Path(sys.argv[2]).resolve()
configuration = json.loads((root / 'gate-config.json').read_text())
sys.path[:0] = [str(root / 'src'), str(root), str(root / 'tests')]
from mycel._build_identity import current_build
from mycel_build._automatic_backend import recover_owned
if (not sys.flags.isolated or not sys.dont_write_bytecode or platform.python_version() != '3.14.7'
        or sysconfig.get_config_var('Py_GIL_DISABLED') or current_build() != configuration['build']):
    raise RuntimeError('installed cleanup identity differs')
for name, module in tuple(sys.modules.items()):
    if name == 'mycel' or name.startswith('mycel.'):
        origin = getattr(module, '__file__', None)
        if origin is None or not pathlib.Path(origin).resolve().is_relative_to(program):
            raise RuntimeError('automatic cleanup imported product outside the installed Build')
recovered = recover_owned(configuration['storeAddress'], configuration['ownershipJournal'])
if any(pathlib.Path(configuration['ownershipJournal']).iterdir()):
    raise RuntimeError('owned automatic cleanup is incomplete')
print(json.dumps({'recovered': len(recovered), 'remaining': 0}))
'''


@contextmanager
def _automatic_workspace():
    base = Path(tempfile.mkdtemp(prefix='mycel-installed-checks-'))
    state = {'path': base, 'retain': False}
    try:
        yield state
    finally:
        if not state['retain']:
            with _defer_cleanup_signals():
                for path in base.rglob('*'):
                    if path.is_dir() and not path.is_symlink():
                        path.chmod(0o700)
                base.chmod(0o700)
                shutil.rmtree(base)


def _unsafe_process(error):
    state = getattr(error, 'process_state', None)
    return bool(state and (state.get('spawnOutcomeUnconfirmed')
                or (state.get('spawnConfirmed') and state.get('processGroupAbsent') is not True)))


def _recover_automatic(journal, command, options, state):
    if not any(journal.iterdir()):
        return
    try:
        with _defer_cleanup_signals():
            reply = run_group([*command[:-3], _RECOVER, *command[-2:]], **{**options, 'timeout': 60})
        if reply.returncode or reply.stderr or json.loads(reply.stdout).get('remaining') != 0:
            raise BuildError('refused', 'The owned automatic-check databases could not be cleaned.')
        if any(journal.iterdir()):
            raise BuildError('refused', 'The owned automatic-check database journal remains incomplete.')
    except BaseException as error:
        state['retain'] = True
        error.retained_check_workspace = str(state['path'])
        if isinstance(error, (ValueError, TypeError)):
            raise BuildError('refused', 'The owned automatic-check cleanup returned invalid evidence.') from None
        raise


def store_address(settings: Path | None) -> str | None:
    """Read only an explicitly selected server address; retain no settings."""
    if settings is None:
        return None
    try:
        address = tomllib.loads(settings.read_text(encoding="utf-8"))["store"]["address"]
        if not isinstance(address, str):
            raise ValueError("store address type")
        parsed = urlsplit(address)
        if (parsed.scheme not in {"postgres", "postgresql"}
                or not parsed.hostname or parsed.password is not None or parsed.fragment
                or not parsed.path.startswith("/") or not parsed.path[1:] or "/" in parsed.path[1:]):
            raise ValueError("store address")
        parsed.port  # Validate the port before making a sandbox rule.
        return address
    except (OSError, ValueError, KeyError, TypeError):
        raise BuildError("invalid_input", "The explicit check settings require a password-free PostgreSQL server address.") from None


def _failure(target: str, reason: str, *, executed: bool = False) -> dict:
    return {"target": target, "passed": False, "executed": executed, "checks": [],
            "required": 1, "passedCount": 0, "failedCount": 1,
            "automaticQualification": False, "reason": reason}


def _sanitize_report(raw: bytes, number: int, *, contract: dict) -> dict:
    """Validate the closed runner protocol; refuse raw provider/test details."""
    try:
        report = json.loads(raw)
        if (type(report["passed"]) is not bool or report["executed"] is not True
                or report["python"] != "3.14.7" or report["machine"] != "arm64" or report["isolated"] is not True
                or report["dontWriteBytecode"] is not True or report["installedProductImports"] is not True
                or type(report["build"]) is not int or report["build"] != number
                or type(report["gateErrorCount"]) is not int or report["gateErrorCount"] < 0
                or not isinstance(report["checks"], list) or not report["checks"]):
            raise ValueError("gate result")
        names = set()
        for check in report["checks"]:
            if (set(check) != {"name", "kind", "status", "passed", "detail"}
                    or not isinstance(check["name"], str)
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", check["name"]) or check["name"] in names
                    or check["kind"] not in {"unit", "store"}
                    or check["status"] not in {"passed", "failed", "skipped"}
                    or check["passed"] is not (check["status"] == "passed")):
                raise ValueError("check result")
            names.add(check["name"])
            check["detail"] = None if check["passed"] else "The named automatic check did not pass."
        expected_passed = not report["gateErrorCount"] and all(check["passed"] for check in report["checks"])
        if report["passed"] != expected_passed:
            raise ValueError("gate outcome")
        declarations = [{'name': row['name'], 'kind': row['kind']} for row in report['checks']]
        if (sorted(declarations, key=lambda row: row['name']) != contract['declarations']
                or report['inventorySha256'] != contract['inventorySha256']):
            raise ValueError('incomplete frozen inventory')
        return {"passed": report["passed"], "executed": True, "checks": report["checks"],
                "gateErrorCount": report["gateErrorCount"],
                "gateErrors": ["The automatic gate reported an error."] * report["gateErrorCount"],
                "python": "3.14.7", "isolated": True, "dontWriteBytecode": True,
                "installedProductImports": True, "build": number,
                "inventorySha256": contract['inventorySha256'], "completeFrozenInventory": True}
    except (KeyError, TypeError, ValueError):
        raise BuildError("refused", "The installed automatic gate returned incomplete or invalid evidence.") from None


def _run_automatic(program: Path, target: str, frozen: dict[str, bytes], *, source_root: Path,
                  number: str, address: str | None = None, timeout: int = 5400) -> dict:
    """All top-tier unit/store checks; never the mid tier, eval/live or working publication."""
    if target not in TARGETS:
        return _failure(target, "The release target is unsupported.")
    expected_machine = "arm64"
    if platform.system() != "Darwin" or platform.machine() != expected_machine:
        return _failure(target, "Native target automatic checks are unavailable on this host.")
    if not Path("/usr/bin/sandbox-exec").is_file():
        return _failure(target, "The source/developer-denying automatic check boundary is unavailable.")
    if address:
        server = urlsplit(address)
        try:
            loopback = server.hostname == "localhost" or ipaddress.ip_address(server.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            # macOS's sandbox network-address grammar can constrain localhost
            # or any host, but cannot constrain a remote server hostname/IP.
            return _failure(target, "A restrictive automatic-check network boundary for this non-loopback store server is unavailable.")
    retained_program = program.resolve()
    contract = automatic_contract(frozen)
    before = file_manifest(retained_program)
    with _automatic_workspace() as state:
        base = state['path']
        journal = base / 'owned-databases'
        journal.mkdir(mode=0o700)
        workers = min(6, os.cpu_count() or 1, len(contract['declarations']))
        # The owner registry is deliberately unreadable to check processes.
        # Relocate an exact installed copy outside it rather than weakening
        # owner-state denial when the ordinary default registry is selected.
        program = base / "program"
        shutil.copytree(retained_program, program, symlinks=True)
        if file_manifest(program) != before:
            raise BuildError("refused", "The automatic check relocation differs from its sealed installed inputs.")
        workspace = base / "checks"
        workspace.mkdir()
        for name, contents in frozen.items():
            if name.startswith("src/mycel/"):
                continue
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        (workspace / "src").mkdir(exist_ok=True)
        installed = program.resolve() / "runtime/lib/python3.14/site-packages/mycel"
        (workspace / "src/mycel").symlink_to(installed, target_is_directory=True)
        (workspace / "gate-config.json").write_bytes(json_bytes({"build": int(number, 16), "storeAddress": address,
            'declarations': contract['declarations'], 'inventorySha256': contract['inventorySha256'],
            'workers': workers, 'ownershipJournal': str(journal)}))
        (workspace / "gate-config.json").chmod(0o600)
        home = base / "private-home"
        home.mkdir()
        temporary = base / "temporary"
        temporary.mkdir()
        denied = [source_root.resolve(), Path(sys.executable).resolve().parents[1]]
        # Unreachable-target fixtures reserve an unused loopback TCP port by
        # binding without listening. Permit that local reservation; inbound
        # traffic remains denied and outbound has the separate store-only rule.
        sandbox = "(version 1)(allow default)(deny network*)(allow network-bind (local tcp \"localhost:*\"))" + "".join(
            "(deny file-read* file-write* (subpath " + json.dumps(str(path)) + "))" for path in denied)
        sandbox += "(deny file-write* (subpath " + json.dumps(str(program.resolve())) + "))"
        sandbox += "(deny file-write* (subpath " + json.dumps(str(workspace)) + "))"
        owner_home = Path.home().resolve()
        sandbox += "(deny file-read* file-write* (subpath " + json.dumps(str(owner_home / ".mycel")) + "))"
        sandbox += "(deny file-write* (subpath " + json.dumps(str(owner_home)) + "))"
        # Only the explicit configured PostgreSQL server can receive network
        # traffic. Unit checks additionally enforce their existing no-network
        # guard; no embedding/classifier/reviewer endpoint is permitted here.
        if address:
            server = urlsplit(address)
            remote = f"localhost:{server.port or 5432}"
            sandbox += "(allow network-outbound (remote tcp " + json.dumps(remote) + "))"
        command = ["/usr/bin/sandbox-exec", "-p", sandbox,
                   str(program.resolve() / "runtime/bin/python3"), "-I", "-B", "-c", _RUNNER,
                   str(workspace), str(program.resolve())]
        # The explicit store backend may lazily read the caller's fixed store
        # Keychain item. HOME therefore keeps that credential contract while
        # MYCEL_CONFIG and the OS sandbox keep owner settings inaccessible.
        environment = {"HOME": str(owner_home if address else home), "PATH": os.defpath,
                       "LC_ALL": "C", "TMPDIR": str(temporary),
                       "MYCEL_CONFIG": str(home / "missing.toml"), "PYTHONDONTWRITEBYTECODE": "1"}
        environment.update({name: '1' for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
            'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')})
        options = {'cwd': workspace, 'env': environment, 'timeout': timeout}
        try:
            try:
                reply = run_group(command, **options)
            except BaseException as error:
                if _unsafe_process(error):
                    state['retain'] = True
                    error.retained_check_workspace = str(base)
                else:
                    _recover_automatic(journal, command, options, state)
                raise
            _recover_automatic(journal, command, options, state)
            if reply.returncode or reply.stderr:
                raise BuildError("refused", "The installed automatic check process could not complete.")
            result = _sanitize_report(reply.stdout, int(number, 16), contract=contract)
            if file_manifest(program) != before or file_manifest(retained_program) != before:
                raise BuildError("refused", "Automatic checks changed the sealed installed files.")
        except (BuildError, OSError, subprocess.SubprocessError) as error:
            failure = _failure(target, str(error) if isinstance(error, BuildError) else
                "The installed automatic checks could not complete.", executed=not isinstance(error, OSError))
            failure.update(expectedDeclarations=contract['declarations'], inventorySha256=contract['inventorySha256'],
                missingAutomaticChecks=[row['name'] for row in contract['declarations']])
            if state['retain']:
                failure['retainedCheckWorkspace'] = str(base)
            if hasattr(error, 'process_state'):
                failure['processState'] = error.process_state
                failure['executed'] = error.process_state['spawnConfirmed']
            return failure
    failed = sum(not check["passed"] for check in result["checks"])
    declaration_failure = int(bool(result["gateErrorCount"]))
    result.update(target=target, required=len(result["checks"]) + declaration_failure,
                  passedCount=len(result["checks"]) - failed, failedCount=failed + declaration_failure,
                  automaticQualification=False, networkRestrictedToCheckStore=True,
                  sourceReadDenied=True, developerReadDenied=True, installedFilesUnchanged=True,
                  verifiedPrivateRelocation=True, workers=workers, ownershipJournalCleaned=True,
                  fixtureInitialization="Installed SQL schema initializer; explicit init command/audit proofs use uninitialized fixtures.",
                  initCommandProofs=[check["name"] for check in result["checks"]
                                    if check["name"].startswith("test_init_activity.InitActivityStoreTests.")],
                  sourceInputsSha256=digest(json_bytes([{"path": name, "sha256": digest(raw), "size": len(raw)}
                                                       for name, raw in sorted(frozen.items())])),
                  reason=("Every frozen unit/store check and registered automatic proof passed; packaged qualification and publication are separate."
                          if result["passed"] else "One or more automatic checks did not pass."))
    return result


def run_automatic(program: Path, target: str, frozen: dict[str, bytes], *, source_root: Path,
                  number: str, address: str | None = None, timeout: int = 5400) -> dict:
    """Retain a named unavailable gate even if preparing its workspace fails."""
    try:
        return _run_automatic(program, target, frozen, source_root=source_root,
                              number=number, address=address, timeout=timeout)
    except (BuildError, OSError):
        return _failure(target, "The installed automatic check workspace or input integrity is unavailable.")
