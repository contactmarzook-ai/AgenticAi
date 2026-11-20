"""Workflow graph execution.

A definition is {"nodes": [...], "edges": [...]} as saved by the visual builder.

Node types:
  input      Start. Output = the workflow input (form values, webhook body, ...).
  action     A step from the node catalog: data = {action, config, settings}.
             Text in `config` may contain {{ }} variables.
  condition  If: data.condition = {left, operator, right}. Outgoing edges use handle "true"/"false".
  switch     data = {value, cases: [..]}. Outgoing edges use a case value or "default".
  end        Finish. data.config.output (optional) chooses what to return.
  agent / tool / transform   older node types, still supported.

Variables: {{input.field}}, {{<node id>.field}}, {{<node id>.a.b.0}}. A field consisting of a
single variable keeps the value's type (numbers stay numbers, lists stay lists).

A node runs once all its predecessors are finished, if at least one incoming branch was taken;
otherwise it is skipped (and so are nodes reachable only through it).

Per-node settings (data.settings): retries (0-5), retry_delay_seconds, continue_on_error.
"""

import json
import re
import time
from typing import Any, Callable, Optional

from ..config import settings

VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)((?:\.[A-Za-z0-9_\-]+)*)\s*\}\}")
WHOLE_VAR_RE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_\-]+)((?:\.[A-Za-z0-9_\-]+)*)\s*\}\}\s*$")

AgentCaller = Callable[[int, str], dict]
ToolCaller = Callable[[str, dict], Any]
ActionCaller = Callable[[str, dict, dict], Any]  # (action key, resolved config, node) -> output

BRANCHING = {"condition", "switch"}


class WorkflowError(Exception):
    def __init__(self, message: str, steps: Optional[list] = None):
        super().__init__(message)
        self.steps = steps or []


# ---------------- values ----------------
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


def _lookup(root: str, rest: str, outputs: dict, workflow_input: dict) -> Any:
    base = workflow_input if root == "input" else outputs.get(root)
    return _get_path(base, rest.lstrip("."))


def _to_text(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str)
    return str(val)


def resolve_template(text: str, outputs: dict, workflow_input: dict) -> Any:
    whole = WHOLE_VAR_RE.match(text)
    if whole:
        return _lookup(whole.group(1), whole.group(2), outputs, workflow_input)
    return VAR_RE.sub(lambda m: _to_text(_lookup(m.group(1), m.group(2), outputs, workflow_input)), text)


def resolve_value(value: Any, outputs: dict, workflow_input: dict) -> Any:
    """Resolve {{ }} variables in strings, recursively through dicts and lists."""
    if isinstance(value, str):
        return resolve_template(value, outputs, workflow_input) if "{{" in value else value
    if isinstance(value, list):
        return [resolve_value(v, outputs, workflow_input) for v in value]
    if isinstance(value, dict):
        return {k: resolve_value(v, outputs, workflow_input) for k, v in value.items()}
    return value


def resolve_mapping(mapping: Any, outputs: dict, workflow_input: dict) -> Any:
    """Older mapping objects ({source: static|input|node|template, ...}); plain values are templates."""
    if not isinstance(mapping, dict) or "source" not in mapping:
        return resolve_value(mapping, outputs, workflow_input)
    source = mapping.get("source")
    if source == "static":
        return mapping.get("value")
    if source in ("input", "workflow"):
        return _get_path(workflow_input, mapping.get("path"))
    if source == "node":
        return _get_path(outputs.get(mapping.get("node_id")), mapping.get("path"))
    if source == "template":
        return VAR_RE.sub(
            lambda m: _to_text(_lookup(m.group(1), m.group(2), outputs, workflow_input)), str(mapping.get("value", ""))
        )
    return None


