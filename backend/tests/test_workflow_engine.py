"""Workflow engine: node states, dependencies, branches, parallelism, failures, retries,
timeouts, cancellation, durable checkpoints and recovery, lifecycle, and validation of
malformed definitions."""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models import Run, RunNode, Workflow
from app.services import runs as runs_service
from app.services.workflow_engine import MemoryStore, WorkflowError, run_definition
from app.services.workflow_validator import validate_definition

from .conftest import create_agent, wait_for_run
from .test_automation import chain, finish, start, step


# ---------- engine-level helpers ----------
def act(nid, key="echo", **cfg):
    settings = cfg.pop("settings", {})
    return {"id": nid, "type": "action", "data": {"label": nid, "action": key, "config": cfg, "settings": settings}}


def cond(nid, left, op, right):
    return {
        "id": nid,
        "type": "condition",
        "data": {"label": nid, "condition": {"left": left, "operator": op, "right": right}},
    }


def e(s, t, h=None):
    return {"id": f"{s}-{t}-{h}", "source": s, "target": t, **({"sourceHandle": h} if h else {})}


def S():
    return {"id": "start", "type": "input", "data": {"label": "Start"}}


def F(out=None):
    return {"id": "end", "type": "end", "data": {"label": "Finish", "config": {"output": out} if out else {}}}


class Actions:
    """Fake step implementations, thread-safe, recording what ran and when."""

    def __init__(self):
        self.calls: list[str] = []
        self.lock = threading.Lock()
        self.fail_times: dict[str, int] = {}
        self.active = 0
        self.max_active = 0

    def __call__(self, key, cfg, node):
        nid = node["id"]
        with self.lock:
            self.calls.append(nid)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if cfg.get("sleep"):
                time.sleep(float(cfg["sleep"]))
            if key == "fail" or self.fail_times.get(nid, 0) > 0:
                with self.lock:
                    if nid in self.fail_times:
                        self.fail_times[nid] -= 1
                raise RuntimeError(f"{nid} broke")
            return {"value": cfg.get("value", nid)}
        finally:
            with self.lock:
                self.active -= 1


def run(defn, actions, inp=None, **kw):
    return run_definition(defn, inp or {}, None, None, actions, **kw)


def status_of(steps):
    return {s["node_id"]: s["status"] for s in steps}


# ---------- linear, branching, multiple branches ----------
def test_linear_workflow_runs_in_dependency_order():
    a = Actions()
    d = {
        "nodes": [F("{{b.value}}"), act("b", value="{{a.value}}-b"), act("a", value="A"), S()],
        "edges": [e("start", "a"), e("a", "b"), e("b", "end")],
    }
    res = run(d, a)
    assert a.calls == ["a", "b"]
    assert res["output"] == "A-b"
    assert all(s["status"] == "success" for s in res["steps"])
    assert [s["node_id"] for s in res["steps"]] == ["start", "a", "b", "end"]


def test_conditional_branch_only_runs_the_taken_path_and_join_waits():
    a = Actions()
    d = {
        "nodes": [S(), cond("c", "{{input.amount}}", ">", "1000"), act("big"), act("small"), act("join"), F()],
        "edges": [
            e("start", "c"),
            e("c", "big", "true"),
            e("c", "small", "false"),
            e("big", "join"),
            e("small", "join"),
            e("join", "end"),
        ],
    }
    st = status_of(run(d, a, {"amount": 5000})["steps"])
    assert st == {
        "start": "success",
        "c": "success",
        "big": "success",
        "small": "skipped",
        "join": "success",
        "end": "success",
    }
    a2 = Actions()
    st2 = status_of(run(d, a2, {"amount": 5})["steps"])
    assert st2["big"] == "skipped" and st2["small"] == "success" and a2.calls == ["small", "join"]


