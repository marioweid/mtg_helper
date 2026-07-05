"""Card embedding pipeline: generate Gemini embeddings and store in Qdrant."""

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

import asyncpg
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from mtg_helper.config import settings
from mtg_helper.services import card_representation
from mtg_helper.services.llm_client import LLMClient

if TYPE_CHECKING:
    from mtg_helper.services.admin_jobs import ProgressCb

_log = logging.getLogger(__name__)

_QDRANT_UPSERT_BATCH = 500

# Pace batches under the Gemini embeddings RPM quota. Tier 1 paid =
# 100 RPM for gemini-embedding-001; 0.8s per call leaves headroom.
_EMBED_BATCH_DELAY_SECONDS = 0.8


def build_embedding_text(
    name: str,
    type_line: str | None,
    oracle_text: str | None,
    keywords: list[str],
    *,
    color_identity: list[str] | None = None,
    card_types: list[str] | None = None,
    subtypes: list[str] | None = None,
    tags: list[str] | None = None,
    traits: list[str] | None = None,
    token_types: list[str] | None = None,
    mana_value: float | None = None,
    edhrec_rank: int | None = None,
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
    return card_representation.build_embedding_text(
        name=name,
        type_line=type_line,
        oracle_text=oracle_text,
        keywords=keywords,
        color_identity=color_identity,
        card_types=card_types,
        subtypes=subtypes,
        tags=tags,
        traits=traits,
        token_types=token_types,
        mana_value=mana_value,
        edhrec_rank=edhrec_rank,
    )


async def embed_texts(
    ai_client: LLMClient,
    texts: list[str],
) -> list[list[float]]:
    """Embed a batch of card texts for corpus storage.

    Args:
        ai_client: LLM adapter.
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (one per input text).
    """
    return await ai_client.embed(texts, task_type="RETRIEVAL_DOCUMENT")


async def embed_single(ai_client: LLMClient, text: str) -> list[float]:
    """Embed a single search query string.

    Args:
        ai_client: LLM adapter.
        text: Text to embed.

    Returns:
        Embedding vector.
    """
    vectors = await ai_client.embed([text], task_type="RETRIEVAL_QUERY")
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
        row: asyncpg record with card metadata, embedding, and payload fields.

    Returns:
        Qdrant PointStruct ready for upsert.
    """
    legalities: dict[str, Any] = json.loads(row["legalities"]) if row["legalities"] else {}
    representation = card_representation.from_row(row)
    return PointStruct(
        id=str(row["id"]),
        vector=row["embedding"],
        payload={
            "name": row["name"],
            "color_identity": list(row["color_identity"]),
            "commander_legal": legalities.get("commander") == "legal",
            "tags": list(row["tags"]),
            "edhrec_rank": row["edhrec_rank"],
            "card_types": list(row["card_types"]),
            "subtypes": list(row["subtypes"]),
            "traits": list(row["traits"]),
            "token_types": list(row["token_types"]),
            "representation": representation.feature_payload(),
            "feature_labels": representation.feature_labels(),
        },
    )


async def run_batch_embed(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    progress: "ProgressCb | None" = None,
) -> dict[str, Any]:
    """Embed all cards not yet in Qdrant and upsert them into the collection.

    Fetches cards where embedded_at IS NULL or updated_at > embedded_at,
    generates embeddings in batches, upserts into Qdrant, then updates
    embedded_at in Postgres.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter.
        qdrant_client: Async Qdrant client.
        progress: Optional callback ``(phase, current, total)`` invoked after
            each batch. Phase is ``"embedding"``.

    Returns:
        Summary dict with cards_embedded and duration_seconds.
    """
    from mtg_helper.services.admin_jobs import noop_progress

    cb = progress or noop_progress
    await ensure_collection(qdrant_client)
    start = time.monotonic()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, type_line, oracle_text, keywords, cmc,
                   color_identity, legalities, tags, edhrec_rank, card_types, subtypes, traits,
                   token_types
            FROM cards
            WHERE embedded_at IS NULL OR updated_at > embedded_at
            ORDER BY name
            """
        )

    if not rows:
        cb("embedding", 0, 0)
        return {"cards_embedded": 0, "duration_seconds": 0.0}

    row_count = len(rows)
    _log.info("Embedding %d cards", row_count)
    cb("embedding", 0, row_count)
    total = 0
    batch_size = settings.embedding_batch_size

    for i in range(0, row_count, batch_size):
        if i > 0:
            await asyncio.sleep(_EMBED_BATCH_DELAY_SECONDS)
        batch = rows[i : i + batch_size]
        texts = [
            build_embedding_text(
                r["name"],
                r["type_line"],
                r["oracle_text"],
                list(r["keywords"]),
                color_identity=list(r["color_identity"]),
                card_types=list(r["card_types"]),
                subtypes=list(r["subtypes"]),
                tags=list(r["tags"]),
                traits=list(r["traits"]),
                token_types=list(r["token_types"]),
                mana_value=float(r["cmc"]) if r["cmc"] is not None else None,
                edhrec_rank=r["edhrec_rank"],
            )
            for r in batch
        ]

        vectors = await embed_texts(ai_client, texts)

        # Build Qdrant points
        points: list[PointStruct] = []
        card_ids: list[uuid.UUID] = []
        for row, vector in zip(batch, vectors, strict=True):
            representation = card_representation.from_row(row)
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
                    "card_types": list(row["card_types"]),
                    "subtypes": list(row["subtypes"]),
                    "traits": list(row["traits"]),
                    "token_types": list(row["token_types"]),
                    "representation": representation.feature_payload(),
                    "feature_labels": representation.feature_labels(),
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
        _log.info("Embedded %d / %d cards", total, row_count)
        cb("embedding", total, row_count)

    return {
        "cards_embedded": total,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
