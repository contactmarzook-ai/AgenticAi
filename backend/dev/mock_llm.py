"""A tiny OpenAI-compatible server for local development, demos and CI. It is NOT an AI model.

    uvicorn dev.mock_llm:app --port 9999
    # then set the provider base URL to http://localhost:9999/v1

Deterministic behaviour, enough to click through every feature:
- chat routing: picks the first agent/workflow whose name appears in the message
- AI builder: returns a small workflow shaped by keywords in the description
- Classify / Extract steps: keyword and regex based answers
- agents with the `calculator` tool: calls it for arithmetic, then reports the result
- anything else: echoes the request
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


def draft_workflow(description: str) -> dict:
    d = description.lower()
    steps = [
        {
            "id": "start",
            "type": "start",
            "label": "Start",
            "fields": [{"key": "text", "label": "Text", "type": "textarea", "required": True}],
        }
    ]
    links = []
    if any(w in d for w in ("urgent", "classify", "ticket", "route", "complaint")):
        steps += [
            {
                "id": "classify",
                "type": "action",
                "action": "ai_classify",
                "label": "How urgent is it?",
                "config": {"text": "{{input.text}}", "categories": ["urgent", "normal"]},
            },
            {
                "id": "is_urgent",
                "type": "if",
                "label": "Urgent?",
                "left": "{{classify.category}}",
                "operator": "==",
                "right": "urgent",
            },
            {
                "id": "alert",
                "type": "action",
                "action": "slack_message" if "slack" in d else "compose_text",
                "label": "Alert the team",
                "config": {"credential_id": "", "text": "Urgent: {{input.text}}"}
                if "slack" in d
                else {"template": "URGENT: {{input.text}}"},
            },
            {
                "id": "summary",
                "type": "action",
                "action": "ai_summarize",
                "label": "Summarize",
                "config": {"text": "{{input.text}}", "length": "one sentence"},
            },
            {"id": "finish", "type": "finish", "label": "Done"},
        ]
        links += [
            {"from": "start", "to": "classify"},
            {"from": "classify", "to": "is_urgent"},
            {"from": "is_urgent", "to": "alert", "branch": "true"},
            {"from": "is_urgent", "to": "summary", "branch": "false"},
            {"from": "alert", "to": "finish"},
            {"from": "summary", "to": "finish"},
        ]
    else:
        steps += [
            {
                "id": "summary",
                "type": "action",
                "action": "ai_summarize",
                "label": "Summarize",
                "config": {"text": "{{input.text}}", "length": "short"},
            },
            {"id": "finish", "type": "finish", "label": "Done", "output": "{{summary.summary}}"},
        ]
        links += [{"from": "start", "to": "summary"}, {"from": "summary", "to": "finish"}]
    return {
        "name": description[:40].strip().capitalize() or "New automation",
        "description": description[:200],
        "steps": steps,
        "links": links,
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
    system = str(messages[0].get("content", "")) if messages and messages[0].get("role") == "system" else ""

    if system.startswith("You design no-code automation workflows"):
        return reply({"content": json.dumps(draft_workflow(text.removeprefix("Automate this: ")))}, prompt_text)

    if system.startswith("You route a user's request"):
        match = re.search(r"Tools:\n(\[.*\])", system, re.S)
        catalog = json.loads(match.group(1)) if match else []
        pick = next((t for t in catalog if t["name"].lower() in text.lower()), None)
        decision = (
            {"type": pick["type"], "id": pick["id"], "confidence": 0.9}
            if pick
            else {"type": "none", "id": None, "confidence": 0.9}
        )
        return reply({"content": json.dumps(decision)}, prompt_text)

    if text.startswith("Classify the text"):
        cats = json.loads(re.search(r"categories: (\[.*?\])", text).group(1))
        body_text = text.split("Text:", 1)[-1].lower()
        pick = next((c for c in cats if c.lower() in body_text), None)
        if pick is None and any(w in body_text for w in ("asap", "down", "broken", "immediately", "crash")):
            pick = next((c for c in cats if c.lower() in ("urgent", "hot", "technical")), None)
        return reply({"content": json.dumps({"category": pick or cats[-1], "reason": "mock decision"})}, prompt_text)

    if text.startswith("Extract these fields"):
        fields = json.loads(re.search(r"fields from the text: (\[.*?\])", text).group(1))
        source = text.split("\n\nText:\n", 1)[-1]
        numbers = re.findall(r"\d[\d,]*\.?\d*", source)
        out = {}
        for f in fields:
            m = re.search(rf"{re.escape(f.replace('_', ' '))}\s*[:=]\s*([^\n,;]+)", source, re.I)
            out[f] = (
                m.group(1).strip()
                if m
                else (numbers.pop(0).replace(",", "") if ("amount" in f or "total" in f) and numbers else None)
            )
        return reply({"content": json.dumps(out)}, prompt_text)

    if last.get("role") == "tool":
        return reply({"content": f"The {last.get('name', 'tool')} tool returned: {last.get('content')}"}, prompt_text)

    tool_names = {t["function"]["name"] for t in body.get("tools") or []}
    expr = ARITH.search(text)
    if "calculate" in tool_names or "calculator" in tool_names and expr and any(op in expr.group(0) for op in "+-*/%"):
        call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "calculate" if "calculate" in tool_names else "calculator",
                "arguments": json.dumps({"expression": expr.group(0).strip()}),
            },
        }
        return reply({"content": "", "tool_calls": [call]}, prompt_text)

    if text.startswith("Summarize the following text"):
        source = text.split("\n\n", 1)[-1]
        return reply({"content": f"(mock summary) {source[:120]}"}, prompt_text)
    if text.startswith("Translate the following into"):
        return reply({"content": f"(mock translation) {text.split(chr(10) + chr(10), 1)[-1][:200]}"}, prompt_text)
    return reply({"content": f"(mock model) You said: {text[:300]}"}, prompt_text)
