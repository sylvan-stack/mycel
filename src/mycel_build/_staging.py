"""Product-only wheels, offline target staging and bounded installed-load evidence.

This stage retains complete installed automatic qualification but never marks a
Build working. Working publication is a separate release operation.
"""

from __future__ import annotations

import base64
import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sysconfig
import tempfile
import tomllib
import zipfile

from ._core import (BuildError, TARGETS, atomic_json, digest, extract_runtime, file_manifest,
                    install_wheel, json_bytes, load_lock, seal_program, utc_now,
                    read_json, relative_path, snapshot_asset, validate_manifest)
from ._registry import allocate, build_number, read_guard, read_record, registry_path, update_staging
from ._automatic import run_automatic, store_address
from ._packaged_release import probe_packaged_release
from ._qualification import qualification_certificate


def input_manifest(frozen: dict[str, bytes]) -> list[dict]:
    return [{"path": name, "sha256": digest(raw), "size": len(raw)}
            for name, raw in sorted(frozen.items())]


def check_input_manifest(inputs: list[dict]) -> list[dict]:
    # The runner and the code it imports are part of the gate, as are its
    # declarations and tests. Binding only tests/ would miss changed runner
    # semantics even when every named test retained its bytes.
    return [row for row in inputs if row["path"].startswith(("src/", "checks/", "tests/", "scripts/"))
            or row["path"] in {"Makefile", "pyproject.toml"}]


