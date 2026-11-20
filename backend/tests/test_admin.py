from .conftest import create_agent


def test_provider_and_model_admin(client, admin):
    p = client.post(
        "/api/models/providers",
        headers=admin,
        json={"name": "vllm", "base_url": "http://vllm:8000/v1/", "api_key_env": "VLLM_KEY"},
    )
    assert p.status_code == 201
    assert p.json()["base_url"] == "http://vllm:8000/v1"
    bad = client.post("/api/models/providers", headers=admin, json={"name": "x", "base_url": "http://x", "api_key_env": "lower-case"})
    assert bad.status_code == 422  # env var names only; secrets are never stored

    m = client.post(
        "/api/models",
        headers=admin,
        json={"provider_id": p.json()["id"], "model_name": "llama", "display_name": "Llama", "is_default": True},
    ).json()
    defaults = [x for x in client.get("/api/models", headers=admin).json() if x["is_default"]]
    assert [d["id"] for d in defaults] == [m["id"]]

    create_agent(client, admin, model_id=m["id"])
    assert client.delete(f"/api/models/{m['id']}", headers=admin).status_code == 409


def test_metrics_and_audit_filters(client, admin, llm):
    agent = create_agent(client, admin)
    client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "hi"})
    m = client.get("/api/admin/metrics?hours=1", headers=admin).json()
    assert m["runs_total"] == 1
    assert m["runs_by_status"] == {"succeeded": 1}
    assert m["prompt_tokens"] == 10
    assert m["top_targets"][0]["name"] == "Helper"

    audit = client.get("/api/admin/audit?action=agent.", headers=admin).json()
    assert {i["action"] for i in audit["items"]} == {"agent.create", "agent.run"}
    assert all(i["request_id"] for i in audit["items"])
