"""Planned main-deck changes kept separate from physical deck composition."""

from typing import Literal
from uuid import UUID

import asyncpg

from mtg_helper.models.decks import (
    PlannedDeckChange,
    PlannedDeckChangeCreate,
)
from mtg_helper.services import card_identity_service, collection_service


class PlannedChangeError(ValueError):
    """Base error for planned-change operations."""


class PlanNotFoundError(PlannedChangeError):
    """Raised when a pending change does not exist or is not owned."""


class InvalidPlanError(PlannedChangeError):
    """Raised when a requested plan contradicts physical deck state."""


class SelectedCollectionError(PlannedChangeError):
    """Raised when an optional collection cannot supply or receive a card."""


class InsufficientQuantityError(PlannedChangeError):
    """Raised when completion cannot move the requested quantity."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _owned_deck(
    conn: asyncpg.Connection,
    deck_id: UUID,
    email: str,
    *,
    lock: bool = False,
) -> asyncpg.Record:
    lock_sql = " FOR UPDATE" if lock else ""
    row = await conn.fetchrow(
        "SELECT id, commander_id, partner_id FROM decks "
        f"WHERE id = $1 AND lower(owner_email) = $2{lock_sql}",
        deck_id,
        _normalize_email(email),
    )
    if row is None:
        raise PlanNotFoundError(f"Deck {deck_id} not found")
    return row


async def _card_by_scryfall(conn: asyncpg.Connection, scryfall_id: UUID) -> asyncpg.Record:
    row = await card_identity_service.canonical_card_by_scryfall(conn, scryfall_id)
    if row is None:
        raise InvalidPlanError(f"Card {scryfall_id} not found")
    return row


async def _validate_main_deck_card(
    conn: asyncpg.Connection,
    deck: asyncpg.Record,
    card: asyncpg.Record,
    direction: Literal["addition", "cut"],
) -> int:
    if card["id"] in {deck["commander_id"], deck["partner_id"]}:
        raise InvalidPlanError("Commander and partner cards cannot be planned")
    physical = await conn.fetchval(
        "SELECT quantity FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
        deck["id"],
        card["id"],
    )
    physical_quantity = int(physical or 0)
    if direction == "addition":
        identities = await conn.fetch(
            "SELECT id, color_identity FROM cards WHERE id = ANY($1::uuid[])",
            [deck["commander_id"], deck["partner_id"]]
            if deck["partner_id"]
            else [deck["commander_id"]],
        )
        allowed = {color for row in identities for color in (row["color_identity"] or [])}
        card_identity = set(card["color_identity"] or [])
        if not card_identity.issubset(allowed):
            outside = ", ".join(sorted(card_identity - allowed))
            raise InvalidPlanError(f"{card['name']} is outside the deck color identity: {outside}")
    return physical_quantity


def _net_plan(
    existing_direction: str | None,
    existing_quantity: int,
    new_direction: Literal["addition", "cut"],
    new_quantity: int,
) -> tuple[Literal["addition", "cut"] | None, int]:
    if existing_direction is None or existing_direction == new_direction:
        return new_direction, existing_quantity + new_quantity
    if existing_quantity == new_quantity:
        return None, 0
    if existing_quantity > new_quantity:
        kept_direction: Literal["addition", "cut"] = (
            "addition" if existing_direction == "addition" else "cut"
        )
        return kept_direction, existing_quantity - new_quantity
    return new_direction, new_quantity - existing_quantity


async def create_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    data: PlannedDeckChangeCreate,
    email: str,
    account_id: UUID,
) -> PlannedDeckChange | None:
    """Create, increment, or offset a planned main-deck change."""
    async with pool.acquire() as conn, conn.transaction():
        deck = await _owned_deck(conn, deck_id, email, lock=True)
        card = await _card_by_scryfall(conn, data.card_scryfall_id)
        physical_quantity = await _validate_main_deck_card(conn, deck, card, data.direction)
        existing = await conn.fetchrow(
            "SELECT * FROM deck_card_plans WHERE deck_id = $1 AND card_id = $2 FOR UPDATE",
            deck_id,
            card["id"],
        )
        direction, quantity = _net_plan(
            existing["direction"] if existing else None,
            int(existing["quantity"]) if existing else 0,
            data.direction,
            data.quantity,
        )
        if direction == "addition":
            limit = card_identity_service.commander_copy_limit(
                card["type_line"], card["oracle_text"]
            )
            projected = card_identity_service.clamp_quantity(physical_quantity + quantity, limit)
            quantity = projected - physical_quantity
        if direction == "cut" and quantity > physical_quantity:
            raise InvalidPlanError("Planned cut exceeds the physical deck quantity")
        if direction is None or quantity == 0:
            if existing:
                await conn.execute("DELETE FROM deck_card_plans WHERE id = $1", existing["id"])
            return None
        categories = list(data.categories) if direction == "addition" else []
        collection_id = (
            existing["collection_id"] if existing and direction == data.direction else None
        )
        row = await conn.fetchrow(
            """
            INSERT INTO deck_card_plans (
                deck_id, card_id, direction, quantity, collection_id,
                categories, added_by, ai_reasoning
            ) VALUES ($1, $2, $3, $4, $5, $6::text[], $7, $8)
            ON CONFLICT (deck_id, card_id) DO UPDATE SET
                direction = EXCLUDED.direction,
                quantity = EXCLUDED.quantity,
                collection_id = EXCLUDED.collection_id,
                categories = CASE
                    WHEN cardinality(EXCLUDED.categories) > 0 THEN EXCLUDED.categories
                    ELSE deck_card_plans.categories
                END,
                added_by = EXCLUDED.added_by,
                ai_reasoning = COALESCE(EXCLUDED.ai_reasoning, deck_card_plans.ai_reasoning),
                updated_at = now()
            RETURNING id
            """,
            deck_id,
            card["id"],
            direction,
            quantity,
            collection_id,
            categories,
            data.added_by,
            data.ai_reasoning,
        )
    return await get_plan(pool, deck_id, row["id"], email, account_id)


def _row_to_plan(row: asyncpg.Record) -> PlannedDeckChange:
    physical = int(row["physical_quantity"] or 0)
    quantity = int(row["quantity"])
    projected = physical + quantity if row["direction"] == "addition" else physical - quantity
    return PlannedDeckChange(
        id=row["id"],
        deck_id=row["deck_id"],
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"],
        name=row["name"],
        image_uri=row["image_uri"],
        direction=row["direction"],
        quantity=quantity,
        collection_id=row["collection_id"],
        physical_quantity=physical,
        projected_quantity=projected,
        categories=list(row["categories"] or []),
        added_by=row["added_by"],
        ai_reasoning=row["ai_reasoning"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


_PLAN_SELECT = """
    SELECT p.*, c.scryfall_id, c.oracle_id, c.name, c.image_uri,
           COALESCE(dc.quantity, 0)::int AS physical_quantity
    FROM deck_card_plans p
    JOIN cards c ON c.id = p.card_id
    LEFT JOIN deck_cards dc ON dc.deck_id = p.deck_id AND dc.card_id = p.card_id
