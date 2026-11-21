import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="agentos-test-")
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db"),
        "AUTO_CREATE_TABLES": "true",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
        "BOOTSTRAP_ADMIN_PASSWORD": "Admin#Passw0rd!",
        "LLM_BASE_URL": "http://llm.test/v1",
        "LLM_DEFAULT_MODEL": "test-model",
        "USER_RUNS_PER_MINUTE": "1000",
        "AUTH_REQUESTS_PER_MINUTE": "1000",
        "RUN_POLL_SECONDS": "0",  # tests drive recovery explicitly (worker.poll_once)
        "PUBLIC_REQUESTS_PER_MINUTE": "1000",
        "LOGIN_MAX_ATTEMPTS": "3",
        "BCRYPT_ROUNDS": "4",
    }
)

import json  # noqa: E402
import time  # noqa: E402
from typing import Callable  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.bootstrap import seed  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.llm.client import LLMClient, LLMResponse, ToolCall, set_llm_client  # noqa: E402
from app.main import app  # noqa: E402
from app.services.platform_settings import invalidate as invalidate_settings  # noqa: E402

ADMIN = ("admin@example.com", "Admin#Passw0rd!")
PASSWORD = "Str0ng#Password"


class FakeLLM(LLMClient):
    """Scripted LLM. `handler(messages, tools, json_mode)` returns an LLMResponse."""

    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []
        self.handler: Callable = lambda messages, tools, json_mode: LLMResponse(content="fake answer")

    def chat(self, target, messages, tools=None, temperature=0.2, json_mode=False):
        self.calls.append(
            {"model": target.model_name, "messages": list(messages), "tools": tools, "json_mode": json_mode}
        )
        resp = self.handler(messages, tools, json_mode)
        resp.prompt_tokens = resp.prompt_tokens or 10
        resp.completion_tokens = resp.completion_tokens or 5
        return resp


def tool_call(name: str, args: dict, call_id: str = "c1") -> LLMResponse:
    return LLMResponse(content="", tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(args))])


def _wait_for_background_runs(timeout: float = 15.0) -> None:
    """Runs started in the background by a previous test must finish before tables are dropped."""
    from app.services.runs import worker

    deadline = time.time() + timeout
    while worker.free_slots() < worker_threads() and time.time() < deadline:
        time.sleep(0.05)


def worker_threads() -> int:
    from app.config import settings

    return settings.run_worker_threads


@pytest.fixture(autouse=True)
def fresh_db():
    _wait_for_background_runs()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    db.close()
    invalidate_settings()
    ratelimit.reset()
    yield


@pytest.fixture()
def llm():
    fake = FakeLLM()
    set_llm_client(fake)
    yield fake
    set_llm_client(LLMClient())


@pytest.fixture()
def client(llm):
    return TestClient(app)


def login(client, email, password) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin(client):
    return login(client, *ADMIN)


@pytest.fixture()
def make_user(client, admin):
    def _make(email: str, role: str = "operator", department: str | None = "ops") -> dict:
        r = client.post(
            "/api/admin/users",
            headers=admin,
            json={"email": email, "password": PASSWORD, "role": role, "department": department},
        )
        assert r.status_code == 201, r.text
        return login(client, email, PASSWORD)

    return _make


def create_agent(client, headers, **overrides) -> dict:
    body = {"name": "Helper", "system_prompt": "Be helpful.", "tools": [], "visibility": "department"}
    body.update(overrides)
    r = client.post("/api/agents", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def wait_for_run(client, headers, run_id: int, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}", headers=headers).json()
        if run["status"] in ("succeeded", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish")
