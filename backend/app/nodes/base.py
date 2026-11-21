"""Node catalog: the ready-made steps a workflow can use.

Each node type declares its form fields, so the UI can render a no-code form for it,
the validator can check it, and the AI builder can describe it to the model.
Text fields accept {{ }} variables, e.g. "Hello {{input.name}}" or "{{node-2.text}}".
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

FIELD_TYPES = {
    "text",
    "textarea",
    "number",
    "boolean",
    "select",
    "credential",
    "json",
    "keyvalue",
    "list",
    "agent",
    "agent_input",
}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str = "text"
    required: bool = False
    default: Any = None
    help: str = ""
    placeholder: str = ""
    options: tuple = ()  # for select
    credential_type: Optional[str] = None  # for credential
    templated: bool = True  # whether {{ }} variables are resolved

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "help": self.help,
            "placeholder": self.placeholder,
            "options": list(self.options),
            "credential_type": self.credential_type,
        }


class NodeError(Exception):
    """A step failed in a way the user can understand and fix."""


@dataclass
class NodeContext:
    """What a node handler may use. Built per run by the run service."""

    role: str
    get_credential: Callable[[Any, str], dict]  # (credential_id, expected_type) -> secret data
    ask_llm: Callable[..., dict]  # (messages, json_mode=False, model_id=None) -> {"text", "usage"}
    run_agent: Callable[[int, dict], dict]  # (agent_id, input object) -> the agent's output object
    settings: dict = field(default_factory=dict)  # platform settings snapshot


@dataclass(frozen=True)
class NodeType:
    key: str
    name: str
    category: str  # "AI", "Data", "Apps", "Flow"
    description: str
    icon: str
    fields: tuple
    handler: Callable[[dict, NodeContext], Any]
    output_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "icon": self.icon,
            "fields": [f.to_dict() for f in self.fields],
            "output_hint": self.output_hint,
        }


@dataclass(frozen=True)
class CredentialType:
    key: str
    name: str
    fields: tuple  # Field objects; type "password" marks secrets
    help: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "help": self.help,
            "fields": [{**f.to_dict(), "secret": f.type == "password"} for f in self.fields],
        }


NODE_TYPES: dict[str, NodeType] = {}
CREDENTIAL_TYPES: dict[str, CredentialType] = {}


def node(key: str, name: str, category: str, description: str, icon: str, fields: list, output_hint: str = ""):
    def wrap(fn):
        if key in NODE_TYPES:
            raise ValueError(f"Duplicate node type {key}")
        for f in fields:
            assert f.type in FIELD_TYPES, f"{key}.{f.key}: bad field type {f.type}"
        NODE_TYPES[key] = NodeType(key, name, category, description, icon, tuple(fields), fn, output_hint)
        return fn

    return wrap


def credential_type(key: str, name: str, fields: list, help: str = "") -> None:
    CREDENTIAL_TYPES[key] = CredentialType(key, name, tuple(fields), help)


def get_node_type(key: str) -> Optional[NodeType]:
    return NODE_TYPES.get(key)
