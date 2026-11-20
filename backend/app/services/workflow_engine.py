"""Workflow graph execution.

A definition is {"nodes": [...], "edges": [...]} as saved by the visual builder.

Node types and their `data`:
  input      -   output = the workflow input
  agent      {agent_id, mappings: {message: <mapping>}}      output = {"answer": str}
  tool       {tool, mappings: {<arg>: <mapping>}}             output = tool result
  condition  {condition: {left, operator, right}}             output = {"result": bool}
  transform  {mappings: {<key>: <mapping>}}                   output = {<key>: value}
  end        {mappings: {...}} (optional)                     output = mapped values or last input

Mappings say where a value comes from:
  {"source": "static",   "value": ...}
  {"source": "input",    "path": "a.b"}            (workflow input; "workflow" is accepted as an alias)
  {"source": "node",     "node_id": "...", "path": "answer"}
  {"source": "template", "value": "Hello {{input.name}}, see {{node-2.answer}}"}

Edges leaving a condition node carry sourceHandle (or label) "true" / "false".
A node runs once all its predecessors are finished, if at least one incoming edge was taken;
otherwise it is skipped (and so are nodes only reachable through it).
"""

import re
import time
from typing import Any, Callable, Optional

from ..config import settings

TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)((?:\.[A-Za-z0-9_\-]+)*)\s*\}\}")

# Callbacks injected by the caller so the engine stays independent of the DB layer.
AgentCaller = Callable[[int, str], dict]  # (agent_id, message) -> {"answer": ..., ...}
ToolCaller = Callable[[str, dict], Any]


class WorkflowError(Exception):
    def __init__(self, message: str, steps: Optional[list] = None):
        super().__init__(message)
        self.steps = steps or []


def _get_path(value: Any, path: Optional[str]) -> Any:
    if not path:
        return value
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def resolve_mapping(mapping: Any, outputs: dict, workflow_input: dict) -> Any:
    if not isinstance(mapping, dict):
        return mapping
    source = mapping.get("source")
    if source == "static":
        return mapping.get("value")
    if source in ("input", "workflow"):
        return _get_path(workflow_input, mapping.get("path"))
    if source == "node":
        return _get_path(outputs.get(mapping.get("node_id")), mapping.get("path"))
    if source == "template":

        def sub(match):
            root, rest = match.group(1), match.group(2).lstrip(".")
            base = workflow_input if root == "input" else outputs.get(root)
            val = _get_path(base, rest)
            return "" if val is None else str(val)

        return TEMPLATE_RE.sub(sub, str(mapping.get("value", "")))
    return None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def evaluate_condition(condition: dict, outputs: dict, workflow_input: dict) -> bool:
    left = resolve_mapping(condition.get("left", {}), outputs, workflow_input)
    right = resolve_mapping(condition.get("right", {}), outputs, workflow_input)
    op = condition.get("operator", "==")

    if op == "is_empty":
        return left in (None, "", [], {})
    if op == "not_empty":
        return left not in (None, "", [], {})
    if op == "contains":
        if left is None or right is None:
            return False
        if isinstance(left, (list, dict)):
            return right in left
        return str(right).lower() in str(left).lower()

    ln, rn = _num(left), _num(right)
    if op in ("==", "!="):
        equal = (ln == rn) if (ln is not None and rn is not None) else (str(left) == str(right))
        return equal if op == "==" else not equal
    if ln is None or rn is None:
        return False
    return {">": ln > rn, "<": ln < rn, ">=": ln >= rn, "<=": ln <= rn}.get(op, False)


def edge_branch(edge: dict) -> Optional[str]:
    branch = edge.get("sourceHandle") or edge.get("label")
    return str(branch).lower() if branch is not None else None


def topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    ids = [n["id"] for n in nodes]
    indeg = {i: 0 for i in ids}
    children: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in indeg and t in indeg:
            indeg[t] += 1
            children[s].append(t)
    queue = [i for i in ids if indeg[i] == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
    if len(order) != len(ids):
        raise WorkflowError("Workflow contains a cycle")
    return order


def _wrap(result: Any) -> dict:
    return result if isinstance(result, dict) else {"result": result}


def run_definition(
    definition: dict,
    workflow_input: dict,
    call_agent: AgentCaller,
    call_tool: ToolCaller,
    timeout_seconds: Optional[int] = None,
) -> dict:
    """Execute a workflow definition. Returns {"output": ..., "steps": [...]}; raises WorkflowError on failure."""
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    if not nodes:
        raise WorkflowError("Workflow has no nodes")
    if len(nodes) > settings.workflow_max_nodes:
        raise WorkflowError(f"Workflow exceeds the {settings.workflow_max_nodes}-node limit")

    by_id = {n["id"]: n for n in nodes}
    incoming: dict[str, list[dict]] = {nid: [] for nid in by_id}
    for e in edges:
        if e.get("target") in incoming and e.get("source") in by_id:
            incoming[e["target"]].append(e)

    deadline = time.monotonic() + (timeout_seconds or settings.workflow_timeout_seconds)
    outputs: dict[str, Any] = {}
    state: dict[str, str] = {}
    steps: list[dict] = []
    final_output: Any = None
    last_output: Any = None

    for node_id in topological_order(nodes, edges):
        node = by_id[node_id]
        ntype = node.get("type")
        data = node.get("data") or {}

        edges_in = incoming[node_id]
        if edges_in:
            taken = False
            for e in edges_in:
                src = e["source"]
                if state.get(src) != "done":
                    continue
                if by_id[src].get("type") == "condition":
                    if edge_branch(e) == str(bool(outputs[src]["result"])).lower():
                        taken = True
                else:
                    taken = True
            if not taken:
                state[node_id] = "skipped"
                steps.append({"node_id": node_id, "type": ntype, "label": data.get("label"), "status": "skipped"})
                continue

        if time.monotonic() > deadline:
            raise WorkflowError("Workflow exceeded its time limit", steps)

        mappings = data.get("mappings") or {}
        inputs = {k: resolve_mapping(m, outputs, workflow_input) for k, m in mappings.items()}
        started = time.monotonic()
        step = {"node_id": node_id, "type": ntype, "label": data.get("label"), "input": inputs}

        try:
            if ntype == "input":
                out = workflow_input
            elif ntype == "agent":
                message = inputs.get("message")
                if message in (None, ""):
                    message = workflow_input.get("message") if isinstance(workflow_input, dict) else None
                if message in (None, ""):
                    raise WorkflowError("Agent node has no message (map 'message' to a value)")
                out = call_agent(int(data.get("agent_id") or 0), str(message))
            elif ntype == "tool":
                out = _wrap(call_tool(str(data.get("tool") or ""), inputs))
            elif ntype == "condition":
                out = {"result": evaluate_condition(data.get("condition") or {}, outputs, workflow_input)}
            elif ntype == "transform":
                out = inputs
            elif ntype == "end":
                out = inputs if mappings else last_output
                final_output = out
            else:
                raise WorkflowError(f"Unknown node type '{ntype}'")
        except Exception as exc:
            step.update(status="failed", error=str(exc), duration_ms=int((time.monotonic() - started) * 1000))
            steps.append(step)
            raise WorkflowError(f"Node {node_id} ({ntype}) failed: {exc}", steps) from exc

        outputs[node_id] = out
        state[node_id] = "done"
        last_output = out
        step.update(status="success", output=out, duration_ms=int((time.monotonic() - started) * 1000))
        steps.append(step)

    return {"output": final_output if final_output is not None else last_output, "steps": steps}
