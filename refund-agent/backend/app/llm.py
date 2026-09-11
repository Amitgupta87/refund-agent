"""Provider-agnostic LLM client.

Three implementations live in this module: Gemini (raw httpx), Anthropic (SDK),
OpenAI (SDK). The agent loop talks only to the `LLMClient` interface — it
doesn't know which provider is in use.

Tool declarations are defined in lowercase JSON Schema (in `tools.py`) and each
provider serializes them to its native shape. Conversation history is kept in a
provider-neutral `list[Turn]` and serialized per provider on every call.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import settings


class LLMError(RuntimeError):
    """Any failure talking to the LLM provider."""


# ---- Provider-neutral data shapes ----


@dataclass
class MediaPart:
    """A piece of multimodal content the user attached to a chat message."""

    mime_type: str  # "image/jpeg" | "video/mp4" | ...
    data_b64: str
    kind: str       # "image" | "video"


@dataclass
class LLMToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    id: str
    name: str
    output: dict[str, Any]


@dataclass
class Turn:
    """One step in a provider-neutral conversation history."""

    role: str  # "user" | "assistant"
    text: str = ""
    media: list[MediaPart] = field(default_factory=list)
    tool_calls: list[LLMToolCall] = field(default_factory=list)  # assistant only
    tool_results: list[ToolResult] = field(default_factory=list)  # user only
    # Raw Gemini response parts — preserved so thought_signature survives history replay
    # for thinking models (e.g. gemini-3-flash-preview). Ignored by other providers.
    gemini_parts: list[dict[str, Any]] = field(default_factory=list)
    # Raw Anthropic content blocks — preserved so `thinking` block signatures survive
    # history replay if extended thinking is ever enabled on Opus/Sonnet 4. Ignored
    # by other providers and a no-op for the default Haiku 4.5 (no thinking blocks).
    anthropic_blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMStep:
    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    gemini_parts: list[dict[str, Any]] = field(default_factory=list)
    anthropic_blocks: list[dict[str, Any]] = field(default_factory=list)


class LLMClient(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        system: str,
        history: list[Turn],
        tool_decls: list[dict[str, Any]],
    ) -> LLMStep:
        """Send one round-trip and return the model's next step."""


# ─────────────────────────  Gemini (raw httpx)  ─────────────────────────


class GeminiClient(LLMClient):
    name = "gemini"

    def generate(self, system, history, tool_decls):
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured.")

        contents: list[dict[str, Any]] = []
        for turn in history:
            if turn.role == "user":
                parts: list[dict[str, Any]] = []
                if turn.text:
                    parts.append({"text": turn.text})
                for m in turn.media:
                    parts.append({"inline_data": {"mime_type": m.mime_type, "data": m.data_b64}})
                for tr in turn.tool_results:
                    parts.append({"functionResponse": {"name": tr.name, "response": tr.output}})
                contents.append({"role": "user", "parts": parts})
            else:
                if turn.gemini_parts:
                    # Replay raw parts verbatim so thought_signature is preserved
                    # for thinking models (gemini-3-flash-preview etc.).
                    contents.append({"role": "model", "parts": turn.gemini_parts})
                else:
                    parts = []
                    if turn.text:
                        parts.append({"text": turn.text})
                    for tc in turn.tool_calls:
                        parts.append({"functionCall": {"name": tc.name, "args": tc.args}})
                    contents.append({"role": "model", "parts": parts})

        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": tool_decls}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"temperature": 0, "candidateCount": 1},
        }
        url = f"{settings.gemini_base_url}/models/{settings.gemini_model}:generateContent"

        try:
            resp = httpx.post(url, params={"key": settings.gemini_api_key},
                              json=body, timeout=60.0)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"Gemini API returned {exc.response.status_code}: "
                f"{exc.response.text[:500]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach Gemini API: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError("Gemini returned a non-JSON response.") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(
                f"Gemini blocked the request: {block}" if block
                else "Gemini returned no candidates."
            )

        out = LLMStep()
        raw_parts = candidates[0].get("content", {}).get("parts", []) or []
        out.gemini_parts = raw_parts  # preserved for thought_signature replay
        text_chunks: list[str] = []
        for p in raw_parts:
            # thought parts are internal reasoning — don't surface as output text
            if p.get("thought"):
                continue
            if "text" in p:
                text_chunks.append(p["text"])
            if "functionCall" in p:
                fc = p["functionCall"]
                out.tool_calls.append(LLMToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=fc.get("name", ""),
                    args=fc.get("args", {}) or {},
                ))
        out.text = "".join(text_chunks).strip()
        return out


# ─────────────────────────  Anthropic (SDK)  ─────────────────────────


def _anthropic_block_to_dict(block: Any) -> dict[str, Any]:
    """Serialize a response content block into the dict shape the API accepts back.

    Handles `text`, `tool_use`, `thinking`, and `redacted_thinking`. Extended-
    thinking blocks (`thinking` / `redacted_thinking`) carry a `signature` field
    that MUST be echoed verbatim when replaying history — analogous to Gemini's
    `thought_signature`. Stripping them yields HTTP 400 from the API.
    """
    bt = getattr(block, "type", None)
    if bt == "text":
        return {"type": "text", "text": block.text}
    if bt == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input) if block.input else {},
        }
    if bt == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", ""),
            "signature": getattr(block, "signature", ""),
        }
    if bt == "redacted_thinking":
        return {"type": "redacted_thinking", "data": getattr(block, "data", "")}
    # Fallback: best-effort dump for any future block type.
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return {"type": bt} if bt else {}


