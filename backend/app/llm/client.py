"""Client for OpenAI-compatible chat completion APIs (Ollama /v1, vLLM, LM Studio, hosted APIs)."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import settings


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as returned by the model


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_message: dict = field(default_factory=dict)


@dataclass
class ModelTarget:
    base_url: str
    model_name: str
    api_key: Optional[str] = None
    supports_tools: bool = True


class LLMClient:
    """Thin wrapper over POST {base_url}/chat/completions.

    `transport` exists so tests can plug in httpx.MockTransport.
    """

    def __init__(self, transport: Optional[httpx.BaseTransport] = None, timeout: Optional[float] = None):
        self._transport = transport
        self._timeout = timeout or settings.llm_timeout_seconds

    def chat(
        self,
        target: ModelTarget,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": target.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools and target.supports_tools:
            payload["tools"] = tools
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"

        url = target.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as http:
                resp = http.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMError(f"LLM request timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach LLM endpoint: {exc.__class__.__name__}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"LLM endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM endpoint returned an unexpected response shape") from exc

        tool_calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function") or {}
            args = fn.get("arguments", "{}")
            if not isinstance(args, str):  # some servers return a dict
                args = json.dumps(args)
            tool_calls.append(ToolCall(id=call.get("id") or f"call_{i}", name=fn.get("name", ""), arguments=args))

        usage = data.get("usage") or {}
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            raw_message=message,
        )


API_KEY_ENV_PREFIX = "LLM_KEY_"


def resolve_api_key(api_key_env: Optional[str]) -> Optional[str]:
    """Read a provider key, but only from LLM_KEY_* variables (rows saved before this rule are ignored)."""
    if not api_key_env or not api_key_env.startswith(API_KEY_ENV_PREFIX):
        return None
    return os.getenv(api_key_env)


_default_client = LLMClient()


def get_llm_client() -> LLMClient:
    return _default_client


def set_llm_client(client: LLMClient) -> None:
    """Used by tests to swap the client."""
    global _default_client
    _default_client = client
