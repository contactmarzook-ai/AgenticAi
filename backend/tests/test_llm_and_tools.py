import json

import httpx
import pytest

from app.llm.client import LLMClient, LLMError, ModelTarget
from app.tools import registry

TARGET = ModelTarget(base_url="http://llm.test/v1", model_name="m", api_key="secret")


def client_with(handler):
    return LLMClient(transport=httpx.MockTransport(handler))


def test_request_shape_and_tool_call_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {"id": "x1", "function": {"name": "calculator", "arguments": {"expression": "1+1"}}}
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    tools = [registry.get_tool("calculator").openai_spec()]
    resp = client_with(handler).chat(TARGET, [{"role": "user", "content": "hi"}], tools=tools)
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["tools"][0]["function"]["name"] == "calculate"  # unified with the Calculate step
    assert resp.tool_calls[0].name == "calculator"
    assert json.loads(resp.tool_calls[0].arguments) == {"expression": "1+1"}  # dict args normalised to JSON
    assert (resp.prompt_tokens, resp.completion_tokens) == (12, 3)


def test_tools_not_sent_to_models_without_tool_support():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    target = ModelTarget(base_url="http://llm.test/v1", model_name="m", supports_tools=False)
    client_with(handler).chat(target, [], tools=[registry.get_tool("calculator").openai_spec()])
    assert "tools" not in seen["body"]


@pytest.mark.parametrize(
    "response,msg",
    [
        (httpx.Response(500, text="boom"), "HTTP 500"),
        (httpx.Response(200, json={"unexpected": True}), "unexpected response"),
    ],
)
def test_errors_become_llm_errors(response, msg):
    with pytest.raises(LLMError) as exc:
        client_with(lambda r: response).chat(TARGET, [])
    assert msg in str(exc.value)


def test_connection_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError):
        client_with(handler).chat(TARGET, [])


# ---------- tools ----------
def test_calculator_is_safe():
    assert registry.execute("calculator", {"expression": "(2+3)*4"})["result"] == 20
    for bad in ["__import__('os')", "open('x')", "2**1000"]:
        with pytest.raises(registry.ToolError):
            registry.execute("calculator", {"expression": bad})


def test_schema_validation():
    with pytest.raises(registry.ToolError) as exc:
        registry.execute("calculator", {"expression": 5})
    assert "Invalid arguments" in str(exc.value)
    with pytest.raises(registry.ToolError):
        registry.execute("nope", {})


def test_render_template():
    out = registry.execute(
        "render_template", {"template": "Dear $name, you owe $amt", "values": {"name": "A", "amt": 5}}
    )
    assert out["text"] == "Dear A, you owe 5"


def test_http_get_disabled_without_allowlist():
    with pytest.raises(registry.ToolError) as exc:
        registry.execute("http_get", {"url": "http://169.254.169.254/latest"})
    assert "not on the allowed list" in str(exc.value)


def test_http_get_enforces_allowlist():
    from app.database import SessionLocal
    from app.services.platform_settings import save_settings

    db = SessionLocal()
    save_settings(db, {"http_allowed_hosts": ["api.example.com"]})
    db.close()
    with pytest.raises(registry.ToolError) as exc:
        registry.execute("http_get", {"url": "http://evil.example.org/"})
    assert "not on the allowed list" in str(exc.value)
    with pytest.raises(registry.ToolError):
        registry.execute("http_get", {"url": "file:///etc/passwd"})


def test_agent_tools_follow_admin_step_switches():
    from app.database import SessionLocal
    from app.services.platform_settings import save_settings

    assert registry.get_tool("render_template").name == "fill_template"  # old names are aliases
    db = SessionLocal()
    save_settings(db, {"disabled_nodes": ["calculate"]})
    db.close()
    with pytest.raises(registry.ToolError) as exc:
        registry.execute("calculator", {"expression": "1+1"})
    assert "disabled by your administrator" in str(exc.value)
