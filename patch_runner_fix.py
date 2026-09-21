--- backend/app/services/workflow_runner.py
+++ backend/app/services/workflow_runner.py
@@ -148,8 +148,8 @@
     if final_output is None:
          if execution_history:
               final_output = execution_history[-1].get("output_produced", {})

-    if is_test:
+    if locals().get("is_test"):
         return {"status": "success", "is_test": True, "final_output": final_output, "history": execution_history}

     return {
