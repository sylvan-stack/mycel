"""Resolver seams and separate genuine disposable-store selection checks."""

import unittest
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from mycel._resolver import ResolvedChunk, ResolvedFile
from mycel._settings import SettingsSnapshot, _freeze
from mycel._source_refs import SourceAddress
from mycel._store import search_text


def settings(*, enabled=True):
    return SettingsSnapshot(Path('/fictional/settings.toml'), _freeze({
        'repos': {'fixture': {'enabled': enabled}, 'disabled': {'enabled': False}},
        'store': {},}), True, True)


def chunk(name, source, *, kind='document', title=None, family=None, number=1, span=None):
    raw = source.encode()
    return ResolvedChunk(str(uuid4()), number, name, kind, raw, sha256(raw).hexdigest(), span, title, family)


def file(path, source, *, root='artifact', members=(), aliases=()):
    raw = source.encode()
    primary = SourceAddress('fixture', root, path)
    return ResolvedFile(str(uuid4()), 'fixture', primary, aliases or (primary,), raw,
                        sha256(raw).hexdigest(), tuple(members))


class ResolverUnitTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.
# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_file_declarations_are_reused_but_an_edited_capture_is_parsed_afresh
#     def test_file_declarations_are_reused_but_an_edited_capture_is_parsed_afresh(self):
#         from mycel import _source_refs
#         retained = file('guide.md', '---\nrole: authored\nsources: ["fixture:source.md"]\n---\n# Guide\nBody.\n')
#         catalog = SourceResolver(settings(), (retained,))
#         with patch.object(_source_refs, 'read_document_declarations',
#                           wraps=_source_refs.read_document_declarations) as read:
#             original = catalog.files[0].document_declarations
#             for _ in range(100):
#                 self.assertIs(catalog.files[0].document_declarations, original)
#             self.assertEqual(read.call_count, 1)
#             self.assertEqual(original.role, 'authored')
#             edited = retained.source.replace(b'authored', b'derived')
#             current = replace(retained, source=edited, snapshot_hash=sha256(edited).hexdigest())
#             changed = SourceResolver(settings(), (current,)).files[0].document_declarations
#             self.assertEqual(changed.role, 'derived')
#             self.assertEqual(read.call_count, 2)
#             self.assertEqual(original.role, 'authored')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_file_declarations_are_reused_but_an_edited_capture_is_parsed_afresh

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_authoritative_body_nul_survives_and_text_projection_is_not_a_source
#     def test_authoritative_body_nul_survives_and_text_projection_is_not_a_source(self):
#         raw = '# Heading\n雪\0body\0\n'.encode()
#         metadata = {'name':'Heading','kind':'document','bodySpan':{'start':len('# Heading\n'),'end':len(raw)}}
#         member = _resolver._chunk(uuid4(),1,sha256(raw).hexdigest(),memoryview(raw),metadata,{})
#         self.assertEqual(member.source,raw)
#         self.assertEqual(member.body,'雪\0body\0\n'.encode())
#         SourceResolver(settings(),(file('guide.md',raw.decode(),members=(member,)),))
#         with self.assertRaises(MycelError):
#             _resolver._chunk(uuid4(),1,sha256(raw).hexdigest(),search_text(raw),metadata,{})
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_authoritative_body_nul_survives_and_text_projection_is_not_a_source

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_settings_eligibility_precedes_index_lookup_and_preserves_raw_declaration
#     def test_settings_eligibility_precedes_index_lookup_and_preserves_raw_declaration(self):
#         resolver=SourceResolver(settings(), ())
#         for ref, state, fault in [('unregistered:path', 'invalid', 'unregistered_repository'),
#                                   ('disabled:path', 'invalid', 'disabled_repository'),
#                                   ('fixture:path', 'unresolved', 'missing_file'),
#                                   ('not a ref', 'invalid', 'invalid_ref')]:
#             result=resolver.resolve(ref)
#             self.assertEqual((result.declaration,result.state,result.fault),(ref,state,fault))
#             self.assertIsNone(result.selection)
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_settings_eligibility_precedes_index_lookup_and_preserves_raw_declaration

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_aliases_resolve_once_canonical_primary_and_distinct_paths_stay_ambiguous
#     def test_aliases_resolve_once_canonical_primary_and_distinct_paths_stay_ambiguous(self):
#         shared=file('README.md','# Shared\n',aliases=(SourceAddress('fixture','artifact','README.md'),
#                                                         SourceAddress('fixture','code','docs/README.md')))
#         resolver=SourceResolver(settings(), (shared,))
#         self.assertEqual(resolver.resolve('fixture:@code/docs/README.md').selection.file.identifier,shared.identifier)
#         self.assertEqual(resolver.resolve('fixture:docs/README.md').selection.place.address,'fixture:@artifact/README.md')
#         distinct=file('README.md','# Shared\n',root='code')
#         resolver=SourceResolver(settings(),(shared,distinct))
#         result=resolver.resolve('fixture:README.md')
#         self.assertEqual((result.state,result.fault),('unresolved','ambiguous_path'))
#         self.assertEqual(result.candidates,('fixture:@artifact/README.md','fixture:@code/README.md'))
#         self.assertEqual(resolver.resolve('fixture:@code/README.md').selection.file.identifier,distinct.identifier)
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_aliases_resolve_once_canonical_primary_and_distinct_paths_stay_ambiguous

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_exact_heading_paths_and_only_unique_bare_heading_shortcuts
#     def test_exact_heading_paths_and_only_unique_bare_heading_shortcuts(self):
#         members=(chunk('One > Repeat','# Repeat\n',title='Repeat'),
#                  chunk('Two > Repeat','# Repeat\n',title='Repeat'),
#                  chunk('Two > Unique','# Unique\n',title='Unique'))
#         resolver=SourceResolver(settings(),(file('guide.md','whole file',members=members),))
#         result=resolver.resolve('fixture:guide.md#Repeat')
#         self.assertEqual(result.fault,'ambiguous_name')
#         self.assertEqual(len(result.candidates),2)
#         self.assertEqual(resolver.resolve('fixture:guide.md#Unique').selection.members[0].chunk,members[2])
#         self.assertEqual(resolver.resolve('fixture:guide.md#One > Repeat').selection.members[0].chunk,members[0])
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_exact_heading_paths_and_only_unique_bare_heading_shortcuts

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_class_source_family_read_header_and_endpoint_one_chunk
#     def test_class_source_family_read_header_and_endpoint_one_chunk(self):
#         members=(chunk('Policy','class Policy:\n',kind='class'),
#                  chunk('Policy.z',' def z(self): pass\n',kind='method',family='Policy',number=2),
#                  chunk('Policy.a',' def a(self): pass\n',kind='method',family='Policy',number=3),
#                  chunk('Other','class Other:\n',kind='class',number=4))
#         resolver=SourceResolver(settings(),(file('policy.py','whole file',root='code',members=members),))
#         source=resolver.resolve('fixture:policy.py#Policy').selection
#         self.assertEqual(source.kind,'family')
#         self.assertEqual([member.chunk.name for member in source.members],['Policy','Policy.a','Policy.z'])
#         for purpose in ('read','endpoint'):
#             selected=resolver.resolve('fixture:policy.py#Policy',purpose=purpose).selection
#             self.assertEqual((selected.kind,len(selected.members)),('chunk',1))
#         self.assertEqual(resolver.resolve('fixture:policy.py',purpose='endpoint').fault,'one_chunk_required')
#         self.assertEqual(resolver.resolve('fixture:policy.py').selection.file.source,b'whole file')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_class_source_family_read_header_and_endpoint_one_chunk

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_bare_methods_require_unique_match_but_fully_qualified_symbols_work
#     def test_bare_methods_require_unique_match_but_fully_qualified_symbols_work(self):
#         members=(chunk('One.run','one',kind='method',family='One'),
#                  chunk('Two.run','two',kind='method',family='Two',number=2))
#         resolver=SourceResolver(settings(),(file('policy.py','whole',root='code',members=members),))
#         self.assertEqual(resolver.resolve('fixture:policy.py#run').fault,'ambiguous_name')
#         self.assertEqual(resolver.resolve('fixture:policy.py#One.run').selection.members[0].chunk,members[0])
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_bare_methods_require_unique_match_but_fully_qualified_symbols_work

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_nested_class_families_include_owned_continuations_without_expanding_a_continuation
#     def test_nested_class_families_include_owned_continuations_without_expanding_a_continuation(self):
#         members=(chunk('Outer','outer',kind='class',family='Outer'),
#                  chunk('Outer.<end>','fields',kind='class',family='Outer',number=2),
#                  chunk('Outer.Inner','inner',kind='class',family='Outer.Inner',number=3),
#                  chunk('Outer.Inner.run','method',kind='method',family='Outer.Inner',number=4),
#                  chunk('Outerish.run','unrelated',kind='method',family='Outerish',number=5))
#         resolver=SourceResolver(settings(),(file('policy.py','whole',root='code',members=members),))
#         outer=resolver.resolve('fixture:policy.py#Outer').selection
#         self.assertEqual({member.chunk.name for member in outer.members},
#                          {'Outer','Outer.<end>','Outer.Inner','Outer.Inner.run'})
#         inner=resolver.resolve('fixture:policy.py#Outer.Inner').selection
#         self.assertEqual({member.chunk.name for member in inner.members},{'Outer.Inner','Outer.Inner.run'})
#         continuation=resolver.resolve('fixture:policy.py#Outer.<end>').selection
#         self.assertEqual((continuation.kind,len(continuation.members)),('chunk',1))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_nested_class_families_include_owned_continuations_without_expanding_a_continuation

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_real_nested_python_headers_expand_their_own_family_and_continuations_stay_single
#     def test_real_nested_python_headers_expand_their_own_family_and_continuations_stay_single(self):
#         source=('class Policy:\n flag = 1\n class Inner:\n  def a(self): pass\n'
#                 '  between = 1\n  def b(self): pass\n  after = 2\n tail = 3\n'
#                 'class Other:\n def unrelated(self): pass\n')
#         parsed=chunk_code('policy.py',source)
#         members=tuple(chunk(item.symbol,item.text,kind=item.kind,number=number,
#                      family=(item.symbol.split('.<',1)[0] if '.<' in item.symbol else
#                              item.symbol.rpartition('.')[0] or None),
#                      span=(item.byte_start,item.byte_end)) for number,item in enumerate(parsed,1))
#         retained=file('policy.py',source,root='code',members=members)
#         resolver=SourceResolver(settings(),(retained,))
#         by_name={member.name:member for member in members}
#         self.assertEqual(by_name['Policy.Inner'].family,'Policy')
#         self.assertEqual(by_name['Policy.Inner.a'].family,'Policy.Inner')
#         inner=resolver.resolve('fixture:policy.py#Policy.Inner').selection
#         expected={'Policy.Inner','Policy.Inner.a','Policy.Inner.b',
#                   'Policy.Inner.<before Policy.Inner.b>','Policy.Inner.<end>'}
#         self.assertEqual(inner.kind,'family')
#         self.assertEqual({item.chunk.name for item in inner.members},expected)
#         outer=resolver.resolve('fixture:policy.py#Policy').selection
#         self.assertEqual({item.chunk.name for item in outer.members},expected|{'Policy','Policy.<end>'})
#         for name in ('Policy.Inner','Policy.Inner.<before Policy.Inner.b>',
#                      'Policy.Inner.<end>','Policy.<end>'):
#             address=SourceAddress('fixture','code','policy.py',name).address
#             for purpose in ('read','endpoint'):
#                 selection=resolver.resolve(address,purpose=purpose).selection
#                 self.assertEqual((selection.kind,tuple(item.chunk for item in selection.members)),
#                                  ('chunk',(by_name[name],)))
#             if '.<' in name:
#                 selection=resolver.resolve(address).selection
#                 self.assertEqual((selection.kind,tuple(item.chunk for item in selection.members)),
#                                  ('chunk',(by_name[name],)))
#         # The parser disambiguates repeated synthetic symbols with :number.
#         repeated=replace(by_name['Policy.Inner.<end>'],identifier=str(uuid4()),
#                          version=100,name='Policy.Inner.<end>:2',span=None)
#         duplicate_catalog=SourceResolver(settings(),(replace(retained,chunks=members+(repeated,)),))
#         selected=duplicate_catalog.resolve(SourceAddress('fixture','code','policy.py',repeated.name).address).selection
#         self.assertEqual((selected.kind,tuple(item.chunk for item in selected.members)),('chunk',(repeated,)))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_real_nested_python_headers_expand_their_own_family_and_continuations_stay_single

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_read_only_index_namespace_is_ineligible_for_sources_and_mutations
#     def test_read_only_index_namespace_is_ineligible_for_sources_and_mutations(self):
#         member=chunk('Area','# Generated\n',kind='index')
#         place=SourceAddress('fixture','index','summaries','Area')
#         resolver=SourceResolver(settings(),(),index=((place,member),))
#         self.assertEqual(resolver.resolve(place.address,purpose='read').selection.kind,'index')
#         for purpose in ('source','endpoint'):
#             self.assertEqual(resolver.resolve(place.address,purpose=purpose).fault,'ineligible_index')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_read_only_index_namespace_is_ineligible_for_sources_and_mutations

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_legacy_index_read_alias_requires_no_colliding_physical_file
#     def test_legacy_index_read_alias_requires_no_colliding_physical_file(self):
#         member=chunk('Area','# Generated\n',kind='index')
#         place=SourceAddress('fixture','index','summaries','Area')
#         resolver=SourceResolver(settings(),(),index=((place,member),))
#         result=resolver.resolve('fixture:summaries#Area',purpose='read')
#         self.assertEqual((result.state,result.declaration,result.selection.place),
#                          ('resolved','fixture:summaries#Area',place))
#         collision=file('summaries','# Physical\n',members=(chunk('Area','# Physical\n'),))
#         resolver=SourceResolver(settings(),(collision,),index=((place,member),))
#         ambiguous=resolver.resolve('fixture:summaries#Area',purpose='read')
#         self.assertEqual((ambiguous.state,ambiguous.fault),('unresolved','ambiguous_path'))
#         self.assertEqual(set(ambiguous.candidates), {place.address, collision.primary.address})
#         self.assertEqual(resolver.resolve('fixture:summaries#Area',purpose='source').selection.kind,'chunk')
#         physical=SourceAddress(collision.repository,collision.primary.root,collision.primary.path,'Area')
#         self.assertEqual(resolver.resolve(physical.address,purpose='read').selection.kind,'chunk')
#         self.assertEqual(resolver.resolve(place.address,purpose='read').selection.kind,'index')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_legacy_index_read_alias_requires_no_colliding_physical_file

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_file_and_index_chunks_reject_bad_known_metadata_before_resolution
#     def test_file_and_index_chunks_reject_bad_known_metadata_before_resolution(self):
#         valid=chunk('Area','# Exact\n')
#         for bad in (replace(valid,identifier=''),replace(valid,version=0),replace(valid,version=True),
#                     replace(valid,kind=None),replace(valid,title=[]),replace(valid,family={})):
#             with self.subTest(bad=bad):
#                 with self.assertRaises(MycelError):
#                     SourceResolver(settings(),(file('guide.md','# Exact\n',members=(bad,)),))
#                 with self.assertRaises(MycelError):
#                     SourceResolver(settings(),(),index=((SourceAddress('fixture','index','summaries','Area'),bad),))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_file_and_index_chunks_reject_bad_known_metadata_before_resolution

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_ambiguity_candidates_are_bounded_and_record_total_distinct_places
#     def test_ambiguity_candidates_are_bounded_and_record_total_distinct_places(self):
#         members=tuple(chunk(f'Parent {number:03} > Repeat','# Repeat\n',title='Repeat',number=number+1)
#                       for number in range(30))
#         resolver=SourceResolver(settings(),(file('guide.md','whole',members=members),))
#         result=resolver.resolve('fixture:guide.md#Repeat')
#         self.assertEqual((result.fault,len(result.candidates),result.candidate_count),('ambiguous_name',20,30))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_ambiguity_candidates_are_bounded_and_record_total_distinct_places

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_recorded_comparison_and_body_bytes_stay_exact_immutable_and_location_specific
#     def test_recorded_comparison_and_body_bytes_stay_exact_immutable_and_location_specific(self):
#         text='# Heading\n雪 body\n'
#         raw=text.encode()
#         metadata={'name':'Heading','kind':'document','bodySpan':{'start':len('# Heading\n'),'end':len(raw)}}
#         comparison={'kind':'document_body','revision':'recorded-old','hash':'public-recorded-digest'}
#         result=_resolver._chunk(uuid4(),1,sha256(raw).hexdigest(),raw,metadata,comparison)
#         self.assertEqual(result.body,'雪 body\n'.encode())
#         self.assertEqual(result.body_span,(len('# Heading\n'),len(raw)))
#         self.assertEqual(result.comparison['revision'],'recorded-old')
#         with self.assertRaises(TypeError):
#             result.comparison['revision']='new'
#         comparison['revision']='mutated'
#         self.assertEqual(result.comparison['revision'],'recorded-old')
#         with self.assertRaises(MycelError):
#             _resolver._chunk(uuid4(),1,sha256(raw).hexdigest(),raw,
#                              {**metadata,'bodySpan':{'start':len('# Heading\n')+1,'end':len(raw)}},comparison)
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_recorded_comparison_and_body_bytes_stay_exact_immutable_and_location_specific

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_corrupt_bytes_bad_spans_duplicate_versions_and_aliases_are_refused
#     def test_corrupt_bytes_bad_spans_duplicate_versions_and_aliases_are_refused(self):
#         good=file('guide.md','# Exact\n',members=(chunk('Exact','# Exact\n',span=(0,8)),))
#         for bad in (replace(good,source=b'changed'),replace(good,aliases=()),
#                     replace(good,chunks=(replace(good.chunks[0],span=(1,8)),)),
#                     replace(good,chunks=(good.chunks[0],good.chunks[0]))):
#             with self.assertRaises(MycelError) as error:
#                 SourceResolver(settings(),(bad,))
#             self.assertEqual(error.exception.code.value,'store_format')
#         with self.assertRaises(MycelError):
#             SourceResolver(settings(),(good,good))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_corrupt_bytes_bad_spans_duplicate_versions_and_aliases_are_refused

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverUnitTests.test_branch_and_stash_need_explicit_location_before_any_store_access
#     def test_branch_and_stash_need_explicit_location_before_any_store_access(self):
#         for kind in ('branch','stash'):
#             with self.assertRaises(MycelError) as error:
#                 SourceResolver.from_store(object(),settings(),kind=kind)
#             self.assertEqual(error.exception.code.value,'invalid_input')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverUnitTests.test_branch_and_stash_need_explicit_location_before_any_store_access


