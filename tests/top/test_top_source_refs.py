"""Individually selected top-tier cases. Shared fixtures retain their original paths."""
from __future__ import annotations

import test_source_refs as _support
from test_source_refs import (
    parse_source_address,
)


class SourceAddressTests(_support.SourceAddressTests):
    def test_double_encoded_sequences_remain_literal_after_one_decode(self):
        address = parse_source_address("repo:@code/a%252Fb/%252e%252e.py#Name%2523x")
        self.assertEqual((address.path, address.name), ("a%2Fb/%2e%2e.py", "Name%23x"))
        self.assertEqual(address.address, "repo:@code/a%252Fb/%252e%252e.py#Name%2523x")
