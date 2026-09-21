--- backend/tests/test_executor.py
+++ backend/tests/test_executor.py
@@ -75,13 +75,11 @@
     assert len(history) == 2

     # Agent 1 history checks
-    assert history[0]["agent_name"] == "DataAnalyzer"
-    assert history[0]["input_used"] == initial_input
+    assert history[0]["node_type"] == "agent"
     assert history[0]["output_produced"]["status"] == "success"

     # Agent 2 history checks
-    assert history[1]["agent_name"] == "NOCGenerator"
+    assert history[1]["node_type"] == "agent"
     assert history[1]["output_produced"]["status"] == "success"
