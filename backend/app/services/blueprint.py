"""A compact workflow format ("blueprint") used by templates and by the AI builder.

Blueprint:
{
  "name": "...", "description": "...",
  "steps": [
    {"id": "start", "type": "start", "label": "...", "fields": [{"key": "email", "label": "Email", "type": "text", "required": true}]},
    {"id": "n1", "type": "action", "action": "ai_summarize", "label": "...", "config": {...}, "settings": {...}},
    {"id": "n2", "type": "if", "label": "...", "left": "{{n1.total}}", "operator": ">", "right": "1000"},
    {"id": "n3", "type": "switch", "label": "...", "value": "{{n1.category}}", "cases": ["a", "b"]},
    {"id": "finish", "type": "finish", "label": "...", "output": "{{n1.summary}}"}
  ],
  "links": [{"from": "start", "to": "n1"}, {"from": "n2", "to": "n3", "branch": "true"}]
}

`to_definition` converts it to the builder's node/edge graph and lays it out top to bottom.
"""

from typing import Any

TYPE_MAP = {
    "start": "input",
    "input": "input",
    "action": "action",
    "if": "condition",
    "condition": "condition",
    "switch": "switch",
    "finish": "end",
    "end": "end",
}
FORM_FIELD_TYPES = {"text", "textarea", "number", "email", "select", "boolean", "date"}


def layout(nodes: list[dict], edges: list[dict]) -> None:
    """Assign positions: depth = longest path from a start node; siblings spread horizontally."""
    depth: dict[str, int] = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for e in edges:
            if e["source"] in depth and e["target"] in depth and depth[e["target"]] < depth[e["source"]] + 1:
                depth[e["target"]] = depth[e["source"]] + 1
                changed = True
        if not changed:
            break
    rows: dict[int, list[dict]] = {}
    for n in nodes:
        rows.setdefault(depth[n["id"]], []).append(n)
    for d, row in rows.items():
        width = 280
        start_x = 300 - (len(row) - 1) * width / 2
        for i, n in enumerate(row):
            n["position"] = {"x": start_x + i * width, "y": 40 + d * 140}


def _form_fields(raw: Any) -> list[dict]:
    fields = []
    for f in raw or []:
        if not isinstance(f, dict) or not str(f.get("key", "")).strip():
            continue
        key = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(f["key"]).strip())[:50]
        ftype = f.get("type") if f.get("type") in FORM_FIELD_TYPES else "text"
        field = {
            "key": key,
            "label": str(f.get("label") or key)[:100],
            "type": ftype,
            "required": bool(f.get("required")),
        }
        if ftype == "select":
            field["options"] = [str(o) for o in f.get("options") or []][:30]
        fields.append(field)
    return fields


def to_definition(blueprint: dict) -> dict:
    nodes, edges = [], []
    seen = set()
    for step in blueprint.get("steps") or []:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id") or f"n{len(nodes) + 1}")[:40]
        if sid in seen:
            continue
        seen.add(sid)
        ntype = TYPE_MAP.get(str(step.get("type", "")).lower(), "action")
        data: dict[str, Any] = {"label": str(step.get("label") or "")[:120]}
        if ntype == "input":
            data["label"] = data["label"] or "Start"
            data["fields"] = _form_fields(step.get("fields"))
        elif ntype == "action":
            data["action"] = str(step.get("action") or "")
            data["config"] = step.get("config") if isinstance(step.get("config"), dict) else {}
            data["settings"] = step.get("settings") if isinstance(step.get("settings"), dict) else {}
        elif ntype == "condition":
            data["condition"] = {
                "left": str(step.get("left", "")),
                "operator": str(step.get("operator") or "=="),
                "right": "" if step.get("right") is None else str(step.get("right")),
            }
        elif ntype == "switch":
            data["value"] = str(step.get("value", ""))
            data["cases"] = [str(c) for c in step.get("cases") or []][:20]
        elif ntype == "end":
            data["label"] = data["label"] or "Finish"
            data["config"] = {"output": step.get("output", "")} if step.get("output") else {}
        nodes.append({"id": sid, "type": ntype, "data": data})

    for i, link in enumerate(blueprint.get("links") or []):
        if not isinstance(link, dict):
            continue
        src, dst = str(link.get("from", "")), str(link.get("to", ""))
        if src not in seen or dst not in seen:
            continue
        edge = {"id": f"e{i + 1}", "source": src, "target": dst}
        branch = link.get("branch")
        if branch not in (None, ""):
            edge["sourceHandle"] = (
                str(branch).strip().lower() if str(branch).lower() in ("true", "false", "default") else str(branch)
            )
            edge["label"] = {"true": "Yes", "false": "No"}.get(edge["sourceHandle"], edge["sourceHandle"])
        edges.append(edge)

    layout(nodes, edges)
    return {"nodes": nodes, "edges": edges}
