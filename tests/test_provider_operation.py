# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Synthetic, provider-free operator boundaries; no qualification is measured.

All 200-case sets, staged-binding replies and proof-shaped objects below are
controlled unit fixtures. They are never the owner's reviewed release corpus,
actual staged execution, provider results or on-demand requirement acceptance.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mycel_provider_operation_script',
                                              ROOT / 'scripts/qualify_providers.py')
operation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = operation
SPEC.loader.exec_module(operation)


def synthetic_suite(path, *, unavailable=False):
    """Distinct, intentionally simple test bytes, not an authored label set."""
    rows = ['schema_version = 1\n']
    for index in range(200):
        critical, unchanged = index < 50, 50 <= index < 100
        expected = 'still_supported' if unchanged else 'needs_review'
        missing = unavailable and index == 199
        if missing:
            expected = 'unresolved'
        before = f'Synthetic unit fixture before {index}.'
        rows.extend(['[[drift]]', f'id = "synthetic-{index}"',
            'before = ' + json.dumps(before),
            'current = ' + json.dumps(before if unchanged else f'Synthetic unit fixture current {index}.'),
            'dependant = ' + json.dumps(f'Synthetic unit fixture claim {index}.'),
            'expect = ' + json.dumps(expected)])
        if critical:
            rows.append('critical = ' + json.dumps([('negation', 'operator', 'permission', 'deletion')[index % 4]]))
        if unchanged:
            rows.append('unchanged = true')
        if missing:
            rows.append('unavailable = ["baseline"]')
    path.write_text('\n'.join(rows) + '\n')


class ProviderOperationTests(unittest.TestCase):
    @contextmanager
    def fixture(self, *, reviewer=True, staged=False, unavailable=False, limits=''):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reviewer_file = root / 'synthetic-reviewer'
            reviewer_file.write_text('#!/bin/sh\nexit 99\n')
            reviewer_file.chmod(0o700)  # Inspection only; no test executes it.
            settings = root / 'config.toml'
            text = ('[store]\naddress="postgresql://unit@localhost:55432/synthetic_only"\n'
                    '[repos.synthetic]\nenabled=true\nartifact_root=' + json.dumps(str(root)) + '\n'
                    '[drifts]\n' + limits)
            if reviewer:
                text += ('review_command=' + json.dumps([str(reviewer_file)]) + '\n'
                         'review_provider="synthetic-provider"\nreview_model="synthetic-model-1"\n'
                         'review_revision="synthetic-adapter-v1"\n')
            settings.write_text(text)
            suite = root / 'synthetic-unit-cases.toml'
            synthetic_suite(suite, unavailable=unavailable)
            source = {'commit': 'synthetic-unit-commit', 'dirty': True, 'inputsSha256': 'a' * 64}
            frozen = {'src/mycel/data/settings-defaults.json':
                      (ROOT / 'src/mycel/data/settings-defaults.json').read_bytes()}
            staged_shape = {'registry': str(root / 'synthetic-registry'), 'build': '1',
                'program': str(root / 'synthetic-program'), 'sourceInputsSha256': 'a' * 64,
                'filesSha256': 'b' * 64, 'programStampSha256': 'synthetic-metadata-stamp'}
            record = root / 'synthetic-registry/1/build.json'
            record.parent.mkdir(parents=True)
            record.write_text('{"syntheticUnitFixtureOnly":true}\n')
            staged_shape['buildRecordSha256'] = sha256(record.read_bytes()).hexdigest()
            arguments = {'settings_path': settings, 'suite_path': suite, 'repository': 'synthetic'}
            if staged:
                arguments.update(build_registry=root / 'synthetic-registry', build='1')
            with patch.object(operation, 'source_inputs', return_value=(source, frozen)), \
                    patch.object(operation, '_staged_binding', return_value=staged_shape), \
                    patch.object(operation, '_program_stamp', return_value='synthetic-metadata-stamp'):
                yield root, arguments, reviewer_file, source, staged_shape



# Archived complete imports; restore needed names in their original scope, not at this file tail.