def test_multiple_branches_with_switch():
    d = {
        "nodes": [
            S(),
            {
                "id": "sw",
                "type": "switch",
                "data": {"label": "sw", "value": "{{input.kind}}", "cases": ["bug", "billing"]},
            },
            act("bug"),
            act("billing"),
            act("other"),
            F(),
        ],
        "edges": [
            e("start", "sw"),
            e("sw", "bug", "bug"),
            e("sw", "billing", "billing"),
            e("sw", "other", "default"),
            e("bug", "end"),
            e("billing", "end"),
            e("other", "end"),
        ],
    }
    for kind, ran in [("bug", "bug"), ("Billing", "billing"), ("praise", "other")]:
        a = Actions()
        st = status_of(run(d, a, {"kind": kind})["steps"])
        assert a.calls == [ran], kind
        assert [k for k in ("bug", "billing", "other") if st[k] == "success"] == [ran]
        assert st["end"] == "success"


def test_node_waits_for_all_predecessors_not_just_any_connection():
    a = Actions()
    d = {
        "nodes": [S(), act("slow", sleep=0.3), act("fast"), act("after"), F()],
        "edges": [e("start", "slow"), e("start", "fast"), e("slow", "after"), e("fast", "after"), e("after", "end")],
    }
    run(d, a, max_parallel=3)
    assert a.calls.index("after") > a.calls.index("slow") and a.calls[-1] == "after"


# ---------- parallel execution ----------
def test_independent_branches_run_in_parallel():
    d = {
        "nodes": [S(), act("p1", sleep=0.4), act("p2", sleep=0.4), act("p3", sleep=0.4), act("join"), F()],
        "edges": [
            e("start", "p1"),
            e("start", "p2"),
            e("start", "p3"),
            e("p1", "join"),
            e("p2", "join"),
            e("p3", "join"),
            e("join", "end"),
        ],
    }
    a = Actions()
    t = time.monotonic()
    run(d, a, max_parallel=3)
    parallel = time.monotonic() - t
    assert a.max_active == 3 and parallel < 1.0
    b = Actions()
    t = time.monotonic()
    run(d, b, max_parallel=1)
    assert b.max_active == 1 and time.monotonic() - t >= 1.2  # sequential


# ---------- failures, retries, timeouts ----------
def test_failure_stops_the_run_and_marks_downstream_skipped():
    a = Actions()
    d = {
        "nodes": [S(), act("ok"), act("bad", "fail"), act("after"), act("side"), F()],
        "edges": [
            e("start", "ok"),
            e("ok", "bad"),
            e("bad", "after"),
            e("start", "side"),
            e("after", "end"),
            e("side", "end"),
        ],
    }
    with pytest.raises(WorkflowError) as exc:
        run(d, a)
    assert "Step 'bad' failed: bad broke" in str(exc.value)
    steps = {s["node_id"]: s for s in exc.value.steps}
    assert steps["bad"]["status"] == "failed" and steps["bad"]["error"] == "bad broke"
    assert steps["after"]["status"] == "skipped" and "earlier step failed" in steps["after"]["error"]
    assert "after" not in a.calls


def test_continue_on_error_lets_the_workflow_go_on():
    a = Actions()
    d = {
        "nodes": [
            S(),
            act("bad", "fail", settings={"continue_on_error": True}),
            act("after", value="{{bad.error}}"),
            F("{{after.value}}"),
        ],
        "edges": [e("start", "bad"), e("bad", "after"), e("after", "end")],
    }
    res = run(d, a)
    assert res["output"] == "bad broke"
    assert status_of(res["steps"])["bad"] == "error_continued"


def test_retry_until_success_records_attempts_and_logs():
    a = Actions()
    a.fail_times["flaky"] = 2
    d = {
        "nodes": [S(), act("flaky", settings={"retries": 3, "retry_delay_seconds": 0.05}), F()],
        "edges": [e("start", "flaky"), e("flaky", "end")],
    }
    res = run(d, a)
    flaky = next(s for s in res["steps"] if s["node_id"] == "flaky")
    assert flaky["status"] == "success" and flaky["attempts"] == 3
    assert len(flaky["logs"]) == 2 and "attempt 1 failed: flaky broke" in flaky["logs"][0]


