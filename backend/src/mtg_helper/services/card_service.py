"""Card search and retrieval service using the local Scryfall card database."""

import json
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.cards import CardResponse, CardSearchParams


def _parse_jsonb(value: Any) -> dict:
    """Parse a JSONB value returned by asyncpg (may be a string or dict)."""
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _row_to_card(row: asyncpg.Record) -> CardResponse:
    """Convert an asyncpg record to a CardResponse."""
    return CardResponse(
        id=row["id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        colors=list(row["colors"] or []),
        keywords=list(row["keywords"] or []),
        power=row["power"],
        toughness=row["toughness"],
        legalities=_parse_jsonb(row["legalities"]),
        image_uri=row["image_uri"],
        prices=_parse_jsonb(row["prices"]),
        rarity=row["rarity"],
        set_code=row["set_code"],
        released_at=row["released_at"],
        edhrec_rank=row["edhrec_rank"],
    )


def _add_text_search(q: str, clauses: list[str], values: list[Any]) -> None:
    """Append name fuzzy + oracle full-text search clauses for q."""
    n1 = len(values) + 1
    values.append(q)
    n2 = len(values) + 1
    values.append(q)
    clauses.append(
        f"(name % ${n1} OR to_tsvector('english', COALESCE(oracle_text, '')) "
        f"@@ plainto_tsquery('english', ${n2}))"
    )


def _build_where_clauses(params: CardSearchParams) -> tuple[list[str], list[Any]]:
    """Build parameterized WHERE clauses from search params.

    Args:
        params: Validated search parameters.

    Returns:
        A tuple of (clause_strings, bound_values).
    """
    clauses: list[str] = []
    values: list[Any] = []

    if params.q:
        _add_text_search(params.q, clauses, values)

    if params.color_identity is not None:
        n = len(values) + 1
        values.append([c.upper() for c in params.color_identity])
        clauses.append(f"color_identity <@ ${n}::text[]")

    if params.type is not None:
        n = len(values) + 1
        values.append(params.type)
        clauses.append(f"type_line ILIKE '%' || ${n} || '%'")

    if params.cmc_min is not None:
        n = len(values) + 1
        values.append(params.cmc_min)
        clauses.append(f"cmc >= ${n}")

    if params.cmc_max is not None:
        n = len(values) + 1
        values.append(params.cmc_max)
        clauses.append(f"cmc <= ${n}")

    if params.keywords is not None:
        kw_list = [k.strip() for k in params.keywords.split(",") if k.strip()]
        n = len(values) + 1
        values.append(kw_list)
        clauses.append(f"keywords && ${n}::text[]")

    if params.commander_legal:
        clauses.append("legalities->>'commander' = 'legal'")

    return clauses, values


async def search_cards(
    pool: asyncpg.Pool, params: CardSearchParams
) -> tuple[list[CardResponse], int]:
    """Search cards with optional filters and pagination.

    Args:
        pool: asyncpg connection pool.
        params: Search parameters including filters and pagination.

    Returns:
        A tuple of (matching cards, total count).
    """
    clauses, values = _build_where_clauses(params)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    order = "ORDER BY edhrec_rank ASC NULLS LAST"
    if params.q:
        # Rank name similarity first
        idx = 1  # q was the first value added
        order = f"ORDER BY similarity(name, ${idx}) DESC, edhrec_rank ASC NULLS LAST"

    limit_idx = len(values) + 1
    offset_idx = len(values) + 2

    query = f"SELECT * FROM cards {where} {order} LIMIT ${limit_idx} OFFSET ${offset_idx}"
    count_query = f"SELECT count(*) FROM cards {where}"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *values, params.limit, params.offset)
        total: int = await conn.fetchval(count_query, *values)

    return [_row_to_card(r) for r in rows], total


async def get_card_by_scryfall_id(pool: asyncpg.Pool, scryfall_id: UUID) -> CardResponse | None:
    """Fetch a single card by its Scryfall ID.

    Args:
        pool: asyncpg connection pool.
        scryfall_id: Scryfall UUID for the card.

    Returns:
        CardResponse if found, None otherwise.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cards WHERE scryfall_id = $1", scryfall_id)
    return _row_to_card(row) if row else None


async def get_card_by_id(pool: asyncpg.Pool, card_id: UUID) -> CardResponse | None:
    """Fetch a single card by its internal UUID.

    Args:
        pool: asyncpg connection pool.
        card_id: Internal UUID for the card.

    Returns:
        CardResponse if found, None otherwise.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cards WHERE id = $1", card_id)
    return _row_to_card(row) if row else None
