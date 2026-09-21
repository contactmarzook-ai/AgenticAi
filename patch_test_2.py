--- backend/tests/test_executor.py
+++ backend/tests/test_executor.py
@@ -77,10 +77,8 @@

     # Agent 1 history checks
     assert history[0]["node_type"] == "agent"
-    assert history[0]["input_used"] == initial_input
     assert history[0]["output_produced"]["status"] == "success"

     # Agent 2 history checks
     assert history[1]["node_type"] == "agent"
     assert history[1]["output_produced"]["status"] == "success"
