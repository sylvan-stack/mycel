"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_justify as _support
from test_justify import (MycelError ,json ,patch)


class JustifyStoreTests(_support.JustifyStoreTests):


# TEST-TIER-BEGIN tests/test_justify.py::JustifyStoreTests.test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically
    def test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically(self):
        from mycel._justify import JustifyStore
        from mycel._verification import ConfirmationStore
        original=ConfirmationStore.apply_in_transaction
        count=0
        def edit_after_second(store,*args,**kwargs):
            nonlocal count
            reply=original(store,*args,**kwargs)
            count+=1
            if count==2:
                (self.fixture.clone/'value.py').write_text('def value():\n    return 9\n')
            return reply
        pairs=((self.ref,self.uri),(self.other,'fixture:@code/value.py'))
        with self.base.connect() as connection:
            before=self.state(connection)
            with patch.object(ConfirmationStore,'apply_in_transaction',edit_after_second),self.assertRaises(MycelError):
                JustifyStore(connection).apply_pairs(self.secondary,pairs,by='owner',build=1)
            self.assertEqual(count,2)
            self.assertEqual(self.state(connection),before)
        (self.fixture.clone/'value.py').write_text('def value():\n    return 1\n')
        path=self.base.base/'pairs.jsonl'
        path.write_text('\n'.join(json.dumps(dict(zip(('chunk','origin'),pair))) for pair in pairs)+'\n')
        status,reply=self.invoke('justify','--file',str(path),'--by','owner')
        self.assertEqual(status,0,reply)
        self.assertEqual(len(reply['justifications']),2)
        with self.base.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchone()[0],2)
            self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],2)
# TEST-TIER-END tests/test_justify.py::JustifyStoreTests.test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically
