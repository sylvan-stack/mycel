"""Pure whole-file identity decisions; no persistence or automatic pinning."""

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from itertools import permutations
import unittest

from mycel._code import chunk_code
from mycel._coverage import load_registry, proves, no_network
from mycel._evidence import ComparisonRecord, EvidenceError, exact_comparison
from mycel._identity import ChunkInput, KnownChunk, KnownVersion, reconcile_file
from mycel._markdown import split_markdown


def document(name, body='', *, source=None):
    parsed=split_markdown(source if source is not None else '# '+name+'\n'+body)
    return ChunkInput.document(parsed.chunks[-1])


def known(identifier, chunk, version=1, *, retained=(), current=None):
    versions=(KnownVersion(version,chunk),*retained)
    return KnownChunk(identifier,version if current is None else current,versions)


def identities(plan):
    return {decision.incoming.name:decision.chunk_id for decision in plan.decisions}


class IdentityTests(unittest.TestCase):
    @proves('MYC-1.17')
    def test_all_file_name_matches_are_reserved_before_any_content_match(self):
        stored=(known('A',document('A','same body\n'),1),
                known('B',document('B','same body\n'),2))
        incoming=(document('New','same body\n'),document('A','edited body\n'))
        plan=reconcile_file(incoming,stored)
        self.assertEqual(identities(plan),{'New':'B','A':'A'})
        self.assertEqual([decision.reason for decision in plan.decisions],['renamed','edited'])
        self.assertEqual([decision.matched_by for decision in plan.decisions],['content','current_name'])
        self.assertEqual(plan.removed,())

    @proves('MYC-1.17')
    def test_reordered_empty_headings_keep_names_and_new_empty_heading_steals_none(self):
        stored=(known('A',document('A'),1),known('B',document('B'),2))
        plan=reconcile_file((document('Introduced'),document('B'),document('A')),stored)
        self.assertEqual(identities(plan),{'Introduced':None,'B':'B','A':'A'})
        self.assertEqual([decision.reason for decision in plan.decisions],['new','unchanged','unchanged'])
        self.assertEqual(plan.removed,())

    @proves('MYC-1.17')
    def test_normalized_empty_document_bodies_never_match_by_content(self):
        for body in ('','\n',' \t\n','\u00a0\u2003\n'):
            with self.subTest(body=body):
                stored=known('empty',document('Original',body))
                plan=reconcile_file((document('Unrelated',body),),(stored,))
                self.assertIsNone(plan.decisions[0].chunk_id)
                self.assertEqual(plan.removed[0].chunk_id,'empty')

    @proves('MYC-1.17')
    def test_a_name_match_preserves_an_empty_chunk_through_a_content_edit(self):
        old=document('A')
        current=document('A','new body\n')
        decision=reconcile_file((current,),(known('A',old),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.reason,decision.matched_by),('A','edited','current_name'))
        self.assertEqual(decision.pin_decision,'requires_authorized_capture')

    @proves('MYC-1.17')
    def test_names_are_exact_and_do_not_use_title_normalization_as_name_identity(self):
        old=document('A','old body\n')
        fullwidth=document('Ａ','unrelated body\n')
        self.assertEqual(old.title_comparison,fullwidth.title_comparison)
        decision=reconcile_file((fullwidth,),(known('A',old),)).decisions[0]
        self.assertEqual(decision.reason,'new')
        case_changed=document('a','old body\n')
        decision=reconcile_file((case_changed,),(known('A',old),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by,decision.reason),('A','content','renamed'))

    @proves('MYC-1.17')
    def test_whole_name_round_prefers_current_name_over_historical_exact_text(self):
        historical=document('B','historical A body\n')
        A=known('A',document('A','current A body\n'),1,retained=(KnownVersion(2,historical),))
        B=known('B',document('B','current B body\n'),3)
        plan=reconcile_file((historical,),(A,B))
        decision=plan.decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by),('B','current_name'))
        self.assertEqual(decision.pin_decision,'requires_authorized_capture')
        self.assertIsNone(decision.version_id)
        self.assertEqual([decision.chunk_id for decision in plan.removed],['A'])

    @proves('MYC-1.17')
    def test_all_current_names_are_reserved_before_historical_name_assignment(self):
        old_B=document('B','old A body\n')
        A=known('A',document('A','current A body\n'),1,retained=(KnownVersion(2,old_B),))
        B=known('B',document('B','current B body\n'),3)
        plan=reconcile_file((old_B,document('A','edited A body\n')),(A,B))
        self.assertEqual(identities(plan),{'B':'B','A':'A'})
        self.assertTrue(all(decision.matched_by=='current_name' for decision in plan.decisions))

    @proves('MYC-1.17', 'MYC-13.15')
    def test_one_exact_empty_child_version_retains_multiple_located_names_and_its_own_pin(self):
        old=ChunkInput.document(split_markdown('# Disk parent\n## Child\n').chunks[-1])
        branch=ChunkInput.document(split_markdown('# Branch parent\n## Child\n').chunks[-1])
        stash=ChunkInput.document(split_markdown('# Stash parent\n## Child\n').chunks[-1])
        version=KnownVersion(10,old,(stash.name,branch.name))
        stored=KnownChunk('child',10,(version,))
        self.assertEqual(len(stored.versions),1)
        self.assertEqual(version.historical_names,(branch.name,stash.name))
        for incoming in (branch,stash):
            self.assertEqual(incoming.source,old.source)
            self.assertFalse(incoming.has_body)
            decision=reconcile_file((incoming,),(stored,)).decisions[0]
            self.assertEqual((decision.chunk_id,decision.matched_by,decision.reference_version),
                             ('child','historical_name',10))
            self.assertEqual((decision.version_action,decision.version_id),('reuse_existing',10))
            self.assertEqual((decision.pin_decision,decision.pin_version),('restore_existing',10))
            self.assertTrue(decision.reuse_vectors)

    @proves('MYC-1.17')
    def test_current_name_reservations_precede_competing_located_aliases(self):
        old=ChunkInput.document(split_markdown('# Disk\n## Child\n').chunks[-1])
        alias=ChunkInput.document(split_markdown('# Branch\n## Child\n').chunks[-1])
        A=KnownChunk('A',1,(KnownVersion(1,old,(alias.name,)),))
        B=known('B',document(alias.name),2)
        for incoming in ((alias,old),(old,alias)):
            for stored in ((A,B),(B,A)):
                plan=reconcile_file(incoming,stored)
                self.assertEqual(identities(plan),{old.name:'A',alias.name:'B'})
                self.assertTrue(all(decision.matched_by=='current_name' for decision in plan.decisions))
                branch_decision=next(decision for decision in plan.decisions if decision.incoming.name==alias.name)
                self.assertNotEqual(branch_decision.version_id,1)
                self.assertEqual(branch_decision.pin_version,2)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_archived_located_alias_restoration_keeps_that_exact_versions_pin(self):
        original=ChunkInput.document(split_markdown('# Old parent\n## Child\n').chunks[-1])
        restored=ChunkInput.document(split_markdown('# Branch parent\n## Child\n').chunks[-1])
        current=ChunkInput.document(split_markdown('# Current parent\n## Child\nLater body.\n').chunks[-1])
        retained=(KnownVersion(20,current),KnownVersion(10,original,(restored.name,)))
        stored=KnownChunk('child',20,retained)
        decision=reconcile_file((restored,),(stored,)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by,decision.reference_version),
                         ('child','historical_name',10))
        self.assertEqual((decision.version_id,decision.pin_decision,decision.pin_version),
                         (10,'restore_existing',10))
        self.assertNotEqual(decision.pin_version,stored.current_version)
        self.assertTrue(decision.reuse_vectors)

    @proves('MYC-1.17')
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

    @proves('MYC-1.17', 'MYC-13.15')
    def test_located_aliases_are_exact_canonical_immutable_labels_and_do_not_duplicate_versions(self):
        old=document('Current')
        version=KnownVersion(1,old,('é','A','e\u0301','é','Ａ'))
        self.assertEqual(version.historical_names,('A','e\u0301','é','Ａ'))
        self.assertNotEqual(version.historical_names[1],version.historical_names[2])
        with self.assertRaises(FrozenInstanceError):
            version.historical_names=('changed',)
        for aliases in (['Alias'],{'Alias'},'Alias',(None,),('',),('bad\0name',),('bad\udcff',)):
            with self.subTest(aliases=aliases),self.assertRaises(EvidenceError) as error:
                KnownVersion(1,old,aliases)
            self.assertEqual(error.exception.status,'invalid_input')
        with self.assertRaises(EvidenceError):
            KnownChunk('one',1,(version,KnownVersion(2,old,('different located name',))))
        with self.assertRaises(EvidenceError):
            KnownChunk('one',1,(version,replace(version,historical_names=('different located name',))))

    @proves('MYC-1.17')
    def test_historical_names_use_deterministic_maximum_assignment(self):
        X,Y=document('X','historical X\n'),document('Y','historical Y\n')
        A=known('A',document('OtherA','current A\n'),1,
                retained=(KnownVersion(2,X),KnownVersion(3,Y)))
        B=known('B',document('OtherB','current B\n'),4,retained=(KnownVersion(5,X),))
        first=reconcile_file((X,Y),(A,B))
        second=reconcile_file((Y,X),(B,replace(A,versions=tuple(reversed(A.versions)))))
        self.assertEqual(identities(first),{'X':'B','Y':'A'})
        self.assertEqual(identities(first),identities(second))
        self.assertTrue(all(decision.matched_by=='historical_name' for decision in first.decisions))

    @proves('MYC-1.17')
    def test_large_historical_name_conflict_chain_is_complete_without_recursive_matching(self):
        count=1100
        incoming=tuple(document(f'N{index:04}','historical body\n') for index in range(count+1))
        stored=[]
        version=1
        for index in range(count+1):
            current=document(f'C{index:04}','current body\n')
            current_id=version
            versions=[KnownVersion(version,current)]
            version+=1
            aliases=([0,count] if index==0 else [index-1,index] if index<count else [count-1])
            for alias in aliases:
                versions.append(KnownVersion(version,incoming[alias]))
                version+=1
            stored.append(KnownChunk(f'K{index:04}',current_id,tuple(versions)))
        plan=reconcile_file(incoming,tuple(stored))
        self.assertEqual(len(plan.decisions),count+1)
        self.assertEqual(plan.removed,())
        self.assertEqual(plan.decisions[-1].chunk_id,'K0000')
        self.assertTrue(all(decision.chunk_id==f'K{index+1:04}'
                            for index,decision in enumerate(plan.decisions[:-1])))
        self.assertTrue(all(decision.matched_by=='historical_name' for decision in plan.decisions))

    @proves('MYC-1.17')
    def test_equal_digest_bytes_do_not_mix_document_and_code_comparison_kinds(self):
        old=document('A','same')
        code=ChunkInput('Other','code',b'same',exact_comparison(b'same','code_text'))
        self.assertEqual(old.comparison.hash,code.comparison.hash)
        plan=reconcile_file((code,),(known('document',old),))
        self.assertEqual(plan.decisions[0].reason,'new')
        self.assertEqual(plan.removed[0].chunk_id,'document')

    @proves('MYC-1.17', 'MYC-13.15')
    def test_exact_utf8_document_body_controls_are_preserved_and_compared(self):
        source=b'# Valid\nbody\x00text\n'
        chunk=ChunkInput.document(split_markdown(source).chunks[0])
        self.assertEqual(chunk.source,source)
        self.assertEqual(chunk.body,'body\x00text\n')
        self.assertEqual(chunk.snapshot_hash,sha256(source).hexdigest())
        self.assertTrue(chunk.has_body)
        decision=reconcile_file((chunk,),(known('valid',chunk,7),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.version_id),('valid',7))
        self.assertEqual(decision.pin_decision,'restore_existing')
        self.assertTrue(decision.reuse_vectors)

    @proves('MYC-1.17')
    def test_duplicate_bodies_match_once_and_use_stable_ids_not_input_storage_order(self):
        stored=(known('B',document('OldB','body\n'),2),known('A',document('OldA','body\n'),1))
        incoming=(document('Y','body\n'),document('X','body\n'),document('Z','body\n'))
        first=reconcile_file(incoming,stored)
        second=reconcile_file(tuple(reversed(incoming)),tuple(reversed(stored)))
        self.assertEqual(identities(first),{'Y':'B','X':'A','Z':None})
        self.assertEqual(identities(first),identities(second))
        self.assertEqual([decision.incoming.name for decision in first.decisions],['Y','X','Z'])
        self.assertEqual(len({decision.chunk_id for decision in first.decisions if decision.chunk_id}),2)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_document_heading_rename_keeps_identity_but_creates_exact_version_and_inherits_pin(self):
        old,current=document('Old','body\n'),document('New','body\n')
        decision=reconcile_file((current,),(known('chunk',old,17),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.reason),('chunk','renamed'))
        self.assertNotEqual(old.snapshot_hash,current.snapshot_hash)
        self.assertEqual((decision.version_action,decision.version_id),('create_new',None))
        self.assertEqual((decision.pin_decision,decision.pin_version),('inherit_existing',17))
        self.assertFalse(decision.reuse_vectors)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_whitespace_or_nfkc_equivalence_is_identity_comparison_not_exact_text_reuse(self):
        old=document('A','Café Ａ  body\n')
        current=document('A','Cafe\u0301 A\n\t body\n')
        self.assertEqual(old.comparison,current.comparison)
        decision=reconcile_file((current,),(known('chunk',old,7),)).decisions[0]
        self.assertEqual(decision.reason,'unchanged')
        self.assertEqual(decision.version_action,'create_new')
        self.assertEqual((decision.pin_decision,decision.pin_version),('inherit_existing',7))
        self.assertFalse(decision.reuse_vectors)
        self.assertEqual(decision.incoming.source,current.source)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_same_exact_text_with_changed_heading_path_metadata_reuses_only_its_own_version(self):
        old=ChunkInput.document(split_markdown('# Old parent\n## Child\nbody\n').chunks[-1])
        current=ChunkInput.document(split_markdown('# New parent\n## Child\nbody\n').chunks[-1])
        self.assertNotEqual(old.name,current.name)
        self.assertEqual(old.source,current.source)
        decision=reconcile_file((current,),(known('child',old,9),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.reason),('child','renamed'))
        self.assertEqual((decision.version_action,decision.version_id),('reuse_existing',9))
        self.assertEqual((decision.pin_decision,decision.pin_version),('restore_existing',9))
        self.assertTrue(decision.reuse_vectors)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_restored_known_text_restores_that_versions_pin_even_when_current_body_differs(self):
        older,current=document('A','old pinned body\n'),document('A','new pinned body\n')
        chunk=known('A',older,10,retained=(KnownVersion(20,current),),current=20)
        decision=reconcile_file((older,),(chunk,)).decisions[0]
        self.assertEqual(decision.chunk_id,'A')
        self.assertEqual((decision.version_id,decision.pin_version),(10,10))
        self.assertEqual(decision.pin_decision,'restore_existing')
        self.assertTrue(decision.reuse_vectors)
        self.assertEqual(decision.reason,'edited')

    @proves('MYC-1.17', 'MYC-13.15')
    def test_historical_empty_heading_name_can_restore_known_version_without_content_match(self):
        original,current=document('Original'),document('Current')
        chunk=known('empty',original,10,retained=(KnownVersion(20,current),),current=20)
        decision=reconcile_file((original,),(chunk,)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by),('empty','historical_name'))
        self.assertEqual((decision.version_id,decision.pin_decision,decision.pin_version),(10,'restore_existing',10))

    @proves('MYC-1.17', 'MYC-13.15')
    def test_archive_body_similarity_does_not_override_substantive_current_name_edit(self):
        older,current=document('A','old   body\n'),document('A','current content\n')
        chunk=known('A',older,10,retained=(KnownVersion(20,current),),current=20)
        equivalent=document('A','old\nbody\n')
        decision=reconcile_file((equivalent,),(chunk,)).decisions[0]
        self.assertEqual(decision.chunk_id,'A')
        self.assertEqual((decision.reason,decision.reference_version),('edited',20))
        self.assertEqual((decision.version_action,decision.pin_decision,decision.pin_version),
                         ('create_new','requires_authorized_capture',None))
        self.assertFalse(decision.reuse_vectors)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_historical_name_equivalence_inherits_the_explicitly_selected_retained_reference(self):
        older,current=document('Original','old   body\n'),document('Current','current content\n')
        chunk=known('A',older,10,retained=(KnownVersion(20,current),),current=20)
        equivalent=document('Original','old\nbody\n')
        decision=reconcile_file((equivalent,),(chunk,)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by,decision.reference_version),
                         ('A','historical_name',10))
        self.assertEqual((decision.version_action,decision.pin_decision,decision.pin_version),
                         ('create_new','inherit_existing',10))
        self.assertFalse(decision.reuse_vectors)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_substantive_content_edit_requests_authorization_and_never_carries_a_fresh_pin(self):
        old,current=document('A','old body\n'),document('A','new substantive body\n')
        decision=reconcile_file((current,),(known('A',old,8),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.reason),('A','edited'))
        self.assertEqual(decision.pin_decision,'requires_authorized_capture')
        self.assertIsNone(decision.pin_version)
        self.assertIsNone(decision.version_id)
        self.assertFalse(decision.reuse_vectors)
        new=reconcile_file((current,),()).decisions[0]
        self.assertEqual((new.reason,new.pin_decision),('new','requires_authorized_capture'))

    @proves('MYC-1.17')
    def test_code_names_share_whole_file_name_reservation_and_empty_body_rule(self):
        old=ChunkInput.code(chunk_code('old.py','def work():\n    return 1\n')[0])
        edit=ChunkInput.code(chunk_code('old.py','def work():\n    return 2\n')[0])
        decision=reconcile_file((edit,),(known('function',old),)).decisions[0]
        self.assertEqual((decision.chunk_id,decision.matched_by,decision.reason),('function','current_name','edited'))
        empty=ChunkInput('Old','code',b' \n\t',exact_comparison(b' \n\t','code_text'))
        introduced=replace(empty,name='New')
        self.assertFalse(empty.has_body)
        self.assertIsNone(reconcile_file((introduced,),(known('empty',empty),)).decisions[0].chunk_id)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_code_path_is_file_metadata_and_exact_text_can_reuse_a_known_version(self):
        old=ChunkInput.code(chunk_code('old.py','def work():\n    return 1\n')[0])
        moved=ChunkInput.code(chunk_code('new.py','def work():\n    return 1\n')[0])
        self.assertEqual(old,moved)
        decision=reconcile_file((moved,),(known('function',old,3),)).decisions[0]
        self.assertEqual(decision.version_id,3)
        self.assertTrue(decision.reuse_vectors)
        # This supplied same-file identity does not infer a genuine file move.

    @proves('MYC-1.18')
    def test_actual_code_declaration_rename_uses_owner_accepted_body_projection(self):
        old=ChunkInput.code(chunk_code('file.py','def original():\n    return 1\n')[0])
        renamed=ChunkInput.code(chunk_code('file.py','def renamed():\n    return 1\n')[0])
        self.assertNotEqual(old.comparison,renamed.comparison)
        self.assertEqual(old.comparison.hash,sha256(old.source).hexdigest())
        decision=reconcile_file((renamed,),(known('function',old),)).decisions[0]
        self.assertEqual(decision.reason,'renamed')
        self.assertEqual(decision.chunk_id,'function')
        self.assertEqual(decision.pin_decision,'inherit_existing')
        self.assertEqual(decision.version_action,'create_new')
        self.assertFalse(decision.reuse_vectors)

    @proves('MYC-1.18')
    def test_parser_rename_keys_cover_structural_languages_without_ignoring_other_bytes(self):
        examples = [
            ('file.py', '# old stays a comment\n@decorator\nasync def old(arg=1):\n    return "old"\n', 'old', 'renamed'),
            ('file.py', 'class Container:\n    def old(self, arg=1):\n        return "old"\n', 'Container.old', 'Container.new'),
            ('file.py', 'def café(arg=1):\r    return "old"\r', 'café', 'nuevo'),
            ('file.ts', 'export function old(arg: number=1) { return "old"; }\n', 'old', 'renamed'),
            ('file.js', 'const old = (arg=1) => "old";\n', 'old', 'renamed'),
            ('file.tsx', 'class Container { old(arg=1) { return "old"; } }\n', 'Container.old', 'Container.new'),
        ]
        for path, source, old_name, new_name in examples:
            with self.subTest(path=path, name=old_name):
                old_chunk = next(c for c in chunk_code(path,source) if c.symbol==old_name)
                # Replace precisely the declaration span, preserving occurrences
                # in comments, strings and the complete body.
                first,last=old_chunk.declaration_name_span
                file_raw=source.encode()
                new_source=(file_raw[:old_chunk.byte_start+first]+new_name.rsplit('.',1)[-1].encode()+file_raw[old_chunk.byte_start+last:]).decode()
                renamed=ChunkInput.code(next(c for c in chunk_code(path,new_source) if c.symbol==new_name))
                old=ChunkInput.code(old_chunk)
                self.assertEqual(old.identity_comparison,renamed.identity_comparison)
                self.assertNotEqual(old.snapshot_hash,renamed.snapshot_hash)
                decision=reconcile_file((renamed,),(known('stable',old),)).decisions[0]
                self.assertEqual((decision.reason,decision.chunk_id),('renamed','stable'))
                changed=new_source.replace('arg=1','arg=2').replace('arg: number=1','arg: number=2')
                edited=ChunkInput.code(next(c for c in chunk_code(path,changed) if c.symbol==new_name))
                self.assertIsNone(reconcile_file((edited,),(known('stable',old),)).decisions[0].chunk_id)
                changed=new_source.replace('"old"','"changed body"')
                edited=ChunkInput.code(next(c for c in chunk_code(path,changed) if c.symbol==new_name))
                self.assertIsNone(reconcile_file((edited,),(known('stable',old),)).decisions[0].chunk_id)

    @proves('MYC-1.18')
    def test_code_and_documents_reserve_every_name_before_body_rename_matches(self):
        for items in (
            (document('A','same\n'),document('B','same\n'),document('New','same\n'),document('A','edited\n')),
            tuple(ChunkInput.code(chunk_code('file.py',source)[0]) for source in (
                'def A():\n    return 1\n','def B():\n    return 1\n',
                'def New():\n    return 1\n','def A():\n    return 2\n')),
        ):
            a,b,new,edit=items
            plan=reconcile_file((new,edit),(known('A',a),known('B',b,2)))
            self.assertEqual([(d.chunk_id,d.reason) for d in plan.decisions],[('B','renamed'),('A','edited')])

    @proves('MYC-1.17', 'MYC-13.15')
    def test_code_whitespace_is_exact_comparison_and_does_not_inherit_document_policy(self):
        old=ChunkInput.code(chunk_code('file.py','def work():\n    return 1\n')[0])
        current=ChunkInput.code(chunk_code('file.py','def work():\n    return  1\n')[0])
        decision=reconcile_file((current,),(known('function',old),)).decisions[0]
        self.assertEqual(decision.chunk_id,'function')
        self.assertEqual(decision.pin_decision,'requires_authorized_capture')
        self.assertFalse(decision.reuse_vectors)

    @proves('MYC-1.17', 'MYC-13.15')
    def test_removed_decisions_are_pure_file_absences_and_input_objects_are_immutable(self):
        chunks=(known('B',document('B'),2),known('A',document('A'),1))
        with no_network():
            plan=reconcile_file((),chunks)
        self.assertEqual([decision.chunk_id for decision in plan.removed],['A','B'])
        self.assertEqual(plan.decisions,())
        self.assertTrue(all(decision.version_action is None and decision.pin_decision is None
                            for decision in plan.removed))
        with self.assertRaises(FrozenInstanceError):
            chunks[0].identifier='other'
        with self.assertRaises(FrozenInstanceError):
            plan.removed=()

    @proves('MYC-13.15')
    def test_parser_hash_or_comparison_revision_forgery_is_refused_without_repair(self):
        parsed=split_markdown('# A\nbody\n').chunks[0]
        for changed in (replace(parsed,content_hash='0'*64),replace(parsed,title_hash='0'*64),
                        replace(parsed,snapshot_hash='0'*64),replace(parsed,comparison_revision='future'),
                        replace(parsed,unicode_version='future')):
            with self.subTest(changed=changed),self.assertRaises(EvidenceError):
                ChunkInput.document(changed)
        old=document('A','body\n')
        with self.assertRaises(EvidenceError) as error:
            replace(old,comparison=replace(old.comparison,revision='future'))
        self.assertEqual(error.exception.status,'unsupported_comparison')
        with self.assertRaises(EvidenceError) as error:
            ChunkInput.document(replace(parsed,snapshot_hash='0'*64))
        self.assertEqual(error.exception.status,'snapshot_corrupt')

    @proves('MYC-13.15')
    def test_forged_parser_text_without_exact_utf8_representation_is_a_sanitized_fault(self):
        parsed=split_markdown('# A\nbody\n').chunks[0]
        code=chunk_code('file.py','def run():\n    pass\n')[0]
        for operation in (lambda:ChunkInput.document(replace(parsed,text='private\udcff')),
                          lambda:ChunkInput.code(replace(code,text='private\udcff'))):
            with self.assertRaises(EvidenceError) as error:
                operation()
            self.assertEqual(error.exception.status,'insufficient_evidence')
            self.assertEqual(str(error.exception),'insufficient_evidence')

    @proves('MYC-13.15')
    def test_invalid_mutable_non_utf8_or_inconsistent_inputs_are_visible_faults(self):
        old=document('A','body\n')
        for values in ({'source':bytearray(old.source)},{'source':b'\xff'},{'body':'not present'},
                       {'name':'bad\0name'},{'comparison':exact_comparison(old.source,'code_text')},
                       {'title_comparison':old.comparison}):
            with self.subTest(values=values),self.assertRaises(EvidenceError):
                replace(old,**values)
        invalid=ComparisonRecord('code_text','sha256-exact-v1','0'*64)
        with self.assertRaises(EvidenceError):
            ChunkInput('code','code',b'bytes',invalid)

    @proves('MYC-13.15')
    def test_duplicate_names_ids_versions_or_exact_text_and_invalid_current_pointer_are_refused(self):
        A=document('A','body\n')
        chunk=known('A',A)
        failures=(lambda:reconcile_file((A,A),(chunk,)),
                  lambda:reconcile_file((A,),(chunk,chunk)),
                  lambda:reconcile_file([A],(chunk,)),
                  lambda:reconcile_file((A,),[chunk]),
                  lambda:KnownVersion(True,A),lambda:KnownVersion(0,A),
                  lambda:KnownChunk('A',2,(KnownVersion(1,A),)),
                  lambda:KnownChunk('A',1,(KnownVersion(1,A),KnownVersion(2,A))),
                  lambda:reconcile_file((A,),(chunk,known('B',document('B'),1))))
        for failure in failures:
            with self.subTest(failure=failure),self.assertRaises(EvidenceError):
                failure()

    @proves('MYC-13.15')
    def test_unit_plans_do_not_qualify_native_identity_or_evidence_persistence(self):
        registry=load_registry()
        for requirement in ('MYC-1.19','MYC-1.31','MYC-1.34','MYC-2.26','MYC-16.2','MYC-16.6'):
            self.assertEqual(registry[requirement].kind,'store')
