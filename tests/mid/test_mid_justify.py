"""Commented mid-tier selections; see MID_TIER.md before restoring a case."""

# Restore the needed imports and class header only for an explicit testing task.
# import test_justify as _support
# from test_justify import (
#     CloneAbsenceStoreTests,
#     CloneEntityMoveStoreTests,
#     CloneGraphStoreTests,
#     ClonePolicyStoreTests,
#     JustifyInputTests,
#     JustifySelectionStoreTests,
#     JustifySharedChunkStoreTests,
#     JustifyStoreTests,
#     OTHER,
#     REQ,
#     SPEC,
#     StringIO,
#     UriMutationStoreTests,
#     UriSyntaxTests,
#     format_entity_uri,
#     json,
#     patch,
#     replace,
#     unittest,
# )


# class UriSyntaxTests(_support.UriSyntaxTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::UriSyntaxTests.test_mutation_preflight_accepts_uuid_spelling_and_rejects_malformed_inputs
#     def test_mutation_preflight_accepts_uuid_spelling_and_rejects_malformed_inputs(self):
#         from mycel._derive import _validate_ref_syntax
#         from mycel._source_refs import read_document_declarations
#         from mycel._markdown import split_markdown
#         uri=format_entity_uri('req',REQ,'title')
#         _validate_ref_syntax((uri,'fixture:@code/value.py#value'))
#         declarations=read_document_declarations(split_markdown('# Answer\n\n<!-- sources:\n'+uri+'\n-->\n'),
#                                                file='fixture:@artifact/answer.md')
#         source=declarations.chunk_sources[0].sources[0]
#         self.assertEqual((source.ref,source.fault),(uri,None))
#         self.assertIsNone(source.address)
#         for raw in ('[req:broken:title]','not a ref',None):
#             with self.subTest(raw=raw),self.assertRaises(MycelError):
#                 _validate_ref_syntax((raw,))
# TEST-TIER-DISABLED-END tests/test_justify.py::UriSyntaxTests.test_mutation_preflight_accepts_uuid_spelling_and_rejects_malformed_inputs



# class UriMutationStoreTests(_support.UriMutationStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::UriMutationStoreTests.test_entity_uris_work_in_declarations_and_existing_mutations
#     def test_entity_uris_work_in_declarations_and_existing_mutations(self):
#         from mycel._derive import DeriveStore
#         from mycel._relate import RelateStore
#         from mycel._verification import ConfirmationStore
#         answer=self.fixture.artifact/'answer.md'
#         answer.write_text('---\nsources: ['+json.dumps(self.uri)+']\n---\n# Answer\nThe value is governed.\n')
#         self.ingest(self.secondary)
#         with self.base.connect() as connection:
#             declared=connection.execute("SELECT source_place,state FROM public.mycel_dependencies "
#                 "WHERE repository='fixture' AND kind='declared'").fetchall()
#             self.assertEqual(len(declared),1)
#             self.assertIn('#FIX-1.1',declared[0][0])
#             self.assertEqual(declared[0][1]['resolution']['state'],'resolved')
#             derived=DeriveStore(connection).apply(self.secondary,self.ref,self.uri)
#             self.assertEqual(derived['source']['repository'],'origins')
#             verification=ConfirmationStore(connection).apply(self.secondary,self.ref,by='fixture-owner')
#             self.assertTrue(verification['current'])
#             related=RelateStore(connection).apply(self.secondary,self.other,self.ref)
#             self.assertTrue(related['changed'])
#             entity_verification=ConfirmationStore(connection).apply(self.secondary,self.other,by='fixture-owner')
#             self.assertTrue(entity_verification['current'])
#         # The UUID keeps the assertion attached when its row moves to another file.
#         moved=self.origins/'renamed.md';self.spec.rename(moved)
#         self.ingest(self.secondary,'origins')
#         with self.base.connect() as connection:
#             row=connection.execute("SELECT source_place,state FROM public.mycel_dependencies "
#                 "WHERE repository='fixture' AND kind='asserted'").fetchone()
#             self.assertIn('renamed.md',row[0])
#             self.assertEqual(row[1]['resolution']['state'],'resolved')
#             self.assertTrue(ConfirmationStore(connection).apply(self.secondary,self.ref)['current'])
#         for arguments in (('derive',self.ref,self.other),('confirm',self.ref,'--by','fixture-owner'),
#                           ('relate','--remove',self.other,self.ref),('confirm',self.other)):
#             status,reply=self.invoke(*arguments)
#             self.assertEqual(status,0,reply)
#         # Wrong tags never select a different entity by a matching display name.
#         wrong=format_entity_uri('dec',REQ,'the same UUID')
#         status,reply=self.invoke('derive',self.ref,wrong)
#         self.assertEqual(status,1)
#         self.assertEqual(reply['error']['code'],'invalid_input')
# TEST-TIER-DISABLED-END tests/test_justify.py::UriMutationStoreTests.test_entity_uris_work_in_declarations_and_existing_mutations



