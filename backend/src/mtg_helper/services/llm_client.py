"""Gemini-backed LLM adapter: chat completions + embeddings.

Single touchpoint to `google.genai` so services stay provider-agnostic.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

_log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """One function-call request emitted by the model."""

    name: str
    args: dict[str, Any]


@dataclass
class ChatToolResponse:
    """Either a final text response or pending tool calls to dispatch.

    Exactly one of ``text`` and ``tool_calls`` is populated per turn.
    """

    text: str | None = None
    tool_calls: list[ToolCall] | None = None


_EMBED_RETRY_ATTEMPTS = 6
_EMBED_RETRY_BASE_SECONDS = 2.0
_EMBED_RETRY_MAX_SECONDS = 60.0


class LLMClient:
    """Async adapter exposing chat and embedding primitives.

    Attributes:
        chat_model: Gemini model ID used for chat completions.
        embed_model: Gemini model ID used for embeddings.
        embed_dim: Output dimensionality of embedding vectors.
    """

    def __init__(
        self,
        api_key: str,
        chat_model: str,
        embed_model: str,
        embed_dim: int,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.embed_dim = embed_dim

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """Run a chat completion and return the assistant reply text.

        Args:
            system: System instruction prepended to the request.
            messages: Alternating user/assistant turns in OpenAI shape —
                `{"role": "user"|"assistant", "content": str}`.
            temperature: Sampling temperature.
            max_output_tokens: Upper bound on reply tokens.

        Returns:
            Plain text reply. Empty string if the model returned no content.
        """
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=m["content"])],
            )
            for m in messages
        ]
        response = await self._client.aio.models.generate_content(
            model=self.chat_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )
        return response.text or ""

    async def chat_with_tools(
        self,
        *,
        system: str,
        history: list[types.Content],
        tools: list[types.Tool],
        temperature: float,
        max_output_tokens: int,
    ) -> ChatToolResponse:
        """Run a chat completion with function-calling enabled.

        ``history`` is the raw Gemini content list (the caller manages turn
        appending) so tool_call / tool_response pairs can be threaded without
        format translation. Returns either text or a list of pending tool
        calls — exactly one branch is populated per turn.
        """
        # Cast through Any: google-genai's stubs declare `tools` as a union
        # involving generic callables that confuses ty.
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "tools": tools,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        response = await self._client.aio.models.generate_content(
            model=self.chat_model,
            contents=history,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        calls: list[ToolCall] = []
        text_parts: list[str] = []
        candidates = response.candidates or []
        if not candidates:
            return ChatToolResponse(text=response.text or "")
        content = candidates[0].content
        for part in content.parts if content and content.parts else []:
            if part.function_call is not None:
                fc = part.function_call
                calls.append(ToolCall(name=fc.name or "", args=dict(fc.args or {})))
                continue
            if part.text:
                text_parts.append(part.text)
        if calls:
            return ChatToolResponse(tool_calls=calls)
        return ChatToolResponse(text="".join(text_parts))

    async def embed(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Strings to embed.
            task_type: Gemini embedding task type. Use `RETRIEVAL_DOCUMENT`
                for corpus items and `RETRIEVAL_QUERY` for search queries.

        Returns:
            One vector per input text, in the same order.
        """
        for attempt in range(_EMBED_RETRY_ATTEMPTS):
            try:
                response = await self._client.aio.models.embed_content(
                    model=self.embed_model,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self.embed_dim,
                        task_type=task_type,
                    ),
                )
                break
            except genai_errors.APIError as exc:
                if exc.code != 429 or attempt == _EMBED_RETRY_ATTEMPTS - 1:
                    raise
                delay = min(
                    _EMBED_RETRY_BASE_SECONDS * (2**attempt),
                    _EMBED_RETRY_MAX_SECONDS,
                ) + random.uniform(0, 1)
                _log.warning(
                    "Embed 429 on attempt %d/%d; sleeping %.1fs",
                    attempt + 1,
                    _EMBED_RETRY_ATTEMPTS,
                    delay,
                )
                await asyncio.sleep(delay)
        embeddings = response.embeddings or []
        return [list(e.values or []) for e in embeddings]