class AnthropicClient(LLMClient):
    name = "anthropic"

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not configured.")
        from anthropic import Anthropic  # local import keeps it optional
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def generate(self, system, history, tool_decls):
        messages: list[dict[str, Any]] = []
        for turn in history:
            if turn.role == "user":
                content: list[dict[str, Any]] = []
                if turn.text:
                    content.append({"type": "text", "text": turn.text})
                for m in turn.media:
                    if m.kind != "image":
                        # Anthropic doesn't natively accept video; surface a note in-band.
                        content.append({"type": "text", "text": (
                            "[Customer attached a video — provider doesn't support "
                            "video; please ask for a photo instead.]"
                        )})
                        continue
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": m.mime_type,
                            "data": m.data_b64,
                        },
                    })
                for tr in turn.tool_results:
                    content.append({
                        "type": "tool_result",
                        "tool_use_id": tr.id,
                        "content": [{"type": "text", "text": json.dumps(tr.output)}],
                    })
                messages.append({"role": "user", "content": content})
            else:
                if turn.anthropic_blocks:
                    # Replay raw blocks verbatim so any `thinking` signatures survive.
                    messages.append({
                        "role": "assistant", "content": turn.anthropic_blocks,
                    })
                else:
                    content = []
                    if turn.text:
                        content.append({"type": "text", "text": turn.text})
                    for tc in turn.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.args,
                        })
                    messages.append({"role": "assistant", "content": content})

        anthropic_tools = [
            {"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]}
            for t in tool_decls
        ]

        try:
            response = self._client.messages.create(
                model=settings.anthropic_model,
                system=system,
                messages=messages,
                tools=anthropic_tools,
                max_tokens=2048,
                temperature=0,
            )
        except Exception as exc:  # SDK can raise various subclasses; normalize.
            raise LLMError(f"Anthropic API error: {exc}") from exc

        out = LLMStep()
        out.anthropic_blocks = [_anthropic_block_to_dict(b) for b in response.content]
        text_chunks: list[str] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_chunks.append(block.text)
            elif block_type == "tool_use":
                out.tool_calls.append(LLMToolCall(
                    id=block.id, name=block.name,
                    args=dict(block.input) if block.input else {},
                ))
            # `thinking` / `redacted_thinking` blocks are preserved in
            # anthropic_blocks for replay but NOT surfaced to the customer.
        out.text = "".join(text_chunks).strip()
        return out


# ─────────────────────────  OpenAI (SDK)  ─────────────────────────
#
# NOTE: This client uses the Chat Completions API, which does NOT return
# reasoning chains from o-series models (o1, o3, o4-mini). Those models work
# end-to-end here, but their reasoning is invisible — fine for our use case.
# If you ever migrate to the Responses API for o-series, you must preserve and
# replay `reasoning` items the same way we preserve Gemini `thought_signature`
# and Anthropic `thinking` signatures (see those clients above).


class OpenAIClient(LLMClient):
    name = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not configured.")
        from openai import OpenAI
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self._client = OpenAI(**kwargs)

    def generate(self, system, history, tool_decls):
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

        for turn in history:
            if turn.role == "user":
                # Tool results in OpenAI chat are sent as separate "tool" role
                # messages, not bundled into the user content.
                user_parts: list[dict[str, Any]] = []
                if turn.text:
                    user_parts.append({"type": "text", "text": turn.text})
                for m in turn.media:
                    if m.kind != "image":
                        user_parts.append({"type": "text", "text": (
                            "[Customer attached a video — provider doesn't support "
                            "video; please ask for a photo instead.]"
                        )})
                        continue
                    data_url = f"data:{m.mime_type};base64,{m.data_b64}"
                    user_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                if user_parts:
                    messages.append({"role": "user", "content": user_parts})
                for tr in turn.tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr.id,
                        "content": json.dumps(tr.output),
                    })
            else:
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": turn.text or None,
                }
                if turn.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.args),
                            },
                        }
                        for tc in turn.tool_calls
                    ]
                messages.append(assistant_msg)

        openai_tools = [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["parameters"],
            }}
            for t in tool_decls
        ]

        try:
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=openai_tools,
                temperature=0,
            )
        except Exception as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        out = LLMStep()
        choice = response.choices[0].message
        out.text = (choice.content or "").strip()
        for tc in (choice.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            out.tool_calls.append(LLMToolCall(
                id=tc.id, name=tc.function.name, args=args,
            ))
        return out


# ─────────────────────────  Factory  ─────────────────────────


def make_client() -> LLMClient:
    """Construct the LLM client configured by LLM_PROVIDER."""
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        return GeminiClient()
    if provider == "anthropic":
        return AnthropicClient()
    if provider == "openai":
        return OpenAIClient()
    raise LLMError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        "Use one of: gemini | anthropic | openai."
    )