def test_retries_exhausted_and_exponential_backoff():
    a = Actions()
    a.fail_times["flaky"] = 10
    d = {
        "nodes": [
            S(),
            act("flaky", settings={"retries": 2, "retry_delay_seconds": 0.1, "retry_backoff": "exponential"}),
            F(),
        ],
        "edges": [e("start", "flaky"), e("flaky", "end")],
    }
    t = time.monotonic()
    with pytest.raises(WorkflowError) as exc:
        run(d, a)
    assert time.monotonic() - t >= 0.3  # 0.1 + 0.2
    flaky = next(s for s in exc.value.steps if s["node_id"] == "flaky")
    assert flaky["attempts"] == 3 and flaky["status"] == "failed"


def test_step_timeout():
    a = Actions()
    d = {
        "nodes": [S(), act("slow", sleep=2, settings={"timeout_seconds": 0.2}), F()],
        "edges": [e("start", "slow"), e("slow", "end")],
    }
    t = time.monotonic()
    with pytest.raises(WorkflowError) as exc:
        run(d, a)
    assert time.monotonic() - t < 1.5 and "timed out after 0.2s" in str(exc.value)


# ---------- cancellation ----------
def test_cancellation_between_steps():
    a = Actions()
    flag = {"cancel": False}

    def first(key, cfg, node):
        flag["cancel"] = True  # cancelled while the first step runs
        return a(key, cfg, node)

    d = {"nodes": [S(), act("one"), act("two"), F()], "edges": [e("start", "one"), e("one", "two"), e("two", "end")]}
    with pytest.raises(WorkflowError) as exc:
        run_definition(d, {}, None, None, first, should_cancel=lambda: flag["cancel"])
    assert "cancelled" in str(exc.value)
    st = status_of(exc.value.steps)
    assert st["one"] == "success" and st["two"] == "cancelled" and st["end"] == "cancelled"
    assert a.calls == ["one"]


# ---------- checkpoints and resume ----------
def test_resume_skips_finished_steps_and_reruns_interrupted_ones():
    d = {
        "nodes": [S(), act("a", value="A"), act("b", value="{{a.value}}-B"), F("{{b.value}}")],
        "edges": [e("start", "a"), e("a", "b"), e("b", "end")],
    }
    store = MemoryStore()
    store.save(
        {
            "node_id": "start",
            "seq": 0,
            "type": "input",
            "label": "Start",
            "status": "success",
            "continued": False,
            "attempts": 1,
            "input": None,
            "output": {},
            "error": None,
            "logs": [],
        }
    )
    store.save(
        {
            "node_id": "a",
            "seq": 1,
            "type": "action",
            "label": "a",
            "status": "success",
            "continued": False,
            "attempts": 1,
            "input": None,
            "output": {"value": "A"},
            "error": None,
            "logs": [],
        }
    )
    store.save(
        {
            "node_id": "b",
            "seq": 2,
            "type": "action",
            "label": "b",
            "status": "running",
            "continued": False,
            "attempts": 1,
            "input": None,
            "output": None,
            "error": None,
            "logs": [],
        }
    )
    a = Actions()
    res = run(d, a, store=store)
    assert a.calls == ["b"]  # 'a' was not run again
    assert res["output"] == "A-B"
    assert "resumed after an interruption" in store.records["b"]["logs"][0]


# ---------- malformed definitions ----------
MALFORMED = [
    None,
    [],
    "x",
    {"nodes": "x"},
    {"nodes": [1, 2]},
    {"nodes": [{"id": 5}]},
    {"nodes": [{"type": "input"}]},
    {"nodes": [{"id": "a", "type": "input", "data": "x"}]},
    {"nodes": [{"id": "a", "type": "input"}], "edges": "x"},
    {"nodes": [{"id": "a", "type": "input"}], "edges": [1, None, {"source": 1}]},
    {"nodes": [{"id": "a", "type": "action", "data": {"config": "x", "settings": "y"}}]},
    {"nodes": [{"id": "a", "type": "condition", "data": {"condition": [1]}}]},
    {"nodes": [{"id": "a", "type": "switch", "data": {"cases": "x"}}]},
    {"nodes": [{"id": "a", "type": "loop", "data": {"items": {"x": 1}}}]},
    {"nodes": [{"id": "a" * 500, "type": "input"}]},
    {"nodes": [{"id": "a", "type": "end", "data": {"config": {"output": {"x": "{{nope.y}}"}}}}], "settings": "x"},
]


def test_malformed_definitions_never_crash_validation_or_runs(client, admin):
    db = SessionLocal()
    try:
        for d in MALFORMED:
            errors = validate_definition(d, db)
            assert errors and all(isinstance(x, str) for x in errors), d
            try:
                run_definition(d, {}, None, None, Actions())
            except WorkflowError:
                pass
    finally:
        db.close()


def _errors(client, headers, definition):
    wf = client.post("/api/workflows", headers=headers, json={"name": "V", "definition": definition})
    assert wf.status_code == 201, wf.text
    return client.post(f"/api/workflows/{wf.json()['id']}/validate", headers=headers).json()["errors"]


def test_validation_catches_structural_problems(client, admin):
    good = [S(), act("a", "set_fields", fields={"x": "1"}), F()]
    cases = {
        "duplicate ids": (
            {"nodes": [*good, act("a", "set_fields", fields={"x": "1"})], "edges": [e("start", "a"), e("a", "end")]},
            "same id (a)",
        ),
        "edge to missing step": (
            {"nodes": good, "edges": [e("start", "a"), e("a", "end"), e("a", "ghost")]},
            "no longer exists",
        ),
        "missing start": ({"nodes": good[1:], "edges": [e("a", "end")]}, "exactly one Start"),
        "missing finish": ({"nodes": good[:2], "edges": [e("start", "a")]}, "Add a Finish"),
        "cycle": (
            {
                "nodes": [*good, act("b", "set_fields", fields={"y": "1"})],
                "edges": [e("start", "a"), e("a", "b"), e("b", "a"), e("b", "end")],
            },
            "loop",
        ),
        "unreachable": (
            {
                "nodes": [*good, act("lost", "set_fields", fields={"y": "1"})],
                "edges": [e("start", "a"), e("a", "end"), e("lost", "end")],
            },
            "cannot be reached",
        ),
        "self loop": ({"nodes": good, "edges": [e("start", "a"), e("a", "a"), e("a", "end")]}, "connected to itself"),
        "duplicate edge": (
            {"nodes": good, "edges": [e("start", "a"), {"id": "x", "source": "start", "target": "a"}, e("a", "end")]},
            "two identical connections",
        ),
        "after finish": (
            {
                "nodes": [*good, act("z", "set_fields", fields={"y": "1"})],
                "edges": [e("start", "a"), e("a", "end"), e("end", "z")],
            },
            "Nothing can follow",
        ),
        "bad id": (
            {
                "nodes": [S(), act("a b", "set_fields", fields={"x": "1"}), F()],
                "edges": [e("start", "a b"), e("a b", "end")],
            },
            "must be 1-100 letters",
        ),
        "if without branches": (
            {"nodes": [S(), cond("c", "{{input.x}}", ">", "5"), F()], "edges": [e("start", "c"), e("c", "end")]},
            "Yes or No handle",
        ),
        "if non-number": (
            {
                "nodes": [S(), cond("c", "{{input.x}}", ">", "lots"), F()],
                "edges": [e("start", "c"), e("c", "end", "true")],
            },
            "is not a number",
        ),
        "if missing value": (
            {"nodes": [S(), cond("c", "", "==", "x"), F()], "edges": [e("start", "c"), e("c", "end", "true")]},
            "choose the value to check",
        ),
        "unknown step type": (
            {
                "nodes": [*good, {"id": "q", "type": "quantum", "data": {}}],
                "edges": [e("start", "a"), e("a", "end"), e("a", "q")],
            },
            "unknown step type",
        ),
        "missing required config": (
            {"nodes": [S(), act("w", "wait"), F()], "edges": [e("start", "w"), e("w", "end")]},
            None,
        ),
    }
    for name, (d, expected) in cases.items():
        errs = _errors(client, admin, d)
        if expected is None:
            continue
        assert any(expected in x for x in errs), (name, errs)


