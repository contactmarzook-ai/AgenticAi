"""Agent input/output contracts: one JSON Schema implementation for the whole platform.

Every agent has an input schema and an output schema (JSON Schema, draft 2020-12, restricted to
the subset below). The frontend edits the same JSON Schema documents and asks the API to check
them; nothing validates contracts anywhere else.

Supported: type object / string / integer / number / boolean / array, nested objects, arrays
(`items`), `required`, `enum`, `default`, `description`, `title`, `additionalProperties`.
The root of a contract is always an object. Objects reject unknown properties unless the schema
says otherwise (normalised on save so the stored schema states it explicitly).
"""

import copy
import json
import re
from typing import Any

import jsonschema

TYPES = ("object", "string", "integer", "number", "boolean", "array")
KEYWORDS = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "default",
    "description",
    "title",
    "additionalProperties",
}
MAX_DEPTH = 6
MAX_PROPERTIES = 100
MAX_ENUM = 100
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

DEFAULT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}
DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def is_default_input(schema: dict | None) -> bool:
    return not schema or schema == DEFAULT_INPUT_SCHEMA


def is_default_output(schema: dict | None) -> bool:
    return not schema or schema == DEFAULT_OUTPUT_SCHEMA


# ---------- schema checking ----------
def schema_problems(schema: Any) -> list[str]:
    """Problems with a contract schema itself (empty list = usable)."""
    problems: list[str] = []
    if not isinstance(schema, dict):
        return ["The schema must be a JSON object"]
    if schema.get("type") != "object":
        return ["The top level of a contract must be an object (type: object)"]
    counter = {"props": 0}
    _check_node(schema, "(root)", 0, problems, counter)
    if not problems:
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            problems.append(f"Invalid JSON Schema: {exc.message}")
    return problems


def _type_ok(value: Any, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return {
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }.get(typ, False)


def _check_node(node: Any, path: str, depth: int, problems: list[str], counter: dict) -> None:
    if not isinstance(node, dict):
        problems.append(f"{path}: must be an object describing a value")
        return
    if depth > MAX_DEPTH:
        problems.append(f"{path}: nested more than {MAX_DEPTH} levels deep")
        return
    unknown = set(node) - KEYWORDS
    if unknown:
        problems.append(f"{path}: unsupported keyword(s) {', '.join(sorted(unknown))}")
    typ = node.get("type")
    if typ not in TYPES:
        problems.append(f"{path}: type must be one of {', '.join(TYPES)}")
        return
    for key in ("description", "title"):
        if key in node and (not isinstance(node[key], str) or len(node[key]) > 1000):
            problems.append(f"{path}: {key} must be text (at most 1000 characters)")

    if typ == "object":
        props = node.get("properties", {})
        if not isinstance(props, dict):
            problems.append(f"{path}: properties must be an object")
            return
        for name, sub in props.items():
            counter["props"] += 1
            if not NAME_RE.match(name):
                problems.append(f"{path}: property name '{name}' must start with a letter and use letters, digits or _")
            _check_node(sub, f"{name}" if path == "(root)" else f"{path}.{name}", depth + 1, problems, counter)
        if counter["props"] > MAX_PROPERTIES:
            problems.append(f"At most {MAX_PROPERTIES} properties in one contract")
        required = node.get("required", [])
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            problems.append(f"{path}: required must be a list of property names")
        else:
            missing = [r for r in required if r not in props]
            if missing:
                problems.append(f"{path}: required lists unknown properties: {', '.join(missing)}")
            if len(set(required)) != len(required):
                problems.append(f"{path}: required lists a property twice")
        if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):
            problems.append(f"{path}: additionalProperties must be true or false")
    elif "properties" in node or "required" in node:
        problems.append(f"{path}: properties/required only apply to objects")

    if typ == "array":
        if "items" not in node:
            problems.append(f"{path}: an array must say what its items are (items)")
        else:
            _check_node(node["items"], f"{path}[]", depth + 1, problems, counter)
    elif "items" in node:
        problems.append(f"{path}: items only applies to arrays")

    if "enum" in node:
        enum = node["enum"]
        if typ in ("object", "array"):
            problems.append(f"{path}: enum is only supported for text, numbers and booleans")
        elif not isinstance(enum, list) or not enum or len(enum) > MAX_ENUM:
            problems.append(f"{path}: enum must be a list of 1-{MAX_ENUM} allowed values")
        elif not all(_type_ok(v, typ) for v in enum):
            problems.append(f"{path}: every enum value must be of type {typ}")
        elif len({json.dumps(v) for v in enum}) != len(enum):
            problems.append(f"{path}: enum has duplicate values")

    if "default" in node:
        sub = {k: v for k, v in node.items() if k != "default"}
        try:
            if _ok_for_jsonschema(sub):
                jsonschema.Draft202012Validator(sub).validate(node["default"])
        except jsonschema.ValidationError as exc:
            problems.append(f"{path}: default value is not valid ({exc.message})")


def _ok_for_jsonschema(node: dict) -> bool:
    try:
        jsonschema.Draft202012Validator.check_schema(node)
        return True
    except jsonschema.SchemaError:
        return False


def normalize(schema: dict) -> dict:
    """Make implicit choices explicit: objects state additionalProperties (default false) and
    `required` (default empty). Returns a copy."""
    out = copy.deepcopy(schema)

    def walk(node: dict) -> None:
        if node.get("type") == "object":
            node.setdefault("properties", {})
            node.setdefault("required", [])
            node.setdefault("additionalProperties", False)
            for sub in node["properties"].values():
                walk(sub)
        elif node.get("type") == "array" and isinstance(node.get("items"), dict):
            walk(node["items"])

    walk(out)
    return out


