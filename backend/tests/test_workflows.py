import pytest

from app.llm.client import LLMResponse
from app.services.workflow_engine import WorkflowError, evaluate_condition, resolve_mapping, run_definition

from .conftest import create_agent, wait_for_run


def node(nid, ntype, **data):
    return {"id": nid, "type": ntype, "data": data}


def edge(s, t, handle=None):
    e = {"id": f"{s}-{t}", "source": s, "target": t}
    if handle:
        e["sourceHandle"] = handle
    return e


def no_agent(agent_id, message):
    raise AssertionError("agent should not be called")


def tool_fn(name, args):
    from app.tools import registry

    return registry.execute(name, args)


# ---------- engine ----------
def test_mappings_and_templates():
    outputs = {"n1": {"answer": "yes", "nested": {"x": [10, 20]}}}
    inp = {"name": "Asha"}
    assert resolve_mapping({"source": "static", "value": 5}, outputs, inp) == 5
    assert resolve_mapping({"source": "input", "path": "name"}, outputs, inp) == "Asha"
    assert resolve_mapping({"source": "workflow", "path": "name"}, outputs, inp) == "Asha"
    assert resolve_mapping({"source": "node", "node_id": "n1", "path": "nested.x.1"}, outputs, inp) == 20
    tpl = {"source": "template", "value": "Hi {{input.name}}, answer={{ n1.answer }}, missing={{n9.x}}"}
    assert resolve_mapping(tpl, outputs, inp) == "Hi Asha, answer=yes, missing="


@pytest.mark.parametrize(
    "left,op,right,expected",
    [
        (5, ">", "3", True),
        ("10", "<", 9, False),
        ("abc", "==", "abc", True),
        (2, "==", "2.0", True),
        ("Hello World", "contains", "world", True),
        ("", "is_empty", None, True),
        ("text", ">", 3, False),  # non-numeric comparisons are false, not a crash
    ],
)
def test_conditions(left, op, right, expected):
    cond = {"left": {"source": "static", "value": left}, "operator": op, "right": {"source": "static", "value": right}}
    assert evaluate_condition(cond, {}, {}) is expected


def test_branching_skips_untaken_path_and_join_waits():
    calls = []

    def agent(agent_id, agent_input):
        calls.append((agent_id, agent_input["message"]))
        return {"answer": f"agent{agent_id}:{agent_input['message']}"}

    definition = {
        "nodes": [
            node("in", "input"),
            node(
                "cond",
                "condition",
                condition={
                    "left": {"source": "input", "path": "amount"},
                    "operator": ">",
                    "right": {"source": "static", "value": 1000},
                },
            ),
            node(
                "big",
                "agent",
                agent_id=1,
                mappings={"message": {"source": "template", "value": "big {{input.amount}}"}},
            ),
            node("small", "agent", agent_id=2, mappings={"message": {"source": "static", "value": "small"}}),
            node("end", "end", mappings={"big": {"source": "node", "node_id": "big", "path": "answer"}}),
        ],
        "edges": [
            edge("in", "cond"),
            edge("cond", "big", "true"),
            edge("cond", "small", "false"),
            edge("big", "end"),
            edge("small", "end"),
        ],
    }
    res = run_definition(definition, {"amount": 5000}, agent, tool_fn)
    assert calls == [(1, "big 5000")]
    assert res["output"] == {"big": "agent1:big 5000"}
    statuses = {s["node_id"]: s["status"] for s in res["steps"]}
    assert statuses["small"] == "skipped" and statuses["end"] == "success"


def test_join_runs_after_all_predecessors():
    order = []

    def agent(agent_id, message):
        order.append(agent_id)
        return {"answer": str(agent_id)}

    definition = {
        "nodes": [
            node("in", "input"),
            node("a", "agent", agent_id=1, mappings={"message": {"source": "static", "value": "a"}}),
            node("b1", "transform", mappings={"v": {"source": "static", "value": 1}}),
            node("b2", "agent", agent_id=2, mappings={"message": {"source": "static", "value": "b"}}),
            node(
                "join",
                "transform",
                mappings={
                    "a": {"source": "node", "node_id": "a", "path": "answer"},
                    "b": {"source": "node", "node_id": "b2", "path": "answer"},
                },
            ),
            node("end", "end"),
        ],
        "edges": [
            edge("in", "a"),
            edge("in", "b1"),
            edge("b1", "b2"),
            edge("a", "join"),
            edge("b2", "join"),
            edge("join", "end"),
        ],
    }
    res = run_definition(definition, {}, agent, tool_fn)
    assert res["output"] == {"a": "1", "b": "2"}


def test_tool_node_and_failure_reporting():
    definition = {
        "nodes": [
            node("in", "input"),
            node("calc", "tool", tool="calculator", mappings={"expression": {"source": "input", "path": "expr"}}),
            node("end", "end"),
        ],
        "edges": [edge("in", "calc"), edge("calc", "end")],
    }
    assert run_definition(definition, {"expr": "6*7"}, no_agent, tool_fn)["output"]["result"] == 42
    with pytest.raises(WorkflowError) as exc:
        run_definition(definition, {"expr": "1/0"}, no_agent, tool_fn)
    assert "Division by zero" in str(exc.value)
    by_node = {st["node_id"]: st for st in exc.value.steps}
    assert by_node["calc"]["status"] == "failed"
    assert by_node["end"]["status"] == "skipped" and "earlier step failed" in by_node["end"]["error"]