def test_validation_of_agent_references_and_types(client, admin):
    agent = create_agent(
        client,
        admin,
        name="Pricer",
        input_schema={
            "type": "object",
            "properties": {"qty": {"type": "integer"}, "note": {"type": "string"}},
            "required": ["qty"],
        },
        output_schema={
            "type": "object",
            "properties": {"price": {"type": "number"}, "ok": {"type": "boolean"}},
            "required": ["price"],
        },
    )
    ask = lambda nid, mapping: step(nid, "run_agent", {"agent_id": agent["id"], "input": mapping})  # noqa: E731
    # Unknown agent.
    errs = _errors(
        client, admin, chain(start(), step("x", "run_agent", {"agent_id": 999999, "message": "hi"}), finish())
    )
    assert any("choose an agent" in x for x in errs)
    # Reference to an output field the agent does not return.
    errs = _errors(client, admin, chain(start(), ask("p", {"qty": 1}), finish("{{p.cost}}")))
    assert any(
        "uses 'cost' from agent 'Pricer', which it does not return (it returns: price, ok, agent)" in x for x in errs
    )
    # Incompatible types between steps: a yes/no output into a number input, a number into text.
    d = chain(start(), ask("p", {"qty": 1}), ask("q", {"qty": "{{p.ok}}", "note": "{{p.price}}"}), finish())
    errs = _errors(client, admin, d)
    assert any("'qty' needs integer but {{p.ok}} gives boolean" in x for x in errs)
    assert any("'note' needs string but {{p.price}} gives number" in x for x in errs)
    # Compatible: number into integer is checked at run time; text from the form is converted.
    d = chain(
        start([{"key": "n", "label": "N", "type": "text"}]),
        ask("p", {"qty": "{{input.n}}"}),
        ask("q", {"qty": "{{p.price}}"}),
        finish(),
    )
    assert _errors(client, admin, d) == []
    # Missing required mapping.
    errs = _errors(client, admin, chain(start(), ask("p", {"note": "x"}), finish()))
    assert any("'qty' is required by this agent but not mapped" in x for x in errs)


# ---------- through the API: durable records, cancel, recovery, lifecycle ----------
def _publish(client, headers, definition, name="Flow"):
    wf = client.post("/api/workflows", headers=headers, json={"name": name, "definition": definition}).json()
    r = client.post(f"/api/workflows/{wf['id']}/activate", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_run_records_every_step_durably(client, admin):
    d = chain(
        start(),
        step("a", "set_fields", {"fields": {"x": "1"}}),
        step("b", "compose_text", {"template": "x={{a.x}}"}),
        finish("{{b.text}}"),
    )
    wf = _publish(client, admin, d)
    run = client.post(f"/api/workflows/{wf['id']}/run", headers=admin, json={"input": {}}).json()
    done = wait_for_run(client, admin, run["id"])
    assert done["status"] == "succeeded" and done["output"]["result"] == "x=1"
    nodes = {n["node_id"]: n for n in done["nodes"]}
    assert [n["node_id"] for n in done["nodes"]] == ["start", "a", "b", "finish"]
    for n in nodes.values():
        assert n["status"] == "success" and n["attempts"] == 1 and n["started_at"] and n["finished_at"]
    assert nodes["b"]["input"] == {"template": "x=1"} and nodes["b"]["output"] == {"text": "x=1"}


def test_failed_step_through_the_api(client, admin):
    d = chain(
        start(),
        step("calc", "calculate", {"expression": "1/0"}),
        step("after", "set_fields", {"fields": {"x": "1"}}),
        finish(),
    )
    wf = _publish(client, admin, d)
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}}).json()
    assert run["status"] == "failed" and "Step 'calc' failed" in run["error"]
    nodes = {n["node_id"]: n for n in run["nodes"]}
    assert nodes["calc"]["status"] == "failed" and nodes["calc"]["error"]
    assert nodes["after"]["status"] == "skipped" and nodes["finish"]["status"] == "skipped"


