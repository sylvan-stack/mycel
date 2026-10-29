"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_embedding_store as _support
from test_embedding_store import (
    CompletedChild,
    Credentials,
    EmbeddingFixtureFailure,
    EmbeddingStandIn,
    EmbeddingStoreAcceptanceTests,
    EmbeddingStoreUnitTests,
    HTTPResult,
    InvocationPolicy,
    Jsonb,
    MycelError,
    PartFailure,
    PartIdentity,
    Path,
    Rows,
    ScriptedConnection,
    SettingsSnapshot,
    SimpleNamespace,
    UUID,
    VectorWrite,
    VoyageClient,
    atomic_transaction,
    checked,
    contextmanager,
    deepcopy,
    guarded,
    json,
    load_settings,
    load_tokenizer,
    operation_guard,
    patch,
    pq,
    psycopg,
    replace,
    require_check_database,
    require_store,
    search_text,
    settings,
    sha256,
    store,
    unittest,
    uuid4,
)


class EmbeddingStoreUnitTests(_support.EmbeddingStoreUnitTests):
# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_changed_exact_bytes_are_refused_before_a_paid_plan_is_constructed
    def test_changed_exact_bytes_are_refused_before_a_paid_plan_is_constructed(self):
        version = self.seed('original\0body')
        self.connection.versions[version]['text'] = 'changed\0body'
        with self.assertRaises(MycelError) as error:
            self.prepare(self.writer())
        self.assertEqual(error.exception.code.value,'store_format')
        self.assertFalse(self.connection.plans)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_changed_exact_bytes_are_refused_before_a_paid_plan_is_constructed

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_provisional_plans_and_disabled_unknown_settings_never_write
    def test_provisional_plans_and_disabled_unknown_settings_never_write(self):
        self.seed()
        before = deepcopy((self.connection.plans, self.connection.parts, self.connection.vectors, self.connection.receipts))
        value = self.prepare(self.writer())
        self.assertEqual((value.counts.pending_versions, value.counts.pending_parts), (1, 1))
        self.assertEqual(value.estimate["parts"], 1)
        disabled = self.writer(settings_=settings(enabled=False))
        value = self.prepare(disabled)
        self.assertEqual(value.counts.pending_parts, 0)
        self.assertFalse(value.batches)
        self.assertFalse(disabled.eligible("unknown"))
        with self.assertRaises(MycelError):
            with disabled.session("fixture"):
                self.fail("disabled session entered")
        self.assertEqual(before, (self.connection.plans, self.connection.parts, self.connection.vectors, self.connection.receipts))
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for sql, _ in self.connection.sql))
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_provisional_plans_and_disabled_unknown_settings_never_write

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_one_bad_vector_or_model_pair_rejects_the_whole_batch_before_staging
    def test_one_bad_vector_or_model_pair_rejects_the_whole_batch_before_staging(self):
        self.seed(); self.seed("second")
        writer = self.writer()
        with writer.session("fixture"):
            writes = self.writes(self.prepare(writer, persist=True))
            for bad in (replace(writes[-1], vector=(float("nan"),) * 1024),
                        replace(writes[-1], vector=(True,) * 1024), replace(writes[-1], dimensions=True),
                        replace(writes[-1], model="other"), replace(writes[-1], vector=(0.0,)),
                        replace(writes[-1], vector=(10**1000,) * 1024)):
                with self.subTest(bad=type(bad.vector[0])), self.assertRaises(MycelError):
                    writer.commit((writes[0], bad))
                self.assertFalse(self.connection.receipts)
                self.assertFalse(self.connection.vectors)
            with self.assertRaises(MycelError):
                writer.commit((writes[0], writes[0]))
            writer.commit(writes)
        self.assertEqual(len(self.connection.vectors), 2)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_one_bad_vector_or_model_pair_rejects_the_whole_batch_before_staging

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_callbacks_require_prepared_canonical_exact_part_association
    def test_callbacks_require_prepared_canonical_exact_part_association(self):
        self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            write = self.writes(self.prepare(writer, persist=True))[0]
            for part in (replace(write.part, chunk_version="01"), replace(write.part, part_order=True),
                         replace(write.part, repository="disabled"), replace(write.part, chunk_id=str(uuid4())),
                         replace(write.part, part_order=1)):
                with self.subTest(part=part), self.assertRaises(MycelError):
                    writer.commit((replace(write, part=part),))
            self.assertFalse(self.connection.receipts)
        with self.assertRaises(MycelError):
            writer.commit((write,))
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_callbacks_require_prepared_canonical_exact_part_association

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_changed_retained_plan_or_repository_is_refused_without_losing_receipt
    def test_changed_retained_plan_or_repository_is_refused_without_losing_receipt(self):
        version = self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            writes = self.writes(self.prepare(writer, persist=True))
            self.connection.pass_busy = True
            writer.commit(writes)
            self.connection.pass_busy = False
            old = self.connection.versions[version]["repository"]
            self.connection.versions[version]["repository"] = "disabled"
            with self.assertRaises(MycelError):
                writer.drain("fixture")
            self.connection.versions[version]["repository"] = old
            identifier = next(iter(self.connection.plans))
            row = self.connection.plans[identifier]
            self.connection.plans[identifier] = (*row[:4], "0" * 64, *row[5:])
            with self.assertRaises(MycelError):
                writer.drain("fixture")
        self.assertFalse(self.connection.vectors)
        self.assertEqual(len(self.connection.receipts), 1)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_changed_retained_plan_or_repository_is_refused_without_losing_receipt

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_staged_payload_tampering_cannot_bypass_vector_or_input_validation
    def test_staged_payload_tampering_cannot_bypass_vector_or_input_validation(self):
        self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            writes = self.writes(self.prepare(writer, persist=True))
            self.connection.pass_busy = True
            writer.commit(writes)
            self.connection.pass_busy = False
            identifier = next(iter(self.connection.receipts))
            original = deepcopy(self.connection.receipts[identifier])
            for mutation in (lambda p: p["results"][0].update(vector=[1.0]),
                             lambda p: p["plans"][0]["metadata"].update(place_line="wrong input"),
                             lambda p: p.update(model="other"),
                             lambda p: p["results"].append(deepcopy(p["results"][0]))):
                self.connection.receipts[identifier] = deepcopy(original)
                mutation(self.connection.receipts[identifier][4])
                with self.assertRaises(MycelError):
                    writer.drain("fixture")
                self.assertFalse(self.connection.vectors)
                self.assertEqual(len(self.connection.receipts), 1)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_staged_payload_tampering_cannot_bypass_vector_or_input_validation

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_part_failure_is_sanitized_and_other_pending_parts_continue_then_retry_keeps_success
    def test_part_failure_is_sanitized_and_other_pending_parts_continue_then_retry_keeps_success(self):
        local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=24))
        self.seed("alpha beta gamma delta\n" * 8)
        writer = self.writer(tokenizer=local)
        with writer.session("fixture"):
            prepared = self.prepare(writer, persist=True)
            writes = self.writes(prepared)
            self.assertGreater(len(writes), 1)
            failed = writes[0]
            writer.record_failures((PartFailure(failed.part, "content", "private body and credentials"),))
            pending = self.prepare(writer)
            self.assertEqual((pending.counts.failed_parts, pending.counts.pending_versions), (1, 1))
            remaining = self.writes(pending)
            for write in remaining:
                writer.commit((write,))
            failed_only = self.prepare(writer)
            self.assertEqual((failed_only.counts.failed_versions, failed_only.counts.embedded_versions), (1, 0))
            self.assertFalse(failed_only.batches)
            retry = self.prepare(writer, retry_failed=True)
            self.assertEqual(tuple(value.part for value in self.writes(retry)), (failed.part,))
            # An intervening ordinary status read cannot erase the captured
            # input association for an explicitly selected retry.
            self.prepare(writer)
            writer.commit(self.writes(retry))
            self.assertEqual(self.prepare(writer).counts.embedded_versions, 1)
        self.assertNotIn("private", repr(self.connection.parts))
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_part_failure_is_sanitized_and_other_pending_parts_continue_then_retry_keeps_success

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_busy_failure_receipt_is_deferred_and_drain_records_only_sanitized_failure
    def test_busy_failure_receipt_is_deferred_and_drain_records_only_sanitized_failure(self):
        self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            write = self.writes(self.prepare(writer, persist=True))[0]
            self.connection.pass_busy = True
            receipt = writer.record_failures((PartFailure(write.part, "content", "private provider body"),))
            self.assertEqual(receipt.deferred, (write.part,))
            deferred = self.prepare(writer)
            self.assertEqual((deferred.counts.deferred_parts, deferred.counts.failed_parts), (1, 0))
            self.assertFalse(deferred.batches)
            self.connection.pass_busy = False
            writer.drain("fixture")
            failed = self.prepare(writer)
            self.assertEqual((failed.counts.failed_versions, failed.counts.failed_parts), (1, 1))
            retry = self.prepare(writer, retry_failed=True)
            self.connection.pass_busy = True
            writer.record_failures((PartFailure(write.part, "content", "private retry body"),))
            deferred = self.prepare(writer)
            self.assertEqual((deferred.counts.failed_parts, deferred.counts.deferred_parts), (0, 1))
            self.assertFalse(deferred.batches)
        self.assertNotIn("private", repr(self.connection.parts) + repr(self.connection.receipts))
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_busy_failure_receipt_is_deferred_and_drain_records_only_sanitized_failure

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_failed_plan_records_exact_counting_provenance_and_is_not_silently_retried
    def test_failed_plan_records_exact_counting_provenance_and_is_not_silently_retried(self):
        self.seed()
        impossible = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=1))
        writer = self.writer(tokenizer=impossible)
        with writer.session("fixture"):
            prepared = self.prepare(writer, persist=True)
            original = next(iter(self.connection.plans))
            self.assertEqual(prepared.counts.failed_versions, 1)
            self.assertFalse(prepared.batches)
            self.assertIn("tokenizers_library_sha256", self.connection.plans[original][6]["provenance"])
            self.prepare(writer, persist=True)
            self.assertEqual(next(iter(self.connection.plans)), original)
        repaired = self.writer()
        with repaired.session("fixture"):
            valid = self.prepare(repaired, persist=True)
        self.assertEqual(valid.counts.pending_versions, 1)
        self.assertNotEqual(next(iter(self.connection.plans)), original)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_failed_plan_records_exact_counting_provenance_and_is_not_silently_retried

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_catalog_compatible_saved_plan_is_retained_and_incompatible_one_gets_new_pending_parts
    def test_catalog_compatible_saved_plan_is_retained_and_incompatible_one_gets_new_pending_parts(self):
        self.seed("many words\n" * 12)
        writer = self.writer()
        with writer.session("fixture"):
            prepared = self.prepare(writer, persist=True)
            writer.commit(self.writes(prepared))
            original = next(iter(self.connection.plans))
        compatible = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, catalog_sha256="1" * 64))
        writer = self.writer(tokenizer=compatible)
        with writer.session("fixture"):
            self.assertEqual(self.prepare(writer, persist=True).counts.embedded_versions, 1)
        self.assertEqual(next(iter(self.connection.plans)), original)
        restricted = replace(compatible, catalog=replace(compatible.catalog, input_token_cap=24))
        writer = self.writer(tokenizer=restricted)
        with writer.session("fixture"):
            replanned = self.prepare(writer, persist=True)
        self.assertNotEqual(next(iter(self.connection.plans)), original)
        self.assertGreater(replanned.counts.pending_parts, 1)
        self.assertFalse(self.connection.vectors)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_catalog_compatible_saved_plan_is_retained_and_incompatible_one_gets_new_pending_parts

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_old_model_plans_vectors_and_receipts_do_not_count_or_publish_for_current_model
    def test_old_model_plans_vectors_and_receipts_do_not_count_or_publish_for_current_model(self):
        self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            writes = self.writes(self.prepare(writer, persist=True))
            self.connection.pass_busy = True
            writer.commit(writes)
            self.connection.pass_busy = False
        new_model = "fictional-next-model"
        tokenizer = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, model=new_model))
        writer = self.writer(settings_=settings(model=new_model), tokenizer=tokenizer)
        with writer.session("fixture"):
            current = self.prepare(writer, persist=True)
        self.assertEqual(current.counts.pending_parts, 1)
        self.assertEqual(current.counts.embedded_parts, 0)
        self.assertFalse(current.staged)
        self.assertEqual(len(self.connection.receipts), 1)
        self.assertEqual(len(self.connection.plans), 2)
        self.assertFalse(self.connection.vectors)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_old_model_plans_vectors_and_receipts_do_not_count_or_publish_for_current_model

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_historical_batch_caps_publish_after_compatible_current_caps_shrink
    def test_historical_batch_caps_publish_after_compatible_current_caps_shrink(self):
        self.seed("first"); self.seed("second")
        writer = self.writer()
        with writer.session("fixture"):
            writes = self.writes(self.prepare(writer, persist=True))
            self.connection.pass_busy = True
            writer.commit(writes)
            self.connection.pass_busy = False
        smaller = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=1,
                          input_token_cap=24, batch_token_cap=24))
        writer = self.writer(tokenizer=smaller)
        with writer.session("fixture"):
            value = self.prepare(writer)
            self.assertEqual(value.counts.embedded_versions, 2)
            self.assertFalse(value.batches)
        self.assertFalse(self.connection.receipts)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_historical_batch_caps_publish_after_compatible_current_caps_shrink

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_incompatible_paid_inputs_are_preserved_in_quarantine_and_new_plan_remains_pending
    def test_incompatible_paid_inputs_are_preserved_in_quarantine_and_new_plan_remains_pending(self):
        self.seed("full source words\n" * 20)
        writer = self.writer()
        with writer.session("fixture"):
            prepared = self.prepare(writer, persist=True)
            original_id = prepared.versions[0].id
            self.connection.pass_busy = True
            writer.commit(self.writes(prepared))
            self.connection.pass_busy = False
            original = deepcopy(next(iter(self.connection.receipts.values()))[4])
        smaller = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=24))
        writer = self.writer(tokenizer=smaller)
        with writer.session("fixture"):
            pending = self.prepare(writer, persist=True)
            self.assertEqual((pending.obsolete_receipts, pending.obsolete_parts), (1, 1))
            self.assertEqual((pending.counts.embedded_versions, pending.counts.pending_versions), (0, 1))
            self.assertFalse(pending.staged)
            self.assertGreater(pending.counts.pending_parts, 1)
            self.assertNotEqual(pending.versions[0].id, original_id)
            for batch in pending.batches:
                writer.commit(self.writes(replace(pending, batches=(batch,))))
            self.assertEqual(self.prepare(writer).counts.embedded_versions, 1)
        envelope = next(iter(self.connection.receipts.values()))[4]
        self.assertEqual(envelope, {"format": 2, "kind": "quarantined", "reason": "catalog_incompatible", "payload": original})
        self.assertNotIn(original_id, {key[0] for key in self.connection.vectors})
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_incompatible_paid_inputs_are_preserved_in_quarantine_and_new_plan_remains_pending

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_corrupt_counting_data_is_not_misclassified_as_catalog_incompatibility
    def test_corrupt_counting_data_is_not_misclassified_as_catalog_incompatibility(self):
        self.seed()
        writer = self.writer()
        with writer.session("fixture"):
            writer.prepare("fixture", contexts=self.contexts, persist=True)
            writes = self.writes(self.prepare(writer))
            self.connection.pass_busy = True
            writer.commit(writes)
            self.connection.pass_busy = False
        row = next(iter(self.connection.receipts.values()))
        payload = row[4]
        payload["plans"][0]["metadata"]["parts"][0]["submitted_tokens"] += 1
        payload["integrity"] = store._integrity(payload)
        with self.assertRaises(MycelError):
            with self.writer().session("fixture"):
                self.fail("corrupt token counts were quarantined")
        self.assertEqual(next(iter(self.connection.receipts.values()))[4]["format"], 1)
        self.assertFalse(self.connection.vectors)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_corrupt_counting_data_is_not_misclassified_as_catalog_incompatibility

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_persisted_capture_does_not_expand_to_concurrently_added_unsaved_versions
    def test_persisted_capture_does_not_expand_to_concurrently_added_unsaved_versions(self):
        first = self.seed("first")
        writer = self.writer()
        original_save = writer._save
        def interleave(repository, replacements):
            original_save(repository, replacements)
            self.seed("introduced after the captured plans were saved")
        with writer.session("fixture"), patch.object(writer, "_save", side_effect=interleave):
            prepared = self.prepare(writer, persist=True)
            self.assertEqual({v.version.version for v in prepared.versions}, {str(first)})
            self.assertTrue(all(v.id is not None for v in prepared.versions))
            receipt = writer.commit(self.writes(prepared))
            self.assertEqual(len(receipt.retained), 1)
            status = self.prepare(writer)
            self.assertEqual((status.counts.embedded_versions, status.counts.pending_versions), (1, 1))
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreUnitTests.test_persisted_capture_does_not_expand_to_concurrently_added_unsaved_versions



