import json

from app.llm.client import LLMResponse
from app.services.orchestrator import keyword_matches

from .conftest import create_agent


def new_session(client, headers, **body):
    r = client.post("/api/chat/sessions", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def send(client, headers, sid, text):
    r = client.post(f"/api/chat/sessions/{sid}/messages", headers=headers, json={"message": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_keyword_matching_ignores_empty_and_partial_words():
    assert keyword_matches("Please generate a NOC letter", "noc, ")
    assert not keyword_matches("what is the weather", "noc,")  # trailing comma must not match everything
    assert not keyword_matches("economic outlook", "noc")  # no matches inside words
    assert not keyword_matches("anything", ",, ,")


def test_keyword_fast_path(client, admin, llm):
    agent = create_agent(client, admin, name="NOC", trigger_keywords="noc letter, no objection", visibility="public")
    llm.handler = lambda messages, tools, json_mode: LLMResponse(content="NOC drafted")
    sid = new_session(client, admin)
    reply = send(client, admin, sid, "I need a NOC letter for Ravi")
    assert reply["content"] == "NOC drafted"
    assert reply["metadata_json"]["routing"]["method"] == "keyword"
    assert reply["metadata_json"]["target"]["id"] == agent["id"]
    assert reply["run_id"]
    # Router LLM was never called; only the agent call happened.
    assert not any(c["json_mode"] for c in llm.calls)


def test_llm_routing_and_general_fallback(client, admin, llm):
    agent = create_agent(client, admin, name="Invoices", description="Answers invoice questions", visibility="public")

    def handler(messages, tools, json_mode):
        if json_mode:
            wants = "invoice" in messages[-1]["content"]
            return LLMResponse(
                content=json.dumps({"type": "agent" if wants else "none", "id": agent["id"], "confidence": 0.9})
            )
        if messages[0]["content"] == "Be helpful.":
            return LLMResponse(content="agent answer")
        return LLMResponse(content="general answer")

    llm.handler = handler
    sid = new_session(client, admin)
    r1 = send(client, admin, sid, "status of invoice 42?")
    assert r1["content"] == "agent answer"
    assert r1["metadata_json"]["routing"]["method"] == "llm"
    r2 = send(client, admin, sid, "hello there")
    assert r2["content"] == "general answer"
    assert r2["metadata_json"]["routing"]["method"] == "general"


def test_router_cannot_pick_hidden_agent(client, admin, make_user, llm):
    hidden = create_agent(client, admin, name="Secret", visibility="private")
    user = make_user("u@example.com")
    llm.handler = lambda messages, tools, json_mode: (
        LLMResponse(content=json.dumps({"type": "agent", "id": hidden["id"], "confidence": 1}))
        if json_mode
        else LLMResponse(content="general")
    )
    sid = new_session(client, user)
    reply = send(client, user, sid, "use the secret agent")
    assert reply["content"] == "general"
    assert reply["run_id"] is None


def test_pinned_agent_and_history(client, admin, llm):
    agent = create_agent(client, admin, name="Pinned")
    llm.handler = lambda messages, tools, json_mode: LLMResponse(content=f"seen {len(messages)} messages")
    sid = new_session(client, admin, agent_id=agent["id"])
    send(client, admin, sid, "first")
    second = send(client, admin, sid, "second")
    # system + (user, assistant) history + new user message
    assert second["content"] == "seen 4 messages"
    assert second["metadata_json"]["routing"]["method"] == "pinned"


def test_sessions_are_private(client, admin, make_user):
    sid = new_session(client, admin)
    user = make_user("u@example.com")
    assert client.get(f"/api/chat/sessions/{sid}/messages", headers=user).status_code == 404
    assert client.post(f"/api/chat/sessions/{sid}/messages", headers=user, json={"message": "x"}).status_code == 404
    assert client.delete(f"/api/chat/sessions/{sid}", headers=user).status_code == 404


def test_no_model_configured_gives_clear_message(client, admin):
    for m in client.get("/api/models", headers=admin).json():
        client.put(f"/api/models/{m['id']}", headers=admin, json={**m, "is_active": False})
    sid = new_session(client, admin)
    reply = send(client, admin, sid, "hi")
    assert "No LLM model is configured" in reply["content"] or "disabled" in reply["content"]