# ---------------- conditions ----------------
def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _as_number(v: Any) -> Optional[float]:
    if _is_number(v):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _equal(left: Any, right: Any) -> bool:
    """A real number on either side compares numerically ("5" == 5). Booleans compare as
    true/false text ("true" == True). Two strings compare exactly, so "01234" != "1234"."""
    if _is_number(left) or _is_number(right):
        ln, rn = _as_number(left), _as_number(right)
        if ln is not None and rn is not None:
            return ln == rn
    if isinstance(left, bool) or isinstance(right, bool):
        return _to_text(left).strip().lower() == _to_text(right).strip().lower()
    return _to_text(left) == _to_text(right)


def evaluate_condition(condition: dict, outputs: dict, workflow_input: dict) -> bool:
    left = resolve_mapping(condition.get("left", ""), outputs, workflow_input)
    right = resolve_mapping(condition.get("right", ""), outputs, workflow_input)
    op = condition.get("operator", "==")

    if op == "is_empty":
        return left in (None, "", [], {})
    if op == "not_empty":
        return left not in (None, "", [], {})
    if op in ("contains", "not_contains"):
        if left is None or right is None:
            found = False
        elif isinstance(left, (list, dict)):
            found = right in left
        else:
            found = _to_text(right).lower() in _to_text(left).lower()
        return found if op == "contains" else not found
    if op == "starts_with":
        return _to_text(left).lower().startswith(_to_text(right).lower())
    if op in ("==", "!="):
        eq = _equal(left, right)
        return eq if op == "==" else not eq
    ln, rn = _as_number(left), _as_number(right)
    if ln is None or rn is None:
        return False
    return {">": ln > rn, "<": ln < rn, ">=": ln >= rn, "<=": ln <= rn}.get(op, False)


def edge_branch(edge: dict) -> Optional[str]:
    branch = edge.get("sourceHandle") or edge.get("label")
    return str(branch).strip().lower() if branch is not None else None


def switch_match(value: Any, cases: list) -> str:
    for c in cases:
        c = str(c)
        if _equal(value, c) or _to_text(value).strip().lower() == c.strip().lower():
            return c
    return "default"


# ---------------- graph ----------------
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
        raise WorkflowError("Workflow contains a loop (a step leads back to an earlier step)")
    return order


def _wrap(result: Any) -> dict:
    return result if isinstance(result, dict) else {"result": result}


def _branch_taken(src_node: dict, src_output: dict, edge: dict) -> bool:
    stype = src_node.get("type")
    if stype == "condition":
        return edge_branch(edge) == ("true" if src_output.get("result") else "false")
    if stype == "switch":
        return edge_branch(edge) == str(src_output.get("matched", "")).strip().lower()
    return True


def _settings(data: dict) -> tuple[int, float, bool]:
    s = data.get("settings") or {}
    try:
        retries = max(0, min(int(s.get("retries") or 0), 5))
        delay = max(0.0, min(float(s.get("retry_delay_seconds") or 1), 60.0))
    except (TypeError, ValueError):
        retries, delay = 0, 1.0
    return retries, delay, bool(s.get("continue_on_error"))