class EmbeddingStoreAcceptanceTests(_support.EmbeddingStoreAcceptanceTests):
# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_exact_version_all_locations_saved_spans_vectors_and_metadata_move_coverage
    def test_exact_version_all_locations_saved_spans_vectors_and_metadata_move_coverage(self):
        with self.connect() as connection:
            text = "# Heading\r\n\n雪 é 😀 body  \r\n" * 12
            chunk, version = self.seed(connection, text, locations=("disk", "branch", "stash", "index"))
            local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=28))
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=local)
            with writer.session("fixture"):
                prepared = self.prepare(writer, persist=True)
                self.assertEqual(len(prepared.versions), 1)
                self.assertGreater(prepared.counts.pending_parts, 1)
                self.assertEqual("".join(p.text for p in prepared.versions[0].plan.parts), text)
                original = prepared.versions[0]
                # Submit each generated batch as its own actual atomic result.
                for batch in prepared.batches:
                    writes = self.writes(replace(prepared, batches=(batch,)))
                    receipt = writer.commit(writes)
                    self.assertEqual(receipt.retained, tuple(w.part for w in writes))
                complete = self.prepare(writer)
                self.assertEqual(complete.counts.embedded_versions, 1)
                self.assertEqual(complete.counts.embedded_parts, len(original.plan.parts))
                self.assertFalse(complete.batches)
                with atomic_transaction(connection):
                    connection.execute("UPDATE public.mycel_locations SET metadata=%s WHERE chunk_version=%s",
                                       (Jsonb({"path": "moved.md"}), version))
                self.contexts[version] = store.EmbeddingContext("moved.md › Changed metadata", "document")
                moved = self.prepare(writer, persist=True)
                self.assertEqual(moved.versions[0].id, original.id)
                self.assertEqual(moved.versions[0].plan, original.plan)
                self.seed(connection, text.replace("Heading", "Changed"), chunk=chunk, locations=("branch",))
                changed = self.prepare(writer, persist=True)
                self.assertEqual((changed.counts.embedded_versions, changed.counts.pending_versions), (1, 1))
            rows = connection.execute("SELECT plan_id,part_order,model,dimensions,embedding::text FROM public.mycel_vectors").fetchall()
            self.assertEqual({row[0] for row in rows}, {original.id})
            self.assertTrue(all(row[2:4] == ("voyage-code-4", 1024) for row in rows))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_exact_version_all_locations_saved_spans_vectors_and_metadata_move_coverage

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_disabled_unknown_and_old_model_state_never_supply_current_coverage
    def test_disabled_unknown_and_old_model_state_never_supply_current_coverage(self):
        with self.connect() as connection:
            self.seed(connection, "retained exact text", locations=("stash",))
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                prepared = self.prepare(writer, persist=True)
                writer.commit(self.writes(prepared))
            identifier = prepared.versions[0].id
            with atomic_transaction(connection):
                connection.execute("UPDATE public.mycel_embedding_plans SET model='historical-model' WHERE id=%s", (identifier,))
                connection.execute("UPDATE public.mycel_vectors SET model='historical-model' WHERE plan_id=%s", (identifier,))
            disabled = store.EmbeddingStore(connection, settings(enabled=False, base=self.settings), tokenizer=self.tokenizer)
            self.assertEqual(self.prepare(disabled).counts.pending_parts, 0)
            self.assertFalse(disabled.eligible("unknown"))
            with self.assertRaises(MycelError):
                with disabled.session("fixture"):
                    self.fail("ineligible session entered")
            with writer.session("fixture"):
                current = self.prepare(writer, persist=True)
                self.assertEqual((current.counts.embedded_parts, current.counts.pending_parts), (0, 1))
                self.assertNotEqual(current.versions[0].id, identifier)
                writer.commit(self.writes(current))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_plans").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors WHERE model='historical-model'").fetchone()[0], 1)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_disabled_unknown_and_old_model_state_never_supply_current_coverage

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_real_nul_saved_inputs_receipts_and_restart_preserve_exact_bytes
    def test_real_nul_saved_inputs_receipts_and_restart_preserve_exact_bytes(self):
        text = '# Heading\n雪\0body literal \\000\0end\n'
        with self.connect() as owner, self.connect() as passer:
            _,version = self.seed(owner,text)
            writer = store.EmbeddingStore(owner,self.settings,tokenizer=self.tokenizer)
            with writer.session('fixture'):
                prepared = self.prepare(writer,persist=True)
                self.assertEqual(prepared.versions[0].plan.text,text)
                expected = tuple(part.input_text.encode() for part in prepared.versions[0].plan.parts)
                actual = owner.execute('SELECT input_bytes FROM public.mycel_embedding_parts ORDER BY part_order').fetchall()
                self.assertEqual(tuple(row[0] for row in actual),expected)
                with operation_guard(passer,'fixture','pass'):
                    receipt = writer.commit(self.writes(prepared))
                    self.assertTrue(receipt.deferred)
                    payload = owner.execute('SELECT payload FROM public.mycel_embedding_receipts').fetchone()[0]
                    self.assertIsInstance(payload,bytes)
                    self.assertEqual(store._receipt_payload(payload)['plans'][0]['text'],text)
                    self.assertEqual(self.prepare(writer).counts.deferred_parts,len(expected))
            restarted = store.EmbeddingStore(owner,self.settings,tokenizer=self.tokenizer)
            with restarted.session('fixture'):
                complete = self.prepare(restarted)
                self.assertEqual(complete.versions[0].plan.text,text)
                self.assertEqual(complete.counts.embedded_versions,1)
                self.assertFalse(complete.batches)
            self.assertEqual(owner.execute('SELECT source_bytes,text FROM public.mycel_chunk_versions WHERE id=%s',(version,)).fetchone(),
                             (text.encode(),search_text(text.encode())))
            self.assertEqual(owner.execute('SELECT count(*) FROM public.mycel_embedding_receipts').fetchone()[0],0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_real_nul_saved_inputs_receipts_and_restart_preserve_exact_bytes

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_busy_pass_durable_batch_is_not_coverage_and_next_session_publishes_without_resend
    def test_busy_pass_durable_batch_is_not_coverage_and_next_session_publishes_without_resend(self):
        with self.connect() as owner, self.connect() as passer:
            self.seed(owner, "first"); self.seed(owner, "second")
            writer = store.EmbeddingStore(owner, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                writes = self.writes(self.prepare(writer, persist=True))
                with operation_guard(passer, "fixture", "pass"):
                    receipt = writer.commit(writes)
                    self.assertEqual(receipt.deferred, tuple(w.part for w in writes))
                    pending = self.prepare(writer)
                    self.assertEqual((pending.counts.embedded_versions, pending.counts.deferred_parts), (0, 2))
                    self.assertFalse(pending.batches)
                    self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
                    self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 1)
            restarted = store.EmbeddingStore(owner, self.settings, tokenizer=self.tokenizer)
            with restarted.session("fixture"):
                complete = self.prepare(restarted)
                self.assertEqual(complete.counts.embedded_versions, 2)
                self.assertFalse(complete.batches)
            self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_busy_pass_durable_batch_is_not_coverage_and_next_session_publishes_without_resend

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_row_lock_defers_whole_response_and_deleted_versions_alone_are_discarded
    def test_row_lock_defers_whole_response_and_deleted_versions_alone_are_discarded(self):
        with self.connect() as owner, self.connect() as passer:
            _, first = self.seed(owner, "first"); _, second = self.seed(owner, "second")
            writer = store.EmbeddingStore(owner, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                writes = self.writes(self.prepare(writer, persist=True))
                with atomic_transaction(passer):
                    passer.execute("SELECT id FROM public.mycel_chunk_versions WHERE id=%s FOR UPDATE", (second,))
                    deferred = writer.commit(writes)
                    self.assertEqual(set(deferred.deferred), {w.part for w in writes})
                    self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
                with operation_guard(passer, "fixture", "pass"), atomic_transaction(passer):
                    passer.execute("DELETE FROM public.mycel_chunk_versions WHERE id=%s", (first,))
                    passer.execute("DELETE FROM public.mycel_locations WHERE chunk_version=%s", (second,))
                drained = writer.drain("fixture")
                self.assertEqual({p.chunk_version for p in drained.deleted}, {str(first)})
                self.assertEqual({p.chunk_version for p in drained.retained}, {str(second)})
            self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 1)
            self.assertEqual(owner.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_row_lock_defers_whole_response_and_deleted_versions_alone_are_discarded

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_isolated_failure_does_not_block_pending_parts_and_explicit_retry_retains_success
    def test_isolated_failure_does_not_block_pending_parts_and_explicit_retry_retains_success(self):
        with self.connect() as connection:
            self.seed(connection, "complete source line\n" * 8)
            local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=28))
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=local)
            with writer.session("fixture"):
                prepared = self.prepare(writer, persist=True)
                writes = self.writes(prepared)
                self.assertGreater(len(writes), 1)
                first = writes[0]
                writer.record_failures((PartFailure(first.part, "content", "raw provider body must not be saved"),))
                pending = self.prepare(writer)
                self.assertEqual((pending.counts.failed_parts, pending.counts.pending_versions), (1, 1))
                for batch in pending.batches:
                    writer.commit(self.writes(replace(pending, batches=(batch,))))
                failed = self.prepare(writer)
                self.assertEqual((failed.counts.failed_versions, failed.counts.embedded_versions), (1, 0))
                successes = connection.execute("SELECT plan_id,part_order,embedding::text FROM public.mycel_vectors ORDER BY part_order").fetchall()
                retry = self.prepare(writer, retry_failed=True)
                self.assertEqual(tuple(w.part for w in self.writes(retry)), (first.part,))
                writer.commit(self.writes(retry))
                self.assertEqual(self.prepare(writer).counts.embedded_versions, 1)
                after = connection.execute("SELECT plan_id,part_order,embedding::text FROM public.mycel_vectors ORDER BY part_order").fetchall()
                self.assertTrue(all(row in after for row in successes))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_parts WHERE failure IS NOT NULL").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_isolated_failure_does_not_block_pending_parts_and_explicit_retry_retains_success

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_invalid_whole_batch_and_corrupt_receipt_write_no_vectors
    def test_invalid_whole_batch_and_corrupt_receipt_write_no_vectors(self):
        with self.connect() as connection, self.connect() as passer:
            self.seed(connection, "first"); self.seed(connection, "second")
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                writes = self.writes(self.prepare(writer, persist=True))
                with self.assertRaises(MycelError):
                    writer.commit((writes[0], replace(writes[1], vector=(float("inf"),) * 1024)))
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
                with operation_guard(passer, "fixture", "pass"):
                    writer.commit(writes)
                row = connection.execute("SELECT id,payload FROM public.mycel_embedding_receipts").fetchone()
                payload = store._receipt_payload(row[1])
                payload["results"][0]["vector"] = [1.0]
                with atomic_transaction(connection):
                    connection.execute("UPDATE public.mycel_embedding_receipts SET payload=%s WHERE id=%s", (store._payload_bytes(payload), row[0]))
                with self.assertRaises(MycelError):
                    writer.drain("fixture")
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 1)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_invalid_whole_batch_and_corrupt_receipt_write_no_vectors

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume
    def test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume(self):
        class FaultingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.calls = 0
                self.inject = True

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, params=None):
                if sql.startswith("INSERT INTO public.mycel_vectors"):
                    self.calls += 1
                    if self.inject and self.calls == 2:
                        raise psycopg.ProgrammingError("fictional secret native failure")
                return self.connection.execute(sql, params)

        with self.connect() as connection:
            self.seed(connection, "first"); self.seed(connection, "second")
            proxy = FaultingConnection(connection)
            writer = store.EmbeddingStore(proxy, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                writes = self.writes(self.prepare(writer, persist=True))
                with self.assertRaises(MycelError) as failure:
                    writer.commit(writes)
                self.assertEqual(failure.exception.code, "store_unavailable")
                self.assertNotIn("secret", str(failure.exception))
                # The first INSERT executed against PostgreSQL, then the
                # product transaction rolled it back when the second failed.
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 1)
                proxy.inject = False
                resumed = writer.drain("fixture")
                self.assertEqual(set(resumed.retained), {w.part for w in writes})
                self.assertEqual(self.prepare(writer).counts.embedded_versions, 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_actual_sql_transaction_rolls_back_mid_batch_fault_and_durable_receipt_can_resume

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_recorded_plan_provenance_is_validated_and_incompatible_replanning_removes_old_vectors
    def test_recorded_plan_provenance_is_validated_and_incompatible_replanning_removes_old_vectors(self):
        with self.connect() as connection:
            self.seed(connection, "full exact body line\r\n" * 16)
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                prepared = self.prepare(writer, persist=True)
                writer.commit(self.writes(prepared))
                original = prepared.versions[0]
            metadata = connection.execute("SELECT provenance FROM public.mycel_embedding_plans WHERE id=%s",
                                          (original.id,)).fetchone()[0]
            self.assertEqual(metadata, original.plan.to_dict())
            self.assertEqual(metadata["provenance"]["tokenizers_library_sha256"], self.tokenizer.library_sha256)
            compatible = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, catalog_sha256="1" * 64))
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=compatible)
            with writer.session("fixture"):
                unchanged = self.prepare(writer, persist=True)
                self.assertEqual(unchanged.versions[0].id, original.id)
                self.assertEqual(unchanged.counts.embedded_versions, 1)
            restricted = replace(compatible, catalog=replace(compatible.catalog, input_token_cap=28))
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=restricted)
            with writer.session("fixture"):
                replacement = self.prepare(writer, persist=True)
                self.assertNotEqual(replacement.versions[0].id, original.id)
                self.assertEqual(replacement.counts.embedded_parts, 0)
                self.assertGreater(replacement.counts.pending_parts, 1)
                self.assertEqual("".join(p.text for p in replacement.versions[0].plan.parts), original.version.text)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_plans WHERE id=%s",
                                               (original.id,)).fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_recorded_plan_provenance_is_validated_and_incompatible_replanning_removes_old_vectors

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_real_voyage_orchestration_stages_paid_results_stops_sending_and_drains_without_resend
    def test_real_voyage_orchestration_stages_paid_results_stops_sending_and_drains_without_resend(self):
        with self.connect() as connection, self.connect() as passer:
            for number, text in enumerate(("first valid input", "second valid input", "later valid input", "bad content input"), 1):
                self.seed(connection, text, chunk=UUID(int=number))
            local = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=2))
            service = EmbeddingStandIn(local.counts, inputs_cap=2)
            policy = InvocationPolicy("embed")
            key_reads = []
            def public_key(argv, **kwargs):
                key_reads.append(argv)
                return CompletedChild(0, b"public-fixture-credential\n", b"", 0.0)
            credentials = Credentials(self.settings, policy, home=self.store_fixture.root, _runner=public_key)
            def transport(body, key, **kwargs):
                self.assertEqual(key.reveal(), "public-fixture-credential")
                try:
                    response = service.request(json.loads(body))
                    return HTTPResult(200, json.dumps(response).encode())
                except EmbeddingFixtureFailure as failure:
                    self.assertEqual(failure.kind, "content")
                    return HTTPResult(413, b'{"body":"fictional raw provider detail"}')
            client = VoyageClient(credentials, policy, tokenizer=local, _transport=transport)
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=local)
            with writer.session("fixture"):
                prepared = self.prepare(writer, persist=True)
                self.assertEqual(len(prepared.batches), 2)
                first_inputs = tuple(item.input_text for item in prepared.batches[0].inputs)
                with operation_guard(passer, "fixture", "pass"):
                    progress = client.embed_repository("fixture", prepared.batches,
                                commit=writer.commit, record_failures=writer.record_failures)
                    self.assertEqual((progress.requests, progress.submitted_inputs, progress.deferred_parts), (1, 2, 2))
                    self.assertEqual((progress.embedded_parts, progress.failed_parts, progress.discarded_parts), (0, 0, 0))
                    self.assertEqual(progress.stopping_kind, "busy")
                    self.assertEqual(progress.provider_tokens, sum(local.count(text) for text in first_inputs))
                    self.assertEqual(len(service.attempts), 1)
                    coverage = self.prepare(writer)
                    self.assertEqual((coverage.counts.embedded_versions, coverage.counts.deferred_parts), (0, 2))
                    self.assertEqual(coverage.estimate["parts"], 2)
            restarted = store.EmbeddingStore(connection, self.settings, tokenizer=local)
            with restarted.session("fixture"):
                drained = self.prepare(restarted)
                self.assertEqual(len(service.attempts), 1)
                self.assertEqual(drained.counts.embedded_versions, 2)
                self.assertEqual(drained.counts.deferred_parts, 0)
                self.assertEqual(drained.estimate["parts"], 2)
                service.reject_input = lambda text: "bad content input" in text
                progress = client.embed_repository("fixture", drained.batches,
                            commit=restarted.commit, record_failures=restarted.record_failures)
                self.assertEqual((progress.embedded_parts, progress.failed_parts, progress.deferred_parts), (1, 1, 0))
                self.assertIsNone(progress.stopping_reason)
                complete = self.prepare(restarted)
                self.assertEqual((complete.counts.embedded_versions, complete.counts.failed_versions), (3, 1))
                self.assertFalse(complete.batches)
            self.assertEqual(len(key_reads), 1)
            self.assertTrue(all(not set(first_inputs).intersection(attempt.inputs) for attempt in service.attempts[1:]))
            failures = connection.execute("SELECT failure FROM public.mycel_embedding_parts WHERE failure IS NOT NULL").fetchall()
            self.assertEqual(len(failures), 1)
            self.assertNotIn("raw provider", json.dumps(failures))
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_real_voyage_orchestration_stages_paid_results_stops_sending_and_drains_without_resend

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_historical_request_caps_publish_compatible_results_and_incompatible_inputs_are_quarantined
    def test_historical_request_caps_publish_compatible_results_and_incompatible_inputs_are_quarantined(self):
        with self.connect() as connection, self.connect() as passer:
            self.seed(connection, "first"); self.seed(connection, "second")
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            with writer.session("fixture"):
                original = self.prepare(writer, persist=True)
                with operation_guard(passer, "fixture", "pass"):
                    writer.commit(self.writes(original))
            smaller_batch = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, batch_input_cap=1))
            compatible = store.EmbeddingStore(connection, self.settings, tokenizer=smaller_batch)
            with compatible.session("fixture"):
                complete = self.prepare(compatible)
                self.assertEqual(complete.counts.embedded_versions, 2)
                self.assertEqual({v.id for v in complete.versions}, {v.id for v in original.versions})
                self.assertFalse(complete.batches)
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_embedding_receipts").fetchone()[0], 0)
            self.seed(connection, "full exact source line\r\n" * 20)
            with writer.session("fixture"):
                current = self.prepare(writer, persist=True)
                new = next(v for v in current.versions if not v.complete)
                with operation_guard(passer, "fixture", "pass"):
                    writer.commit(self.writes(current))
                paid_payload = store._receipt_payload(connection.execute("SELECT payload FROM public.mycel_embedding_receipts").fetchone()[0])
            smaller_input = replace(self.tokenizer, catalog=replace(self.tokenizer.catalog, input_token_cap=28))
            replacement = store.EmbeddingStore(connection, self.settings, tokenizer=smaller_input)
            with replacement.session("fixture"):
                pending = self.prepare(replacement, persist=True)
                self.assertEqual((pending.obsolete_receipts, pending.obsolete_parts), (1, 1))
                self.assertEqual((pending.counts.embedded_versions, pending.counts.pending_versions), (2, 1))
                self.assertEqual(pending.counts.deferred_parts, 0)
                self.assertGreater(pending.estimate["parts"], 1)
                self.assertNotIn(new.id, {v.id for v in pending.versions})
                for batch in pending.batches:
                    replacement.commit(self.writes(replace(pending, batches=(batch,))))
                complete = self.prepare(replacement)
                self.assertEqual(complete.counts.embedded_versions, 3)
                self.assertEqual(complete.obsolete_parts, 1)
            envelope = store._receipt_payload(connection.execute("SELECT payload FROM public.mycel_embedding_receipts").fetchone()[0])
            self.assertEqual(envelope, {"format": 2, "kind": "quarantined", "reason": "catalog_incompatible", "payload": paid_payload})
            self.assertEqual(connection.execute("SELECT count(*) FROM public.mycel_vectors WHERE plan_id=%s", (new.id,)).fetchone()[0], 0)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_historical_request_caps_publish_compatible_results_and_incompatible_inputs_are_quarantined

# TEST-TIER-BEGIN tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture
    def test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture(self):
        with self.connect() as connection, self.connect() as passer:
            _, first = self.seed(connection, "first captured input")
            writer = store.EmbeddingStore(connection, self.settings, tokenizer=self.tokenizer)
            original_save = writer._save
            def interleave(repository, replacements):
                original_save(repository, replacements)
                with operation_guard(passer, "fixture", "pass"):
                    self.seed(passer, "introduced after capture was saved")
            with writer.session("fixture"):
                with patch.object(writer, "_save", side_effect=interleave):
                    captured = self.prepare(writer, persist=True)
                self.assertEqual({v.version.version for v in captured.versions}, {str(first)})
                self.assertTrue(all(v.id is not None for v in captured.versions))
                receipt = writer.commit(self.writes(captured))
                self.assertEqual(len(receipt.retained), 1)
                provisional = self.prepare(writer)
                self.assertEqual((provisional.counts.embedded_versions, provisional.counts.pending_versions), (1, 1))
                self.assertTrue(any(v.id is None for v in provisional.versions))
                next_pass = self.prepare(writer, persist=True)
                self.assertTrue(all(v.id is not None for v in next_pass.versions))
                writer.commit(self.writes(next_pass))
                self.assertEqual(self.prepare(writer).counts.embedded_versions, 2)
# TEST-TIER-END tests/test_embedding_store.py::EmbeddingStoreAcceptanceTests.test_concurrent_native_ingest_after_plan_save_does_not_expand_the_finite_paid_capture