def test_failed_agent_step(client, admin, llm):
    from app.llm.client import LLMError

    agent = create_agent(client, admin)

    def boom(messages, tools, json_mode):
        raise LLMError("model is down")

    llm.handler = boom
    d = chain(
        start(),
        step(
            "ask",
            "run_agent",
            {
                "agent_id": agent["id"],
                "message": "hi",
            },
            settings={"retries": 1, "retry_delay_seconds": 0.01},
        ),
        finish(),
    )
    wf = _publish(client, admin, d)
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}}).json()
    ask = next(n for n in run["nodes"] if n["node_id"] == "ask")
    assert run["status"] == "failed" and ask["status"] == "failed" and "model is down" in ask["error"]
    assert ask["attempts"] == 2


def test_cancel_a_running_and_a_queued_run(client, admin):
    d = chain(start(), step("w", "wait", {"seconds": 1}), step("after", "set_fields", {"fields": {"x": "1"}}), finish())
    wf = _publish(client, admin, d)
    run = client.post(f"/api/workflows/{wf['id']}/test?background=true", headers=admin, json={"input": {}}).json()
    deadline = time.time() + 5
    while time.time() < deadline:  # wait until the Wait step is running
        cur = client.get(f"/api/runs/{run['id']}", headers=admin).json()
        if any(n["node_id"] == "w" and n["status"] == "running" for n in cur["nodes"]):
            break
        time.sleep(0.05)
    r = client.post(f"/api/runs/{run['id']}/cancel", headers=admin)
    assert r.status_code == 200 and r.json()["cancel_requested"]
    done = None
    deadline = time.time() + 10
    while time.time() < deadline:
        done = client.get(f"/api/runs/{run['id']}", headers=admin).json()
        if done["status"] in ("cancelled", "failed", "succeeded"):
            break
        time.sleep(0.05)
    assert done["status"] == "cancelled"
    nodes = {n["node_id"]: n["status"] for n in done["nodes"]}
    assert nodes["after"] == "cancelled" and nodes["finish"] == "cancelled"
    assert client.post(f"/api/runs/{run['id']}/cancel", headers=admin).status_code == 409

    # A queued run (nobody has picked it up) is cancelled at once.
    db = SessionLocal()
    queued = Run(
        target_type="workflow", target_id=wf["id"], target_name="x", status="queued", input={}, user_id=1, org_id=1
    )
    db.add(queued)
    db.commit()
    qid = queued.id
    db.close()
    r = client.post(f"/api/runs/{qid}/cancel", headers=admin).json()
    assert r["status"] == "cancelled"
    runs_service.execute_run(qid)  # a worker that picks it up later does nothing
    assert client.get(f"/api/runs/{qid}", headers=admin).json()["status"] == "cancelled"


