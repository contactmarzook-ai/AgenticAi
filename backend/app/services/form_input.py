"""Server-side checks for the Start step's form, applied to every way an automation is started
(form, API, webhook, chat, schedule), so missing or malformed values fail early and clearly."""

import re
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def form_fields(definition: dict) -> list[dict]:
    for n in (definition or {}).get("nodes") or []:
        if isinstance(n, dict) and n.get("type") == "input":
            fields = (n.get("data") or {}).get("fields") or []
            return [f for f in fields if isinstance(f, dict) and f.get("key")]
    return []


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def check_input(definition: dict, data: Any) -> tuple[dict, list[str]]:
    """Returns (cleaned input, problems). Extra keys are kept (webhooks send more than the form)."""
    if not isinstance(data, dict):
        return {}, ["Input must be an object of field values"]
    cleaned = dict(data)
    problems = []
    for f in form_fields(definition):
        key, label, ftype = f["key"], f.get("label") or f["key"], f.get("type") or "text"
        value = cleaned.get(key)
        if _empty(value):
            if f.get("required"):
                problems.append(f"'{label}' is required")
            continue
        if ftype == "number":
            if isinstance(value, bool):
                problems.append(f"'{label}' must be a number")
                continue
            try:
                num = float(str(value).strip().replace(",", ""))
                cleaned[key] = int(num) if num.is_integer() else num
            except ValueError:
                problems.append(f"'{label}' must be a number")
        elif ftype == "email":
            if not EMAIL_RE.match(str(value).strip()):
                problems.append(f"'{label}' must be an email address")
        elif ftype == "boolean":
            if isinstance(value, str):
                if value.strip().lower() in ("true", "yes", "1", "on"):
                    cleaned[key] = True
                elif value.strip().lower() in ("false", "no", "0", "off"):
                    cleaned[key] = False
                else:
                    problems.append(f"'{label}' must be yes or no")
            elif not isinstance(value, bool):
                problems.append(f"'{label}' must be yes or no")
        elif ftype == "select":
            options = [str(o) for o in f.get("options") or [] if str(o).strip()]
            if options and str(value) not in options:
                problems.append(f"'{label}' must be one of: {', '.join(options)}")
        elif not isinstance(value, (str, int, float)):
            problems.append(f"'{label}' must be text")
    return cleaned, problems


def from_chat_message(definition: dict, message: str) -> dict:
    """Map a chat message onto the form: it fills the first text field (and `message`)."""
    data = {"message": message}
    for f in form_fields(definition):
        if (f.get("type") or "text") in ("text", "textarea"):
            data[f["key"]] = message
            break
    return data
