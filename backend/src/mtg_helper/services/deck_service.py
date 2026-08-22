"""Deck CRUD service with color identity validation."""

import asyncio
import json
import logging
from collections.abc import Mapping
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
    PlannedDeckChange,
)
from mtg_helper.services import (
    card_identity_service,
    collection_service,
    deck_fit_service,
    mana_curve_service,
    planned_change_service,
    preference_service,
)
from mtg_helper.services.builder_roles import derive_builder_roles

_log = logging.getLogger(__name__)

# Ordered list of build stages. "created" is the initial state before any stage.
STAGES: list[str] = ["theme", "ramp", "draw", "interaction", "lands", "complete"]


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
    if isinstance(raw, Mapping):
        return dict(raw)
    raise TypeError(f"Stage targets must be a JSON object, got {type(raw).__name__}")


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
        archetype_tags=list(row["archetype_tags"] or []),
    )


def _parse_power(raw: str | None) -> int | None:
    """Scryfall ``power`` is TEXT — may be ``"*"``, ``"X"``, ``"1+*"``, etc. Only
    purely numeric strings are honored; everything else returns ``None``.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _row_to_deck_card_item(row: asyncpg.Record) -> DeckCardItem:
    hub_tags = list(row["hub_tags"] or []) if "hub_tags" in row.keys() else []
    tags = hub_tags or (list(row["tags"] or []) if "tags" in row.keys() else [])
    mtgjson_tags = list(row["mtgjson_tags"] or []) if "mtgjson_tags" in row.keys() else []
    categories = list(row["categories"] or [])
    builder_roles = derive_builder_roles(tags, mtgjson_tags, row["type_line"])
    stages = list(builder_roles.roles)
    for cat in categories:
        if cat not in stages:
            stages.append(cat)
    power = _parse_power(row["power"]) if "power" in row.keys() else None
    return DeckCardItem(
        deck_card_id=row["deck_card_id"],
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"] if "oracle_id" in row.keys() else None,
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
        role_reasons=builder_roles.reasons,
        tags=tags,
        hub_tags=tags,
        mtgjson_tags=mtgjson_tags,
        power=power,
        price_eur_cents=row["price_eur_cents"] if "price_eur_cents" in row.keys() else None,
        game_changer=bool(row["game_changer"]) if "game_changer" in row.keys() else False,
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _planned_state(
    pool: asyncpg.Pool,
    deck_id: UUID,
    cards: list[DeckCardItem],
    partner_id: UUID | None,
    email: str | None,
    *,
    account_id: UUID | None,
) -> tuple[list[PlannedDeckChange], int, int]:
    physical = sum(card.quantity for card in cards) + 1 + (1 if partner_id else 0)
    if account_id is None or email is None:
        return [], physical, physical
    plans = await planned_change_service.list_plans(pool, deck_id, email, account_id)
    cuts = {plan.card_id: plan.quantity for plan in plans if plan.direction == "cut"}
    for card in cards:
        card.planned_cut_quantity = cuts.get(card.card_id, 0)
    projected = physical + sum(
        plan.quantity if plan.direction == "addition" else -plan.quantity for plan in plans
    )
    return plans, physical, projected


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
    row = await card_identity_service.canonical_card_by_scryfall(conn, scryfall_id)
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
        archetype_tags = list(data.archetype_tags)
        if not archetype_tags:
            archetype_tags = await _commander_seed_tags(conn, commander_id)

        row = await conn.fetchrow(
            """
            INSERT INTO decks (name, commander_id, partner_id, description, bracket, owner_email,
                               stage_targets, suggestion_collection_ids, archetype_tags)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
            archetype_tags,
        )
    deck = _row_to_deck(row)
    asyncio.create_task(_safe_moxfield_refresh(pool, deck.commander_id))
    return deck


async def _commander_seed_tags(conn: asyncpg.Connection, commander_id: UUID) -> list[str]:
    """Use the commander's Moxfield hub tags as initial deck identity when available."""
    row = await conn.fetchrow(
        """
        SELECT hub_tags, tags
        FROM cards
        WHERE id = $1
        """,
        commander_id,
    )
    if row is None:
        return []
    return list(row["hub_tags"] or row["tags"] or [])


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
                -- +1 for the commander (INNER JOIN above guarantees one).
                (SELECT COALESCE(SUM(quantity), 0)
                   FROM deck_cards
                  WHERE deck_id = d.id)::int + 1 AS card_count
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
    protected_names: set[str] = set()
    if account_id is not None and cards:
        ownership_map = await collection_service.build_ownership_map(
            pool, account_id, [c.scryfall_id for c in cards]
        )
        for card in cards:
            card.owned_in = ownership_map.get(card.scryfall_id, [])
        preferences = await preference_service.get_preferences_for_prompt(pool, account_id)
        protected_names.update(preferences["pet_cards"])

    mana_curve = await mana_curve_service.deck_curve(pool, deck_row["commander_id"], cards)
    planned_changes, physical_card_count, planned_card_count = await _planned_state(
        pool,
        deck_id,
        cards,
        deck_row["partner_id"],
        email,
        account_id=account_id,
    )

    deck = DeckDetailResponse(
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
        archetype_tags=list(deck_row["archetype_tags"] or []),
        mana_curve=mana_curve,
        cards=cards,
        physical_card_count=physical_card_count,
        planned_card_count=planned_card_count,
        planned_changes=planned_changes,
    )
    try:
        await deck_fit_service.enrich_deck_fit(
            pool,
            deck,
            protected_names=protected_names,
        )
    except Exception:  # noqa: BLE001 - scoring must not make deck detail unavailable
        _log.exception("Deck fit scoring failed for deck %s", deck_id)
    return deck