"""


async def _enrich_ownership(
    pool: asyncpg.Pool,
    plans: list[PlannedDeckChange],
    account_id: UUID,
) -> None:
    additions = [plan.scryfall_id for plan in plans if plan.direction == "addition"]
    ownership = await collection_service.build_ownership_map(pool, account_id, additions)
    for plan in plans:
        if plan.direction == "addition":
            plan.owned_in = ownership.get(plan.scryfall_id, [])


async def list_plans(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str,
    account_id: UUID,
) -> list[PlannedDeckChange]:
    """List a deck's pending changes without merging them into physical cards."""
    async with pool.acquire() as conn:
        await _owned_deck(conn, deck_id, email)
        rows = await conn.fetch(
            _PLAN_SELECT + " WHERE p.deck_id = $1 ORDER BY p.direction, p.created_at, c.name",
            deck_id,
        )
    plans = [_row_to_plan(row) for row in rows]
    await _enrich_ownership(pool, plans, account_id)
    return plans


async def export_shopping_list(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str,
    account_id: UUID,
    collection_ids: list[UUID],
) -> str:
    """Build a Cardmarket buy list using inventory from selected collections only."""
    selected_ids = list(dict.fromkeys(collection_ids))
    async with pool.acquire() as conn:
        await _owned_deck(conn, deck_id, email)
        if selected_ids:
            owned_count = await conn.fetchval(
                "SELECT count(*) FROM collections WHERE account_id = $1 AND id = ANY($2::uuid[])",
                account_id,
                selected_ids,
            )
            if int(owned_count or 0) != len(selected_ids):
                raise SelectedCollectionError("One or more selected collections were not found")
        rows = await conn.fetch(
            """
            WITH planned AS (
                SELECT COALESCE(c.oracle_id, c.id) AS oracle_key,
                       MIN(c.name) AS name,
                       SUM(p.quantity)::int AS planned_quantity
                FROM deck_card_plans p
                JOIN cards c ON c.id = p.card_id
                WHERE p.deck_id = $1 AND p.direction = 'addition'
                GROUP BY COALESCE(c.oracle_id, c.id)
            ),
            owned AS (
                SELECT COALESCE(c.oracle_id, c.id) AS oracle_key,
                       SUM(cc.quantity)::int AS owned_quantity
                FROM collection_cards cc
                JOIN cards c ON c.id = cc.card_id
                JOIN collections col ON col.id = cc.collection_id
                WHERE cc.collection_id = ANY($2::uuid[])
                  AND col.account_id = $3
                GROUP BY COALESCE(c.oracle_id, c.id)
            )
            SELECT planned.name,
                   (planned.planned_quantity - COALESCE(owned.owned_quantity, 0))::int
                       AS missing_quantity
            FROM planned
            LEFT JOIN owned USING (oracle_key)
            WHERE planned.planned_quantity - COALESCE(owned.owned_quantity, 0) > 0
            ORDER BY lower(planned.name), planned.name
            """,
            deck_id,
            selected_ids,
            account_id,
        )
    return "\n".join(f"{row['missing_quantity']} {row['name']}" for row in rows)


