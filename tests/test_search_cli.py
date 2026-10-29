# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Search syntax and offline query fallback across real bounded adapters."""
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import EmbeddingStandIn

from mycel._credentials import Credentials
from mycel._safeguards import CompletedChild, InvocationPolicy
from mycel._settings import load_settings
from mycel._voyage import HTTPResult, ProviderFailure, VoyageClient


class SearchCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='mycel_search_query_')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'config.toml'
        self.config.write_text('[store]\naddress="postgresql://fixture@localhost/fixture"\n'
            '[search]\nshared_documents=[]\n[embedding]\ndimensions=256\n'
            '[repos.fixture]\nenabled=true\ncode_root=' + json.dumps(str(self.root)) + '\n')
        self.settings = load_settings(path=self.config)
        self.key_reads, self.requests = [], []

    def credentials(self, *, present=True):
        def reader(argv, **kwargs):
            self.key_reads.append(argv)
            return CompletedChild(0 if present else 1, b'fixture-private-key\n', b'', 0.0)
        return Credentials(self.settings, InvocationPolicy('search'), home=self.root, _runner=reader)

    def factory(self, *, failure=None, invalid=False, zero=False):
        def create(credentials, policy, **options):
            service = EmbeddingStandIn(options['tokenizer'].counts)
            def transport(body, key, **limits):
                request = json.loads(body)
                self.requests.append(request)
                if failure is not None:
                    raise ProviderFailure(failure)
                if invalid:
                    return HTTPResult(200, b'{"private":"fixture-private-key"}')
                result = service.request(request)
                if zero:
                    for row in result['data']:
                        row['embedding'] = [0.0] * request['output_dimension']
                return HTTPResult(200, json.dumps(result).encode())
            return VoyageClient(credentials, policy, **options, attempts=1, _transport=transport)
        return create


# Archived complete imports; restore needed names in their original scope, not at this file tail.
