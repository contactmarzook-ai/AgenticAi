"""Agent contracts: JSON Schema input/output, validation before and after runs, workflow
mappings, chat, capabilities and tags."""

import json

from app import contracts
from app.llm.client import LLMResponse

from .conftest import create_agent
from .test_automation import chain, finish, start, step

ORDER_IN = {
    "type": "object",
    "properties": {
        "order_id": {"type": "integer", "description": "Order number"},
        "priority": {"type": "string", "enum": ["low", "high"], "default": "low"},
        "customer": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}, "zip": {"type": "string"}},
                    "required": ["city"],
                },
            },
            "required": ["name"],
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"sku": {"type": "string"}, "qty": {"type": "integer"}},
                "required": ["sku"],
            },
        },
        "gift": {"type": "boolean"},
    },
    "required": ["order_id", "customer"],
}
ORDER_OUT = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["open", "shipped"]},
        "total": {"type": "number"},
        "lines": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "total"],
}
GOOD_INPUT = {"order_id": 42, "customer": {"name": "Ann", "address": {"city": "Chennai"}}}


def contract_agent(client, headers, **kw):
    return create_agent(client, headers, name="Orders", input_schema=ORDER_IN, output_schema=ORDER_OUT, **kw)


def reply(*contents):
    """FakeLLM handler returning the given replies in order (last one repeats)."""
    seq = list(contents)

    def handler(messages, tools, json_mode):
        return LLMResponse(content=seq.pop(0) if len(seq) > 1 else seq[0])

    return handler


# ---------- schemas: create, update, persist, retrieve ----------
def test_default_contract_for_agents_without_schemas(client, admin):
    agent = create_agent(client, admin)
    assert agent["input_schema"] == contracts.DEFAULT_INPUT_SCHEMA
    assert agent["output_schema"] == contracts.DEFAULT_OUTPUT_SCHEMA