def test_only_permitted_users_can_cancel(client, admin, make_user):
    d = chain(start(), step("w", "wait", {"seconds": 1}), finish())
    wf = _publish(client, admin, d)
    db = SessionLocal()
    queued = Run(
        target_type="workflow", target_id=wf["id"], target_name="x", status="queued", input={}, user_id=1, org_id=1
    )
    db.add(queued)
    db.commit()
    qid = queued.id
    db.close()
    auditor = make_user("aud@example.com", "auditor")  # can see all runs, cannot cancel
    assert client.post(f"/api/runs/{qid}/cancel", headers=auditor).status_code == 403
    op = make_user("op@example.com", "operator")  # cannot see the run at all
    assert client.post(f"/api/runs/{qid}/cancel", headers=op).status_code == 404


def test_recovery_resumes_an_abandoned_run_from_its_checkpoint(client, admin):
    d = chain(
        start(),
        step("a", "set_fields", {"fields": {"x": "kept"}}),
        step("b", "compose_text", {"template": "{{a.x}}+b"}),
        finish("{{b.text}}"),
    )
    wf = _publish(client, admin, d)
    # Simulate a pod that died after finishing 'a' while running 'b'.
    db = SessionLocal()
    run = Run(
        target_type="workflow",
        target_id=wf["id"],
        target_name="Flow",
        status="running",
        input={},
        user_id=1,
        org_id=1,
        worker_id="dead-pod",
        heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        started_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    db.add(run)
    db.commit()
    rid = run.id
    for seq, (nid, ntype, status, out) in enumerate(
        [
            ("start", "input", "success", {}),
            ("a", "action", "success", {"x": "FROM-CHECKPOINT"}),  # different from what 'a' would produce now
            ("b", "action", "running", None),
        ]
    ):
        db.add(
            RunNode(
                run_id=rid,
                node_id=nid,
                seq=seq,
                type=ntype,
                label=nid,
                status=status,
                continued=False,
                attempts=1,
                output=out,
                logs=[],
            )
        )
    db.commit()
    db.close()

    assert runs_service.worker.poll_once() == 1
    done = wait_for_run(client, admin, rid)
    assert done["status"] == "succeeded", done
    assert done["output"]["result"] == "FROM-CHECKPOINT+b"  # 'a' was not run again
    assert done["resume_count"] == 1
    b = next(n for n in done["nodes"] if n["node_id"] == "b")
    assert b["status"] == "success" and any("resumed" in line for line in b["logs"])


def test_live_runs_are_not_taken_over(client, admin):
    d = chain(start(), finish())
    wf = _publish(client, admin, d)
    db = SessionLocal()
    run = Run(
        target_type="workflow",
        target_id=wf["id"],
        target_name="x",
        status="running",
        input={},
        user_id=1,
        org_id=1,
        worker_id="busy-pod",
        heartbeat_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    rid = run.id
    db.close()
    assert runs_service.worker.poll_once() == 0
    assert client.get(f"/api/runs/{rid}", headers=admin).json()["status"] == "running"


def test_too_many_interruptions_fail_the_run(client, admin, monkeypatch):
    d = chain(start(), finish())
    wf = _publish(client, admin, d)
    db = SessionLocal()
    run = Run(
        target_type="workflow",
        target_id=wf["id"],
        target_name="x",
        status="running",
        input={},
        user_id=1,
        org_id=1,
        worker_id="dead",
        heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=1),
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        resume_count=3,
    )
    db.add(run)
    db.commit()
    rid = run.id
    db.close()
    runs_service.execute_run(rid)
    done = client.get(f"/api/runs/{rid}", headers=admin).json()
    assert done["status"] == "failed" and "interrupted too many times" in done["error"]


def test_lifecycle_publish_immutable_history_and_versions(client, admin, make_user):
    d1 = chain(start(), step("a", "set_fields", {"fields": {"v": "one"}}), finish("{{a.v}}"))
    v1 = _publish(client, admin, d1)
    assert v1["status"] == "active" and v1["published_at"] and v1["published_by"]
    # Published versions are immutable.
    assert (
        client.put(f"/api/workflows/{v1['id']}", headers=admin, json={"name": "x", "definition": d1}).status_code == 409
    )
    # New draft version, then publish it: v1 is archived but still runnable explicitly.
    d2 = chain(start(), step("a", "set_fields", {"fields": {"v": "two"}}), finish("{{a.v}}"))
    v2 = client.post(
        "/api/workflows", headers=admin, json={"name": "Flow", "definition": d2, "group_id": v1["group_id"]}
    ).json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["published_at"] is None
    draft_run = client.post(f"/api/workflows/{v2['id']}/run", headers=admin, json={"input": {}})
    assert draft_run.status_code == 409 and "never published" in draft_run.text
    client.post(f"/api/workflows/{v2['id']}/activate", headers=admin)
    assert client.get(f"/api/workflows/{v1['id']}", headers=admin).json()["status"] == "archived"
    old = client.post(f"/api/workflows/{v1['id']}/run", headers=admin, json={"input": {}}).json()
    new = client.post(f"/api/workflows/{v2['id']}/run", headers=admin, json={"input": {}}).json()
    assert wait_for_run(client, admin, old["id"])["output"]["result"] == "one"
    assert wait_for_run(client, admin, new["id"])["output"]["result"] == "two"
    assert (
        client.put(f"/api/workflows/{v2['id']}", headers=admin, json={"name": "Flow", "definition": d2}).status_code
        == 409
    )
    # Operators run only the live version.
    op = make_user("op@example.com", "operator")
    db = SessionLocal()
    for w in db.query(Workflow).filter(Workflow.group_id == v1["group_id"]):
        w.visibility = "public"
    db.commit()
    db.close()
    assert client.post(f"/api/workflows/{v1['id']}/run", headers=op, json={"input": {}}).status_code == 403
    # Version history with run counts.
    hist = client.get(f"/api/workflows/groups/{v1['group_id']}/versions", headers=admin).json()
    assert [(h["version"], h["status"], h["published"]) for h in hist] == [(2, "active", True), (1, "archived", True)]
    assert hist[0]["runs"] == {"succeeded": 1} and hist[1]["runs"] == {"succeeded": 1}
    # Duplicate makes an independent draft.
    dup = client.post(f"/api/workflows/{v1['id']}/duplicate", headers=admin).json()
    assert dup["group_id"] != v1["group_id"] and dup["status"] == "draft" and dup["definition"] == d1


def test_parallel_branches_through_the_api(client, admin):
    d = {
        "nodes": [
            start(),
            step("w1", "wait", {"seconds": 1}),
            step("w2", "wait", {"seconds": 1}),
            step("join", "compose_text", {"template": "{{w1.waited_seconds}}+{{w2.waited_seconds}}"}),
            finish("{{join.text}}"),
        ],
        "edges": [e("start", "w1"), e("start", "w2"), e("w1", "join"), e("w2", "join"), e("join", "finish")],
    }
    wf = _publish(client, admin, d)
    t = time.monotonic()
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}}).json()
    assert run["status"] == "succeeded", run
    assert time.monotonic() - t < 1.8  # both waits overlapped
    nodes = {n["node_id"]: n for n in run["nodes"]}
    assert nodes["join"]["started_at"] >= max(nodes["w1"]["finished_at"], nodes["w2"]["finished_at"])


def test_validate_unsaved_definition(client, admin, make_user):
    ok = chain(start(), step("a", "set_fields", {"fields": {"x": "1"}}), finish())
    r = client.post("/api/workflows/validate-definition", headers=admin, json={"definition": ok}).json()
    assert r["is_valid"] and r["errors"] == []
    bad = client.post(
        "/api/workflows/validate-definition", headers=admin, json={"definition": {"nodes": "junk"}}
    ).json()
    assert not bad["is_valid"] and bad["errors"]
    op = make_user("op@example.com", "operator")
    assert client.post("/api/workflows/validate-definition", headers=op, json={"definition": ok}).status_code == 403