# ---------- validating values ----------
def apply_defaults(schema: dict, value: Any) -> Any:
    """Fill in missing object properties that have a default (recursively). Returns a copy."""
    if schema.get("type") == "object" and isinstance(value, dict):
        out = dict(value)
        for name, sub in (schema.get("properties") or {}).items():
            if name not in out and "default" in sub:
                out[name] = copy.deepcopy(sub["default"])
            if name in out:
                out[name] = apply_defaults(sub, out[name])
        return out
    if schema.get("type") == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [apply_defaults(schema["items"], v) for v in value]
    return value


def _path(error: jsonschema.ValidationError) -> str:
    parts = []
    for p in error.absolute_path:
        parts.append(f"[{p}]" if isinstance(p, int) else (f".{p}" if parts else str(p)))
    return "".join(parts) or "(root)"


def _message(error: jsonschema.ValidationError) -> str:
    v = error.validator
    if v == "required":
        missing = re.findall(r"'([^']+)' is a required property", error.message)
        return f"'{missing[0]}' is required" if missing else error.message
    if v == "additionalProperties":
        extra = re.findall(r"'([^']+)'", error.message)
        return f"unknown field{'s' if len(extra) > 1 else ''}: {', '.join(extra)}" if extra else error.message
    if v == "type":
        return f"must be {'an' if error.validator_value in ('object', 'array', 'integer') else 'a'} {error.validator_value}"
    if v == "enum":
        return "must be one of: " + ", ".join(json.dumps(x) for x in error.validator_value)
    return error.message


def validate(schema: dict, value: Any) -> tuple[Any, list[dict]]:
    """Validate a value against a contract. Returns (value with defaults applied, errors).

    Each error is {"path": "customer.address.city", "message": "must be a string"}."""
    filled = apply_defaults(schema, value)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(filled), key=lambda e: (list(e.absolute_path), e.message))
    return filled, [{"path": _path(e), "message": _message(e)} for e in errors[:50]]


def format_errors(errors: list[dict]) -> str:
    return "; ".join(f"{e['path']}: {e['message']}" if e["path"] != "(root)" else e["message"] for e in errors)


# ---------- workflow mappings ----------
TEMPLATE_RE = re.compile(r"{{\s*[^}]+}}")


def coerce(schema: dict, value: Any) -> Any:
    """Turn text from forms/templates into the declared scalar type when it is unambiguous
    ("42" -> 42 for integers, "true" -> True for booleans). Anything else is left alone so
    validation reports it."""
    typ = schema.get("type")
    if isinstance(value, str):
        text = value.strip()
        if typ == "integer" and re.fullmatch(r"-?\d+", text):
            return int(text)
        if typ == "number" and re.fullmatch(r"-?\d+(\.\d+)?", text):
            return float(text) if "." in text else int(text)
        if typ == "boolean" and text.lower() in ("true", "false"):
            return text.lower() == "true"
        if typ in ("object", "array") and text[:1] in "{[":
            try:
                return coerce(schema, json.loads(text))
            except ValueError:
                return value
        return value
    if typ == "object" and isinstance(value, dict):
        props = schema.get("properties") or {}
        return {k: coerce(props[k], v) if k in props else v for k, v in value.items()}
    if typ == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [coerce(schema["items"], v) for v in value]
    return value


def mapping_problems(schema: dict, mapping: dict) -> list[str]:
    """Static check of a workflow step's input mapping against an agent's input contract.

    Values containing {{ }} are only known at run time (they are validated then); fixed values
    are checked now. Reports unknown fields, missing required fields and fixed values of the
    wrong type, so incompatible mappings are caught before a workflow is published."""
    problems: list[str] = []
    _mapping_walk(schema, mapping, "", problems)
    return problems


def _mapping_walk(schema: dict, mapping: Any, prefix: str, problems: list[str]) -> None:
    if isinstance(mapping, str) and TEMPLATE_RE.search(mapping):
        return  # resolved at run time
    if schema.get("type") == "object" and isinstance(mapping, dict):
        props = schema.get("properties") or {}
        for key, val in mapping.items():
            if key not in props:
                if schema.get("additionalProperties") is not True:
                    problems.append(f"'{prefix}{key}' is not an input of this agent")
                continue
            _mapping_walk(props[key], val, f"{prefix}{key}.", problems)
        for req in schema.get("required") or []:
            if req not in mapping and "default" not in props.get(req, {}):
                problems.append(f"'{prefix}{req}' is required by this agent but not mapped")
        return
    value = coerce(schema, mapping)
    _, errors = validate(schema, value)
    for e in errors:
        where = prefix.rstrip(".") + ("" if e["path"] == "(root)" else "." + e["path"])
        problems.append(f"'{where}' {e['message']}")


# ---------- prompts and parsing ----------
def describe(schema: dict) -> str:
    return json.dumps(schema, separators=(",", ":"))


def parse_json_output(text: str) -> tuple[Any, str | None]:
    """Parse a model's reply as JSON (tolerating ```json fences). Returns (value, problem)."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned), None
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(cleaned[start : end + 1]), None
            except ValueError:
                pass
    return None, "The reply was not valid JSON"


def input_as_message(schema: dict, value: dict) -> str:
    """The user message an agent receives for a validated input."""
    if is_default_input(schema):
        return str(value.get("message", ""))
    return "Input (JSON, matches your input schema):\n" + json.dumps(value, ensure_ascii=False, indent=2)
