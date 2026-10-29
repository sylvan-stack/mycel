
# LOW TIER — DO NOT ENABLE OR RECREATE
# Historical examples only. Read before adding related tests; never execute.
# LOW-TIER-BEGIN: tests/mid/test_mid_store_cli.py::StoreCliTests.test_init_uses_one_snapshot_and_private_connection_without_child_forwarding
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Init uses one snapshot and private connection without child forwarding.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_store_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_init_uses_one_snapshot_and_private_connection_without_child_forwarding(self):
#         connection = object()
#         @contextmanager
#         def connect(credentials):
#             self.assertEqual(credentials.store_target().address, self.address)
#             yield connection
#         before = StoreInspection("empty")
#         after = StoreInspection("current", STORE_FORMAT, 256, "b45a9826-caca-4481-a4b0-8d60c55d9894")
#         with patch("mycel._database.store_connection", connect), \
#                 patch("mycel._store.initialize_store", return_value=InitResult(before, after, True)) as initialize, \
#                 patch("mycel._build_identity.current_build", return_value=None), \
#                 patch("subprocess.Popen") as child:
#             status, result, error = self.invoke(["init"])
#         self.assertEqual(status, 0)
#         self.assertEqual(result["store"], self.address)
#         self.assertEqual(result["indexGeneration"], after.index_generation)
#         self.assertEqual(result["dimensions"], {"before": None, "after": 256})
#         initialize.assert_called_once_with(connection, dimensions=256)
#         child.assert_not_called()
#         self.assertEqual(error, "")
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_store_cli.py::StoreCliTests.test_info_keeps_unavailable_and_newer_store_diagnostics_successful
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Info keeps unavailable and newer store diagnostics successful.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_store_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_info_keeps_unavailable_and_newer_store_diagnostics_successful(self):
#         with patch("mycel._database.store_connection", side_effect=MycelError("store_unavailable", "Store unavailable.")):
#             status, result, error = self.invoke(["info"])
#         self.assertEqual(status, 0)
#         self.assertEqual(result["store"]["state"], "unavailable")
#         self.assertEqual(result["store"]["location"], self.address)
#         @contextmanager
#         def connect(credentials):
#             yield object()
#         with patch("mycel._database.store_connection", connect), \
#                 patch("mycel._store.inspect_store", return_value=StoreInspection("newer", STORE_FORMAT + 1, 256, "generation")), \
#                 patch("mycel._store.initialize_store") as initialize:
#             status, result, error = self.invoke(["info"])
#         self.assertEqual(status, 0)
#         self.assertEqual(result["store"]["format"], STORE_FORMAT + 1)
#         initialize.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END

# LOW-TIER-BEGIN: tests/mid/test_mid_store_cli.py::StoreCliTests.test_invalid_init_arguments_and_settings_stop_before_connection
# Reason: This family is not retained under the raised bar. Its isolated formatting, option, field, expected-state or orchestration checks do not justify a separate runtime selection beyond the retained public-command, actual-store, process and source-integrity checks. Absence is a deliberate coverage tradeoff, not a claim that the behavior is unimportant or fully covered elsewhere. Case reviewed: Invalid init arguments and settings stop before connection.
# Source: mycel@560e2e2b1623066240ebd128bfa1e552f0a4f25f:tests/mid/test_mid_store_cli.py
# Historical fixtures and class context are available at the source revision; no active dependencies restored.
# LOW-TIER-SOURCE-BEGIN
#     def test_invalid_init_arguments_and_settings_stop_before_connection(self):
#         with patch("mycel._database.store_connection") as connect:
#             status, result, error = self.invoke(["init", "unexpected"])
#             self.assertEqual((status, result["error"]["code"]), (1, "invalid_input"))
#             self.path.write_text('[store]\naddress="postgresql://fixture:private-sentinel@localhost/fixture"\n')
#             self.snapshot = load_settings(path=self.path)
#             status, result, error = self.invoke(["init"])
#             self.assertEqual((status, result["error"]["code"]), (1, "settings"))
#             status, result, error = self.invoke(["info"])
#             self.assertEqual(status, 0)
#             self.assertNotIn("private-sentinel", json.dumps(result) + error)
#             connect.assert_not_called()
# LOW-TIER-SOURCE-END
# LOW-TIER-END
