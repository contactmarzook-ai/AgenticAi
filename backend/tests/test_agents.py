from app.llm.client import LLMResponse

from .conftest import create_agent, tool_call


def default_model_id(client, headers) -> int:
    return client.get("/api/models", headers=headers).json()[0]["id"]


def test_builder_creates_agent_and_department_is_forced(client, make_user):
    builder = make_user("b@example.com", "builder", department="ops")
    agent = create_agent(client, builder, department="finance", tools=["calculator"])
    assert agent["department"] == "ops"  # builders cannot place agents in other departments
    assert agent["can_edit"] is True


def test_visibility_rules(client, make_user):
    builder = make_user("b@example.com", "builder", department="ops")
    same_dept = make_user("same@example.com", "user", department="ops")
    other_dept = make_user("other@example.com", "user", department="hr")

    dept = create_agent(client, builder, name="DeptAgent", visibility="department")
    private = create_agent(client, builder, name="PrivateAgent", visibility="private")
    public = create_agent(client, builder, name="PublicAgent", visibility="public")

    names = lambda h: {a["name"] for a in client.get("/api/agents", headers=h).json()}  # noqa: E731
    assert names(same_dept) == {"DeptAgent", "PublicAgent"}
    assert names(other_dept) == {"PublicAgent"}
    assert names(builder) == {"DeptAgent", "PrivateAgent", "PublicAgent"}

    # Hidden agents cannot be run either (the gap in the reference platform).
    for agent in (dept, private):
        assert (
            client.post(f"/api/agents/{agent['id']}/run", headers=other_dept, json={"message": "hi"}).status_code == 404
        )
    assert client.post(f"/api/agents/{public['id']}/run", headers=other_dept, json={"message": "hi"}).status_code == 200
    # Users can run but not edit.
    assert client.put(f"/api/agents/{public['id']}", headers=same_dept, json={"name": "x"}).status_code == 403


def test_tool_role_restriction_and_unknown_tool(client, make_user, admin):
    builder = make_user("b@example.com", "builder")
    r = client.post("/api/agents", headers=builder, json={"name": "x", "tools": ["does_not_exist"]})
    assert r.status_code == 400
    # http_get requires builder: fine for builder; admin too.
    create_agent(client, builder, tools=["http_get"])


def test_model_without_tool_support_rejects_tools(client, admin):
    providers = client.get("/api/models/providers", headers=admin).json()
    m = client.post(
        "/api/models",
        headers=admin,
        json={"provider_id": providers[0]["id"], "model_name": "tiny", "display_name": "Tiny", "supports_tools": False},
    ).json()
    r = client.post("/api/agents", headers=admin, json={"name": "x", "model_id": m["id"], "tools": ["calculator"]})
    assert r.status_code == 400


def test_model_role_allowlist(client, admin, make_user):
    providers = client.get("/api/models/providers", headers=admin).json()
    big = client.post(
        "/api/models",
        headers=admin,
        json={
            "provider_id": providers[0]["id"],
            "model_name": "big",
            "display_name": "Big",
            "allowed_roles": ["admin"],
        },
    ).json()
    builder = make_user("b@example.com", "builder")
    assert big["id"] not in {m["id"] for m in client.get("/api/models", headers=builder).json()}
    r = client.post("/api/agents", headers=builder, json={"name": "x", "model_id": big["id"]})
    assert r.status_code == 403

    # An admin-built public agent on the restricted model cannot be run by a normal user.
    agent = create_agent(client, admin, model_id=big["id"], visibility="public")
    user = make_user("u@example.com", "user")
    run = client.post(f"/api/agents/{agent['id']}/run", headers=user, json={"message": "hi"}).json()
    assert run["status"] == "failed"
    assert "not allowed" in run["error"]


def test_tool_calling_loop(client, admin, llm):
    agent = create_agent(client, admin, tools=["calculator"])

    def handler(messages, tools, json_mode):
        if messages[-1]["role"] == "tool":
            return LLMResponse(content=f"The total is {messages[-1]['content']}")
        assert tools and tools[0]["function"]["name"] == "calculate"
        return tool_call("calculator", {"expression": "2 + 3 * 4"})

    llm.handler = handler
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "add it up"}).json()
    assert run["status"] == "succeeded", run
    assert "14" in run["output"]["answer"]
    tool_steps = [s for s in run["steps"] if s["type"] == "tool"]
    assert tool_steps[0]["status"] == "success"
    assert run["llm_calls"] == 2
    assert run["prompt_tokens"] == 20
    # System prompt went first.
    assert llm.calls[0]["messages"][0] == {"role": "system", "content": "Be helpful."}


def test_model_cannot_call_tools_not_attached(client, admin, llm):
    agent = create_agent(client, admin, tools=["calculator"])
    state = {"n": 0}

    def handler(messages, tools, json_mode):
        state["n"] += 1
        if state["n"] == 1:
            return tool_call("http_get", {"url": "http://169.254.169.254/"})
        return LLMResponse(content="done")

    llm.handler = handler
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "x"}).json()
    step = next(s for s in run["steps"] if s["type"] == "tool")
    assert step["status"] == "error"
    assert "not available" in step["error"]
    assert run["status"] == "succeeded"


def test_invalid_tool_arguments_are_reported_to_model(client, admin, llm):
    agent = create_agent(client, admin, tools=["calculator"])
    state = {"n": 0}

    def handler(messages, tools, json_mode):
        state["n"] += 1
        if state["n"] == 1:
            return tool_call("calculator", {"expr": "1+1"})
        assert "Invalid arguments" in messages[-1]["content"]
        return LLMResponse(content="sorry")

    llm.handler = handler
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "x"}).json()
    assert run["status"] == "succeeded"


def test_step_cap_forces_final_answer(client, admin, llm):
    agent = create_agent(client, admin, tools=["get_current_time"], max_steps=2)

    def handler(messages, tools, json_mode):
        if tools is None:
            return LLMResponse(content="final")
        return tool_call("get_current_time", {})

    llm.handler = handler
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "loop"}).json()
    assert run["output"]["answer"] == "final"
    assert run["llm_calls"] == 3  # 2 steps + forced final


def test_llm_failure_marks_run_failed(client, admin, llm):
    from app.llm.client import LLMError

    agent = create_agent(client, admin)

    def handler(messages, tools, json_mode):
        raise LLMError("LLM endpoint returned HTTP 500")

    llm.handler = handler
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "x"}).json()
    assert run["status"] == "failed"
    assert "HTTP 500" in run["error"]


def test_disable_agent_hides_it(client, admin):
    agent = create_agent(client, admin)
    assert client.delete(f"/api/agents/{agent['id']}", headers=admin).status_code == 200
    assert agent["id"] not in {a["id"] for a in client.get("/api/agents", headers=admin).json()}
    r = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "x"})
    assert r.status_code == 409