async def _fetch_commander_summary(
    conn: asyncpg.Connection, card_id: UUID
) -> CommanderCardSummary | None:
    """Load minimal card fields for the deck detail commander preview."""
    row = await conn.fetchrow(
        "SELECT id, name, mana_cost, cmc, type_line, oracle_text, image_uri, "
        "color_identity, power, tags, hub_tags, mtgjson_tags, game_changer "
        "FROM cards WHERE id = $1",
        card_id,
    )
    if row is None:
        return None
    hub_tags = list(row["hub_tags"] or row["tags"] or [])
    mtgjson_tags = list(row["mtgjson_tags"] or [])
    return CommanderCardSummary(
        id=row["id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        image_uri=row["image_uri"],
        color_identity=list(row["color_identity"] or []),
        power=_parse_power(row["power"]),
        tags=hub_tags,
        hub_tags=hub_tags,
        mtgjson_tags=mtgjson_tags,
        game_changer=bool(row["game_changer"]),
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

    fields = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    values = list(updates.values())

    async with pool.acquire() as conn:
        prev_stage_row = await conn.fetchrow("SELECT stage FROM decks WHERE id = $1", deck_id)
        prev_stage = prev_stage_row["stage"] if prev_stage_row else None
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
    if row is None:
        return None
    new_stage = row["stage"]
    if prev_stage != new_stage and new_stage in STAGES:
        # Auto-snapshot on stage advance. Best-effort; failures are logged inside the helper.
        from mtg_helper.services import snapshot_service

        await snapshot_service.create_auto_snapshot(pool, deck_id, new_stage=new_stage)
    return _row_to_deck(row)


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
        card = await card_identity_service.canonical_card_by_id(conn, card_id)
        if card is None:
            raise CardNotFoundError(f"Card with Scryfall ID {data.card_scryfall_id} not found")
        copy_limit = card_identity_service.commander_copy_limit(
            card["type_line"], card["oracle_text"]
        )
        quantity = card_identity_service.clamp_quantity(data.quantity, copy_limit)
        commander_identity = await _get_color_identity(conn, deck_row["commander_id"])
        card_identity = await _get_color_identity(conn, card_id)
        _check_color_identity(card_identity, commander_identity)

        old_quantity = await conn.fetchval(
            "SELECT quantity FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_id,
        )
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
            quantity,
            list(data.categories),
            data.added_by,
            data.ai_reasoning,
        )

        card_row = await conn.fetchrow(
            "SELECT scryfall_id, oracle_id, name FROM cards WHERE id = $1", card_id
        )

    added_quantity = max(0, quantity - int(old_quantity or 0))
    if added_quantity:
        await planned_change_service.consume_immediate_plan(
            pool, deck_id, card_id, "addition", added_quantity
        )
    return DeckCardResponse(
        deck_card_id=row["id"],
        deck_id=row["deck_id"],
        card_id=row["card_id"],
        scryfall_id=card_row["scryfall_id"],
        oracle_id=card_row["oracle_id"],
        name=card_row["name"],
        quantity=quantity,
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
        card_row = await card_identity_service.canonical_card_by_scryfall(conn, scryfall_id)
        if card_row is None:
            return False
        result = await conn.execute(
            "UPDATE deck_cards SET categories = $3::text[] WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
            list(categories),
        )
    return result == "UPDATE 1"


async def update_deck_card_quantity(
    pool: asyncpg.Pool,
    deck_id: UUID,
    scryfall_id: UUID,
    quantity: int,
    email: str | None = None,
) -> bool:
    """Set the quantity for a card already in the deck.

    Quantity must be >= 1. To remove the card use ``remove_card_from_deck``.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        scryfall_id: Scryfall ID of the card.
        quantity: New quantity (>= 1).
        email: When provided, only succeeds if the deck is owned by this email.

    Returns:
        True when a row was updated, False if the card isn't in the deck.
    """
    if quantity < 1:
        return False
    async with pool.acquire() as conn:
        if email is not None:
            try:
                await _assert_owner(conn, deck_id, email)
            except DeckNotFoundError:
                return False
        card_row = await card_identity_service.canonical_card_by_scryfall(conn, scryfall_id)
        if card_row is None:
            return False
        copy_limit = card_identity_service.commander_copy_limit(
            card_row["type_line"], card_row["oracle_text"]
        )
        quantity = card_identity_service.clamp_quantity(quantity, copy_limit)
        if quantity < 1:
            return False
        old_quantity = await conn.fetchval(
            "SELECT quantity FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
        )
        result = await conn.execute(
            "UPDATE deck_cards SET quantity = $3 WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
            quantity,
        )
    if result != "UPDATE 1":
        return False
    await _reconcile_quantity_plan(
        pool,
        deck_id,
        card_row["id"],
        quantity,
        int(old_quantity or 0),
    )
    return True


async def _reconcile_quantity_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    card_id: UUID,
    quantity: int,
    previous: int,
) -> None:
    if quantity > previous:
        await planned_change_service.consume_immediate_plan(
            pool, deck_id, card_id, "addition", quantity - previous
        )
    elif quantity < previous:
        await planned_change_service.consume_immediate_plan(
            pool, deck_id, card_id, "cut", previous - quantity
        )
    await planned_change_service.clamp_cut_plan(pool, deck_id, card_id, quantity)


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
        card_row = await card_identity_service.canonical_card_by_scryfall(conn, scryfall_id)
        if card_row is None:
            return False
        result = await conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            deck_id,
            card_row["id"],
        )
    if result != "DELETE 1":
        return False
    await planned_change_service.consume_immediate_plan(pool, deck_id, card_row["id"], "cut")
    return True
