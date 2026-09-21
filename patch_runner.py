--- backend/app/services/workflow_runner.py
+++ backend/app/services/workflow_runner.py
@@ -1,90 +1,196 @@
 from typing import Dict, Any, List
 from sqlalchemy.orm import Session
 from app.models import Workflow, Agent
 from app.services.executor import execute_agent_script
+import copy

+def resolve_mapping(mapping: Dict[str, Any], context: Dict[str, Any], initial_input: Dict[str, Any]) -> Any:
+    source_type = mapping.get("source") # "workflow", "node", "static"
+
+    if source_type == "static":
+        return mapping.get("value")
+
+    elif source_type == "workflow":
+        path = mapping.get("path")
+        if not path:
+            return initial_input
+        return initial_input.get(path)
+
+    elif source_type == "node":
+        node_id = mapping.get("node_id")
+        path = mapping.get("path")
+        node_output = context.get(node_id, {})
+        if not path:
+            return node_output
+        return node_output.get(path)
+
+    return None
+
+def evaluate_condition(condition: Dict[str, Any], context: Dict[str, Any], initial_input: Dict[str, Any]) -> bool:
+    left = resolve_mapping(condition.get("left", {}), context, initial_input)
+    right = resolve_mapping(condition.get("right", {}), context, initial_input)
+    operator = condition.get("operator", "==")
+
+    if operator == "==":
+        return left == right
+    elif operator == "!=":
+        return left != right
+    elif operator == ">":
+        return left > right if (left is not None and right is not None) else False
+    elif operator == "<":
+        return left < right if (left is not None and right is not None) else False
+    return False
+
 def run_workflow_pipeline(workflow_id: int, initial_input: Dict[str, Any], db: Session) -> Dict[str, Any]:
     """
-    Executes a workflow by fetching it from the DB and chaining its agents sequentially.
-    The output of Agent N becomes the input of Agent N+1.
-
-    Args:
-        workflow_id: The ID of the workflow to run.
-        initial_input: The starting parameters for the first agent.
-        db: SQLAlchemy session.
-
-    Returns:
-        A dictionary containing the final output and the history of execution steps.
+    Executes a node-based workflow graph.
     """
     workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

     if not workflow:
         return {
             "status": "error",
             "error": f"Workflow with ID {workflow_id} not found."
         }

-    agent_ids = workflow.steps_json
-    if not agent_ids or not isinstance(agent_ids, list):
-        return {
-             "status": "error",
-             "error": "Workflow has no defined steps or steps_json is invalid."
-        }
+    definition = workflow.definition
+    nodes = definition.get("nodes", [])
+    edges = definition.get("edges", [])

+    if not nodes:
+         return {
+              "status": "error",
+              "error": "Workflow has no nodes."
+         }
+
     execution_history = []
-    current_input = initial_input
+    context = {}
+
+    # Build adjacency list
+    graph = {node["id"]: [] for node in nodes}
+    for edge in edges:
+         source = edge.get("source")
+         target = edge.get("target")
+         if source in graph:
+             graph[source].append({"target": target, "edge_data": edge})
+
+    # Find input node or start nodes (nodes with 0 in-degree)
+    in_degree = {node["id"]: 0 for node in nodes}
+    for edge in edges:
+        if edge.get("target") in in_degree:
+            in_degree[edge.get("target")] += 1
+
+    start_nodes = [node["id"] for node in nodes if in_degree[node["id"]] == 0]
+    if not start_nodes:
+         return {"status": "error", "error": "Workflow has cyclic dependencies or no start node."}
+
+    queue = start_nodes.copy()
+    visited = set()
+    final_output = None

-    for idx, agent_id in enumerate(agent_ids):
-        agent = db.query(Agent).filter(Agent.id == agent_id).first()
+    while queue:
+        node_id = queue.pop(0)
+        if node_id in visited:
+            continue
+
+        node = next((n for n in nodes if n["id"] == node_id), None)
+        if not node:
+            continue
+
+        visited.add(node_id)
+        node_type = node.get("type")
+        node_data = node.get("data", {})
+
+        # Build inputs for this node
+        node_inputs = {}
+        mappings = node_data.get("mappings", {})
+        for param_name, mapping in mappings.items():
+            node_inputs[param_name] = resolve_mapping(mapping, context, initial_input)

-        if not agent:
-            error_msg = f"Agent with ID {agent_id} not found in database."
-            execution_history.append({
-                "step": idx + 1,
-                "agent_id": agent_id,
-                "status": "error",
-                "error": error_msg
-            })
-            return {
-                "status": "error",
-                "error": "Pipeline failed.",
-                "history": execution_history
-            }
+        step_record = {
+            "node_id": node_id,
+            "node_type": node_type,
+            "input_used": node_inputs
+        }

-        if not agent.is_active:
-             error_msg = f"Agent '{agent.name}' (ID: {agent_id}) is inactive."
-             execution_history.append({
-                "step": idx + 1,
-                "agent_id": agent_id,
-                "agent_name": agent.name,
-                "status": "error",
-                "error": error_msg
-            })
-             return {
-                "status": "error",
-                "error": "Pipeline failed.",
-                "history": execution_history
-            }
-
-        # Execute the agent script
-        step_result = execute_agent_script(agent.handler, current_input)
-
-        # Check for execution failure
-        if step_result.get("status") == "error":
-             execution_history.append({
-                "step": idx + 1,
-                "agent_id": agent.id,
-                "agent_name": agent.name,
-                "status": "error",
-                "error": step_result.get("error"),
-                "traceback": step_result.get("traceback")
-             })
-             return {
-                "status": "error",
-                "error": f"Agent '{agent.name}' failed during execution.",
-                "history": execution_history
-             }
+        if node_type == "input":
+            # Input node just passes along the workflow input or mapped input
+            step_result = node_inputs if node_inputs else initial_input
+            context[node_id] = step_result
+            step_record["output_produced"] = step_result
+            step_record["status"] = "success"
+            execution_history.append(step_record)
+
+        elif node_type == "agent":
+            agent_id = node_data.get("agent_id")
+            agent = db.query(Agent).filter(Agent.id == agent_id).first()
+
+            if not agent or not agent.is_active:
+                step_record["status"] = "error"
+                step_record["error"] = f"Agent {agent_id} not found or inactive."
+                execution_history.append(step_record)
+                return {"status": "error", "error": step_record["error"], "history": execution_history}
+
+            # Execute the agent script
+            # For agent nodes without specific mappings but part of a chain, we might want to default to previous node output?
+            # If there are no mappings, and we have exactly one incoming edge, maybe pass that.
+            # For now, explicit mappings are best. If no mappings, pass empty dict or initial_input?
+            # The prompt says: "Each node receives its configured input mappings"
+            result = execute_agent_script(agent.handler, node_inputs)

-        # Record successful step execution
-        execution_history.append({
-            "step": idx + 1,
-            "agent_id": agent.id,
-            "agent_name": agent.name,
-            "status": "success",
-            "input_used": current_input,
-            "output_produced": step_result
-        })
-
-        # Pipeline logic: current output becomes next step's input
-        current_input = step_result
+            if result.get("status") == "error":
+                 step_record["status"] = "error"
+                 step_record["error"] = result.get("error")
+                 execution_history.append(step_record)
+                 return {"status": "error", "error": f"Agent execution failed: {result.get('error')}", "history": execution_history}
+
+            context[node_id] = result
+            step_record["output_produced"] = result
+            step_record["status"] = "success"
+            execution_history.append(step_record)
+
+        elif node_type == "condition":
+            condition = node_data.get("condition", {})
+            eval_result = evaluate_condition(condition, context, initial_input)
+            context[node_id] = {"result": eval_result}
+            step_record["output_produced"] = {"result": eval_result}
+            step_record["status"] = "success"
+            execution_history.append(step_record)
+
+            # Handle branching by adding specific targets based on condition
+            # Edges from condition node should have a 'label' or 'condition_match' (True/False)
+            for edge_info in graph.get(node_id, []):
+                edge_data = edge_info["edge_data"]
+                if str(edge_data.get("label", "true")).lower() == str(eval_result).lower():
+                    queue.append(edge_info["target"])
+            continue # skip default enqueue
+
+        elif node_type == "transform":
+            # simple transform/mapping node, just returns the mapped inputs
+            context[node_id] = node_inputs
+            step_record["output_produced"] = node_inputs
+            step_record["status"] = "success"
+            execution_history.append(step_record)
+
+        elif node_type == "end":
+            # final node
+            final_output = node_inputs
+            context[node_id] = final_output
+            step_record["output_produced"] = final_output
+            step_record["status"] = "success"
+            execution_history.append(step_record)
+            break
+
+        # Default enqueue all children
+        for edge_info in graph.get(node_id, []):
+            if edge_info["target"] not in visited:
+                queue.append(edge_info["target"])
+
+    if final_output is None:
+         # If no explicit End node, just return the last context value?
+         # Let's return the full context or the last step's output
+         if execution_history:
+              final_output = execution_history[-1].get("output_produced", {})

     return {
         "status": "success",
-        "final_output": current_input,
+        "final_output": final_output,
         "history": execution_history
     }
