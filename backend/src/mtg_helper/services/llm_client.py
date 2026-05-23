"""Gemini-backed embedding adapter.

After the pydantic-ai agent migration this client only exposes ``embed`` —
all chat / function-calling traffic now flows through ``services.agents``.
The class name is kept as ``LLMClient`` because services thread it through
as ``ai_client`` for embedding-driven retrieval.
"""

import asyncio
import logging
import random

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

_log = logging.getLogger(__name__)

_EMBED_RETRY_ATTEMPTS = 6
_EMBED_RETRY_BASE_SECONDS = 2.0
_EMBED_RETRY_MAX_SECONDS = 60.0


class LLMClient:
    """Async embedding adapter.

    Attributes:
        chat_model: Gemini chat model ID — retained because callers pass it
            through to ``services.agents`` when constructing pydantic-ai
            agents (kept here to avoid widening every signature).
        embed_model: Gemini embedding model ID.
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

    async def embed(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Strings to embed.
            task_type: Gemini embedding task type. Use ``RETRIEVAL_DOCUMENT``
                for corpus items and ``RETRIEVAL_QUERY`` for search queries.

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
