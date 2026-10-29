# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Isolated installer ownership, complete staging and preserved older bundles.

Synthetic checked bundles exercise installation, not native release acceptance.
Their shell runtime adapter execs a real isolated interpreter without a mock.
"""
import fcntl
import os
import subprocess
import tempfile
from unittest.mock import patch

from mycel_build import _launcher as installer
from mycel_build._core import BuildError, atomic_json, digest, file_manifest, json_bytes, seal_program
try:
    from .test_launcher_selection import LauncherFixture, ROOT, tree_state
    from .test_launcher_maintenance import peer_lock
except ImportError:
    from test_launcher_selection import LauncherFixture, ROOT, tree_state
    from test_launcher_maintenance import peer_lock


import json
import shlex
import sys
import unittest
from pathlib import Path

from mycel_build._core import (
    atomic_json,
    digest,
    file_manifest,
    json_bytes,
    seal_program,
)

try:
    from .test_launcher_selection import ROOT
    pass
except ImportError:
    from test_launcher_selection import ROOT


def bundle_fixture(base, label):
    """Real immutable payload/manifest; synthetic release-check evidence only."""
    bundle = Path(base) / label
    program = bundle / 'program'
    runtime = program / 'runtime/bin/python3'
    runtime.parent.mkdir(parents=True)
    runtime.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    runtime.chmod(0o755)
    payload = (ROOT / 'src/mycel_build/_launcher_runtime.py').read_text()
    # Exercise the real standalone selector on any test host. Host qualification
    # remains the native packaged check, not this synthetic bundle's evidence.
    assert payload.count('raise SystemExit(main())') == 1
    payload = payload.replace('raise SystemExit(main())',
        'raise SystemExit(main(target="macos-arm64"))') + '\n# fixture ' + label + '\n'
    (program / 'launcher.py').write_text(payload)
    (program / 'licenses').mkdir()
    (program / 'licenses/fixture.txt').write_text('Synthetic bootstrap fixture only.\n')
    pin = json.loads((ROOT / 'packaging/build-lock.json').read_bytes())['targets']['macos-arm64']['runtime']
    atomic_json(program / 'bootstrap-pin.json', {'schemaVersion': 1, 'target': 'macos-arm64', 'runtime': pin})
    seal_program(program)
    manifest = file_manifest(program)
    atomic_json(bundle / 'files.json', manifest)
    record = {'schemaVersion': 1, 'kind': 'mycel-launcher', 'target': 'macos-arm64', 'runtime': pin,
        'program': 'program', 'filesManifest': 'files.json', 'filesSha256': digest(json_bytes(manifest)),
        'payloadSha256': digest(payload.encode()), 'checks': {'passed': True, 'executed': True,
            'target': 'macos-arm64', 'relocations': [
                {'label': label, 'python': '3.14.7', 'machine': 'arm64', 'isolated': True,
                 'dontWriteBytecode': True, 'standaloneSelector': True}
                for label in ('first installation', 'second relocated installation')],
            'networkAndWritesDenied': True, 'sourceReadDenied': True}}
    atomic_json(bundle / 'bundle.json', record)
    (bundle / 'files.json').chmod(0o444)
    (bundle / 'bundle.json').chmod(0o444)
    bundle.chmod(0o555)
    return bundle


class LauncherInstallationTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.


# Archived complete imports; restore needed names in their original scope, not at this file tail.