def test_schemas_are_saved_normalised_and_returned(client, admin):
    agent = contract_agent(client, admin)
    got = client.get(f"/api/agents/{agent['id']}", headers=admin).json()
    assert got["input_schema"]["additionalProperties"] is False
    addr = got["input_schema"]["properties"]["customer"]["properties"]["address"]
    assert addr["required"] == ["city"] and addr["additionalProperties"] is False
    assert got["input_schema"]["properties"]["items"]["items"]["additionalProperties"] is False
    assert got["output_schema"]["required"] == ["status", "total"]
    assert "structured-input" in got["effective_capabilities"] and "structured-output" in got["effective_capabilities"]

    # Update: change the output contract, keep the input one.
    body = {
        **{k: got[k] for k in ("name", "system_prompt", "tools", "visibility", "input_schema")},
        "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    }
    r = client.put(f"/api/agents/{agent['id']}", headers=admin, json=body)
    assert r.status_code == 200, r.text
    again = client.get(f"/api/agents/{agent['id']}", headers=admin).json()
    assert again["output_schema"]["properties"] == {"ok": {"type": "boolean"}}
    assert again["input_schema"] == got["input_schema"]


def test_invalid_schemas_are_rejected_on_save(client, admin):
    deep = {"type": "string"}
    for _ in range(8):
        deep = {"type": "object", "properties": {"x": deep}}
    bad = {
        "root not object": {"type": "string"},
        "unsupported keyword": {"type": "object", "properties": {"a": {"type": "string", "pattern": "x"}}},
        "unknown type": {"type": "object", "properties": {"a": {"type": "date"}}},
        "required unknown": {"type": "object", "properties": {}, "required": ["a"]},
        "array without items": {"type": "object", "properties": {"a": {"type": "array"}}},
        "enum wrong type": {"type": "object", "properties": {"a": {"type": "integer", "enum": ["x"]}}},
        "default wrong type": {"type": "object", "properties": {"a": {"type": "integer", "default": "x"}}},
        "default not in enum": {
            "type": "object",
            "properties": {"a": {"type": "string", "enum": ["x"], "default": "y"}},
        },
        "bad property name": {"type": "object", "properties": {"a b": {"type": "string"}}},
        "too deep": deep,
    }
    for name, schema in bad.items():
        r = client.post("/api/agents", headers=admin, json={"name": "X", "input_schema": schema})
        assert r.status_code == 400, name
        assert r.json()["detail"]["errors"], name
        r = client.post("/api/agents", headers=admin, json={"name": "X", "output_schema": schema})
        assert r.status_code == 400, name
    assert client.get("/api/agents", headers=admin).json() == []


def test_check_schema_endpoint(client, admin):
    ok = client.post("/api/agents/check-schema", headers=admin, json={"schema": ORDER_IN}).json()
    assert ok["valid"] and ok["schema"]["additionalProperties"] is False
    bad = client.post("/api/agents/check-schema", headers=admin, json={"schema": {"type": "array"}}).json()
    assert not bad["valid"] and "top level" in bad["problems"][0]


# ---------- input validation ----------
def test_invalid_input_is_rejected_before_running(client, admin, llm):
    agent = contract_agent(client, admin)
    r = client.post(
        f"/api/agents/{agent['id']}/run",
        headers=admin,
        json={"input": {"order_id": "42", "customer": {"address": {"zip": 1}}, "priority": "urgent", "extra": 1}},
    )
    assert r.status_code == 422
    fields = {(e["path"], e["message"]) for e in r.json()["detail"]["fields"]}
    assert ("order_id", "must be an integer") in fields
    assert ("customer", "'name' is required") in fields
    assert ("customer.address", "'city' is required") in fields
    assert ("customer.address.zip", "must be a string") in fields
    assert ("priority", 'must be one of: "low", "high"') in fields
    assert ("(root)", "unknown field: extra") in fields
    assert llm.calls == []  # nothing ran
    assert client.get("/api/runs", headers=admin).json()["total"] == 0
    audit = client.get("/api/admin/audit?action=agent.run&status=failure", headers=admin).json()
    assert audit["total"] == 1


def test_message_is_rejected_for_structured_agent_and_accepted_for_default(client, admin, llm):
    structured = contract_agent(client, admin)
    assert client.post(f"/api/agents/{structured['id']}/run", headers=admin, json={"message": "hi"}).status_code == 422
    plain = create_agent(client, admin, name="Plain")
    r = client.post(f"/api/agents/{plain['id']}/run", headers=admin, json={"message": "hi"}).json()
    assert r["status"] == "succeeded" and r["output"] == {"answer": "fake answer"}
    assert [s["stage"] for s in r["steps"] if s["type"] == "validation"] == ["input", "output"]
    assert client.post(f"/api/agents/{plain['id']}/run", headers=admin, json={}).status_code == 422


def test_valid_input_gets_defaults_and_reaches_the_model_as_json(client, admin, llm):
    agent = contract_agent(client, admin)
    llm.handler = reply('{"status": "open", "total": 12.5}')
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"input": GOOD_INPUT}).json()
    assert run["status"] == "succeeded", run
    assert run["input"]["input"]["priority"] == "low"  # default applied and recorded
    user_msg = llm.calls[0]["messages"][-1]["content"]
    assert json.loads(user_msg.split("\n", 1)[1]) == {**GOOD_INPUT, "priority": "low"}
    system = llm.calls[0]["messages"][0]["content"]
    assert "JSON Schema" in system and '"total"' in system


# ---------- output validation ----------
def test_valid_structured_output(client, admin, llm):
    agent = contract_agent(client, admin)
    llm.handler = reply('```json\n{"status": "shipped", "total": 99, "lines": ["a"]}\n```')
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"input": GOOD_INPUT}).json()
    assert run["status"] == "succeeded"
    assert run["output"] == {"status": "shipped", "total": 99, "lines": ["a"]}
    out_checks = [s for s in run["steps"] if s.get("stage") == "output"]
    assert out_checks == [{"type": "validation", "stage": "output", "valid": True, "errors": [], "attempt": 1}]


def test_malformed_output_is_repaired_once(client, admin, llm):
    agent = contract_agent(client, admin)
    llm.handler = reply('{"status": "lost", "total": "lots"}', '{"status": "open", "total": 3}')
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"input": GOOD_INPUT}).json()
    assert run["status"] == "succeeded" and run["output"] == {"status": "open", "total": 3}
    checks = [s for s in run["steps"] if s.get("stage") == "output"]
    assert [c["valid"] for c in checks] == [False, True]
    assert {e["path"] for e in checks[0]["errors"]} == {"status", "total"}
    assert llm.calls[1]["json_mode"] is True
    assert "does not match" in llm.calls[1]["messages"][-1]["content"]


