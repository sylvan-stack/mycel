"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_verification_cli as _support
from test_verification_cli import (
    StringIO,
    VerificationCliTests,
    json,
    patch,
    run,
    unittest,
)


class VerificationCliTests(_support.VerificationCliTests):
# TEST-TIER-BEGIN tests/test_verification_cli.py::VerificationCliTests.test_invalid_verification_options_refuse_before_settings_or_store_access
    def test_invalid_verification_options_refuse_before_settings_or_store_access(self):
        cases = (("confirm",), ("confirm", "one", "two"),
                 ("confirm", "one", "--by", " "), ("confirm", "one", "--by"),
                 ("confirm", "one", "--how", "maybe"), ("confirm", "one", "--history"),
                 ("confirm", "one", "--repo", "cellar"), ("verifications", "extra"),
                 ("verifications", "--repo", "a", "--repo", "b"),
                 ("verifications", "--all"), ("verifications", "--how", "read"))
        with patch("mycel._cli.load_settings") as settings:
            for arguments in cases:
                output, diagnostic = StringIO(), StringIO()
                self.assertEqual(run(arguments, stdout=output, stderr=diagnostic), 1)
                self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_input")
                self.assertEqual(diagnostic.getvalue(), "")
            settings.assert_not_called()
# TEST-TIER-END tests/test_verification_cli.py::VerificationCliTests.test_invalid_verification_options_refuse_before_settings_or_store_access
