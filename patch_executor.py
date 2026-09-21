--- backend/app/services/executor.py
+++ backend/app/services/executor.py
@@ -1,7 +1,8 @@
 import traceback
-from typing import Dict, Any
+from typing import Dict, Any, Optional
 from app.agents.registry import get_handler
+from app.services.agent_validator import validate_schema

-def execute_agent_script(handler_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
+def execute_agent_script(handler_name: str, params: Dict[str, Any], input_schema: Optional[Dict[str, Any]] = None, output_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
     """
     Executes an agent by finding its registered handler function.
@@ -18,6 +19,13 @@
             "error": f"Handler '{handler_name}' not found in registry."
         }

+    if input_schema:
+        in_errors = validate_schema(params, input_schema)
+        if in_errors:
+            return {
+                "status": "error",
+                "error": f"Input validation failed: {', '.join(in_errors)}"
+            }

     try:
         result = handler(params)
@@ -26,6 +34,14 @@
             return {"status": "error", "error": "Handler did not produce a dictionary."}

+        if output_schema:
+            out_errors = validate_schema(result, output_schema)
+            if out_errors:
+                return {
+                    "status": "error",
+                    "error": f"Output validation failed: {', '.join(out_errors)}"
+                }
+
         return result

     except Exception as e:
