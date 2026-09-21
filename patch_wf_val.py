--- backend/app/services/workflow_validator.py
+++ backend/app/services/workflow_validator.py
@@ -23,6 +23,12 @@
     node_ids = {n["id"] for n in nodes}
     source_edges = {e["source"] for e in edges}
     target_edges = {e["target"] for e in edges}
+
+    # Build map for type checking
+    agent_cache = {}
+    for n in nodes:
+        if n.get("type") == "agent" and n.get("data", {}).get("agent_id"):
+            agent_cache[n["id"]] = db.query(Agent).filter(Agent.id == n["data"]["agent_id"]).first()

     for node in nodes:
         node_id = node["id"]
@@ -40,18 +46,27 @@
             if not agent_id:
                 errors.append(f"Agent Node {node_id} has no agent selected.")
             else:
-                agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
-                if not agent:
+                agent = agent_cache.get(node_id)
+                if not agent or not agent.is_active:
                     errors.append(f"Agent Node {node_id} references inactive or missing Agent {agent_id}.")
                 elif agent.input_schema:
-                    # Check required inputs
                     mappings = node.get("data", {}).get("mappings", {})
                     for key, val in agent.input_schema.items():
-                        if isinstance(val, dict) and val.get("required") == True:
-                            if key not in mappings:
-                                errors.append(f"Agent Node {node_id} is missing required mapping for '{key}'.")
+                        if not isinstance(val, dict):
+                            continue
+                        if val.get("required") == True and key not in mappings:
+                            errors.append(f"Agent Node {node_id} is missing required mapping for '{key}'.")
+                            continue
+
+                        mapping = mappings.get(key)
+                        if mapping and mapping.get("source") == "node":
+                            source_node_id = mapping.get("node_id")
+                            source_path = mapping.get("path")
+                            source_agent = agent_cache.get(source_node_id)
+                            if source_agent and source_agent.output_schema and source_path:
+                                source_type = source_agent.output_schema.get(source_path, {}).get("type")
+                                dest_type = val.get("type")
+                                if source_type and dest_type and source_type != dest_type:
+                                    errors.append(f"Incompatible mapping on {node_id}.{key}: Expected {dest_type}, but {source_node_id}.{source_path} outputs {source_type}.")

     # Basic Cycle detection (BFS/DFS could be used for advanced check, but let's do a simple topological sort attempt)
