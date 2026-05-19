"""Deck CRUD service with color identity validation."""

import asyncio
import json
import logging
from uuid import UUID

import asyncpg

from mtg_helper.models.decks import (
    CommanderCardSummary,
    DeckCardAdd,
    DeckCardItem,
    DeckCardResponse,
    DeckCreate,
    DeckDetailResponse,
    DeckResponse,
    DeckSummary,
    DeckUpdate,
)
from mtg_helper.services import collection_service
from mtg_helper.services.retrieval_service import card_qualifying_stages

_log = logging.getLogger(__name__)

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
        owner_email=row["owner_email"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stage_targets=_parse_stage_targets(row["stage_targets"]),
        suggestion_collection_ids=list(row["suggestion_collection_ids"] or []),
        max_price_cents=row["max_price_cents"],
        min_price_cents=row["min_price_cents"],
        archetype_tags=list(row["archetype_tags"] or []),
    )


def _row_to_deck_card_item(row: asyncpg.Record) -> DeckCardItem:
    tags = list(row["tags"] or []) if "tags" in row.keys() else []
    categories = list(row["categories"] or [])
    stages = card_qualifying_stages(tags, row["type_line"])
    for cat in categories:
        if cat not in stages:
            stages.append(cat)
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
        categories=categories,
        added_by=row["added_by"],
        ai_reasoning=row["ai_reasoning"],
        qualifying_stages=stages,
        tags=tags,
        price_eur_cents=row["price_eur_cents"] if "price_eur_cents" in row.keys() else None,
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _assert_owner(conn: asyncpg.Connection, deck_id: UUID, email: str) -> None:
    """Raise DeckNotFoundError if the deck doesn't exist or isn't owned by the email.

    Uses the same 404 for missing and cross-account hits so existence does not
    leak across users. Comparison is case-insensitive.
    """
    row = await conn.fetchrow(
        "SELECT lower(owner_email) AS owner_email FROM decks WHERE id = $1", deck_id
    )
    if row is None or row["owner_email"] != _normalize_email(email):
        raise DeckNotFoundError(f"Deck {deck_id} not found")


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


async def create_deck(pool: asyncpg.Pool, data: DeckCreate, email: str) -> DeckResponse:
    """Create a new deck owned by the given email.

    Args:
        pool: asyncpg connection pool.
        data: Deck creation parameters.
        email: The authenticated account's email; stored as ``owner_email``.

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
            INSERT INTO decks (name, commander_id, partner_id, description, bracket, owner_email,
                               stage_targets, suggestion_collection_ids, max_price_cents,
                               min_price_cents, archetype_tags)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
            """,
            data.name,
            commander_id,
            partner_id,
            data.description,
            data.bracket,
            _normalize_email(email),
            json.dumps(data.stage_targets or {}),
            list(data.suggestion_collection_ids),
            data.max_price_cents,
            data.min_price_cents,
            list(data.archetype_tags),
        )
    deck = _row_to_deck(row)
    asyncio.create_task(_safe_edhrec_refresh(pool, deck.commander_id))
    asyncio.create_task(_safe_moxfield_refresh(pool, deck.commander_id))
    return deck


async def _safe_edhrec_refresh(pool: asyncpg.Pool, commander_id: UUID) -> None:
    """Pre-warm the EDHREC cache for a freshly created deck's commander.

    Errors are logged and swallowed so deck creation never fails because of an
    EDHREC outage or slug miss.
    """
    from mtg_helper.services import edhrec_service

    try:
        await edhrec_service.get_or_refresh(pool, commander_id)
    except Exception:
        _log.exception("Background EDHREC refresh failed for commander %s", commander_id)


async def _safe_moxfield_refresh(pool: asyncpg.Pool, commander_id: UUID) -> None:
    """Pre-warm the Moxfield top-decks cache for a freshly created deck's commander."""
    from mtg_helper.services import moxfield_recs_service

    try:
        await moxfield_recs_service.get_or_refresh(pool, commander_id)
    except Exception:
        _log.exception("Background Moxfield refresh failed for commander %s", commander_id)


