"""A tiny OpenAI-compatible server for local development, demos and CI. It is NOT an AI model.

    uvicorn dev.mock_llm:app --port 9999
    # then set the provider base URL to http://localhost:9999/v1

Behaviour (deterministic):
- Routing requests (response_format=json_object): picks the first tool whose name appears in the message.
- If the `calculator` tool is offered and the message contains arithmetic, it calls it, then reports the result.
- Otherwise it echoes the last user message.
"""

import json
import re
import uuid

from fastapi import FastAPI, Request

app = FastAPI(title="mock-llm")
ARITH = re.compile(r"[\d\.\s\(\)\+\-\*/%]{3,}")


def reply(message: dict, prompt_text: str) -> dict:
    return {
        "id": "mock-" + uuid.uuid4().hex[:8],
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", **message}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": max(1, len(prompt_text) // 4), "completion_tokens": 12},
    }


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "mock-model", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    prompt_text = " ".join(str(m.get("content") or "") for m in messages)
    last = messages[-1] if messages else {"role": "user", "content": ""}
    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), {"content": ""})
    text = str(last_user.get("content") or "")

    if (body.get("response_format") or {}).get("type") == "json_object":
        system = str(messages[0].get("content", "")) if messages else ""
        match = re.search(r"Tools:\n(\[.*\])", system, re.S)
        catalog = json.loads(match.group(1)) if match else []
        pick = next((t for t in catalog if t["name"].lower() in text.lower()), None)
        decision = (
            {"type": pick["type"], "id": pick["id"], "confidence": 0.9}
            if pick
            else {"type": "none", "id": None, "confidence": 0.9}
        )
        return reply({"content": json.dumps(decision)}, prompt_text)

    if last.get("role") == "tool":
        return reply({"content": f"The {last.get('name', 'tool')} tool returned: {last.get('content')}"}, prompt_text)

    tool_names = {t["function"]["name"] for t in body.get("tools") or []}
    expr = ARITH.search(text)
    if "calculator" in tool_names and expr and any(op in expr.group(0) for op in "+-*/%"):
        call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "calculator", "arguments": json.dumps({"expression": expr.group(0).strip()})},
        }
        return reply({"content": "", "tool_calls": [call]}, prompt_text)

    return reply({"content": f"(mock model) You said: {text}"}, prompt_text)
