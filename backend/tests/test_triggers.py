import time
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.llm.client import LLMResponse
from app.models import Run, Trigger
from app.services.scheduler import next_fire_time, tick

from .conftest import create_agent, wait_for_run
from .test_workflows import simple_definition


def active_workflow(client, admin):
    agent = create_agent(client, admin)
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "Flow", "definition": simple_definition(agent["id"])}
    ).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    return wf


def test_schedule_validation(client, admin):
    wf = active_workflow(client, admin)
    base = {"name": "t", "workflow_group_id": wf["group_id"], "type": "schedule"}
    assert client.post("/api/triggers", headers=admin, json={**base, "cron": "not a cron"}).status_code == 400
    assert (
        client.post(
            "/api/triggers", headers=admin, json={**base, "cron": "0 9 * * *", "timezone": "Mars/Base"}
        ).status_code
        == 400
    )
    r = client.post("/api/triggers", headers=admin, json={**base, "cron": "0 9 * * 1-5", "timezone": "Asia/Kolkata"})
    assert r.status_code == 201
    assert r.json()["next_run_at"] is not None
    assert r.json()["webhook_token"] is None


def test_next_fire_time_respects_timezone():
    after = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # Monday 05:30 IST
    nxt = next_fire_time("0 9 * * *", "Asia/Kolkata", after)
    assert nxt == datetime(2026, 1, 5, 3, 30, tzinfo=timezone.utc)


def test_tick_fires_due_trigger_once(client, admin, llm):
    llm.handler = lambda messages, tools, json_mode: LLMResponse(content="scheduled ok")
    wf = active_workflow(client, admin)
    trig = client.post(
        "/api/triggers",
        headers=admin,
        json={
            "name": "t",
            "workflow_group_id": wf["group_id"],
            "type": "schedule",
            "cron": "*/5 * * * *",
            "input": {"message": "go"},
        },
    ).json()

    db = SessionLocal()
    row = db.get(Trigger, trig["id"])
    row.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert tick(db) == 1
    assert tick(db) == 0  # already advanced
    run = db.query(Run).filter(Run.trigger_id == trig["id"]).one()
    for _ in range(100):  # the schedule queues the run; the worker executes it
        db.refresh(run)
        if run.status not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert run.status == "succeeded" and run.source == "schedule"
    db.close()


def test_webhook_auth_and_payload(client, admin, llm):
    llm.handler = lambda messages, tools, json_mode: LLMResponse(content="hook:" + messages[-1]["content"])
    wf = active_workflow(client, admin)
    trig = client.post(
        "/api/triggers",
        headers=admin,
        json={"name": "hook", "workflow_group_id": wf["group_id"], "type": "webhook", "input": {"channel": "ops"}},
    ).json()
    token = trig["webhook_token"]
    assert token.startswith("whk_")

    assert client.post(f"/api/hooks/{trig['id']}", json={}).status_code == 404
    assert client.post(f"/api/hooks/{trig['id']}", headers={"X-Webhook-Token": "wrong"}, json={}).status_code == 404

    r = client.post(f"/api/hooks/{trig['id']}", headers={"X-Webhook-Token": token}, json={"message": "from webhook"})
    assert r.status_code == 202
    run = wait_for_run(client, admin, r.json()["id"])
    assert run["output"]["result"]["answer"] == "hook:from webhook"

    rotated = client.post(f"/api/triggers/{trig['id']}/rotate-token", headers=admin).json()["webhook_token"]
    assert client.post(f"/api/hooks/{trig['id']}", headers={"X-Webhook-Token": token}, json={}).status_code == 404
    assert client.post(f"/api/hooks/{trig['id']}", headers={"X-Webhook-Token": rotated}, json={}).status_code == 202


def test_users_cannot_create_triggers(client, admin, make_user):
    wf = active_workflow(client, admin)
    user = make_user("u@example.com")
    r = client.post(
        "/api/triggers", headers=user, json={"name": "t", "workflow_group_id": wf["group_id"], "type": "webhook"}
    )
    assert r.status_code == 403
