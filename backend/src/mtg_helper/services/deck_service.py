"""Deck CRUD service with color identity validation."""

import json
from uuid import UUID

import asyncpg

from mtg_helper.models.decks import (
    DeckCardAdd,
    DeckCardItem,
    DeckCardResponse,
    DeckCreate,
    DeckDetailResponse,
    DeckResponse,
    DeckSummary,
    DeckUpdate,
)

# Ordered list of build stages. "created" is the initial state before any stage.
STAGES: list[str] = ["ramp", "interaction", "draw", "theme", "utility", "lands", "complete"]


def next_stage(current: str) -> str | None:
    """Return the next build stage after the given one.

    Args:
        current: Current deck stage (e.g. "created", "theme").

    Returns:
        Next stage name, or None if already complete.
    """
    if current == "created":
        return STAGES[0]
    if current == "complete" or current not in STAGES:
        return None
    idx = STAGES.index(current)
    return STAGES[idx + 1] if idx + 1 < len(STAGES) else None


def stage_number(stage: str) -> int:
    """Return the 1-indexed position of a build stage.

    Args:
        stage: Stage name. "created" returns 0; unknown stages return 0.

    Returns:
        Stage number (1-indexed) or 0 if not a recognized active stage.
    """
    if stage in STAGES:
        return STAGES.index(stage) + 1
    return 0


class ColorIdentityError(ValueError):
    """Raised when a card violates the commander's color identity."""


class CardNotFoundError(ValueError):
    """Raised when a referenced card does not exist in the local DB."""


class DeckNotFoundError(ValueError):
    """Raised when a deck does not exist."""


def _parse_stage_targets(raw: object) -> dict[str, int]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _row_to_deck(row: asyncpg.Record) -> DeckResponse:
    return DeckResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        bracket=row["bracket"],
        stage=row["stage"],
        commander_id=row["commander_id"],
        partner_id=row["partner_id"],
        owner_id=row["owner_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stage_targets=_parse_stage_targets(row["stage_targets"]),
        collection_mode=row["collection_mode"],
        collection_id=row["collection_id"],
        collection_threshold=row["collection_threshold"],
    )


def _row_to_deck_card_item(row: asyncpg.Record) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=row["deck_card_id"],
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        image_uri=row["image_uri"],
        rarity=row["rarity"],
        quantity=row["quantity"],
        category=row["category"],
        added_by=row["added_by"],
        ai_reasoning=row["ai_reasoning"],
    )