# class JustifyInputTests(_support.JustifyInputTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifyInputTests.test_bulk_format_and_cli_reject_ambiguous_input_before_store_access
#     def test_bulk_format_and_cli_reject_ambiguous_input_before_store_access(self):
#         import tempfile
#         from pathlib import Path
#         from mycel._justify import pairs_from_file
#         from mycel._cli import parse
#         with tempfile.TemporaryDirectory() as directory:
#             path=Path(directory)/'pairs.jsonl'
#             good={'chunk':'fixture:@code/value.py#value','origin':format_entity_uri('req',REQ,'title')}
#             path.write_text('\n'+json.dumps(good)+'\n')
#             self.assertEqual(pairs_from_file(path),((good['chunk'],good['origin']),))
#             for content in ('',json.dumps(good)+'\n'+json.dumps(good),
#                             '{"chunk":"x","chunk":"y","origin":"z"}',
#                             json.dumps({**good,'extra':True}),json.dumps({**good,'origin':False})):
#                 path.write_text(content)
#                 with self.subTest(content=content),self.assertRaises(MycelError):
#                     pairs_from_file(path)
#         for arguments in (('justify',),('justify','x'),('justify','x','y','--file','z'),
#                           ('justify','--file',''),('justify','x','y','--by','')):
#             with self.subTest(arguments=arguments),self.assertRaises(MycelError):
#                 parse(arguments)
#         self.assertEqual(parse(['justify','--file','pairs.jsonl','--by','owner']).arguments,
#                          ('--by','owner','--file','pairs.jsonl'))
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifyInputTests.test_bulk_format_and_cli_reject_ambiguous_input_before_store_access



# class JustifyStoreTests(_support.JustifyStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifyStoreTests.test_atomic_stated_link_and_verification_persist_only_in_index_store
#     def test_atomic_stated_link_and_verification_persist_only_in_index_store(self):
#         from mycel._justify import JustifyStore,checked_link
#         before={path:path.read_bytes() for root in (self.fixture.clone,self.origins,self.fixture.artifact)
#                 for path in root.rglob('*') if path.is_file() and '.git' not in path.parts}
#         with self.base.connect() as connection:
#             reply=JustifyStore(connection).apply(self.secondary,self.ref,self.uri,by='owner',build=1)
#             self.assertEqual(reply['chunk'],self.ref)
#             self.assertEqual(reply['origin'],format_entity_uri('req',REQ,'keep the value stable','origins'))
#             self.assertEqual(reply['link']['method'],'stated')
#             self.assertEqual((reply['link']['confidenceScore'],reply['link']['confidence']),(1.0,'asserted'))
#             self.assertEqual(reply['link']['who'],'owner')
#             self.assertTrue(reply['verification']['current'])
#             self.assertEqual(checked_link(reply['link']),reply['link'])
#             row=connection.execute("SELECT state,baseline_owner FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
#             self.assertEqual(row[0]['originLink'],reply['link'])
#             self.assertEqual(row[0]['originId'],REQ)
#             self.assertIsNotNone(row[1])
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],1)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_activity WHERE kind='justify'").fetchone()[0],1)
#         self.assertEqual(before,{path:path.read_bytes() for path in before})
#         status,reply=self.invoke('justify',self.other,self.ref,'--by','owner')
#         self.assertEqual(status,0,reply)
#         self.assertEqual(reply['link']['origin'],self.ref)
#         # Re-ingesting preserves the statement and its independent evidence.
#         self.ingest(self.secondary)
#         with self.base.connect() as connection:
#             links=connection.execute("SELECT state->'originLink' FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchall()
#             self.assertEqual(len(links),2)
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifyStoreTests.test_atomic_stated_link_and_verification_persist_only_in_index_store

# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifyStoreTests.test_all_pairs_resolve_before_mutation_and_changed_or_generated_inputs_refuse
#     def test_all_pairs_resolve_before_mutation_and_changed_or_generated_inputs_refuse(self):
#         from mycel._justify import JustifyStore
#         from mycel._derive import DeriveStore
#         with self.base.connect() as connection:
#             before=self.state(connection)
#             with patch.object(DeriveStore,'apply_in_transaction',side_effect=AssertionError('No writes before all pairs resolve')):
#                 with self.assertRaises(MycelError):
#                     JustifyStore(connection).apply_pairs(self.secondary,((self.ref,self.uri),(self.other,'fixture:@code/absent.py#x')),build=1)
#             self.assertEqual(self.state(connection),before)
#             (self.fixture.clone/'value.py').write_text('def value():\n    return 2\n')
#             with self.assertRaises(MycelError):
#                 JustifyStore(connection).apply(self.secondary,self.ref,self.uri,build=1)
#             self.assertEqual(self.state(connection),before)
#             (self.fixture.clone/'value.py').write_text('def value():\n    return 1\n')
#             for chunk,origin in ((self.ref,format_entity_uri('dec',REQ,'wrong tag')),
#                                  (self.ref,'fixture:@index/overview'),('fixture:@code/value.py',self.uri)):
#                 with self.subTest(chunk=chunk,origin=origin),self.assertRaises(MycelError):
#                     JustifyStore(connection).apply(self.secondary,chunk,origin)
#                 self.assertEqual(self.state(connection),before)
#         generated=self.fixture.artifact/'generated.md'
#         generated.write_text('---\ngenerated: true\n---\n# Generated\nComputed answer.\n')
#         self.ingest(self.secondary)
#         with self.base.connect() as connection:
#             from mycel._resolver import SourceResolver
#             selection=SourceResolver.from_store(connection,self.secondary).resolve('fixture:@artifact/generated.md',purpose='read').selection
#             before=self.state(connection)
#             for chunk,origin in ((selection.members[0].place.address,self.uri),(self.ref,selection.members[0].place.address)):
#                 with self.subTest(chunk=chunk,origin=origin),self.assertRaises(MycelError):
#                     JustifyStore(connection).apply(self.secondary,chunk,origin,build=1)
#                 self.assertEqual(self.state(connection),before)
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifyStoreTests.test_all_pairs_resolve_before_mutation_and_changed_or_generated_inputs_refuse

# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifyStoreTests.test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically
#     def test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically(self):
#         from mycel._justify import JustifyStore
#         from mycel._verification import ConfirmationStore
#         original=ConfirmationStore.apply_in_transaction
#         count=0
#         def edit_after_second(store,*args,**kwargs):
#             nonlocal count
#             reply=original(store,*args,**kwargs)
#             count+=1
#             if count==2:
#                 (self.fixture.clone/'value.py').write_text('def value():\n    return 9\n')
#             return reply
#         pairs=((self.ref,self.uri),(self.other,'fixture:@code/value.py'))
#         with self.base.connect() as connection:
#             before=self.state(connection)
#             with patch.object(ConfirmationStore,'apply_in_transaction',edit_after_second),self.assertRaises(MycelError):
#                 JustifyStore(connection).apply_pairs(self.secondary,pairs,by='owner',build=1)
#             self.assertEqual(count,2)
#             self.assertEqual(self.state(connection),before)
#         (self.fixture.clone/'value.py').write_text('def value():\n    return 1\n')
#         path=self.base.base/'pairs.jsonl'
#         path.write_text('\n'.join(json.dumps(dict(zip(('chunk','origin'),pair))) for pair in pairs)+'\n')
#         status,reply=self.invoke('justify','--file',str(path),'--by','owner')
#         self.assertEqual(status,0,reply)
#         self.assertEqual(len(reply['justifications']),2)
#         with self.base.connect() as connection:
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchone()[0],2)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],2)
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifyStoreTests.test_bulk_rolls_back_every_pair_when_late_capture_changes_then_succeeds_atomically