async def get_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    plan_id: UUID,
    email: str,
    account_id: UUID,
) -> PlannedDeckChange:
    """Return one owned plan enriched with current physical and ownership state."""
    async with pool.acquire() as conn:
        await _owned_deck(conn, deck_id, email)
        row = await conn.fetchrow(
            _PLAN_SELECT + " WHERE p.deck_id = $1 AND p.id = $2",
            deck_id,
            plan_id,
        )
    if row is None:
        raise PlanNotFoundError(f"Planned change {plan_id} not found")
    plan = _row_to_plan(row)
    await _enrich_ownership(pool, [plan], account_id)
    return plan


async def _validate_collection(
    conn: asyncpg.Connection,
    collection_id: UUID,
    account_id: UUID,
    card_id: UUID,
    direction: str,
) -> None:
    owned = await conn.fetchval(
        "SELECT 1 FROM collections WHERE id = $1 AND account_id = $2",
        collection_id,
        account_id,
    )
    if owned is None:
        raise SelectedCollectionError(f"Collection {collection_id} not found")
    if direction == "addition":
        available = await conn.fetchval(
            """
            SELECT 1
            FROM collection_cards cc
            JOIN cards owned_card ON owned_card.id = cc.card_id
            JOIN cards planned_card ON planned_card.id = $2
            WHERE cc.collection_id = $1
              AND COALESCE(owned_card.oracle_id, owned_card.id)
                  = COALESCE(planned_card.oracle_id, planned_card.id)
            LIMIT 1
            """,
            collection_id,
            card_id,
        )
        if available is None:
            raise SelectedCollectionError("Selected collection does not contain this card")


async def update_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    plan_id: UUID,
    email: str,
    account_id: UUID,
    *,
    quantity: int | None,
    collection_id: UUID | None,
    set_collection: bool,
) -> PlannedDeckChange:
    """Update pending quantity or the optional collection selection."""
    async with pool.acquire() as conn, conn.transaction():
        await _owned_deck(conn, deck_id, email, lock=True)
        plan = await conn.fetchrow(
            "SELECT * FROM deck_card_plans WHERE deck_id = $1 AND id = $2 FOR UPDATE",
            deck_id,
            plan_id,
        )
        if plan is None:
            raise PlanNotFoundError(f"Planned change {plan_id} not found")
        if quantity is not None and plan["direction"] == "cut":
            physical = await conn.fetchval(
                "SELECT quantity FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
                deck_id,
                plan["card_id"],
            )
            if quantity > int(physical or 0):
                raise InvalidPlanError("Planned cut exceeds the physical deck quantity")
        if set_collection and collection_id is not None:
            await _validate_collection(
                conn,
                collection_id,
                account_id,
                plan["card_id"],
                plan["direction"],
            )
        await conn.execute(
            """
            UPDATE deck_card_plans
            SET quantity = COALESCE($3, quantity),
                collection_id = CASE WHEN $4 THEN $5 ELSE collection_id END,
                updated_at = now()
            WHERE deck_id = $1 AND id = $2
            """,
            deck_id,
            plan_id,
            quantity,
            set_collection,
            collection_id,
        )
    return await get_plan(pool, deck_id, plan_id, email, account_id)