async def list_decks(
    pool: asyncpg.Pool, email: str, limit: int = 20, offset: int = 0
) -> tuple[list[DeckSummary], int]:
    """List the given email's decks with commander info and card count.

    Args:
        pool: asyncpg connection pool.
        email: The authenticated account's email; restricts results.
        limit: Max results to return.
        offset: Pagination offset.

    Returns:
        Tuple of (deck summaries, total count).
    """
    normalized = _normalize_email(email)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                d.id, d.name, d.bracket, d.stage, d.created_at, d.updated_at,
                c.name AS commander_name, c.image_uri AS commander_image,
                c.color_identity AS commander_color_identity,
                (SELECT COALESCE(SUM(quantity), 0)
                   FROM deck_cards
                  WHERE deck_id = d.id)::int AS card_count
            FROM decks d
            JOIN cards c ON d.commander_id = c.id
            WHERE lower(d.owner_email) = $1
            ORDER BY d.updated_at DESC
            LIMIT $2 OFFSET $3
            """,
            normalized,
            limit,
            offset,
        )
        total: int = await conn.fetchval(
            "SELECT count(*) FROM decks WHERE lower(owner_email) = $1", normalized
        )

    summaries = [
        DeckSummary(
            id=r["id"],
            name=r["name"],
            commander_name=r["commander_name"],
            commander_image=r["commander_image"],
            commander_color_identity=list(r["commander_color_identity"] or []),
            bracket=r["bracket"],
            stage=r["stage"],
            card_count=r["card_count"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return summaries, total


async def get_deck(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str | None = None,
    account_id: UUID | None = None,
) -> DeckDetailResponse | None:
    """Fetch a deck with all its cards.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        email: When provided, the deck must be owned by this email or the
            call returns None (treated as 404 by callers).
        account_id: When provided, each card's ``owned_in`` is populated with
            the caller's collections containing that card. Omit when ownership
            info isn't needed (internal callers, exports).

    Returns:
        DeckDetailResponse or None if not found / not owned.
    """
    async with pool.acquire() as conn:
        deck_row = await conn.fetchrow("SELECT * FROM decks WHERE id = $1", deck_id)
        if deck_row is None:
            return None
        if email is not None:
            owner = deck_row["owner_email"]
            if owner is None or owner.lower() != _normalize_email(email):
                return None
        card_rows = await conn.fetch("SELECT * FROM deck_detail_view WHERE deck_id = $1", deck_id)
        commander_identity = await _get_color_identity(conn, deck_row["commander_id"])
        commander_card = await _fetch_commander_summary(conn, deck_row["commander_id"])
        partner_card: CommanderCardSummary | None = None
        if deck_row["partner_id"]:
            partner_identity = await _get_color_identity(conn, deck_row["partner_id"])
            commander_identity = sorted(set(commander_identity) | set(partner_identity))
            partner_card = await _fetch_commander_summary(conn, deck_row["partner_id"])

    cards = [_row_to_deck_card_item(r) for r in card_rows]
    if account_id is not None and cards:
        ownership_map = await collection_service.build_ownership_map(
            pool, account_id, [c.scryfall_id for c in cards]
        )
        for card in cards:
            card.owned_in = ownership_map.get(card.scryfall_id, [])

    return DeckDetailResponse(
        id=deck_row["id"],
        name=deck_row["name"],
        description=deck_row["description"],
        bracket=deck_row["bracket"],
        stage=deck_row["stage"],
        commander_id=deck_row["commander_id"],
        partner_id=deck_row["partner_id"],
        commander_color_identity=commander_identity,
        commander_card=commander_card,
        partner_card=partner_card,
        owner_email=deck_row["owner_email"],
        created_at=deck_row["created_at"],
        updated_at=deck_row["updated_at"],
        stage_targets=_parse_stage_targets(deck_row["stage_targets"]),
        suggestion_collection_ids=list(deck_row["suggestion_collection_ids"] or []),
        max_price_cents=deck_row["max_price_cents"],
        min_price_cents=deck_row["min_price_cents"],
        archetype_tags=list(deck_row["archetype_tags"] or []),
        cards=cards,
    )


async def _fetch_commander_summary(
    conn: asyncpg.Connection, card_id: UUID
) -> CommanderCardSummary | None:
    """Load minimal card fields for the deck detail commander preview."""
    row = await conn.fetchrow(
        "SELECT id, name, mana_cost, type_line, oracle_text, image_uri, color_identity "
        "FROM cards WHERE id = $1",
        card_id,
    )
    if row is None:
        return None
    return CommanderCardSummary(
        id=row["id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        image_uri=row["image_uri"],
        color_identity=list(row["color_identity"] or []),
    )


async def update_deck(
    pool: asyncpg.Pool,
    deck_id: UUID,
    data: DeckUpdate,
    email: str | None = None,
) -> DeckResponse | None:
    """Update deck metadata. Only provided fields are changed.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        data: Fields to update.
        email: When provided, scopes the update to decks owned by this
            email; cross-account updates return None (404 to the caller).

    Returns:
        Updated DeckResponse or None if not found / not owned.
    """
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return await _fetch_deck(pool, deck_id)

    # Serialize JSONB fields for asyncpg
    if "stage_targets" in updates:
        updates["stage_targets"] = json.dumps(updates["stage_targets"])

    # Sentinel: 0 clears the price cap back to NULL (positive check constraint).
    if updates.get("max_price_cents") == 0:
        updates["max_price_cents"] = None
    # Min floor: 0 is equivalent to no floor; store NULL for consistency.
    if updates.get("min_price_cents") == 0:
        updates["min_price_cents"] = None

    fields = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    values = list(updates.values())

    async with pool.acquire() as conn:
        if email is not None:
            owner_clause = f" AND lower(owner_email) = ${len(updates) + 2}"
            args: list[object] = [deck_id, *values, _normalize_email(email)]
        else:
            owner_clause = ""
            args = [deck_id, *values]
        row = await conn.fetchrow(
            f"UPDATE decks SET {fields}, updated_at = now() "
            f"WHERE id = $1{owner_clause} RETURNING *",
            *args,
        )
    return _row_to_deck(row) if row else None


async def _fetch_deck(pool: asyncpg.Pool, deck_id: UUID) -> DeckResponse | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM decks WHERE id = $1", deck_id)
    return _row_to_deck(row) if row else None


async def delete_deck(pool: asyncpg.Pool, deck_id: UUID, email: str | None = None) -> bool:
    """Delete a deck and all its cards (cascade).

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        email: When provided, only deletes if the deck is owned by this
            email. Returns False otherwise.

    Returns:
        True if deleted, False if not found / not owned.
    """
    async with pool.acquire() as conn:
        if email is None:
            result = await conn.execute("DELETE FROM decks WHERE id = $1", deck_id)
        else:
            result = await conn.execute(
                "DELETE FROM decks WHERE id = $1 AND lower(owner_email) = $2",
                deck_id,
                _normalize_email(email),
            )
    return result == "DELETE 1"


async def add_card_to_deck(
    pool: asyncpg.Pool,
    deck_id: UUID,
    data: DeckCardAdd,
    email: str | None = None,
) -> DeckCardResponse:
    """Add a card to a deck, enforcing color identity.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        data: Card to add with optional category and reasoning.
        email: When provided, the deck must be owned by this email.

    Returns:
        DeckCardResponse for the added card.

    Raises:
        DeckNotFoundError: If the deck does not exist.
        CardNotFoundError: If the card is not in the local DB.
        ColorIdentityError: If the card violates the commander's color identity.
    """
    async with pool.acquire() as conn:
        if email is not None:
            await _assert_owner(conn, deck_id, email)
        deck_row = await conn.fetchrow("SELECT commander_id FROM decks WHERE id = $1", deck_id)
        if deck_row is None:
            raise DeckNotFoundError(f"Deck {deck_id} not found")

        card_id = await _resolve_scryfall_id(conn, data.card_scryfall_id)
        commander_identity = await _get_color_identity(conn, deck_row["commander_id"])
        card_identity = await _get_color_identity(conn, card_id)
        _check_color_identity(card_identity, commander_identity)

        row = await conn.fetchrow(
            """
            INSERT INTO deck_cards (deck_id, card_id, quantity, categories, added_by, ai_reasoning)
            VALUES ($1, $2, $3, $4::text[], $5, $6)
            ON CONFLICT (deck_id, card_id)
            DO UPDATE SET
                quantity     = EXCLUDED.quantity,
                categories   = CASE
                                 WHEN cardinality(EXCLUDED.categories) > 0 THEN EXCLUDED.categories
                                 ELSE deck_cards.categories
                               END,
                ai_reasoning = COALESCE(EXCLUDED.ai_reasoning, deck_cards.ai_reasoning)
            RETURNING id, deck_id, card_id
            """,
            deck_id,
            card_id,
            data.quantity,
            list(data.categories),
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
        categories=list(data.categories),
        added_by=data.added_by,
    )


async def export_moxfield(
    pool: asyncpg.Pool, deck_id: UUID, email: str | None = None
) -> tuple[str, str] | None:
    """Export a deck in Moxfield-compatible text format.

    Produces a plain-text deck list with commanders tagged *CMDR* and cards
    grouped by category with blank-line separators.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        email: When provided, the deck must be owned by this email or
            the call returns None.

    Returns:
        Tuple of (deck_name, export_text) or None if deck not found / not owned.
    """
    deck = await get_deck(pool, deck_id, email)
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
        cat = card.categories[0] if card.categories else "other"
        by_category.setdefault(cat, []).append(f"{card.quantity} {card.name}")

    for category in sorted(by_category):
        lines.append("")
        lines.extend(by_category[category])

    return deck.name, "\n".join(lines)


async def export_buylist(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str | None,
    *,
    account_id: UUID | None,
) -> tuple[str, str] | None:
    """Export the cards the user still needs to buy in Cardmarket wants format.

    Diff: ``deck quantity - owned quantity`` per card (summed across all the
    user's collections). Plain text, one ``<missing_qty> <name>`` per line,
    sorted alphabetically. Cards fully owned are omitted.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        email: When provided, the deck must be owned by this email or None
            is returned.
        account_id: Account whose collections are diffed against the deck.

    Returns:
        Tuple of ``(deck_name, text)`` or None if the deck isn't found/owned.
        ``text`` is empty when nothing is missing.
    """
    deck = await get_deck(pool, deck_id, email)
    if deck is None:
        return None
    scryfall_ids = [c.scryfall_id for c in deck.cards]
    owned = await collection_service.owned_quantities(pool, account_id, scryfall_ids)
    missing: list[tuple[str, int]] = []
    for card in deck.cards:
        deficit = max(0, card.quantity - owned.get(card.scryfall_id, 0))
        if deficit > 0:
            missing.append((card.name, deficit))
    missing.sort(key=lambda x: x[0].lower())
    text = "\n".join(f"{qty} {name}" for name, qty in missing)
    return deck.name, text


async def update_deck_card_categories(
    pool: asyncpg.Pool,
    deck_id: UUID,
    scryfall_id: UUID,
    categories: list[str],
    email: str | None = None,
) -> bool:
    """Replace the category tag set on a deck card.

    A card can belong to multiple buckets (e.g. ramp + draw); pass an empty
    list to clear all manual categories. The card will still be auto-bucketed
    by its ``qualifying_stages`` derived from the cards table.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        scryfall_id: Scryfall ID of the card to recategorize.
        categories: New category list (replaces any existing categories).
        email: When provided, only succeeds if the deck is owned by this email.

    Returns:
        True if a row was updated, False if the card isn't in the deck or the
        caller doesn't own it.
    """
    async with pool.acquire() as conn:
        if email is not None:
            try:
                await _assert_owner(conn, deck_id, email)
            except DeckNotFoundError:
                return False
        card_row = await conn.fetchrow("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
        if card_row is None:
            return False
        result = await conn.execute(
            "UPDATE deck_cards SET categories = $3::text[] WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
            list(categories),
        )
    return result == "UPDATE 1"


async def remove_card_from_deck(
    pool: asyncpg.Pool,
    deck_id: UUID,
    scryfall_id: UUID,
    email: str | None = None,
) -> bool:
    """Remove a card from a deck by Scryfall ID.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        scryfall_id: Scryfall ID of the card to remove.
        email: When provided, only succeeds if the deck is owned by this
            email.

    Returns:
        True if removed, False if not found / not owned.
    """
    async with pool.acquire() as conn:
        if email is not None:
            try:
                await _assert_owner(conn, deck_id, email)
            except DeckNotFoundError:
                return False
        card_row = await conn.fetchrow("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
        if card_row is None:
            return False
        result = await conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
        )
    return result == "DELETE 1"
