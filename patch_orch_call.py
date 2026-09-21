--- backend/app/services/orchestrator.py
+++ backend/app/services/orchestrator.py
@@ -192,7 +192,7 @@

         agent = db.query(Agent).filter(Agent.id == target_id).first()
         if agent:
-             exe_result = execute_agent_script(agent.handler, params)
+             exe_result = execute_agent_script(agent.handler, params, input_schema=agent.input_schema, output_schema=agent.output_schema)
              metadata["execution"] = exe_result
              final_response["execution_trace"] = exe_result