def test_cycle_rejected():
    definition = {"nodes": [node("a", "transform"), node("b", "transform")], "edges": [edge("a", "b"), edge("b", "a")]}
    with pytest.raises(WorkflowError):
        run_definition(definition, {}, no_agent, tool_fn)


# ---------- validator + API ----------
def simple_definition(agent_id):
    return {
        "nodes": [
            node("in", "input"),
            node("ag", "agent", agent_id=agent_id, mappings={"message": {"source": "input", "path": "message"}}),
            node("end", "end", mappings={"answer": {"source": "node", "node_id": "ag", "path": "answer"}}),
        ],
        "edges": [edge("in", "ag"), edge("ag", "end")],
    }


def test_validator_reports_problems(client, admin):
    bad = {
        "nodes": [node("in", "input"), node("t", "tool", tool="calculator"), node("x", "agent")],
        "edges": [edge("in", "t"), edge("t", "ghost")],
    }
    wf = client.post("/api/workflows", headers=admin, json={"name": "Bad", "definition": bad}).json()
    res = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()
    text = " | ".join(res["errors"])
    assert not res["is_valid"]
    assert "no longer exists" in text
    assert "Finish step" in text
    assert "'expression' is not set" in text
    assert "choose an agent" in text


def test_versioning_lifecycle(client, admin, llm):
    agent = create_agent(client, admin)
    v1 = client.post(
        "/api/workflows", headers=admin, json={"name": "Flow", "definition": simple_definition(agent["id"])}
    ).json()
    assert v1["status"] == "draft" and v1["version"] == 1

    # Drafts are not runnable outside of test.
    assert client.post(f"/api/workflows/{v1['id']}/run", headers=admin, json={"input": {}}).status_code == 409

    assert client.post(f"/api/workflows/{v1['id']}/activate", headers=admin).json()["status"] == "active"
    assert client.put(f"/api/workflows/{v1['id']}", headers=admin, json={"name": "edit"}).status_code == 409

    v2 = client.post(
        "/api/workflows",
        headers=admin,
        json={"name": "Flow", "group_id": v1["group_id"], "definition": simple_definition(agent["id"])},
    ).json()
    assert v2["group_id"] == v1["group_id"] and v2["version"] == 2 and v2["status"] == "draft"

    client.post(f"/api/workflows/{v2['id']}/activate", headers=admin)
    versions = {
        w["version"]: w["status"] for w in client.get(f"/api/workflows?group_id={v1['group_id']}", headers=admin).json()
    }
    assert versions == {1: "archived", 2: "active"}


def test_activation_blocked_by_validation(client, admin):
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "Empty", "definition": {"nodes": [], "edges": []}}
    ).json()
    r = client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    assert r.status_code == 400
    assert r.json()["detail"]["errors"]


def test_test_and_async_run(client, admin, llm):
    llm.handler = lambda messages, tools, json_mode: LLMResponse(content="echo:" + messages[-1]["content"])
    agent = create_agent(client, admin)
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "Flow", "definition": simple_definition(agent["id"])}
    ).json()

    test_run = client.post(
        f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {"message": "hello"}}
    ).json()
    assert test_run["status"] == "succeeded", test_run
    assert test_run["output"]["result"] == {"answer": "echo:hello"}
    assert test_run["llm_calls"] == 1

    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    queued = client.post(f"/api/workflows/{wf['id']}/run", headers=admin, json={"input": {"message": "async"}})
    assert queued.status_code == 202
    run = wait_for_run(client, admin, queued.json()["id"])
    assert run["status"] == "succeeded"
    assert run["output"]["result"]["answer"] == "echo:async"


def test_users_see_only_their_runs(client, admin, make_user, llm):
    agent = create_agent(client, admin, visibility="public")
    user = make_user("u@example.com")
    client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "admin run"})
    mine = client.post(f"/api/agents/{agent['id']}/run", headers=user, json={"message": "user run"}).json()
    listed = client.get("/api/runs", headers=user).json()
    assert [r["id"] for r in listed["items"]] == [mine["id"]]
    assert client.get("/api/runs", headers=admin).json()["total"] == 2
    admin_run = client.get("/api/runs", headers=admin).json()["items"][-1]["id"]
    assert client.get(f"/api/runs/{admin_run}", headers=user).status_code == 404


def test_workflow_visibility(client, make_user):
    builder = make_user("b@example.com", "developer", department="ops")
    other = make_user("o@example.com", "developer", department="hr")
    wf = client.post(
        "/api/workflows", headers=builder, json={"name": "Private", "visibility": "private", "definition": {}}
    ).json()
    assert client.get(f"/api/workflows/{wf['id']}", headers=other).status_code == 404
    r = client.post(
        "/api/workflows", headers=other, json={"name": "hijack", "group_id": wf["group_id"], "definition": {}}
    )
    assert r.status_code == 404