# class ClonePolicyStoreTests(_support.ClonePolicyStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::ClonePolicyStoreTests.test_equal_clone_versions_keep_independent_policies_staleness_and_verification_readback
#     def test_equal_clone_versions_keep_independent_policies_staleness_and_verification_readback(self):
#         from mycel._justify import JustifyStore
#         from mycel._verification import ConfirmationStore
#         from mycel._verification_reader import VerificationReader
#         from mycel._provenance_reports import ProvenanceReports
#         with self.base.connect() as connection:
#             primary=JustifyStore(connection).apply(self.primary,self.ref,self.uri,by='primary')
#             secondary=JustifyStore(connection).apply(self.secondary,self.ref,self.other,by='secondary')
#             self.assertEqual(primary['chunkVersion'],secondary['chunkVersion'])
#             for settings,actor in ((self.primary,'primary'),(self.secondary,'secondary')):
#                 from mycel._locks import snapshot_transaction
#                 from mycel._store import checked_store
#                 with checked_store(connection),snapshot_transaction(connection):
#                     report=VerificationReader(connection,settings).list_in_transaction('fixture',history=True)
#                 current=[record for record in report['verifications'] if record['current']]
#                 self.assertEqual([record['by'] for record in current],[actor])
#         self.spec.write_text(SPEC.replace('keep the value stable','keep the value very stable'))
#         self.ingest(self.primary,'origins')
#         with self.base.connect() as connection:
#             primary_reasons=connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall()
#             self.assertTrue(primary_reasons)
#         # A refresh and confirmation of the secondary policy cannot clear
#         # primary marks even though both dependant versions are identical.
#         self.ingest(self.secondary)
#         with self.base.connect() as connection:
#             self.assertEqual(connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall(),primary_reasons)
#             ConfirmationStore(connection).apply(self.secondary,self.ref,by='secondary-again')
#             self.assertEqual(connection.execute('SELECT id FROM public.mycel_stale_reasons').fetchall(),primary_reasons)
#             self.assertEqual(ProvenanceReports(connection,self.secondary).stale('fixture')['count'],0)
#             self.assertEqual(ProvenanceReports(connection,self.primary).stale('fixture')['count'],1)
#         from mycel._search import QueryEmbedding
#         for settings,expected in ((self.primary,True),(self.secondary,False)):
#             status,reply=self.invoke('read',self.ref,'--no-fresh',settings=settings)
#             self.assertEqual(status,0,reply)
#             self.assertEqual(reply['stale'],expected,reply)
#             with patch('mycel._search.prepare_query',return_value=QueryEmbedding(reason='Provider-free fixture')):
#                 status,reply=self.invoke('search','--repo','fixture','--only','code','--no-fresh','return 1',settings=settings)
#             self.assertEqual(status,0,reply)
#             value=next(row for row in reply['results'] if row['name']=='value')
#             self.assertEqual(value['stale'],expected,value)
#         for settings,uri in ((self.primary,REQ),(self.secondary,OTHER)):
#             status,reply=self.invoke('refs','--repo','fixture',settings=settings)
#             self.assertEqual(status,0,reply)
#             refs=reply['repositories'][0]['result']['refs']
#             self.assertEqual(len(refs),1,refs)
#             self.assertIn(uri,refs[0]['originLink']['origin'])
# TEST-TIER-DISABLED-END tests/test_justify.py::ClonePolicyStoreTests.test_equal_clone_versions_keep_independent_policies_staleness_and_verification_readback



# class JustifySelectionStoreTests(_support.JustifySelectionStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifySelectionStoreTests.test_complete_class_family_and_existing_review_are_retained
#     def test_complete_class_family_and_existing_review_are_retained(self):
#         from psycopg.types.json import Jsonb
#         from mycel._justify import JustifyStore
#         from mycel._resolver import SourceResolver
#         source=self.fixture.clone/'value.py'
#         source.write_text(source.read_text()+'\nclass Policy:\n    def first(self):\n        return 1\n    def second(self):\n        return 2\n')
#         self.ingest(self.secondary)
#         origin='fixture:@code/value.py#Policy'
#         with self.base.connect() as connection:
#             selected=SourceResolver.from_store(connection,self.secondary).resolve(origin,purpose='source').selection
#             self.assertEqual(selected.kind,'family')
#             store=JustifyStore(connection)
#             reply=store.apply(self.secondary,self.ref,origin,by='owner')
#             row=connection.execute("SELECT id,state FROM public.mycel_dependencies WHERE kind='asserted'").fetchone()
#             edges=connection.execute('SELECT source_version FROM public.mycel_edges WHERE dependency=%s',(row[0],)).fetchall()
#             self.assertEqual({value[0] for value in edges},{member.chunk.version for member in selected.members})
#             review={'who':'reviewer','when':reply['link']['when'],'outcome':'Reviewed the complete class selection.'}
#             state=row[1];state['originLink']['review']=review
#             connection.execute('UPDATE public.mycel_dependencies SET state=%s WHERE id=%s',(Jsonb(state),row[0]))
#             repeated=store.apply(self.secondary,self.ref,origin,by='owner-again')
#             self.assertEqual(repeated['link']['review'],review)
#             self.assertEqual(repeated['link']['who'],'owner-again')
#             self.assertEqual(len(repeated['verification']['sources']),len(selected.members))
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifySelectionStoreTests.test_complete_class_family_and_existing_review_are_retained



