--- backend/app/services/workflow_runner.py
+++ backend/app/services/workflow_runner.py
@@ -131,7 +131,7 @@
                 execution_history.append(step_record)
                 return {"status": "error", "error": step_record["error"], "history": execution_history}

-            result = execute_agent_script(agent.handler, node_inputs)
+            result = execute_agent_script(agent.handler, node_inputs, input_schema=agent.input_schema, output_schema=agent.output_schema)

             if result.get("status") == "error":
                  step_record["status"] = "error"
