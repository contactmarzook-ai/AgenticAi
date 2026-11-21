"""AI steps: plain-language instructions run by the configured local model."""

import json

from .base import Field, NodeContext, NodeError, node


def _json_from(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise NodeError("The AI did not return JSON")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NodeError("The AI returned malformed JSON") from exc


@node(
    "ai_prompt",
    "Ask AI",
    "AI",
    "Give the AI an instruction and some text; get its answer back.",
    "sparkles",
    [
        Field(
            "instruction",
            "Instruction",
            "textarea",
            required=True,
            placeholder="Write a polite reply to this customer email: {{input.email}}",
        ),
        Field("system", "Behave as", "textarea", help="Optional. e.g. 'You are a concise support agent.'"),
    ],
    output_hint="{ text }",
)
def ai_prompt(cfg: dict, ctx: NodeContext):
    messages = []
    if cfg.get("system"):
        messages.append({"role": "system", "content": str(cfg["system"])})
    messages.append({"role": "user", "content": str(cfg["instruction"])})
    return {"text": ctx.ask_llm(messages)["text"]}


@node(
    "ai_summarize",
    "Summarize",
    "AI",
    "Summarize text in a chosen length and style.",
    "align-left",
    [
        Field("text", "Text to summarize", "textarea", required=True, placeholder="{{input.text}}"),
        Field(
            "length", "Length", "select", default="short", options=("one sentence", "short", "detailed bullet points")
        ),
    ],
    output_hint="{ summary }",
)
def ai_summarize(cfg: dict, ctx: NodeContext):
    prompt = f"Summarize the following text. Length: {cfg.get('length') or 'short'}. Reply with the summary only.\n\n{cfg['text']}"
    return {"summary": ctx.ask_llm([{"role": "user", "content": prompt}])["text"].strip()}


@node(
    "ai_classify",
    "Classify",
    "AI",
    "Put text into one of your categories (e.g. urgent / normal / spam). Pair it with a Switch step to route.",
    "tags",
    [
        Field("text", "Text to classify", "textarea", required=True),
        Field("categories", "Categories", "list", required=True, help="One per line, e.g. billing, technical, sales"),
        Field("guidance", "Extra guidance", "textarea", help="Optional rules for choosing a category."),
    ],
    output_hint="{ category, reason }",
)
def ai_classify(cfg: dict, ctx: NodeContext):
    categories = [str(c).strip() for c in (cfg.get("categories") or []) if str(c).strip()]
    if len(categories) < 2:
        raise NodeError("Give at least two categories")
    prompt = (
        f"Classify the text into exactly one of these categories: {json.dumps(categories)}.\n"
        f"{cfg.get('guidance') or ''}\n"
        'Reply with JSON: {"category": "<one of the categories>", "reason": "<short reason>"}\n\n'
        f"Text:\n{cfg['text']}"
    )
    data = _json_from(ctx.ask_llm([{"role": "user", "content": prompt}], json_mode=True)["text"])
    chosen = str(data.get("category", "")).strip()
    match = next((c for c in categories if c.lower() == chosen.lower()), None)
    if match is None:
        match = next((c for c in categories if c.lower() in chosen.lower()), categories[-1])
    return {"category": match, "reason": str(data.get("reason", ""))}


@node(
    "ai_extract",
    "Extract data",
    "AI",
    "Pull specific fields out of free text (e.g. invoice number, amount, due date).",
    "scan-text",
    [
        Field("text", "Text", "textarea", required=True),
        Field(
            "fields",
            "Fields to extract",
            "list",
            required=True,
            help="One per line, e.g. invoice_number, total_amount, due_date",
        ),
    ],
    output_hint="{ <your fields> }",
)
def ai_extract(cfg: dict, ctx: NodeContext):
    fields = [str(f).strip() for f in (cfg.get("fields") or []) if str(f).strip()]
    if not fields:
        raise NodeError("List at least one field to extract")
    prompt = (
        f"Extract these fields from the text: {json.dumps(fields)}.\n"
        "Reply with a JSON object with exactly those keys. Use null when a value is not present.\n\n"
        f"Text:\n{cfg['text']}"
    )
    data = _json_from(ctx.ask_llm([{"role": "user", "content": prompt}], json_mode=True)["text"])
    return {f: data.get(f) for f in fields}


@node(
    "ai_translate",
    "Translate",
    "AI",
    "Translate text into another language.",
    "languages",
    [
        Field("text", "Text", "textarea", required=True),
        Field("language", "Target language", "text", required=True, default="English"),
    ],
    output_hint="{ text }",
)
def ai_translate(cfg: dict, ctx: NodeContext):
    prompt = f"Translate the following into {cfg['language']}. Reply with the translation only.\n\n{cfg['text']}"
    return {"text": ctx.ask_llm([{"role": "user", "content": prompt}])["text"].strip()}


@node(
    "run_agent",
    "Run an agent",
    "AI",
    "Hand a task to one of your agents (it can use its own tools).",
    "bot",
    [
        Field("agent_id", "Agent", "agent", required=True),
        Field(
            "message",
            "Task for the agent",
            "textarea",
            placeholder="Find the status of order {{input.order_id}}",
            help="For agents that take a message.",
        ),
        Field(
            "input",
            "Agent input",
            "agent_input",
            help="For agents with their own input fields: one value per field (variables allowed).",
        ),
    ],
    output_hint="{ answer } or the agent's own output fields",
)
def run_agent(cfg: dict, ctx: NodeContext):
    try:
        agent_id = int(cfg["agent_id"])
    except (TypeError, ValueError):
        raise NodeError("Choose an agent") from None
    mapping = cfg.get("input")
    if isinstance(mapping, str) and mapping.strip():
        try:
            mapping = json.loads(mapping)
        except ValueError:
            raise NodeError("Agent input is not valid JSON") from None
    if isinstance(mapping, dict) and mapping:
        return ctx.run_agent(agent_id, mapping)
    return ctx.run_agent(agent_id, {"message": str(cfg.get("message") or "")})