def test_malformed_output_twice_fails_the_run_and_is_recorded(client, admin, llm):
    agent = contract_agent(client, admin)
    llm.handler = reply("Sorry, I could not do it")
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"input": GOOD_INPUT}).json()
    assert run["status"] == "failed"
    assert "Output does not match the agent's output schema" in run["error"]
    checks = [s for s in run["steps"] if s.get("stage") == "output"]
    assert len(checks) == 2 and not any(c["valid"] for c in checks)
    assert checks[0]["errors"][0]["message"] == "The reply was not valid JSON"
    assert run["output"] is None


def test_check_endpoint_validates_input_and_output(client, admin):
    agent = contract_agent(client, admin)
    r = client.post(
        f"/api/agents/{agent['id']}/check", headers=admin, json={"input": GOOD_INPUT, "output": {"status": "x"}}
    ).json()
    assert r["input"]["valid"] and r["input"]["value"]["priority"] == "low"
    assert not r["output"]["valid"]
    assert {e["path"] for e in r["output"]["errors"]} == {"status", "(root)"}


# ---------- workflows: mappings ----------
def _flow(agent_id, mapping, finish_output=None):
    return chain(
        start([{"key": "oid", "label": "Order", "type": "text"}]),
        step("ask", "run_agent", {"agent_id": agent_id, "input": mapping}),
        finish(finish_output),
    )


def test_workflow_maps_inputs_and_uses_structured_output(client, admin, llm):
    agent = contract_agent(client, admin)
    llm.handler = reply('{"status": "open", "total": 7.5}')
    mapping = {"order_id": "{{input.oid}}", "customer": {"name": "Ann", "address": {"city": "Pune"}}, "gift": "true"}
    wf = client.post(
        "/api/workflows",
        headers=admin,
        json={
            "name": "F",
            "definition": _flow(agent["id"], mapping, {"total": "{{ask.total}}", "status": "{{ask.status}}"}),
        },
    ).json()
    assert client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()["is_valid"]
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {"oid": "42"}}).json()
    assert run["status"] == "succeeded", run
    assert run["output"]["result"] == {"total": 7.5, "status": "open"}
    sent = json.loads(llm.calls[0]["messages"][-1]["content"].split("\n", 1)[1])
    assert sent["order_id"] == 42 and sent["gift"] is True  # text from the form coerced to the declared types


def test_incompatible_mappings_are_refused_before_publishing(client, admin):
    agent = contract_agent(client, admin)
    cases = {
        "unknown field": ({"order_id": 1, "customer": {"name": "a"}, "colour": "red"}, "'colour' is not an input"),
        "missing required": ({"order_id": 1}, "'customer' is required by this agent but not mapped"),
        "missing nested required": (
            {"order_id": 1, "customer": {"address": {"city": "x"}}},
            "'customer.name' is required",
        ),
        "wrong fixed type": ({"order_id": "abc", "customer": {"name": "a"}}, "'order_id' must be an integer"),
        "enum violation": (
            {"order_id": 1, "customer": {"name": "a"}, "priority": "urgent"},
            "'priority' must be one of",
        ),
        "nested wrong type": (
            {"order_id": 1, "customer": {"name": "a", "address": {"city": 5}}},
            "'customer.address.city' must be a string",
        ),
        "array of wrong items": (
            {"order_id": 1, "customer": {"name": "a"}, "items": [{"qty": 1}]},
            "'sku' is required",
        ),
    }
    for name, (mapping, expected) in cases.items():
        wf = client.post(
            "/api/workflows", headers=admin, json={"name": name, "definition": _flow(agent["id"], mapping)}
        ).json()
        res = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()
        assert not res["is_valid"], name
        assert any(expected in e for e in res["errors"]), (name, res["errors"])
    # No mapping at all for an agent that needs fields.
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "none", "definition": _flow(agent["id"], {})}
    ).json()
    errs = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()["errors"]
    assert any("needs its input fields filled in (order_id, customer)" in e for e in errs)


def test_runtime_value_that_breaks_the_contract_fails_the_step(client, admin, llm):
    agent = contract_agent(client, admin)
    mapping = {"order_id": "{{input.oid}}", "customer": {"name": "Ann"}}
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "F", "definition": _flow(agent["id"], mapping)}
    ).json()
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {"oid": "not-a-number"}}).json()
    assert run["status"] == "failed"
    assert "Input does not match" in run["error"] and "order_id: must be an integer" in run["error"]
    assert llm.calls == []