async def _resolve_scryfall_id(conn: asyncpg.Connection, scryfall_id: UUID) -> UUID:
    """Resolve a Scryfall ID to an internal card UUID.

    Raises:
        CardNotFoundError: If the card is not in the local DB.
    """
    row = await conn.fetchrow("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
    if row is None:
        raise CardNotFoundError(f"Card with Scryfall ID {scryfall_id} not found")
    return row["id"]


async def _get_color_identity(conn: asyncpg.Connection, card_id: UUID) -> list[str]:
    """Return the color identity of a card by internal ID."""
    row = await conn.fetchrow("SELECT color_identity FROM cards WHERE id = $1", card_id)
    return list(row["color_identity"] or []) if row else []


def _check_color_identity(card_identity: list[str], commander_identity: list[str]) -> None:
    """Verify a card's identity is within the commander's identity.

    Colorless cards (empty identity) are always legal.

    Raises:
        ColorIdentityError: If the card contains colors outside the commander's identity.
    """
    violations = set(card_identity) - set(commander_identity)
    if violations:
        raise ColorIdentityError(
            f"Card has color identity {card_identity} which is outside the "
            f"commander's identity {commander_identity}. "
            f"Offending colors: {sorted(violations)}"
        )


async def create_deck(pool: asyncpg.Pool, data: DeckCreate) -> DeckResponse:
    """Create a new deck.

    Args:
        pool: asyncpg connection pool.
        data: Deck creation parameters.

    Returns:
        The created DeckResponse.

    Raises:
        CardNotFoundError: If the commander or partner is not in the local DB.
    """
    async with pool.acquire() as conn:
        commander_id = await _resolve_scryfall_id(conn, data.commander_scryfall_id)
        partner_id = None
        if data.partner_scryfall_id:
            partner_id = await _resolve_scryfall_id(conn, data.partner_scryfall_id)

        row = await conn.fetchrow(
            """
            INSERT INTO decks (name, commander_id, partner_id, description, bracket, owner_id,
                               stage_targets, collection_mode, collection_id, collection_threshold)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            data.name,
            commander_id,
            partner_id,
            data.description,
            data.bracket,
            data.owner_id,
            json.dumps(data.stage_targets or {}),
            data.collection_mode,
            data.collection_id,
            data.collection_threshold,
        )
    return _row_to_deck(row)


async def list_decks(
    pool: asyncpg.Pool, limit: int = 20, offset: int = 0
) -> tuple[list[DeckSummary], int]:
    """List all decks with commander info and card count.

    Args:
        pool: asyncpg connection pool.
        limit: Max results to return.
        offset: Pagination offset.

    Returns:
        Tuple of (deck summaries, total count).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                d.id, d.name, d.bracket, d.stage, d.created_at, d.updated_at,
                c.name AS commander_name, c.image_uri AS commander_image,
                (SELECT count(*) FROM deck_cards WHERE deck_id = d.id)::int AS card_count
            FROM decks d
            JOIN cards c ON d.commander_id = c.id
            ORDER BY d.updated_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        total: int = await conn.fetchval("SELECT count(*) FROM decks")

    summaries = [
        DeckSummary(
            id=r["id"],
            name=r["name"],
            commander_name=r["commander_name"],
            commander_image=r["commander_image"],
            bracket=r["bracket"],
            stage=r["stage"],
            card_count=r["card_count"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return summaries, total


async def get_deck(pool: asyncpg.Pool, deck_id: UUID) -> DeckDetailResponse | None:
    """Fetch a deck with all its cards.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        DeckDetailResponse or None if not found.
    """
    async with pool.acquire() as conn:
        deck_row = await conn.fetchrow("SELECT * FROM decks WHERE id = $1", deck_id)
        if deck_row is None:
            return None
        card_rows = await conn.fetch("SELECT * FROM deck_detail_view WHERE deck_id = $1", deck_id)

    return DeckDetailResponse(
        id=deck_row["id"],
        name=deck_row["name"],
        description=deck_row["description"],
        bracket=deck_row["bracket"],
        stage=deck_row["stage"],
        commander_id=deck_row["commander_id"],
        partner_id=deck_row["partner_id"],
        owner_id=deck_row["owner_id"],
        created_at=deck_row["created_at"],
        updated_at=deck_row["updated_at"],
        stage_targets=_parse_stage_targets(deck_row["stage_targets"]),
        collection_mode=deck_row["collection_mode"],
        collection_id=deck_row["collection_id"],
        collection_threshold=deck_row["collection_threshold"],
        cards=[_row_to_deck_card_item(r) for r in card_rows],
    )


async def update_deck(pool: asyncpg.Pool, deck_id: UUID, data: DeckUpdate) -> DeckResponse | None:
    """Update deck metadata. Only provided fields are changed.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        data: Fields to update.

    Returns:
        Updated DeckResponse or None if not found.
    """
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return await _fetch_deck(pool, deck_id)

    # Serialize JSONB fields for asyncpg
    if "stage_targets" in updates:
        updates["stage_targets"] = json.dumps(updates["stage_targets"])

    fields = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    values = list(updates.values())

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE decks SET {fields}, updated_at = now() WHERE id = $1 RETURNING *",
            deck_id,
            *values,
        )
    return _row_to_deck(row) if row else None


async def _fetch_deck(pool: asyncpg.Pool, deck_id: UUID) -> DeckResponse | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM decks WHERE id = $1", deck_id)
    return _row_to_deck(row) if row else None


async def delete_deck(pool: asyncpg.Pool, deck_id: UUID) -> bool:
    """Delete a deck and all its cards (cascade).

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        True if deleted, False if not found.
    """
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM decks WHERE id = $1", deck_id)
    return result == "DELETE 1"


async def add_card_to_deck(
    pool: asyncpg.Pool, deck_id: UUID, data: DeckCardAdd
) -> DeckCardResponse:
    """Add a card to a deck, enforcing color identity.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        data: Card to add with optional category and reasoning.

    Returns:
        DeckCardResponse for the added card.

    Raises:
        DeckNotFoundError: If the deck does not exist.
        CardNotFoundError: If the card is not in the local DB.
        ColorIdentityError: If the card violates the commander's color identity.
    """
    async with pool.acquire() as conn:
        deck_row = await conn.fetchrow("SELECT commander_id FROM decks WHERE id = $1", deck_id)
        if deck_row is None:
            raise DeckNotFoundError(f"Deck {deck_id} not found")

        card_id = await _resolve_scryfall_id(conn, data.card_scryfall_id)
        commander_identity = await _get_color_identity(conn, deck_row["commander_id"])
        card_identity = await _get_color_identity(conn, card_id)
        _check_color_identity(card_identity, commander_identity)

        row = await conn.fetchrow(
            """
            INSERT INTO deck_cards (deck_id, card_id, quantity, category, added_by, ai_reasoning)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (deck_id, card_id)
            DO UPDATE SET
                quantity     = EXCLUDED.quantity,
                category     = COALESCE(EXCLUDED.category, deck_cards.category),
                ai_reasoning = COALESCE(EXCLUDED.ai_reasoning, deck_cards.ai_reasoning)
            RETURNING id, deck_id, card_id
            """,
            deck_id,
            card_id,
            data.quantity,
            data.category,
            data.added_by,
            data.ai_reasoning,
        )

        card_row = await conn.fetchrow("SELECT scryfall_id, name FROM cards WHERE id = $1", card_id)

    return DeckCardResponse(
        deck_card_id=row["id"],
        deck_id=row["deck_id"],
        card_id=row["card_id"],
        scryfall_id=card_row["scryfall_id"],
        name=card_row["name"],
        quantity=data.quantity,
        category=data.category,
        added_by=data.added_by,
    )


async def export_moxfield(pool: asyncpg.Pool, deck_id: UUID) -> tuple[str, str] | None:
    """Export a deck in Moxfield-compatible text format.

    Produces a plain-text deck list with commanders tagged *CMDR* and cards
    grouped by category with blank-line separators.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        Tuple of (deck_name, export_text) or None if deck not found.
    """
    deck = await get_deck(pool, deck_id)
    if deck is None:
        return None

    async with pool.acquire() as conn:
        commander_row = await conn.fetchrow(
            "SELECT name FROM cards WHERE id = $1", deck.commander_id
        )
        partner_row = None
        if deck.partner_id:
            partner_row = await conn.fetchrow(
                "SELECT name FROM cards WHERE id = $1", deck.partner_id
            )

    lines: list[str] = []
    lines.append(f"1 {commander_row['name']} *CMDR*")
    if partner_row:
        lines.append(f"1 {partner_row['name']} *CMDR*")

    by_category: dict[str, list[str]] = {}
    for card in deck.cards:
        cat = card.category or "other"
        by_category.setdefault(cat, []).append(f"{card.quantity} {card.name}")

    for category in sorted(by_category):
        lines.append("")
        lines.extend(by_category[category])

    return deck.name, "\n".join(lines)


async def remove_card_from_deck(pool: asyncpg.Pool, deck_id: UUID, scryfall_id: UUID) -> bool:
    """Remove a card from a deck by Scryfall ID.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        scryfall_id: Scryfall ID of the card to remove.

    Returns:
        True if removed, False if not found.
    """
    async with pool.acquire() as conn:
        card_row = await conn.fetchrow("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
        if card_row is None:
            return False
        result = await conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
        )
    return result == "DELETE 1"