async def cancel_plan(pool: asyncpg.Pool, deck_id: UUID, plan_id: UUID, email: str) -> None:
    """Cancel a pending change without mutating deck or collection state."""
    async with pool.acquire() as conn, conn.transaction():
        await _owned_deck(conn, deck_id, email, lock=True)
        result = await conn.execute(
            "DELETE FROM deck_card_plans WHERE deck_id = $1 AND id = $2",
            deck_id,
            plan_id,
        )
        if result != "DELETE 1":
            raise PlanNotFoundError(f"Planned change {plan_id} not found")


async def _consume_collection_cards(
    conn: asyncpg.Connection,
    collection_id: UUID,
    planned_card_id: UUID,
    quantity: int,
) -> list[tuple[UUID, int]]:
    rows = await conn.fetch(
        """
        SELECT cc.collection_id, cc.card_id, cc.set_code, cc.collector_number,
               cc.foil, cc.quantity
        FROM collection_cards cc
        JOIN cards owned_card ON owned_card.id = cc.card_id
        JOIN cards planned_card ON planned_card.id = $2
        WHERE cc.collection_id = $1
          AND COALESCE(owned_card.oracle_id, owned_card.id)
              = COALESCE(planned_card.oracle_id, planned_card.id)
        ORDER BY (cc.card_id = $2) DESC, cc.set_code, cc.collector_number, cc.foil
        FOR UPDATE OF cc
        """,
        collection_id,
        planned_card_id,
    )
    if sum(int(row["quantity"]) for row in rows) < quantity:
        raise InsufficientQuantityError("Selected collection has insufficient quantity")
    remaining = quantity
    consumed: list[tuple[UUID, int]] = []
    for row in rows:
        if remaining == 0:
            break
        moved = min(remaining, int(row["quantity"]))
        if moved == int(row["quantity"]):
            await conn.execute(
                """
                DELETE FROM collection_cards
                WHERE collection_id = $1 AND card_id = $2 AND set_code = $3
                  AND collector_number = $4 AND foil = $5
                """,
                row["collection_id"],
                row["card_id"],
                row["set_code"],
                row["collector_number"],
                row["foil"],
            )
        else:
            await conn.execute(
                """
                UPDATE collection_cards SET quantity = quantity - $6, last_modified = now()
                WHERE collection_id = $1 AND card_id = $2 AND set_code = $3
                  AND collector_number = $4 AND foil = $5
                """,
                row["collection_id"],
                row["card_id"],
                row["set_code"],
                row["collector_number"],
                row["foil"],
                moved,
            )
        consumed.append((row["card_id"], moved))
        remaining -= moved
    return consumed


async def _add_physical_cards(
    conn: asyncpg.Connection,
    deck_id: UUID,
    cards: list[tuple[UUID, int]],
    plan: asyncpg.Record,
) -> None:
    for card_id, quantity in cards:
        await conn.execute(
            """
            INSERT INTO deck_cards (deck_id, card_id, quantity, categories, added_by, ai_reasoning)
            VALUES ($1, $2, $3, $4::text[], $5, $6)
            ON CONFLICT (deck_id, card_id) DO UPDATE SET
                quantity = deck_cards.quantity + EXCLUDED.quantity,
                categories = CASE
                    WHEN cardinality(EXCLUDED.categories) > 0 THEN EXCLUDED.categories
                    ELSE deck_cards.categories
                END,
                ai_reasoning = COALESCE(EXCLUDED.ai_reasoning, deck_cards.ai_reasoning)
            """,
            deck_id,
            card_id,
            quantity,
            list(plan["categories"] or []),
            plan["added_by"],
            plan["ai_reasoning"],
        )


async def _complete_addition(
    conn: asyncpg.Connection,
    plan: asyncpg.Record,
    quantity: int,
) -> None:
    cards = [(plan["card_id"], quantity)]
    if plan["collection_id"] is not None:
        cards = await _consume_collection_cards(
            conn,
            plan["collection_id"],
            plan["card_id"],
            quantity,
        )
    await _add_physical_cards(conn, plan["deck_id"], cards, plan)