def test_message_agents_still_work_in_workflows(client, admin, llm):
    agent = create_agent(client, admin)
    d = chain(
        start(),
        step("ask", "run_agent", {"agent_id": agent["id"], "message": "hello"}),
        finish({"a": "{{ask.answer}}"}),
    )
    wf = client.post("/api/workflows", headers=admin, json={"name": "M", "definition": d}).json()
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}}).json()
    assert run["status"] == "succeeded" and run["output"]["result"] == {"a": "fake answer"}
    d2 = chain(start(), step("ask", "run_agent", {"agent_id": agent["id"]}), finish())
    wf2 = client.post("/api/workflows", headers=admin, json={"name": "M2", "definition": d2}).json()
    assert any(
        "Task for the agent" in e
        for e in client.post(f"/api/workflows/{wf2['id']}/validate", headers=admin).json()["errors"]
    )


# ---------- chat ----------
def _chat(client, headers, agent_id, text):
    sid = client.post("/api/chat/sessions", headers=headers, json={"agent_id": agent_id}).json()["id"]
    return client.post(f"/api/chat/sessions/{sid}/messages", headers=headers, json={"message": text}).json()


def test_chat_explains_structured_agents_and_maps_single_text_field(client, admin, llm):
    agent = contract_agent(client, admin)
    msg = _chat(client, admin, agent["id"], "where is my order?")
    assert "needs structured input (order_id, customer)" in msg["content"]
    summary = create_agent(
        client,
        admin,
        name="Summariser",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}, "words": {"type": "integer", "default": 50}},
            "required": ["text"],
        },
    )
    llm.handler = reply("short summary")
    msg = _chat(client, admin, summary["id"], "a long document")
    assert msg["content"] == "short summary"
    sent = json.loads(llm.calls[-1]["messages"][-1]["content"].split("\n", 1)[1])
    assert sent == {"text": "a long document", "words": 50}


# ---------- capabilities and tags ----------
def test_capabilities_tags_and_discovery(client, admin, llm):
    a = contract_agent(
        client, admin, capabilities=["order.lookup", "order.lookup"], tags=["sales"], tools=["calculate"]
    )
    create_agent(client, admin, name="Other", capabilities=["hr.leave"], tags=["hr"])
    assert a["capabilities"] == ["order.lookup"]
    assert {"order.lookup", "tool:calculate", "structured-output"} <= set(a["effective_capabilities"])
    names = lambda r: [x["name"] for x in r.json()]  # noqa: E731
    assert names(client.get("/api/agents?capability=order.lookup", headers=admin)) == ["Orders"]
    assert names(client.get("/api/agents?capability=tool:calculate", headers=admin)) == ["Orders"]
    assert names(client.get("/api/agents?tag=hr", headers=admin)) == ["Other"]
    assert (
        client.post("/api/agents", headers=admin, json={"name": "Bad", "capabilities": ["Has Spaces"]}).status_code
        == 422
    )
    # The chat router sees capabilities and tags when choosing an agent.
    llm.handler = reply('{"type": "none", "id": null, "confidence": 0}', "general")
    sid = client.post("/api/chat/sessions", headers=admin, json={}).json()["id"]
    client.post(f"/api/chat/sessions/{sid}/messages", headers=admin, json={"message": "anything"})
    routing_prompt = llm.calls[0]["messages"][0]["content"]
    assert (
        '"order.lookup"' in routing_prompt
        and '"hr"' in routing_prompt
        and '"needs": ["customer", "order_id"]' in routing_prompt
    )


# ---------- the shared implementation ----------
def test_contract_helpers_directly():
    schema = contracts.normalize(ORDER_IN)
    value, errors = contracts.validate(schema, GOOD_INPUT)
    assert not errors and value["priority"] == "low"
    assert contracts.coerce(schema, {"order_id": "7", "gift": "false", "items": '[{"sku": "a", "qty": "2"}]'}) == {
        "order_id": 7,
        "gift": False,
        "items": [{"sku": "a", "qty": 2}],
    }
    assert contracts.parse_json_output('noise {"a": 1} noise') == ({"a": 1}, None)
    assert contracts.mapping_problems(schema, {"order_id": "{{x}}", "customer": "{{input.c}}"}) == []
