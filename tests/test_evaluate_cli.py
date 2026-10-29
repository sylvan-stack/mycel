# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Public validation/dispatch acceptance before unavailable feature adapters."""
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from mycel._cli import parse, run
from mycel._evaluate import evaluate


import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from mycel._cli import run


class EvaluateCliTests(unittest.TestCase):
    def configured(self, root, names=("a",)):
        config = root / "config.toml"
        config.write_text('[store]\naddress="postgresql://fixture@unreachable.invalid/owner"\n' +
            ''.join('[repos.' + name + ']\nenabled=true\nartifact_root=' + json.dumps(str(root / name)) +
                '\nevaluation="evaluation.toml"\n' for name in names))
        for name in names:
            (root / name).mkdir()
        return config

    def invoke(self, config, arguments, *, handler=None):
        output, diagnostic = StringIO(), StringIO()
        with patch.dict(os.environ, {"MYCEL_CONFIG": str(config)}):
            status = run(arguments, handlers=None if handler is None else {"evaluate": handler},
                         stdout=output, stderr=diagnostic)
        return status, json.loads(output.getvalue()), diagnostic.getvalue()


# Archived complete imports; restore needed names in their original scope, not at this file tail.