async def _complete_cut(conn: asyncpg.Connection, plan: asyncpg.Record, quantity: int) -> None:
    deck_card = await conn.fetchrow(
        """
        SELECT quantity FROM deck_cards
        WHERE deck_id = $1 AND card_id = $2
        FOR UPDATE
        """,
        plan["deck_id"],
        plan["card_id"],
    )
    if deck_card is None or int(deck_card["quantity"]) < quantity:
        raise InsufficientQuantityError("Physical deck has insufficient quantity")
    if int(deck_card["quantity"]) == quantity:
        await conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
            plan["deck_id"],
            plan["card_id"],
        )
    else:
        await conn.execute(
            """
            UPDATE deck_cards SET quantity = quantity - $3
            WHERE deck_id = $1 AND card_id = $2
            """,
            plan["deck_id"],
            plan["card_id"],
            quantity,
        )
    if plan["collection_id"] is not None:
        set_code = await conn.fetchval("SELECT set_code FROM cards WHERE id = $1", plan["card_id"])
        await conn.execute(
            """
            INSERT INTO collection_cards (
                collection_id, card_id, set_code, collector_number, foil, quantity, last_modified
            ) VALUES ($1, $2, $3, '', false, $4, now())
            ON CONFLICT (collection_id, card_id, set_code, collector_number, foil)
            DO UPDATE SET quantity = collection_cards.quantity + EXCLUDED.quantity,
                          last_modified = now()
            """,
            plan["collection_id"],
            plan["card_id"],
            set_code or "",
            quantity,
        )


async def complete_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    plan_id: UUID,
    quantity: int,
    *,
    email: str,
    account_id: UUID,
) -> PlannedDeckChange | None:
    """Atomically complete copies and optionally move collection inventory."""
    async with pool.acquire() as conn, conn.transaction():
        await _owned_deck(conn, deck_id, email, lock=True)
        plan = await conn.fetchrow(
            """
            SELECT * FROM deck_card_plans
            WHERE deck_id = $1 AND id = $2
            FOR UPDATE
            """,
            deck_id,
            plan_id,
        )
        if plan is None:
            raise PlanNotFoundError(f"Planned change {plan_id} not found")
        if quantity > int(plan["quantity"]):
            raise InsufficientQuantityError("Completion exceeds the pending quantity")
        if plan["collection_id"] is not None:
            await _validate_collection(
                conn,
                plan["collection_id"],
                account_id,
                plan["card_id"],
                plan["direction"],
            )
        if plan["direction"] == "addition":
            await _complete_addition(conn, plan, quantity)
        else:
            await _complete_cut(conn, plan, quantity)
        remaining = int(plan["quantity"]) - quantity
        if remaining == 0:
            await conn.execute("DELETE FROM deck_card_plans WHERE id = $1", plan_id)
        else:
            await conn.execute(
                "UPDATE deck_card_plans SET quantity = $2, updated_at = now() WHERE id = $1",
                plan_id,
                remaining,
            )
    if remaining == 0:
        return None
    return await get_plan(pool, deck_id, plan_id, email, account_id)


async def consume_immediate_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    card_id: UUID,
    direction: Literal["addition", "cut"],
    quantity: int | None = None,
) -> None:
    """Reconcile a matching plan after an immediate physical mutation."""
    async with pool.acquire() as conn:
        plan = await conn.fetchrow(
            """
            SELECT id, quantity FROM deck_card_plans
            WHERE deck_id = $1 AND card_id = $2 AND direction = $3
            """,
            deck_id,
            card_id,
            direction,
        )
        if plan is None:
            return
        if quantity is None or quantity >= int(plan["quantity"]):
            await conn.execute("DELETE FROM deck_card_plans WHERE id = $1", plan["id"])
        else:
            await conn.execute(
                "UPDATE deck_card_plans SET quantity = quantity - $2, updated_at = now() "
                "WHERE id = $1",
                plan["id"],
                quantity,
            )


async def clamp_cut_plan(
    pool: asyncpg.Pool,
    deck_id: UUID,
    card_id: UUID,
    physical_quantity: int,
) -> None:
    """Keep a pending cut bounded after an immediate quantity edit."""
    async with pool.acquire() as conn:
        if physical_quantity == 0:
            await conn.execute(
                "DELETE FROM deck_card_plans "
                "WHERE deck_id = $1 AND card_id = $2 AND direction = 'cut'",
                deck_id,
                card_id,
            )
        else:
            await conn.execute(
                """
                UPDATE deck_card_plans
                SET quantity = LEAST(quantity, $3), updated_at = now()
                WHERE deck_id = $1 AND card_id = $2 AND direction = 'cut'
                """,
                deck_id,
                card_id,
                physical_quantity,
            )