# class CloneAbsenceStoreTests(_support.CloneAbsenceStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::CloneAbsenceStoreTests.test_absence_guard_compares_only_the_selected_clones_retained_witnesses
#     def test_absence_guard_compares_only_the_selected_clones_retained_witnesses(self):
#         source=self.base.code/'primary-only.md'
#         source.write_text('# Source\nA source absent from the other clone.\n')
#         self.base.commit()
#         for root in (self.base.code,self.fixture.clone,self.fixture.artifact):
#             (root/'ambiguous.md').write_text('# Source\nOne of two root candidates.\n')
#         answer=self.fixture.artifact/'answer.md'
#         answer.write_text('---\nsources: ["fixture:@code/primary-only.md#Source", "fixture:ambiguous.md#Source"]\n---\n# Answer\nThe source governs this answer.\n')
#         self.ingest(self.primary)
#         self.ingest(self.secondary)
#         with self.base.connect() as connection:
#             rows=connection.execute("SELECT state FROM public.mycel_dependencies WHERE repository='fixture' AND kind='declared'").fetchall()
#             self.assertEqual(len(rows),4)
#             ambiguous=[row[0] for row in rows if bytes.fromhex(row[0]['rawRef']).decode()=='fixture:ambiguous.md#Source']
#             self.assertEqual(len(ambiguous),2)
#             self.assertTrue(all(row['resolution']['fault']=='ambiguous_path' for row in ambiguous))
#             rows=[row for row in rows if bytes.fromhex(row[0]['rawRef']).decode()!='fixture:ambiguous.md#Source']
#             primary=[row[0] for row in rows if row[0]['declarationLocation']['location']=='disk']
#             secondary=[row[0] for row in rows if row[0]['declarationLocation']['location']!='disk']
#             self.assertEqual(primary[0]['resolution']['state'],'resolved')
#             self.assertEqual(secondary[0]['resolution']['state'],'unresolved')
# TEST-TIER-DISABLED-END tests/test_justify.py::CloneAbsenceStoreTests.test_absence_guard_compares_only_the_selected_clones_retained_witnesses



# class CloneEntityMoveStoreTests(_support.CloneEntityMoveStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::CloneEntityMoveStoreTests.test_refs_keep_each_entitys_actual_file_when_its_row_moves_in_only_one_clone
#     def test_refs_keep_each_entitys_actual_file_when_its_row_moves_in_only_one_clone(self):
#         from mycel._justify import JustifyStore
#         identifier='22222222-3333-4444-8555-666666666666'
#         other='bbbbbbbb-cccc-4ddd-8eee-ffffffffffff'
#         text=SPEC.replace(REQ,identifier).replace(OTHER,other)
#         for root in (self.base.code,self.fixture.clone):
#             (root/'spec.md').write_text(text)
#         self.ingest(self.primary);self.ingest(self.secondary)
#         entity=format_entity_uri('req',identifier,'keep the value stable','fixture')
#         with self.base.connect() as connection:
#             JustifyStore(connection).apply(self.primary,entity,self.uri)
#             JustifyStore(connection).apply(self.secondary,entity,self.other)
#         lines=text.splitlines(keepends=True)
#         (self.fixture.clone/'spec.md').write_text(''.join(line for line in lines if identifier not in line))
#         (self.fixture.clone/'moved.md').write_text(''.join(line for line in lines if other not in line))
#         self.ingest(self.secondary)
#         for settings,path in ((self.primary,'spec.md'),(self.secondary,'moved.md')):
#             status,reply=self.invoke('refs','--repo','fixture',settings=settings)
#             self.assertEqual(status,0,reply)
#             refs=reply['repositories'][0]['result']['refs']
#             self.assertEqual(len(refs),1,refs)
#             self.assertTrue(refs[0]['ownerLocationAvailable'],refs)
#             self.assertEqual(refs[0]['chunk']['path'],path)
#
#         # A subsequent substantive row edit keeps the UUID-owned statement,
#         # while the old exact verification is no longer current.
#         moved=self.fixture.clone/'moved.md'
#         moved.write_text(moved.read_text().replace('keep the value stable','keep the value strictly stable'))
#         self.ingest(self.secondary)
#         status,reply=self.invoke('origins','--repo','fixture','--no-fresh')
#         self.assertEqual(status,0,reply)
#         row=next(row for row in reply['chunks'] if identifier in row['chunk'])
#         self.assertEqual(len(row['links']),1,row)
#         self.assertIn(OTHER,row['links'][0]['origin'])
# TEST-TIER-DISABLED-END tests/test_justify.py::CloneEntityMoveStoreTests.test_refs_keep_each_entitys_actual_file_when_its_row_moves_in_only_one_clone



