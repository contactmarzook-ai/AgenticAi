from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import Agent

def validate_workflow_definition(definition: Dict[str, Any], db: Session) -> Dict[str, Any]:
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not nodes:
        return {"is_valid": False, "errors": ["Workflow must have at least one node."]}

    errors = []

    input_nodes = [n for n in nodes if n.get("type") == "input"]
    end_nodes = [n for n in nodes if n.get("type") == "end"]

    if not input_nodes:
        errors.append("Workflow must have an Input Node.")
    if not end_nodes:
        errors.append("Workflow must have an End Node.")

    # Check connected nodes
    node_ids = {n["id"] for n in nodes}
    source_edges = {e["source"] for e in edges}
    target_edges = {e["target"] for e in edges}

    for node in nodes:
        node_id = node["id"]
        node_type = node.get("type")

        # Start node shouldn't have targets necessarily, but must have sources
        if node_type == "input" and node_id not in source_edges:
            errors.append(f"Input Node {node_id} is disconnected.")

        if node_type == "end" and node_id not in target_edges:
            errors.append(f"End Node {node_id} is disconnected.")

        if node_type not in ["input", "end"] and (node_id not in source_edges or node_id not in target_edges):
            errors.append(f"Node {node_id} ({node_type}) is disconnected.")

        if node_type == "agent":
            agent_id = node.get("data", {}).get("agent_id")
            if not agent_id:
                errors.append(f"Agent Node {node_id} has no agent selected.")
            else:
                agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
                if not agent:
                    errors.append(f"Agent Node {node_id} references inactive or missing Agent {agent_id}.")
                elif agent.input_schema:
                    # Check required inputs
                    mappings = node.get("data", {}).get("mappings", {})
                    for key, val in agent.input_schema.items():
                        if isinstance(val, dict) and val.get("required") == True:
                            if key not in mappings:
                                errors.append(f"Agent Node {node_id} is missing required mapping for '{key}'.")

    # Basic Cycle detection (BFS/DFS could be used for advanced check, but let's do a simple topological sort attempt)
    in_degree = {n_id: 0 for n_id in node_ids}
    graph = {n_id: [] for n_id in node_ids}
    for e in edges:
        in_degree[e["target"]] = in_degree.get(e["target"], 0) + 1
        graph[e["source"]].append(e["target"])

    queue = [n for n in node_ids if in_degree[n] == 0]
    visited = 0
    while queue:
        n = queue.pop(0)
        visited += 1
        for neighbor in graph.get(n, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(node_ids):
        errors.append("Workflow contains circular paths or unreachable nodes.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }
