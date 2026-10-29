"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_identity as _support
from test_identity import (KnownChunk ,KnownVersion ,document ,identities ,permutations ,reconcile_file ,replace)


class IdentityTests(_support.IdentityTests):


# TEST-TIER-BEGIN tests/test_identity.py::IdentityTests.test_located_alias_assignment_is_maximum_and_independent_of_input_alias_and_storage_order
    def test_located_alias_assignment_is_maximum_and_independent_of_input_alias_and_storage_order(self):
        incoming=(document('X'),document('Y'))
        expected=None
        for aliases in permutations(('X','Y')):
            A=KnownChunk('A',10,(KnownVersion(10,document('CurrentA','current A\n')),
                                 KnownVersion(11,document('ArchiveA'),aliases)))
            B=KnownChunk('B',20,(KnownVersion(20,document('CurrentB','current B\n')),
                                 KnownVersion(21,document('ArchiveB'),('X',))))
            for current_order in permutations(incoming):
                for stored_order in permutations((A,B)):
                    for reverse_versions in (False,True):
                        stored=tuple(replace(chunk,versions=tuple(reversed(chunk.versions)))
                                     if reverse_versions else chunk for chunk in stored_order)
                        plan=reconcile_file(current_order,stored)
                        by_name={decision.incoming.name:decision for decision in plan.decisions}
                        result={name:(item.chunk_id,item.matched_by,item.reference_version,
                                     item.pin_decision,item.pin_version) for name,item in by_name.items()}
                        if expected is None:
                            expected=result
                        self.assertEqual(result,expected)
                        self.assertEqual(identities(plan),{'X':'B','Y':'A'})
                        self.assertEqual(plan.removed,())
        self.assertEqual(expected,{'X':('B','historical_name',21,'inherit_existing',21),
                                   'Y':('A','historical_name',11,'inherit_existing',11)})
# TEST-TIER-END tests/test_identity.py::IdentityTests.test_located_alias_assignment_is_maximum_and_independent_of_input_alias_and_storage_order