class ResolverStoreTests(unittest.TestCase):
    check_kind = "store"

    def seed(self, connection, *, path='guide.md', root='artifact', source='# Exact\n',
             name='Exact', kind='document', title='Exact', family=None, aliases=(),
             location_kind='disk', location='disk', file_id=None, chunk_id=None,
             chunk_source=None, span=None, file_metadata=None, location_metadata=None):
        file_id=file_id or uuid4()
        file_version, file_location, chunk_id=uuid4(),uuid4(),chunk_id or uuid4()
        raw=source.encode()
        digest=sha256(raw).hexdigest()
        connection.execute("INSERT INTO public.mycel_repository_state VALUES ('fixture',NULL,'[]') ON CONFLICT DO NOTHING")
        connection.execute('INSERT INTO public.mycel_files VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (file_id,'fixture',root,path,'documents' if kind=='document' else 'code'))
        file_version=connection.execute('INSERT INTO public.mycel_file_versions VALUES (%s,%s,%s,%s,%s) '
                           'ON CONFLICT (file_id,snapshot_hash) DO UPDATE SET metadata=mycel_file_versions.metadata RETURNING id',
                           (file_version,file_id,digest,raw,Jsonb({}))).fetchone()[0]
        file_location=connection.execute('INSERT INTO public.mycel_file_locations VALUES (%s,%s,%s,%s,%s) '
                           'ON CONFLICT (file_version,kind,location) DO UPDATE SET metadata=mycel_file_locations.metadata RETURNING id',
                           (file_location,file_version,location_kind,location,Jsonb(file_metadata or {}))).fetchone()[0]
        for alias_root, alias_path in aliases:
            connection.execute('INSERT INTO public.mycel_file_aliases VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                               (file_id,alias_root,alias_path))
        connection.execute('INSERT INTO public.mycel_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                           (chunk_id,'fixture',file_id,kind,Jsonb({})))
        chunk_source=source if chunk_source is None else chunk_source
        chunk_digest=sha256(chunk_source.encode()).hexdigest()
        metadata={'name':name,'kind':kind,'title':title,'family':family,
                  'span':span or {'start':0,'end':len(raw)}}
        version=connection.execute('INSERT INTO public.mycel_chunk_versions (chunk_id,snapshot_hash,source_bytes,text,comparison,metadata) '
                                   'VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                                   (chunk_id,chunk_digest,chunk_source.encode(),search_text(chunk_source.encode()),Jsonb({}),Jsonb(metadata))).fetchone()[0]
        connection.execute('INSERT INTO public.mycel_locations VALUES (%s,%s,%s,%s,%s,%s)',
                           (uuid4(),version,file_location,location_kind,location,Jsonb(location_metadata or {})))
        return file_id,chunk_id,version

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_source_body_nul_roundtrip_never_reads_bm25_projection
#     def test_real_source_body_nul_roundtrip_never_reads_bm25_projection(self):
#         source = '# Exact\n雪\0body literal \\000\0end\n'
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             _,_,version = self.seed(connection,source=source,
#                 location_metadata={'bodySpan':{'start':len('# Exact\n'),'end':len(source.encode())}})
#             selected = SourceResolver.from_store(connection,settings()).resolve('fixture:guide.md#Exact').selection
#             self.assertEqual(selected.file.source,source.encode())
#             self.assertEqual(selected.members[0].chunk.source,source.encode())
#             self.assertEqual(selected.members[0].chunk.body,'雪\0body literal \\000\0end\n'.encode())
#             self.assertEqual(connection.execute('SELECT text FROM public.mycel_chunk_versions WHERE id=%s',(version,)).fetchone()[0],
#                              source.replace('\0','\ufffd'))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_source_body_nul_roundtrip_never_reads_bm25_projection

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_location_catalog_qualified_aliases_exact_file_bytes_and_colliding_paths
#     def test_real_location_catalog_qualified_aliases_exact_file_bytes_and_colliding_paths(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             shared=self.seed(connection,aliases=(('code','docs/guide.md'),))
#             distinct=self.seed(connection,root='code')
#             resolver=SourceResolver.from_store(connection,settings())
#             result=resolver.resolve('fixture:guide.md')
#             self.assertEqual(result.fault,'ambiguous_path')
#             self.assertEqual(len(result.candidates),2)
#             selected=resolver.resolve('fixture:@code/docs/guide.md').selection
#             self.assertEqual(selected.file.identifier,str(shared[0]))
#             self.assertEqual(selected.file.source,b'# Exact\n')
#             self.assertEqual(selected.place.address,'fixture:@artifact/guide.md')
#             self.assertEqual(resolver.resolve('fixture:@code/guide.md#Exact').selection.members[0].chunk.identifier,str(distinct[1]))
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_location_catalog_qualified_aliases_exact_file_bytes_and_colliding_paths

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_catalog_rechecks_settings_and_never_substitutes_another_location
#     def test_real_catalog_rechecks_settings_and_never_substitutes_another_location(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             file_id,chunk_id,disk=self.seed(connection)
#             _,_,branch=self.seed(connection,source='# Branch\n',name='Branch',title='Branch',
#                                 file_id=file_id,chunk_id=chunk_id,location_kind='branch',location='main')
#             resolver=SourceResolver.from_store(connection,settings(),kind='branch',location='main')
#             selected=resolver.resolve('fixture:guide.md#Branch').selection
#             self.assertEqual(selected.members[0].chunk.version,branch)
#             self.assertEqual(resolver.resolve('fixture:guide.md#Exact').fault,'missing_name')
#             disk_resolver=SourceResolver.from_store(connection,settings())
#             self.assertEqual(disk_resolver.resolve('fixture:guide.md#Exact').selection.members[0].chunk.version,disk)
#             disabled=SourceResolver.from_store(connection,settings(enabled=False))
#             self.assertEqual(disabled.resolve('fixture:guide.md').fault,'disabled_repository')
#             missing=SourceResolver.from_store(connection,settings(),kind='stash',location='never-observed')
#             self.assertEqual(missing.resolve('fixture:guide.md').fault,'missing_file')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_catalog_rechecks_settings_and_never_substitutes_another_location

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_catalog_refuses_incompatible_metadata_and_keeps_source_rows_unchanged
#     def test_real_catalog_refuses_incompatible_metadata_and_keeps_source_rows_unchanged(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             _,_,version=self.seed(connection)
#             before=connection.execute('SELECT count(*) FROM public.mycel_chunk_versions').fetchone()
#             connection.execute("UPDATE public.mycel_chunk_versions SET metadata='{}' WHERE id=%s",(version,))
#             with self.assertRaises(MycelError) as error:
#                 SourceResolver.from_store(connection,settings())
#             self.assertEqual(error.exception.code.value,'store_format')
#             self.assertEqual(connection.execute('SELECT count(*) FROM public.mycel_chunk_versions').fetchone(),before)
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_catalog_refuses_incompatible_metadata_and_keeps_source_rows_unchanged

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_catalog_refuses_a_chunk_bound_to_another_repositorys_file
#     def test_real_catalog_refuses_a_chunk_bound_to_another_repositorys_file(self):
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             _,chunk_id,_=self.seed(connection)
#             connection.execute("INSERT INTO public.mycel_repository_state VALUES ('disabled',NULL,'[]')")
#             connection.execute("UPDATE public.mycel_chunks SET repository='disabled' WHERE id=%s",(chunk_id,))
#             with self.assertRaises(MycelError) as error:
#                 SourceResolver.from_store(connection,settings())
#             self.assertEqual(error.exception.code.value,'store_format')
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_catalog_refuses_a_chunk_bound_to_another_repositorys_file

# TEST-TIER-DISABLED-BEGIN tests/test_resolver.py::ResolverStoreTests.test_real_class_membership_and_located_move_metadata_do_not_change_exact_versions
#     def test_real_class_membership_and_located_move_metadata_do_not_change_exact_versions(self):
#         source='class Policy:\n def a(self): pass\n def z(self): pass\n'
#         header='class Policy:\n'
#         first=' def a(self): pass\n'
#         second=' def z(self): pass\n'
#         with self.store_fixture.backend.connection(self.store_fixture.database) as connection:
#             file_id,chunk_id,version=self.seed(connection,path='old.py',root='code',source=source,
#                     name='Policy',kind='class',title=None,chunk_source=header,span={'start':0,'end':len(header)})
#             self.seed(connection,path='old.py',root='code',source=source,file_id=file_id,
#                     name='Policy.a',kind='method',title=None,family='Policy',chunk_source=first,
#                     span={'start':len(header),'end':len(header+first)})
#             self.seed(connection,path='old.py',root='code',source=source,file_id=file_id,
#                     name='Policy.z',kind='method',title=None,family='Policy',chunk_source=second,
#                     span={'start':len(header+first),'end':len(source)})
#             resolver=SourceResolver.from_store(connection,settings())
#             family_selection=resolver.resolve('fixture:old.py#Policy').selection
#             self.assertEqual([member.chunk.name for member in family_selection.members],['Policy','Policy.a','Policy.z'])
#             self.assertEqual(resolver.resolve('fixture:old.py#Policy',purpose='read').selection.members[0].chunk.version,version)
#             connection.execute("UPDATE public.mycel_file_locations SET metadata=%s",
#                                (Jsonb({'root':'code','path':'new.py','aliases':[{'root':'code','path':'new.py'}]}),))
#             moved=SourceResolver.from_store(connection,settings())
#             self.assertEqual(moved.resolve('fixture:old.py').fault,'missing_file')
#             selected=moved.resolve('fixture:new.py#Policy').selection
#             self.assertEqual(selected.file.identifier,str(file_id))
#             self.assertEqual(selected.members[0].chunk.version,version)
# TEST-TIER-DISABLED-END tests/test_resolver.py::ResolverStoreTests.test_real_class_membership_and_located_move_metadata_do_not_change_exact_versions

# Archived complete imports; restore needed names in their original scope, not at this file tail.
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:3
# from dataclasses import replace
# TEST-TIER-IMPORTS-END tests/test_resolver.py:3
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:7
# from unittest.mock import patch
# TEST-TIER-IMPORTS-END tests/test_resolver.py:7
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:12
# from mycel._code import chunk_code
# TEST-TIER-IMPORTS-END tests/test_resolver.py:12
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:13
# from mycel._errors import MycelError
# TEST-TIER-IMPORTS-END tests/test_resolver.py:13
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:14
# from mycel._resolver import ResolvedChunk, ResolvedFile, SourceResolver
# TEST-TIER-IMPORTS-END tests/test_resolver.py:14
# TEST-TIER-IMPORTS-BEGIN tests/test_resolver.py:15
# from mycel import _resolver
# TEST-TIER-IMPORTS-END tests/test_resolver.py:15