def _read_input_manifest(path: Path) -> list[dict]:
    rows = read_json(path)
    try:
        if not isinstance(rows, list):
            raise ValueError("input manifest")
        names = []
        for row in rows:
            name = row["path"]
            if (set(row) != {"path", "sha256", "size"} or not isinstance(name, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                    or type(row["size"]) is not int or row["size"] < 0):
                raise ValueError("input row")
            relative_path(name)
            names.append(name)
        if names != sorted(set(names)):
            raise ValueError("input order or duplicate")
    except (KeyError, TypeError, ValueError):
        raise BuildError("refused", "The retained source/check input manifest is damaged.") from None
    return rows


def source_inputs(root: Path) -> tuple[dict, dict[str, bytes]]:
    """Freeze each actual source byte; dirty checkouts and untracked inputs count."""
    excluded = {"__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".DS_Store"}
    def paths():
        selected = []
        def select(path):
            if path.is_symlink():
                raise BuildError("refused", "A source input cannot be an editable symbolic link.")
            if path.is_file():
                selected.append(path)
        for name in ("pyproject.toml", "Makefile", "README.md", "package.json", ".gitignore"):
            select(root / name)
        for directory in ("src", "packaging", "tests", "docs", "checks", "scripts"):
            folder = root / directory
            if folder.is_symlink():
                raise BuildError("refused", "A source input directory cannot be an editable symbolic link.")
            for path in folder.rglob("*"):
                if (any(part in excluded or part.endswith(".egg-info") for part in path.relative_to(root).parts)
                        or path.name.endswith((".pyc", ".pyo"))):
                    continue
                select(path)
        return sorted(selected)
    selected = paths()
    frozen = {}
    for path in sorted(selected):
        if path.is_symlink():
            raise BuildError("refused", "A source input cannot be an editable symbolic link.")
        frozen[path.relative_to(root).as_posix()] = path.read_bytes()
    for name, raw in frozen.items():
        if (root / name).read_bytes() != raw:
            raise BuildError("busy", "Source inputs changed while the Build snapshot was being captured.")
    if paths() != selected:
        raise BuildError("busy", "The source input set changed during Build capture.")
    inputs = input_manifest(frozen)
    env = {"PATH": os.defpath, "HOME": str(root), "GIT_OPTIONAL_LOCKS": "0"}
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], env=env,
                                         stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        dirty = bool(subprocess.check_output(["git", "-c", "core.fsmonitor=false", "-C", str(root), "status", "--porcelain"], env=env,
                                            stderr=subprocess.DEVNULL, timeout=10))
    except (OSError, subprocess.SubprocessError):
        commit, dirty = "uncommitted", True
    return {"commit": commit, "dirty": dirty, "inputsSha256": digest(json_bytes(inputs))}, frozen


def verify_source(source_root: Path, registry: Path, number: str) -> dict:
    """Read-only provenance comparison; it neither runs checks nor qualifies a Build."""
    build_number(number)
    root = registry_path(registry)
    identity, frozen = source_inputs(source_root)
    current = input_manifest(frozen)
    with read_guard(root):
        record = read_record(root, number)
        folder = root / number
        if record.get("checkInputs") != "check-inputs.json":
            raise BuildError("refused", "This Build has no complete staged check-input evidence.")
        recorded = _read_input_manifest(folder / "source-inputs.json")
        checks = _read_input_manifest(folder / "check-inputs.json")
        if (digest(json_bytes(recorded)) != record["source"]["inputsSha256"]
                or digest(json_bytes(checks)) != record.get("checkManifestSha256")):
            raise BuildError("refused", "The retained source/check input digests differ from their Build record.")
        # Old stages may have bound only tests/checks. Report that incomplete
        # gate scope explicitly, even if their historical source map is intact.
        complete_checks = checks == check_input_manifest(recorded)
        expected = {row["path"]: row for row in recorded}
        actual = {row["path"]: row for row in current}
        added = sorted(actual.keys() - expected.keys())
        removed = sorted(expected.keys() - actual.keys())
        changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
        same_bytes = current == recorded
        same_git = identity == record["source"]
        lock = frozen.get("packaging/build-lock.json")
        same_lock = lock is not None and digest(lock) == record.get("lockSha256")
        result = {"build": number, "target": record["target"], "status": record["status"],
                  "matches": same_bytes and same_git and same_lock and complete_checks,
                  "sameSourceBytes": same_bytes, "sameSourceIdentity": same_git,
                  "sameLock": same_lock, "completeCheckInputs": complete_checks,
                  "sourceInputsSha256": identity["inputsSha256"],
                  "recordedSourceInputsSha256": record["source"]["inputsSha256"],
                  "differences": {"added": added, "removed": removed, "changed": changed},
                  "automaticQualification": False,
                  "meaning": "Source binding only; retained native results apply to their recorded source and do not establish complete qualification."}
    return result


def product_wheel(frozen: dict[str, bytes], directory: Path) -> tuple[Path, dict]:
    """Write a noneditable PEP 427 pure wheel from the exact frozen product inputs."""
    project = tomllib.loads(frozen["pyproject.toml"].decode())["project"]
    version = project["version"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version) or project["name"] != "mycel":
        raise BuildError("refused", "The product package name or version is unsupported.")
    prefix = f"mycel-{version}.dist-info"
    members = {name[len("src/"):]: raw for name, raw in frozen.items() if name.startswith("src/mycel/")}
    if "mycel/data/build-identity.json" in members:
        raise BuildError("refused", "A source checkout cannot supply an installed Build number.")
    members.pop("mycel/data/development-identity.json", None)
    if "mycel/cli.py" not in members or "mycel/data/voyage-code-4-tokenizer.json" not in members:
        raise BuildError("refused", "The product entry module or required tokenizer data is missing.")
    if any(name.endswith((".pth", ".pyc", ".pyo")) for name in members):
        raise BuildError("refused", "Product inputs contain an editable import hook or bytecode.")
    metadata = ["Metadata-Version: 2.4", "Name: mycel", f"Version: {version}",
                "Summary: A finite command line for maintained repository knowledge",
                f"Requires-Python: {project['requires-python']}"]
    metadata += [f"Requires-Dist: {requirement}" for requirement in project["dependencies"]]
    members[f"{prefix}/METADATA"] = ("\n".join(metadata) + "\n").encode()
    members[f"{prefix}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: mycel_build (stdlib)\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    members[f"{prefix}/entry_points.txt"] = b"[console_scripts]\nmycel = mycel._cli:main\n"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name, raw in sorted(members.items()):
        checksum = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        writer.writerow((name, "sha256=" + checksum, len(raw)))
    writer.writerow((f"{prefix}/RECORD", "", ""))
    members[f"{prefix}/RECORD"] = output.getvalue().encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"mycel-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            wheel.writestr(info, raw)
    return path, project


def install_build_identity(site: Path, number: str) -> None:
    """Add the allocated numeric identity only to this private installed stage."""
    number_value = build_number(number)
    path = site / "mycel/data/build-identity.json"
    if path.exists() or path.is_symlink():
        raise BuildError("refused", "The installed Build identity already exists.")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise BuildError("refused", "The installed product data directory is unavailable.")
    with path.open("xb") as output:
        output.write(json_bytes({"schemaVersion": 1, "build": number_value}))
    path.chmod(0o644)


def installed_command(program: Path, arguments: list[str]) -> list[str]:
    interpreter = program / "runtime" / "bin" / "python3"
    if not interpreter.is_file() or not interpreter.resolve().is_relative_to(program.resolve()):
        raise BuildError("refused", "The bundled interpreter is missing or escapes the Build.")
    return [str(interpreter.absolute()), "-I", "-B", "-m", "mycel.cli", *arguments]


def exec_installed(program: Path, arguments: list[str]) -> None:
    """Preserve cwd/streams/signals and process identity; no installer or extraction."""
    command = installed_command(program, arguments)
    os.execv(command[0], command)


_PROBE = r'''
import importlib, importlib.metadata as metadata, importlib.util, json, os, pathlib, platform, socket, sys, sysconfig
def guard(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.bind', 'subprocess.Popen'}:
        raise RuntimeError('offline installed probe refuses network and child processes')
    if event == 'open' and isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
        raise RuntimeError('offline installed probe refuses file writes')
    if event in {'os.chdir', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir'}:
        raise RuntimeError('offline installed probe refuses mutation')
sys.addaudithook(guard)
root = pathlib.Path(sys.argv[1]).resolve()
expected = json.loads(sys.argv[2])
if not sys.flags.isolated or not sys.dont_write_bytecode or platform.python_version() != '3.14.7':
    raise RuntimeError('interpreter pin or isolated/bytecode flags differ')
if sysconfig.get_config_var('Py_GIL_DISABLED'):
    raise RuntimeError('runtime must be ordinary non-free-threaded CPython')
if any(pathlib.Path(p).resolve() == pathlib.Path.cwd() for p in sys.path if p):
    raise RuntimeError('current directory is an import path')
for name, version in expected.items():
    if metadata.version(name) != version:
        raise RuntimeError('installed dependency pin differs')
from packaging.requirements import Requirement
for name in ['mycel', *expected]:
    for text in metadata.requires(name) or []:
        req = Requirement(text)
        if req.marker is None or req.marker.evaluate({'extra': ''}):
            if metadata.version(req.name) not in req.specifier:
                raise RuntimeError('locked dependency closure is incomplete')
dependency_modules = []
for name in expected:
    module = {'PyYAML': 'yaml', 'scikit-learn': 'sklearn'}.get(name, name.replace('-', '_'))
    dependency_modules.append(module)
import mycel, mycel.cli, pathspec, yaml, tokenizers, tree_sitter, tree_sitter_javascript, tree_sitter_typescript, psycopg, psycopg_binary
import numpy, scipy, sklearn
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits
# Exercise the native numerical path used by mycel-summary-v1 under the same
# offline, no-write boundary as the other product-used extensions.
numerical_vectors = numpy.array([[float(i % 8), float((i % 8) ** 2), float(i // 8) * 20.0,
                                  float((i % 3) + (i // 8) * 10)] for i in range(16)])
with threadpool_limits(limits=1):
    reduced = PCA(n_components=2, svd_solver='full', random_state=0).fit_transform(numerical_vectors)
    mixture = GaussianMixture(n_components=2, covariance_type='spherical', reg_covar=1e-4,
                              random_state=0, n_init=1, max_iter=100, tol=1e-3).fit(reduced)
    probabilities = mixture.predict_proba(reduced)
if (not mixture.converged_ or reduced.shape != (16, 2) or probabilities.shape != (16, 2)
        or not numpy.isfinite(reduced).all() or not numpy.isfinite(probabilities).all()
        or not numpy.isfinite(mixture.bic(reduced)) or not numpy.allclose(probabilities.sum(axis=1), 1.0)):
    raise RuntimeError('bundled summary numerical PCA and spherical Gaussian fit failed')
# Mycel's local tokenizer never imports hf_xet. Initializing that optional Hub
# transport emits cache logs in 1.7.0, so prove its native relocation/loading
# with the dynamic linker only; do not execute its unrelated transport API.
import ctypes
hf_spec = importlib.util.find_spec('hf_xet')
hf_binary = pathlib.Path(hf_spec.origin).parent / 'hf_xet.abi3.so'
hf_handle = ctypes.CDLL(str(hf_binary))
getattr(hf_handle, 'PyInit_hf_xet')
from tree_sitter import Language, Parser
for language, code in [(tree_sitter_javascript.language(), b'function foo() { return 1; }'),
                       (tree_sitter_typescript.language_typescript(), b'function foo(): number { return 1; }'),
                       (tree_sitter_typescript.language_tsx(), b'const x = <span/>;')]:
    if Parser(Language(language)).parse(code).root_node.has_error:
        raise RuntimeError('bundled grammar cannot parse its native target fixture')
from mycel._embedding_plan import load_tokenizer
from mycel._build_identity import current_build
build = current_build()
if type(build) is not int or build <= 0 or (root / 'runtime/lib/python3.14/site-packages/mycel/data/development-identity.json').exists():
    raise RuntimeError('installed product has no numbered immutable Build identity')
tokenizer = load_tokenizer()
if not tokenizer.count('def loaded(): return 1'):
    raise RuntimeError('bundled tokenizer data failed')
for name in ['mycel', 'mycel.cli', *dependency_modules]:
    spec = importlib.util.find_spec(name)
    if not spec.origin or not pathlib.Path(spec.origin).resolve().is_relative_to(root):
        raise RuntimeError('installed module resolved outside its Build')
if importlib.util.find_spec('mycel_build') is not None:
    raise RuntimeError('development release tooling leaked into the product wheel')
print(json.dumps({'python': platform.python_version(), 'machine': platform.machine(), 'macOS': platform.mac_ver()[0],
                  'isolated': bool(sys.flags.isolated), 'dontWriteBytecode': sys.dont_write_bytecode,
                  'nativeModules': ['tokenizers', 'tree_sitter', 'tree_sitter_javascript', 'tree_sitter_typescript', 'psycopg_binary', 'hf_xet', 'numpy', 'scipy', 'sklearn'],
                  'summaryNumericalProbe': {'pca': 'full', 'covariance': 'spherical', 'seed': 0, 'regularization': 1e-4,
                                            'members': 16, 'dimensions': 2, 'components': 2, 'converged': bool(mixture.converged_)},
                  'unusedHfXetValidation': 'dynamic link load and PyInit symbol only; no module initialization or transport call',
                  'cwd': str(pathlib.Path.cwd()), 'dependencyCount': len(expected), 'dependencyModuleOrigins': dependency_modules,
                  'importedDependencyModules': sorted(name for name in dependency_modules if name in sys.modules),
                  'productVersion': metadata.version('mycel'), 'build': build}))
'''


def _delete_tree(path: Path) -> None:
    # Disposal of private test stages only; published files are never passed here.
    if not path.exists():
        return
    for item in path.rglob("*"):
        if not item.is_symlink():
            item.chmod(0o700 if item.is_dir() else 0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


def probe_installed(program: Path, target: str, dependencies: list[dict], *, source_root: Path | None = None,
                    number: str | None = None) -> dict:
    if target not in TARGETS:
        return {"passed": False, "executed": False, "reason": "The release target is unsupported.", "target": target}
    expected_machine = "arm64"
    if platform.system() != "Darwin" or platform.machine() != expected_machine:
        return {"passed": False, "executed": False, "reason": "Native target execution is unavailable on this host.", "target": target}
    if not Path("/usr/bin/sandbox-exec").is_file():
        return {"passed": False, "executed": False, "reason": "The source/network/write-denying installed probe boundary is unavailable.", "target": target}
    with tempfile.TemporaryDirectory(prefix="mycel-packaged-probe-") as directory:
        base = Path(directory)
        caller = base / "caller"
        caller.mkdir()
        hostile = caller / "mycel.py"
        hostile.write_text("raise RuntimeError('current directory import contamination')\n")
        developer = base / "developer-unavailable"
        developer.mkdir(mode=0o000)
        home = base / "private-home"
        home.mkdir()
        env = {"PATH": "/nonexistent", "HOME": str(home), "MYCEL_CONFIG": str(home / "missing.toml"),
               "PYTHONPATH": str(developer), "PYTHONHOME": str(developer), "PYTHONDONTWRITEBYTECODE": "0",
               "OMP_NUM_THREADS": "1"}
        snapshots = []
        versions = {row["name"]: row["version"] for row in dependencies}
        denied_roots = [developer]
        if source_root is not None:
            denied_roots.append(source_root.resolve())
        sandbox = "(version 1)(allow default)(deny network*)(deny file-write*)" + "".join(
            "(deny file-read* (subpath " + json.dumps(str(p)) + "))" for p in denied_roots)
        boundary = ["/usr/bin/sandbox-exec", "-p", sandbox]
        executed = False
        try:
            for label in ("first installation", "second relocated installation"):
                destination = base / label
                shutil.copytree(program, destination, symlinks=True)
                before = file_manifest(destination)
                executed = True
                result = subprocess.run([*boundary, str(destination / "runtime/bin/python3"), "-I", "-B", "-c", _PROBE,
                                         str(destination), json.dumps(versions)], cwd=caller, env=env,
                                        capture_output=True, timeout=60)
                if result.returncode or result.stderr:
                    raise BuildError("refused", "A relocated installed native/data/dependency probe failed.")
                evidence = json.loads(result.stdout)
                if number is not None and evidence["build"] != build_number(number):
                    raise BuildError("refused", "The installed immutable Build number differs from its record.")
                if evidence["machine"] != expected_machine or int(evidence["macOS"].split(".")[0]) < 14:
                    raise BuildError("refused", "The installed interpreter reports the wrong release target.")
                for configuration in ("missing.toml", "invalid.toml"):
                    env["MYCEL_CONFIG"] = str(home / configuration)
                    if configuration == "invalid.toml":
                        (home / configuration).write_text("[invalid\n")
                    for arguments in (["--help"], ["info"]):
                        command = installed_command(destination, list(arguments))
                        reply = subprocess.run([*boundary, *command], cwd=caller, env=env, capture_output=True, timeout=30)
                        if reply.returncode != 0 or reply.stderr:
                            raise BuildError("refused", "A packaged diagnostic command failed its exit contract.")
                        parsed = json.loads(reply.stdout)
                        if (parsed.get("version") != evidence["productVersion"] or "error" in parsed or
                                (arguments == ["--help"] and not parsed.get("commands")) or
                                (arguments == ["info"] and ("settings" not in parsed or "store" not in parsed or
                                                            parsed.get("build") != format(evidence["build"], "x")))):
                            raise BuildError("refused", "A packaged diagnostic command did not return its actual reply.")
                if file_manifest(destination) != before or list(caller.iterdir()) != [hostile]:
                    raise BuildError("refused", "A packaged invocation wrote files or bytecode.")
                snapshots.append(evidence)
                _delete_tree(destination)
        except (BuildError, OSError, ValueError, subprocess.SubprocessError) as error:
            return {"passed": False, "executed": executed and not isinstance(error, OSError),
                    "target": target, "relocations": snapshots, "automaticQualification": False,
                    "reason": (str(error) if isinstance(error, BuildError) else
                               "The installed native probe could not complete its offline checks.")}
        finally:
            developer.chmod(0o700)
            for label in ("first installation", "second relocated installation"):
                _delete_tree(base / label)
        return {"passed": True, "executed": True, "target": target, "relocations": snapshots,
                "diagnosticConfigurations": ["missing", "invalid"], "automaticQualification": False,
                "sourceReadDenied": source_root is not None, "networkAndWritesDenied": True}


def create_stage(source_root: Path, lock_path: Path, assets: Path, registry: Path, target: str,
                 *, store_settings: Path | None = None) -> dict:
    if (platform.python_version() != "3.14.7" or platform.python_implementation() != "CPython"
            or sysconfig.get_config_var("Py_GIL_DISABLED")):
        raise BuildError("refused", "Build creation requires the checked-in development CPython 3.14.7 pin.")
    address = store_address(store_settings)
    lock, row = load_lock(lock_path, target)
    identity, frozen = source_inputs(source_root)
    if json.loads(frozen["packaging/build-lock.json"]) != lock:
        raise BuildError("busy", "The release lock changed during source capture.")
    try:
        constants = [ast.literal_eval(node.value) for node in ast.parse(frozen["src/mycel/_store.py"]).body
                     if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                         and target.id == "STORE_FORMAT" for target in node.targets)]
        if len(constants) != 1 or type(constants[0]) is not int or constants[0] < 1:
            raise ValueError("store format")
        store_format = constants[0]
    except (KeyError, SyntaxError, TypeError, ValueError):
        raise BuildError("refused", "The frozen product has no exact store-format constant.") from None
    metadata = tomllib.loads(frozen["pyproject.toml"].decode())["project"]
    locked_versions = {re.sub(r"[-_.]+", "-", d["name"]).lower(): d["version"] for d in row["dependencies"]}
    for required in metadata["dependencies"]:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^; ]+)", required)
        if not match or locked_versions.get(re.sub(r"[-_.]+", "-", match[1]).lower()) != match[2]:
            raise BuildError("refused", "The direct product dependencies differ from the checked-in lock.")
    record = allocate(registry, target=target, version=metadata["version"], source=identity)
    folder = registry_path(registry) / record["build"]
    try:
        program = folder / "program"
        program.mkdir()
        runtime = program / "runtime"
        site = runtime / "lib" / "python3.14" / "site-packages"
        with tempfile.TemporaryDirectory(prefix="mycel-verified-assets-") as temporary:
            snapshots = Path(temporary)
            archive = snapshot_asset(row["runtime"], assets, snapshots)
            wheels = [snapshot_asset(d, assets, snapshots) for d in row["dependencies"]]
            extract_runtime(archive, runtime)
            for wheel in wheels:
                install_wheel(wheel, site)
        with tempfile.TemporaryDirectory(prefix="mycel-product-wheel-") as temporary:
            wheel, _ = product_wheel(frozen, Path(temporary))
            install_wheel(wheel, site)
            product = {"filename": wheel.name, "sha256": digest(wheel.read_bytes()), "editable": False}
        install_build_identity(site, record["build"])
        licences = program / "licenses"
        licences.mkdir()
        for dependency in [row["runtime"], *row["dependencies"]]:
            for licence in dependency["licenses"]:
                name = licence["path"].removeprefix("licenses/")
                raw = frozen["packaging/" + licence["path"]]
                if digest(raw) != licence["sha256"]:
                    raise BuildError("refused", "A frozen dependency licence differs from its locked digest.")
                destination = licences / name
                if destination.exists() and destination.read_bytes() != raw:
                    raise BuildError("refused", "Dependency licences collide.")
                destination.write_bytes(raw)
        (program / "build-lock.json").write_bytes(frozen["packaging/build-lock.json"])
        seal_program(program)
        manifest = file_manifest(program)
        fingerprint = digest(json_bytes(manifest))
        atomic_json(folder / "files.json", manifest)
        input_rows = input_manifest(frozen)
        atomic_json(folder / "source-inputs.json", input_rows)
        check_inputs = check_input_manifest(input_rows)
        atomic_json(folder / "check-inputs.json", check_inputs)
        data = [m for m in manifest if "/mycel/data/" in m["path"] or m["path"].startswith("licenses/")]
        from ._launcher import stage_launcher
        record = update_staging(registry, record["build"], fields={"launcherBundle": "launcher-bundle"})
        launcher = stage_launcher(source_root, lock_path, assets, folder / "launcher-bundle", target,
                                  frozen=frozen)
        launcher_check = launcher["checks"]
        probe = probe_installed(program, target, row["dependencies"], source_root=source_root, number=record["build"])
        checks = {"schemaVersion": 1, "results": [
                  {"name": "installed_native_and_two_path_probe", **probe},
                  {"name": "independent_launcher_bootstrap_two_path_probe", **launcher_check}],
                  "pending": ["all_unit", "all_store", "packaged_release", "publication"]}
        automatic = None
        if probe["passed"]:
            automatic = run_automatic(program, target, frozen, source_root=source_root,
                                      number=record["build"], address=address)
            checks["results"].append({"name": "installed_automatic_unit_store_gate", **automatic})
            if automatic["executed"] and automatic["checks"]:
                checks["pending"] = ["packaged_release", "publication"]
        automatic_failed = automatic is not None and not automatic["passed"]
        fields = {"program": "program", "runtime": row["runtime"], "dependencies": row["dependencies"],
                  "productWheel": product, "lockSha256": digest(frozen["packaging/build-lock.json"]),
                  "filesSha256": fingerprint, "filesManifest": "files.json", "dataFiles": data,
                  "checkInputs": "check-inputs.json", "checkManifestSha256": digest(json_bytes(check_inputs)),
                  "storeFormat": store_format, "searchReply": 3, "stagedAt": utc_now(),
                  "launcherBundle": "launcher-bundle",
                  "launcherBundleSha256": digest(json_bytes(launcher)),
                  "phase": "staging", "automaticQualification": False,
                  "checks": {"required": 2 + (automatic["required"] if automatic else 0),
                             "passed": int(probe["passed"]) + int(launcher_check["passed"]) + (automatic["passedCount"] if automatic else 0),
                             "failed": int(not probe["passed"]) + int(not launcher_check["passed"]) + (automatic["failedCount"] if automatic else 0),
                             "report": "checks.json"},
                  "reason": (launcher_check["reason"] if not launcher_check["passed"] else automatic["reason"] if automatic is not None else
                             ("Staged files await the complete automatic gate and working publication."
                              if probe["passed"] else probe["reason"]))}
        packaged = {"passed": False, "executed": False, "target": target, "relocations": [],
                    "reason": "Packaged execution requires passing native, bootstrap and complete automatic checks."}
        if probe["passed"] and launcher_check["passed"] and automatic is not None and automatic["passed"]:
            packaged = probe_packaged_release(program, folder / 'launcher-bundle', target,
                source_root=source_root, record={**record, **fields})
        checks['results'].append({'name': 'packaged_selector_and_cli_two_path_probe', **packaged})
        fields['checks']['required'] += 1
        fields['checks']['passed'] += int(packaged['passed'])
        fields['checks']['failed'] += int(not packaged['passed'])
        certificate = qualification_certificate(number=record['build'], source=identity, check_inputs=check_inputs,
            program_sha256=fingerprint, launcher_sha256=fields['launcherBundleSha256'],
            target=target, runtime=row['runtime'], results=checks['results'])
        fields['automaticQualification'] = certificate is not None
        if certificate is not None:
            fields.update(qualification=certificate, phase='qualified',
                reason='Every required automatic and packaged check passed; working publication remains pending.')
            checks['pending'] = ['publication']
        elif not packaged['passed'] and not automatic_failed and probe['passed'] and launcher_check['passed']:
            fields['reason'] = packaged['reason']
        validate_manifest(program, manifest, fingerprint)
        record = update_staging(registry, record["build"], fields=fields, checks=checks,
                                failed=certificate is None)
        (folder / "build.log").write_text("Pinned offline staging completed.\n" +
                                        ("Native installed relocation probes passed.\n" if probe["passed"] else
                                         "Native installed relocation checks failed or could not run.\n") +
                                        (("Installed automatic unit/store checks passed.\n" if automatic["passed"] else
                                          "Installed automatic unit/store checks failed or could not run.\n")
                                         if automatic is not None else "") +
                                        "No working publication or launcher installation was performed.\n")
        return record
    except BaseException as error:
        reason = "Build staging was cancelled." if isinstance(error, KeyboardInterrupt) else "Build staging failed; no working publication occurred."
        try:
            record = update_staging(registry, record["build"], fields={"reason": reason}, failed=True)
            (folder / "build.log").write_text(reason + "\n")
        except (BuildError, OSError):
            pass  # The immutable allocation journal still reserves this identity.
        raise
