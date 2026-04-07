"""Card embedding pipeline: generate OpenAI embeddings and store in Qdrant."""

import json
import logging
import time
import uuid
from typing import Any

import asyncpg
import openai
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from mtg_helper.config import settings

_log = logging.getLogger(__name__)

_QDRANT_UPSERT_BATCH = 500


def build_embedding_text(
    name: str,
    type_line: str | None,
    oracle_text: str | None,
    keywords: list[str],
) -> str:
    """Build a composite text string to embed for a card.

    Args:
        name: Card name.
        type_line: Type line (e.g. "Legendary Creature — Dragon").
        oracle_text: Rules text.
        keywords: MTG keyword abilities.

    Returns:
        Single string combining all fields for embedding.
    """
    parts = [name]
    if type_line:
        parts.append(type_line)
    if oracle_text:
        parts.append(oracle_text)
    if keywords:
        parts.append("Keywords: " + ", ".join(keywords))
    return " | ".join(parts)


async def embed_texts(
    ai_client: openai.AsyncOpenAI,
    texts: list[str],
) -> list[list[float]]:
    """Embed a batch of texts using the configured OpenAI embedding model.

    Args:
        ai_client: Async OpenAI client.
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (one per input text).
    """
    response = await ai_client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


async def embed_single(ai_client: openai.AsyncOpenAI, text: str) -> list[float]:
    """Embed a single text string.

    Args:
        ai_client: Async OpenAI client.
        text: Text to embed.

    Returns:
        Embedding vector.
    """
    vectors = await embed_texts(ai_client, [text])
    return vectors[0]


async def ensure_collection(qdrant_client: AsyncQdrantClient) -> None:
    """Create the Qdrant collection if it does not exist.

    Args:
        qdrant_client: Async Qdrant client.
    """
    collections = await qdrant_client.get_collections()
    existing = {c.name for c in collections.collections}
    if settings.qdrant_collection not in existing:
        await qdrant_client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )
        _log.info("Created Qdrant collection '%s'", settings.qdrant_collection)


def _card_row_to_point(row: asyncpg.Record) -> PointStruct:
    """Convert a DB card row (with embedding) to a Qdrant PointStruct.

    Args:
        row: asyncpg record with id, name, color_identity, legalities,
             tags, edhrec_rank, and embedding fields.

    Returns:
        Qdrant PointStruct ready for upsert.
    """
    legalities: dict[str, Any] = json.loads(row["legalities"]) if row["legalities"] else {}
    return PointStruct(
        id=str(row["id"]),
        vector=row["embedding"],
        payload={
            "name": row["name"],
            "color_identity": list(row["color_identity"]),
            "commander_legal": legalities.get("commander") == "legal",
            "tags": list(row["tags"]),
            "edhrec_rank": row["edhrec_rank"],
        },
    )


async def run_batch_embed(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
) -> dict[str, Any]:
    """Embed all cards not yet in Qdrant and upsert them into the collection.

    Fetches cards where embedded_at IS NULL or updated_at > embedded_at,
    generates embeddings in batches, upserts into Qdrant, then updates
    embedded_at in Postgres.

    Args:
        pool: asyncpg connection pool.
        ai_client: Async OpenAI client.
        qdrant_client: Async Qdrant client.

    Returns:
        Summary dict with cards_embedded and duration_seconds.
    """
    await ensure_collection(qdrant_client)
    start = time.monotonic()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, type_line, oracle_text, keywords,
                   color_identity, legalities, tags, edhrec_rank
            FROM cards
            WHERE embedded_at IS NULL OR updated_at > embedded_at
            ORDER BY name
            """
        )

    if not rows:
        return {"cards_embedded": 0, "duration_seconds": 0.0}

    _log.info("Embedding %d cards", len(rows))
    total = 0
    batch_size = settings.embedding_batch_size

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [
            build_embedding_text(
                r["name"],
                r["type_line"],
                r["oracle_text"],
                list(r["keywords"]),
            )
            for r in batch
        ]

        vectors = await embed_texts(ai_client, texts)

        # Build Qdrant points
        points: list[PointStruct] = []
        card_ids: list[uuid.UUID] = []
        for row, vector in zip(batch, vectors, strict=True):
            point = PointStruct(
                id=str(row["id"]),
                vector=vector,
                payload={
                    "name": row["name"],
                    "color_identity": list(row["color_identity"]),
                    "commander_legal": (
                        (json.loads(row["legalities"]) if row["legalities"] else {}).get(
                            "commander"
                        )
                        == "legal"
                    ),
                    "tags": list(row["tags"]),
                    "edhrec_rank": row["edhrec_rank"],
                },
            )
            points.append(point)
            card_ids.append(row["id"])

        # Upsert into Qdrant in sub-batches
        for j in range(0, len(points), _QDRANT_UPSERT_BATCH):
            await qdrant_client.upsert(
                collection_name=settings.qdrant_collection,
                points=points[j : j + _QDRANT_UPSERT_BATCH],
            )

        # Mark as embedded in Postgres
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cards SET embedded_at = now() WHERE id = ANY($1::uuid[])",
                card_ids,
            )

        total += len(batch)
        _log.info("Embedded %d / %d cards", total, len(rows))

    return {
        "cards_embedded": total,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