# class CloneGraphStoreTests(_support.CloneGraphStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::CloneGraphStoreTests.test_cycles_use_the_selected_location_of_every_repository
#     def test_cycles_use_the_selected_location_of_every_repository(self):
#         from mycel._derive import DeriveStore
#         from mycel._justify import JustifyStore
#         with self.base.connect() as connection:
#             DeriveStore(connection).apply(self.primary,self.other,self.ref)
#             with self.assertRaises(MycelError) as caught:
#                 JustifyStore(connection).apply(self.secondary,self.ref,self.other)
#             self.assertIn('cycle',str(caught.exception).lower())
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_dependencies').fetchone()[0],1)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],0)
#         for root in (self.base.code,self.fixture.clone):
#             path=root/'value.py';path.write_text(path.read_text()+'\ndef other():\n    return 2\n')
#         self.ingest(self.primary);self.ingest(self.secondary)
#         other='fixture:@code/value.py#other'
#         with self.base.connect() as connection:
#             # Opposite policies in two clones are individually acyclic.
#             DeriveStore(connection).apply(self.primary,self.ref,other)
#             DeriveStore(connection).apply(self.secondary,other,self.ref)
# TEST-TIER-DISABLED-END tests/test_justify.py::CloneGraphStoreTests.test_cycles_use_the_selected_location_of_every_repository



# class JustifySharedChunkStoreTests(_support.JustifySharedChunkStoreTests):
# TEST-TIER-DISABLED-BEGIN tests/test_justify.py::JustifySharedChunkStoreTests.test_several_origins_for_one_chunk_share_its_complete_final_verification
#     def test_several_origins_for_one_chunk_share_its_complete_final_verification(self):
#         from mycel._justify import JustifyStore
#         from mycel._locks import snapshot_transaction
#         from mycel._store import checked_store
#         from mycel._verification_reader import VerificationReader
#         with self.base.connect() as connection:
#             replies=JustifyStore(connection).apply_pairs(self.secondary,
#                 ((self.ref,self.uri),(self.ref,self.other)),by='owner',build=1)
#             self.assertEqual(len(replies),2)
#             self.assertEqual(replies[0]['verification'],replies[1]['verification'])
#             self.assertEqual(len(replies[0]['verification']['sources']),2)
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_verifications').fetchone()[0],1)
#             self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_dependencies WHERE state ? 'originLink'").fetchone()[0],2)
#             with checked_store(connection),snapshot_transaction(connection):
#                 report=VerificationReader(connection,self.secondary).list_in_transaction('fixture')
#             self.assertEqual([row['id'] for row in report['verifications']],[replies[0]['verification']['id']])
# TEST-TIER-DISABLED-END tests/test_justify.py::JustifySharedChunkStoreTests.test_several_origins_for_one_chunk_share_its_complete_final_verification


# Original deferred imports (restore at the required scope, never blindly at the tail).
# TEST-TIER-IMPORTS-BEGIN tests/test_justify.py:5
# import os
# TEST-TIER-IMPORTS-END tests/test_justify.py:5

# TEST-TIER-IMPORTS-BEGIN tests/test_justify.py:9
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_justify.py:9

raise RuntimeError("Mid-tier tests require an explicitly requested testing task; see MID_TIER.md.")
