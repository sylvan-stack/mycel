# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._settings import load_settings
from mycel._source_refs import parse_source_address
from mycel._summary_request import SummarySection, load_summary_prompts


def section(path, name, source, position=0, *, identifier=None, repository='fixture'):
    raw = source.encode('utf-8')
    place = parse_source_address(f'{repository}:@artifact/{path}#{name}')
    chunk = ResolvedChunk(identifier or path + ':' + name, 1, name, 'document', raw, sha256(raw).hexdigest())
    return SummarySection(SelectionMember(place, chunk), position)


class SummaryRequestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'config.toml'
        self.config.write_text('')
        self.settings = load_settings(path=self.config)
        self.prompts = load_summary_prompts(self.settings)



# Archived complete imports; restore needed names in their original scope, not at this file tail.
