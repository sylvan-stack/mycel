"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_read as _support
from test_read import (chunk ,file ,json ,read_chunk)


class ReadTests(_support.ReadTests):


# TEST-TIER-BEGIN tests/test_read.py::ReadTests.test_context_does_not_read_a_symlink_that_escapes_the_selected_configured_root
    def test_context_does_not_read_a_symlink_that_escapes_the_selected_configured_root(self):
        body = "def selected():\n    return 'indexed'\n"
        original = "# retained prefix\n" + body + "# retained suffix\n"
        start = len("# retained prefix\n".encode())
        member = chunk("selected", body, span=(start, start + len(body.encode())))
        retained = file("escape.py", original, (member,))
        outside = self.home / "outside.py"
        outside.write_text("# outside secret prefix\n" + body + "# outside secret suffix\n")
        (self.code / "escape.py").symlink_to(outside)
        reply = read_chunk(self.resolver(retained), identifier=member.identifier, context=50)
        self.assertEqual(reply["text"], body)
        self.assertEqual(reply["context"], {"before": "", "after": ""})
        self.assertNotIn("file", reply)
        self.assertTrue(reply["unreadable"])
        self.assertNotIn("outside secret", json.dumps(reply))
# TEST-TIER-END tests/test_read.py::ReadTests.test_context_does_not_read_a_symlink_that_escapes_the_selected_configured_root