def run_definition(
    definition: dict,
    workflow_input: dict,
    call_agent: AgentCaller,
    call_tool: ToolCaller,
    call_action: Optional[ActionCaller] = None,
    timeout_seconds: Optional[int] = None,
) -> dict:
    """Execute a workflow definition. Returns {"output": ..., "steps": [...]}; raises WorkflowError on failure."""
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    if not nodes:
        raise WorkflowError("Workflow has no steps")
    if len(nodes) > settings.workflow_max_nodes:
        raise WorkflowError(f"Workflow exceeds the {settings.workflow_max_nodes}-step limit")

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
    workflow_input = workflow_input if isinstance(workflow_input, dict) else {"value": workflow_input}
    branching_ids = frozenset(n["id"] for n in nodes if n.get("type") in BRANCHING)

    for node_id in topological_order(nodes, edges):
        node = by_id[node_id]
        ntype = node.get("type")
        data = node.get("data") or {}
        label = data.get("label") or ntype

        taken_from = []
        for e in incoming[node_id]:
            src = e["source"]
            if state.get(src) == "done" and _branch_taken(by_id[src], outputs.get(src) or {}, e):
                taken_from.append(src)
        if incoming[node_id] and not taken_from:
            state[node_id] = "skipped"
            steps.append({"node_id": node_id, "type": ntype, "label": label, "status": "skipped"})
            continue

        if time.monotonic() > deadline:
            raise WorkflowError("Workflow exceeded its time limit", steps)

        step = {"node_id": node_id, "type": ntype, "label": label, "action": data.get("action")}
        retries, delay, continue_on_error = _settings(data)
        attempt = 0
        started = time.monotonic()

        while True:
            attempt += 1
            try:
                out = _execute_node(
                    ntype,
                    data,
                    outputs,
                    workflow_input,
                    taken_from,
                    call_agent,
                    call_tool,
                    call_action,
                    node,
                    step,
                    branching_ids,
                    last_output,
                )
                break
            except Exception as exc:  # noqa: BLE001 - every failure is reported on the step
                if attempt <= retries and time.monotonic() + delay < deadline:
                    time.sleep(delay)
                    continue
                message = str(exc) or exc.__class__.__name__
                step.update(error=message, attempts=attempt, duration_ms=int((time.monotonic() - started) * 1000))
                if continue_on_error:
                    out = {"error": message}
                    step["status"] = "error_continued"
                    break
                step["status"] = "failed"
                steps.append(step)
                raise WorkflowError(f"Step '{label}' failed: {message}", steps) from exc

        outputs[node_id] = out
        state[node_id] = "done"
        if ntype == "end":
            final_output = out
        elif ntype not in BRANCHING:
            last_output = out
        step.setdefault("status", "success")
        step.update(output=out, attempts=attempt, duration_ms=int((time.monotonic() - started) * 1000))
        steps.append(step)

    return {"output": final_output if final_output is not None else last_output, "steps": steps}


def _execute_node(
    ntype,
    data,
    outputs,
    workflow_input,
    taken_from,
    call_agent,
    call_tool,
    call_action,
    node,
    step,
    branching_ids=frozenset(),
    last_output=None,
):
    mappings = data.get("mappings") or {}
    if ntype == "input":
        return workflow_input

    if ntype == "action":
        if call_action is None:
            raise WorkflowError("Action steps are not available here")
        config = resolve_value(data.get("config") or {}, outputs, workflow_input)
        step["input"] = config
        return _wrap(call_action(str(data.get("action") or ""), config, node))

    if ntype == "condition":
        return {"result": evaluate_condition(data.get("condition") or {}, outputs, workflow_input)}

    if ntype == "switch":
        value = resolve_value(data.get("value", ""), outputs, workflow_input)
        return {"value": value, "matched": switch_match(value, data.get("cases") or [])}

    if ntype == "end":
        cfg = data.get("config") or {}
        if cfg.get("output") not in (None, ""):
            return resolve_value(cfg["output"], outputs, workflow_input)
        if mappings:
            return {k: resolve_mapping(m, outputs, workflow_input) for k, m in mappings.items()}
        # Default: the output of the step that led here (the last one, if several branches joined).
        # If that step only made a decision (If/Switch), return the last real result instead.
        for src in reversed(taken_from):
            if outputs.get(src) is not None and src not in branching_ids:
                return outputs[src]
        return last_output

    # ---- older node types ----
    inputs = {k: resolve_mapping(m, outputs, workflow_input) for k, m in mappings.items()}
    step["input"] = inputs
    if ntype == "agent":
        message = inputs.get("message")
        if message in (None, ""):
            message = workflow_input.get("message")
        if message in (None, ""):
            raise WorkflowError("Agent step has no message")
        return call_agent(int(data.get("agent_id") or 0), str(message))
    if ntype == "tool":
        return _wrap(call_tool(str(data.get("tool") or ""), inputs))
    if ntype == "transform":
        return inputs
    raise WorkflowError(f"Unknown step type '{ntype}'")
