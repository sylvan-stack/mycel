"""Mid-tier selections. Write or run only in an explicitly requested testing task."""
from __future__ import annotations

import test_voyage as _support
from test_voyage import (
    CommitReceipt,
    CompletedChild,
    Credentials,
    EmbeddingFixtureFailure,
    EmbeddingStandIn,
    HTTPResult,
    InvocationPolicy,
    KEY,
    MycelError,
    Path,
    ProviderFailure,
    Secret,
    VoyageClient,
    VoyageTests,
    _https_request,
    _retry_after,
    _wait,
    io,
    json,
    load_settings,
    load_tokenizer,
    os,
    patch,
    plan_batches,
    plan_chunk,
    plan_query,
    replace,
    ssl,
    tempfile,
    threading,
    time,
    unittest,
)


class VoyageTests(_support.VoyageTests):
# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_exact_request_and_lazy_fixed_credential_boundary_with_no_ambient_fallback
    def test_exact_request_and_lazy_fixed_credential_boundary_with_no_ambient_fallback(self):
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "ambient-wrong-key", "MYCEL_EMBEDDING_ENDPOINT": "wrong"}):
            client = self.client()
            self.assertFalse(self.key_reads)
            progress = self.embed(client)
        self.assertEqual(progress.embedded_parts, 3)
        self.assertIsNone(progress.stopping_reason)
        self.assertEqual(len(self.key_reads), 1)
        self.assertEqual(self.key_reads[0][:6], ("/usr/bin/security", "find-generic-password", "-s", "mycel", "-a", "voyage-api-key"))
        body, deadline = self.requests[0]
        request = json.loads(body)
        self.assertEqual(set(request), {"input", "model", "output_dimension", "output_dtype", "input_type", "truncation"})
        self.assertEqual(request["model"], "voyage-code-4")
        self.assertEqual(request["output_dimension"], 256)
        self.assertEqual(request["output_dtype"], "float")
        self.assertEqual(request["input_type"], "document")
        self.assertFalse(request["truncation"])
        self.assertGreater(deadline, time.monotonic() + 55)
        self.assertEqual(progress.provider_tokens, sum(self.tokenizer.count(text) for text in request["input"]))
        self.assertNotIn(KEY, json.dumps(progress.to_dict()) + repr(client))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_exact_request_and_lazy_fixed_credential_boundary_with_no_ambient_fallback

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_query_exact_input_and_dry_run_or_missing_credentials_make_no_service_call
    def test_query_exact_input_and_dry_run_or_missing_credentials_make_no_service_call(self):
        text = "query with 雪 😀 \t\n"
        response = self.client(policy=InvocationPolicy("search")).query(plan_query(text, dimensions=256, tokenizer=self.tokenizer))
        self.assertEqual(json.loads(self.requests[-1][0])["input"], [text])
        self.assertEqual(json.loads(self.requests[-1][0])["input_type"], "query")
        self.assertEqual(response.provider_tokens, self.tokenizer.count(text))
        self.requests.clear(); self.key_reads.clear()
        with self.assertRaises(MycelError):
            self.embed(self.client(policy=InvocationPolicy("embed", dry_run=True)))
        self.assertFalse(self.key_reads)
        self.assertFalse(self.requests)
        progress = self.embed(self.client(present=False))
        self.assertEqual(progress.stopping_kind, "authentication")
        self.assertEqual(progress.requests, 0)
        self.assertFalse(self.requests)
        self.assertNotIn(KEY, progress.stopping_reason)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_query_exact_input_and_dry_run_or_missing_credentials_make_no_service_call

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_transient_retries_grow_and_keep_identical_saved_inputs
    def test_transient_retries_grow_and_keep_identical_saved_inputs(self):
        for index, kind in enumerate(("connection", "deadline", "rate_limit", "server"), 1):
            self.service.fail_attempt(index, kind)
        progress = self.embed(self.client())
        self.assertEqual(progress.embedded_parts, 3)
        self.assertEqual(progress.requests, 5)
        self.assertEqual(self.waits, [1, 2, 4, 8])
        self.assertEqual(len(set(body for body, _ in self.requests)), 1)
        self.assertEqual(len(self.key_reads), 1)
        self.assertEqual(progress.submitted_inputs, 15)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_transient_retries_grow_and_keep_identical_saved_inputs

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_attempt_limit_leaves_parts_pending_and_stopping_output_is_sanitized
    def test_attempt_limit_leaves_parts_pending_and_stopping_output_is_sanitized(self):
        for attempt in range(1, 9):
            self.service.fail_attempt(attempt, "server")
        progress = self.embed(self.client(attempts=8))
        self.assertEqual(progress.requests, 8)
        self.assertEqual(self.waits, [1, 2, 4, 8, 16, 30, 30])
        self.assertEqual(progress.embedded_parts, 0)
        self.assertEqual(progress.failed_parts, 0)
        self.assertEqual(progress.stopping_kind, "server")
        self.assertFalse(self.writes)
        self.assertFalse(self.failures)
        self.assertNotIn(KEY, json.dumps(progress.to_dict()))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_attempt_limit_leaves_parts_pending_and_stopping_output_is_sanitized

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_retry_after_only_increases_wait_with_sixty_second_cap
    def test_retry_after_only_increases_wait_with_sixty_second_cap(self):
        calls = []
        def transport(body, key, **kwargs):
            calls.append(body)
            if len(calls) <= 3:
                return HTTPResult(429, KEY.encode(), {"Retry-After": ("0", "7", "500")[len(calls)-1]})
            return self.transport(body, key, **kwargs)
        progress = self.embed(self.client(transport=transport))
        self.assertEqual(self.waits, [1, 7, 60])
        self.assertEqual(progress.embedded_parts, 3)
        self.assertEqual(_retry_after({"Retry-After": "Thu, 01 Jan 1970 00:00:10 GMT"}, 5), 5)
        for invalid in ("-1", "1.5", "NaN", "inf", "bad date"):
            self.assertIsNone(_retry_after({"Retry-After": invalid}, 0))
        self.assertEqual(_retry_after({"Retry-After": "9" * 10000}, 0), 60)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_retry_after_only_increases_wait_with_sixty_second_cap

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_cancellation_during_retry_preserves_completed_progress_and_sends_no_later_batch
    def test_cancellation_during_retry_preserves_completed_progress_and_sends_no_later_batch(self):
        batches = self.batches(batch_inputs=1)
        self.service.fail_attempt(2, "server")
        def stop(seconds, cancelled):
            raise ProviderFailure("cancelled")
        progress = self.embed(self.client(waiter=stop), batches)
        self.assertEqual((progress.embedded_parts, progress.requests), (1, 2))
        self.assertEqual(progress.stopping_kind, "cancelled")
        self.assertEqual(len(self.writes), 1)
        checks = iter((False, False, True))
        start = time.monotonic()
        with self.assertRaises(ProviderFailure) as error:
            _wait(5, lambda: next(checks))
        self.assertEqual(error.exception.kind, "cancelled")
        self.assertLess(time.monotonic() - start, 0.2)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_cancellation_during_retry_preserves_completed_progress_and_sends_no_later_batch

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_authentication_authorization_and_model_failures_stop_repo_without_part_failures
    def test_authentication_authorization_and_model_failures_stop_repo_without_part_failures(self):
        for status, body, kind in ((401, KEY.encode(), "authentication"), (403, KEY.encode(), "authorization"),
                                   (404, KEY.encode(), "missing_model"),
                                   (400, json.dumps({"detail": "Invalid model name " + KEY}).encode(), "missing_model")):
            with self.subTest(status=status):
                self.requests.clear(); self.writes.clear(); self.failures.clear()
                calls = []
                def transport(payload, key, **kwargs):
                    calls.append(payload)
                    return HTTPResult(status, body)
                progress = self.embed(self.client(transport=transport), self.batches(batch_inputs=1))
                self.assertEqual(progress.stopping_kind, kind)
                self.assertEqual(len(calls), 1)
                self.assertEqual(progress.failed_parts, 0)
                self.assertFalse(self.writes)
                self.assertFalse(self.failures)
                self.assertNotIn(KEY, json.dumps(progress.to_dict()))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_authentication_authorization_and_model_failures_stop_repo_without_part_failures

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_malformed_error_metadata_stops_safely_without_misattributing_content
    def test_malformed_error_metadata_stops_safely_without_misattributing_content(self):
        responses = (
            HTTPResult(400, json.dumps({"error": {"code": [], "message": KEY}}).encode()),
            HTTPResult(400, json.dumps({"error": {"code": {}, "param": [], "message": KEY}}).encode()),
            HTTPResult(429, KEY.encode(), {1: "60"}),
            HTTPResult(429, KEY.encode(), {"Retry-After": []}),
        )
        for response in responses:
            with self.subTest(status=response.status, malformed_headers=bool(response.headers)):
                self.writes.clear(); self.failures.clear(); self.waits.clear()
                progress = self.embed(self.client(transport=lambda *args, **kwargs: response))
                self.assertEqual(progress.requests, 1)
                self.assertEqual(progress.stopping_kind, "invalid_response" if response.headers else "provider")
                self.assertFalse(self.writes)
                self.assertFalse(self.failures)
                self.assertFalse(self.waits)
                self.assertNotIn(KEY, json.dumps(progress.to_dict()))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_malformed_error_metadata_stops_safely_without_misattributing_content

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_content_isolation_keeps_exact_saved_strings_and_embeds_good_neighbors
    def test_content_isolation_keeps_exact_saved_strings_and_embeds_good_neighbors(self):
        batches = self.batches(("good left", "bad text", "good right", "last"))
        rejected = batches[0].inputs[1].input_text
        self.service.reject_input = lambda text: text == rejected
        progress = self.embed(self.client(), batches)
        self.assertEqual((progress.embedded_parts, progress.failed_parts), (3, 1))
        self.assertIsNone(progress.stopping_reason)
        original = {item.input_text for item in batches[0].inputs}
        self.assertTrue(all(set(json.loads(body)["input"]).issubset(original) for body, _ in self.requests))
        self.assertEqual(self.failures[0].part.chunk_id, "chunk-1")
        self.assertEqual(self.failures[0].kind, "content")
        self.assertEqual(sum(len(writes) for writes in self.writes), 3)
        self.assertTrue(all(not json.loads(body)["truncation"] for body, _ in self.requests))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_content_isolation_keeps_exact_saved_strings_and_embeds_good_neighbors

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_entire_bad_response_writes_nothing_for_duplicate_missing_indices_and_vectors
    def test_entire_bad_response_writes_nothing_for_duplicate_missing_indices_and_vectors(self):
        mutations = [lambda body: {**body, "data": body["data"][:-1]},
                     lambda body: {**body, "data": [{**row, "index": 0} for row in body["data"]]},
                     lambda body: {**body, "data": [{**row, "index": True} for row in body["data"]]},
                     lambda body: {**body, "data": [{**row, "embedding": row["embedding"][:-1]} for row in body["data"]]},
                     lambda body: {**body, "data": [{**row, "embedding": [float("nan")] * 256} for row in body["data"]]},
                     lambda body: {**body, "data": [{**row, "embedding": [float("inf")] * 256} for row in body["data"]]},
                     lambda body: {**body, "data": [{**row, "embedding": [True] * 256} for row in body["data"]]},
                     lambda body: {**body, "usage": {"total_tokens": True}},
                     lambda body: {**body, "model": "wrong"}]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                self.writes.clear(); self.failures.clear()
                self.service.response_mutator = mutate
                progress = self.embed(self.client())
                self.assertEqual(progress.stopping_kind, "invalid_response")
                self.assertEqual(progress.embedded_parts, 0)
                self.assertFalse(self.writes)
                self.assertFalse(self.failures)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_entire_bad_response_writes_nothing_for_duplicate_missing_indices_and_vectors

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_out_of_order_valid_vectors_are_restored_and_race_deleted_vectors_excluded
    def test_out_of_order_valid_vectors_are_restored_and_race_deleted_vectors_excluded(self):
        self.service.response_mutator = lambda body: {**body, "data": list(reversed(body["data"]))}
        def guarded_commit(writes):
            self.writes.append(writes)
            self.assertEqual(writes[0].vector, tuple(self.service.vector(self.batches()[0].inputs[0].input_text, 256)))
            # The exact second version disappears under the commit lock; the
            # first and third are retained, including a metadata-only rename.
            return CommitReceipt((writes[0].part, writes[2].part), (writes[1].part,))
        progress = self.embed(self.client(), commit=guarded_commit)
        self.assertEqual((progress.embedded_parts, progress.discarded_parts), (2, 1))
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(len(self.writes[0]), 3)
        self.assertEqual(progress.failed_parts, 0)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_out_of_order_valid_vectors_are_restored_and_race_deleted_vectors_excluded

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_invalid_response_after_success_retains_only_previously_committed_progress
    def test_invalid_response_after_success_retains_only_previously_committed_progress(self):
        calls = []
        def transport(body, key, **kwargs):
            calls.append(body)
            if len(calls) == 2:
                return HTTPResult(200, b'{"data":[],"usage":{"total_tokens":1}}')
            return self.transport(body, key, **kwargs)
        progress = self.embed(self.client(transport=transport), self.batches(batch_inputs=1))
        self.assertEqual((progress.embedded_parts, progress.requests), (1, 2))
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(progress.stopping_kind, "invalid_response")
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_invalid_response_after_success_retains_only_previously_committed_progress

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_local_bad_limits_duplicate_json_oversized_bodies_and_redirects_never_commit
    def test_local_bad_limits_duplicate_json_oversized_bodies_and_redirects_never_commit(self):
        batches = self.batches()
        bad = replace(batches[0], inputs=(replace(batches[0].inputs[0], input_text="x " * 34000),))
        with self.assertRaises(MycelError):
            self.embed(self.client(), (bad,))
        self.assertFalse(self.key_reads)
        self.assertFalse(self.requests)
        for response in (HTTPResult(302, KEY.encode(), {"Location": "https://elsewhere.invalid"}),
                         HTTPResult(200, b'{"data":[],"data":[],"usage":{"total_tokens":0}}'),
                         HTTPResult(200, b"x" * 65)):
            with self.subTest(status=response.status, size=len(response.body)), patch("mycel._voyage.MAX_RESPONSE_BYTES", 64):
                progress = self.embed(self.client(transport=lambda *args, **kwargs: response))
                self.assertIsNotNone(progress.stopping_reason)
                self.assertFalse(self.writes)
                self.assertFalse(self.failures)
                self.assertNotIn(KEY, json.dumps(progress.to_dict()))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_local_bad_limits_duplicate_json_oversized_bodies_and_redirects_never_commit

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_fixed_https_endpoint_and_headers_use_no_process_proxy_or_endpoint_environment
    def test_fixed_https_endpoint_and_headers_use_no_process_proxy_or_endpoint_environment(self):
        class Response:
            status = 302
            def getheader(self, name): return "0" if name == "Content-Length" else None
            def getheaders(self): return [("Location", "https://wrong.invalid")]
            def read1(self, count): return b""
        class Connection:
            sock = None
            def __init__(self, host, timeout, context):
                self.host = host; self.timeout = timeout; self.context = context; self.calls = []; self.closed = False
            def connect(self): pass
            def request(self, method, path, **kwargs): self.calls.append((method, path, kwargs))
            def getresponse(self): return Response()
            def close(self): self.closed = True
        connections = []
        def factory(*args, **kwargs):
            connection = Connection(*args, **kwargs); connections.append(connection); return connection
        with patch("mycel._voyage.http.client.HTTPSConnection", side_effect=factory), \
                patch.dict(os.environ, {"HTTPS_PROXY": "wrong", "VOYAGE_API_KEY": "wrong", "MYCEL_EMBEDDING_ENDPOINT": "wrong",
                                        "SSLKEYLOGFILE": str(self.root / "must-not-log-tls-secrets")}):
            result = _https_request(b"{}", Secret(KEY), deadline=time.monotonic()+1, cancelled=lambda: False)
        self.assertEqual(result.status, 302)
        self.assertEqual(len(connections), 1)
        connection = connections[0]
        self.assertEqual(connection.host, "api.voyageai.com")
        self.assertEqual(connection.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(connection.context.check_hostname)
        self.assertIsNone(connection.context.keylog_filename)
        self.assertFalse((self.root / "must-not-log-tls-secrets").exists())
        self.assertEqual(connection.calls[0][:2], ("POST", "/v1/embeddings"))
        self.assertEqual(connection.calls[0][2]["headers"]["Authorization"], "Bearer " + KEY)
        self.assertTrue(connection.closed)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_fixed_https_endpoint_and_headers_use_no_process_proxy_or_endpoint_environment

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_dns_deadline_and_cancellation_close_connections_and_prevent_late_post
    def test_dns_deadline_and_cancellation_close_connections_and_prevent_late_post(self):
        for cancel in (False, True):
            release = threading.Event()
            closed = threading.Event()
            connected = threading.Event()
            calls = []
            class Connection:
                sock = None
                def __init__(self, *args, **kwargs): pass
                def connect(self): connected.set(); release.wait(1)
                def request(self, *args, **kwargs): calls.append(args)
                def close(self): closed.set()
            start = time.monotonic()
            with self.subTest(cancel=cancel), patch("mycel._voyage.http.client.HTTPSConnection", Connection):
                with self.assertRaises(ProviderFailure) as error:
                    _https_request(b"{}", Secret(KEY), deadline=start+0.08,
                                   cancelled=lambda: cancel and connected.is_set())
                self.assertEqual(error.exception.kind, "cancelled" if cancel else "deadline")
                self.assertTrue(closed.is_set())
                self.assertLess(time.monotonic()-start, 0.3)
                release.set()
                time.sleep(0.02)
                self.assertFalse(calls)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_dns_deadline_and_cancellation_close_connections_and_prevent_late_post

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends
    def test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends(self):
        for cancellation in (False, True):
            setup_started = threading.Event()
            release_setup = threading.Event()
            worker_done = threading.Event()
            calls = []
            def delayed_context():
                setup_started.set()
                release_setup.wait(1)
                return object()
            class Connection:
                sock = None
                def __init__(self, *args, **kwargs): calls.append("create")
                def connect(self): calls.append("connect")
                def request(self, *args, **kwargs): calls.append("POST")
                def close(self): calls.append("close")
            actual_thread = threading.Thread
            def thread_factory(*args, **kwargs):
                target = kwargs["target"]
                def work():
                    try:
                        target()
                    finally:
                        worker_done.set()
                return actual_thread(*args, **dict(kwargs, target=work))
            started = time.monotonic()
            with self.subTest(cancellation=cancellation), \
                    patch("mycel._voyage._tls_context", side_effect=delayed_context), \
                    patch("mycel._voyage.http.client.HTTPSConnection", Connection), \
                    patch("mycel._voyage.threading.Thread", side_effect=thread_factory):
                try:
                    with self.assertRaises(ProviderFailure) as failure:
                        _https_request(b"{}", Secret(KEY), deadline=started + 0.08,
                                       cancelled=lambda: cancellation and setup_started.is_set())
                    self.assertEqual(failure.exception.kind, "cancelled" if cancellation else "deadline")
                    self.assertTrue(setup_started.is_set())
                    self.assertLess(time.monotonic() - started, 0.3)
                    self.assertFalse(calls)
                finally:
                    release_setup.set()
                    self.assertTrue(worker_done.wait(0.5))
                self.assertFalse(calls)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_tls_setup_is_supervised_and_late_completion_never_connects_or_sends

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_https_read_limit_is_enforced_with_and_without_content_length
    def test_https_read_limit_is_enforced_with_and_without_content_length(self):
        for advertised in (None, "65", "-1", "invalid"):
            class Response:
                status = 200
                def getheader(self, name): return advertised
                def getheaders(self): return []
                def read1(self, limit): return b"x" * limit
            class Connection:
                sock = None
                closed = False
                def __init__(self, *args, **kwargs): self.timeout = 1
                def connect(self): pass
                def request(self, *args, **kwargs): pass
                def getresponse(self): return Response()
                def close(self): Connection.closed = True
            with self.subTest(advertised=advertised), patch("mycel._voyage.MAX_RESPONSE_BYTES", 64), \
                    patch("mycel._voyage.http.client.HTTPSConnection", Connection):
                with self.assertRaises(ProviderFailure) as error:
                    _https_request(b"{}", Secret(KEY), deadline=time.monotonic()+1, cancelled=lambda: False)
                self.assertEqual(error.exception.kind, "invalid_response" if advertised == "invalid" else "response_limit")
                self.assertTrue(Connection.closed)
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_https_read_limit_is_enforced_with_and_without_content_length

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_cancellation_during_response_read_shuts_down_active_socket
    def test_cancellation_during_response_read_shuts_down_active_socket(self):
        reading = threading.Event()
        released = threading.Event()
        shutdown = threading.Event()
        class Socket:
            def settimeout(self, timeout): pass
            def shutdown(self, how): shutdown.set(); released.set()
        class Response:
            status = 200
            def getheader(self, name): return None
            def getheaders(self): return []
            def read1(self, size): reading.set(); released.wait(1); return b"stopped"
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): self.timeout = 1
            def connect(self): self.sock = Socket()
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self):
                if self.sock is not None: self.sock.shutdown(2)
                self.sock = None
        with patch("mycel._voyage.http.client.HTTPSConnection", Connection):
            with self.assertRaises(ProviderFailure) as error:
                _https_request(b"{}", Secret(KEY), deadline=time.monotonic()+1, cancelled=reading.is_set)
        self.assertEqual(error.exception.kind, "cancelled")
        self.assertTrue(shutdown.is_set())
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_cancellation_during_response_read_shuts_down_active_socket

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_injected_transport_cannot_exceed_total_deadline_and_receipts_must_account_for_every_part
    def test_injected_transport_cannot_exceed_total_deadline_and_receipts_must_account_for_every_part(self):
        clock = [100.0]
        policy = InvocationPolicy("embed")
        def late(body, key, **kwargs):
            result = self.transport(body, key, **kwargs)
            self.assertEqual(kwargs["deadline"], 160.0)
            clock[0] = 161.0
            return result
        client = VoyageClient(self.credentials(policy), policy, tokenizer=self.tokenizer, attempts=1,
                              _transport=late, _monotonic=lambda: clock[0])
        progress = self.embed(client)
        self.assertEqual(progress.stopping_kind, "deadline")
        self.assertFalse(self.writes)
        for receipt in (CommitReceipt(()), CommitReceipt((None,)), CommitReceipt((None,), (None,))):
            with self.subTest(receipt=receipt), self.assertRaises(MycelError) as error:
                self.embed(self.client(), commit=lambda writes: receipt)
            self.assertEqual(error.exception.code, "internal")
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_injected_transport_cannot_exceed_total_deadline_and_receipts_must_account_for_every_part

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_durable_deferred_results_preserve_paid_usage_and_stop_before_new_sends
    def test_durable_deferred_results_preserve_paid_usage_and_stop_before_new_sends(self):
        def staged(writes):
            self.writes.append(writes)
            return CommitReceipt((), (), tuple(write.part for write in writes))
        progress = self.embed(self.client(), self.batches(batch_inputs=1), commit=staged)
        self.assertEqual((progress.embedded_parts, progress.deferred_parts, progress.discarded_parts), (0, 1, 0))
        self.assertEqual((progress.requests, progress.submitted_inputs), (1, 1))
        self.assertGreater(progress.provider_tokens, 0)
        self.assertEqual(progress.stopping_kind, "busy")
        self.assertEqual(len(self.writes), 1)
        self.assertNotIn(KEY, json.dumps(progress.to_dict()))
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_durable_deferred_results_preserve_paid_usage_and_stop_before_new_sends

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_publication_failure_keeps_earlier_progress_and_paid_token_accounting
    def test_publication_failure_keeps_earlier_progress_and_paid_token_accounting(self):
        calls = [0]
        def commit(writes):
            calls[0] += 1
            if calls[0] == 2:
                raise MycelError("store_unavailable", "The store connection was lost.")
            return self.commit(writes)
        progress = self.embed(self.client(), self.batches(batch_inputs=1), commit=commit)
        self.assertEqual((progress.embedded_parts, progress.requests), (1, 2))
        self.assertEqual(progress.stopping_kind, "store_unavailable")
        self.assertGreater(progress.provider_tokens, self.tokenizer.counts("doc.md › Heading\none", "document")[0])
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_publication_failure_keeps_earlier_progress_and_paid_token_accounting

# TEST-TIER-BEGIN tests/test_voyage.py::VoyageTests.test_cancellation_after_validation_keeps_returned_results_before_stopping
    def test_cancellation_after_validation_keeps_returned_results_before_stopping(self):
        cancelled = [False]
        def commit(writes):
            cancelled[0] = True
            return self.commit(writes)
        progress = self.embed(self.client(cancelled=lambda: cancelled[0]), self.batches(batch_inputs=1), commit=commit)
        self.assertEqual((progress.embedded_parts, progress.requests), (1, 1))
        self.assertEqual(progress.stopping_kind, "cancelled")
# TEST-TIER-END tests/test_voyage.py::VoyageTests.test_cancellation_after_validation_keeps_returned_results_before_stopping
