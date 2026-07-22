"""Atomic application and history of selected planned deck changes."""

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from mtg_helper.models.revisions import DeckRevision, DeckRevisionChange, DeckRevisionUpdate
from mtg_helper.services import planned_change_service, snapshot_service
from mtg_helper.services.planned_change_service import (
    InsufficientQuantityError,
    PlanNotFoundError,
)


class RevisionNotFoundError(ValueError):
    """Raised when a revision is missing or not owned by the caller."""


@dataclass(frozen=True, slots=True)
class RevisionCommand:
    """Internal command supporting full-plan and legacy partial completion."""

    plan_ids: list[UUID]
    title: str | None
    note: str | None = None
    source: str = "selected_plans"
    quantities: dict[UUID, int] | None = None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _lock_plans(
    conn: asyncpg.Connection,
    deck_id: UUID,
    plan_ids: list[UUID],
) -> list[asyncpg.Record]:
    rows = await conn.fetch(
        """
        SELECT p.*, c.name AS card_name, collections.name AS collection_name
        FROM deck_card_plans p
        JOIN cards c ON c.id = p.card_id
        LEFT JOIN collections ON collections.id = p.collection_id
        WHERE p.deck_id = $1 AND p.id = ANY($2::uuid[])
        ORDER BY p.created_at, p.id
        FOR UPDATE OF p
        """,
        deck_id,
        plan_ids,
    )
    if len(rows) != len(plan_ids):
        raise PlanNotFoundError("One or more selected planned changes no longer exist")
    return list(rows)


def _resolved_title(command: RevisionCommand, plans: list[asyncpg.Record]) -> str:
    if command.title is not None and command.title.strip():
        return command.title.strip()
    plan = plans[0]
    verb = "Added" if plan["direction"] == "addition" else "Cut"
    return f"{verb} {plan['card_name']}"


def _quantity_for(plan: asyncpg.Record, command: RevisionCommand) -> int:
    quantity = (
        command.quantities.get(plan["id"], int(plan["quantity"]))
        if command.quantities is not None
        else int(plan["quantity"])
    )
    if quantity < 1 or quantity > int(plan["quantity"]):
        raise InsufficientQuantityError("Completion exceeds the pending quantity")
    return quantity


async def _apply_plan(
    conn: asyncpg.Connection,
    plan: asyncpg.Record,
    quantity: int,
    account_id: UUID,
) -> None:
    if plan["collection_id"] is not None:
        await planned_change_service._validate_collection(
            conn,
            plan["collection_id"],
            account_id,
            plan["card_id"],
            plan["direction"],
        )
    if plan["direction"] == "addition":
        await planned_change_service._complete_addition(conn, plan, quantity)
    else:
        await planned_change_service._complete_cut(conn, plan, quantity)


async def _consume_plan(
    conn: asyncpg.Connection,
    plan: asyncpg.Record,
    quantity: int,
) -> None:
    remaining = int(plan["quantity"]) - quantity
    if remaining == 0:
        await conn.execute("DELETE FROM deck_card_plans WHERE id = $1", plan["id"])
        return
    await conn.execute(
        "UPDATE deck_card_plans SET quantity = $2, updated_at = now() WHERE id = $1",
        plan["id"],
        remaining,
    )


async def _insert_change(
    conn: asyncpg.Connection,
    revision_id: UUID,
    plan: asyncpg.Record,
    quantity: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO deck_revision_changes (
            revision_id, card_id, card_name, direction, quantity, categories,
            added_by, ai_reasoning, collection_id, collection_name,
            plan_created_at, plan_updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6::text[], $7, $8, $9, $10, $11, $12)
        """,
        revision_id,
        plan["card_id"],
        plan["card_name"],
        plan["direction"],
        quantity,
        list(plan["categories"] or []),
        plan["added_by"],
        plan["ai_reasoning"],
        plan["collection_id"],
        plan["collection_name"],
        plan["created_at"],
        plan["updated_at"],
    )


async def apply_revision(
    pool: asyncpg.Pool,
    deck_id: UUID,
    command: RevisionCommand,
    email: str,
    account_id: UUID,
) -> DeckRevision:
    """Apply selected plans and record the exact before/after transition atomically."""
    async with pool.acquire() as conn, conn.transaction():
        await planned_change_service._owned_deck(conn, deck_id, email, lock=True)
        plans = await _lock_plans(conn, deck_id, command.plan_ids)
        title = _resolved_title(command, plans)
        before = await snapshot_service.insert_snapshot(
            conn, deck_id, label=f"Before: {title}", source="revision"
        )
        quantities = {plan["id"]: _quantity_for(plan, command) for plan in plans}
        for plan in plans:
            await _apply_plan(conn, plan, quantities[plan["id"]], account_id)
        after = await snapshot_service.insert_snapshot(
            conn, deck_id, label=f"After: {title}", source="revision"
        )
        revision = await conn.fetchrow(
            """
            INSERT INTO deck_revisions (
                deck_id, title, note, source, before_snapshot_id, after_snapshot_id
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            deck_id,
            title,
            command.note,
            command.source,
            before["id"],
            after["id"],
        )
        for plan in plans:
            quantity = quantities[plan["id"]]
            await _insert_change(conn, revision["id"], plan, quantity)
            await _consume_plan(conn, plan, quantity)
    return await get_revision(pool, revision["id"], email)


def _change_from_row(row: asyncpg.Record) -> DeckRevisionChange:
    return DeckRevisionChange(
        card_id=row["card_id"],
        card_name=row["card_name"],
        direction=row["direction"],
        quantity=row["quantity"],
        categories=list(row["categories"] or []),
        added_by=row["added_by"],
        ai_reasoning=row["ai_reasoning"],
        collection_id=row["collection_id"],
        collection_name=row["collection_name"],
        plan_created_at=row["plan_created_at"],
        plan_updated_at=row["plan_updated_at"],
    )


async def _hydrate_revisions(
    conn: asyncpg.Connection,
    rows: list[asyncpg.Record],
) -> list[DeckRevision]:
    if not rows:
        return []
    change_rows = await conn.fetch(
        """
        SELECT * FROM deck_revision_changes
        WHERE revision_id = ANY($1::uuid[])
        ORDER BY direction, card_name
        """,
        [row["id"] for row in rows],
    )
    changes: dict[UUID, list[DeckRevisionChange]] = {}
    for row in change_rows:
        changes.setdefault(row["revision_id"], []).append(_change_from_row(row))
    return [DeckRevision(**dict(row), changes=changes.get(row["id"], [])) for row in rows]


async def list_revisions(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str,
) -> list[DeckRevision]:
    """List owned deck revisions newest first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.* FROM deck_revisions r
            JOIN decks d ON d.id = r.deck_id
            WHERE r.deck_id = $1 AND lower(d.owner_email) = $2
            ORDER BY r.created_at DESC, r.id DESC
            """,
            deck_id,
            _normalize_email(email),
        )
        if not rows:
            owned = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM decks WHERE id = $1 AND lower(owner_email) = $2)",
                deck_id,
                _normalize_email(email),
            )
            if not owned:
                raise RevisionNotFoundError(f"Deck {deck_id} not found")
        return await _hydrate_revisions(conn, list(rows))


async def get_revision(
    pool: asyncpg.Pool,
    revision_id: UUID,
    email: str,
) -> DeckRevision:
    """Fetch one owned revision with its frozen changes."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT r.* FROM deck_revisions r
            JOIN decks d ON d.id = r.deck_id
            WHERE r.id = $1 AND lower(d.owner_email) = $2
            """,
            revision_id,
            _normalize_email(email),
        )
        if row is None:
            raise RevisionNotFoundError(f"Revision {revision_id} not found")
        return (await _hydrate_revisions(conn, [row]))[0]


async def update_revision(
    pool: asyncpg.Pool,
    revision_id: UUID,
    data: DeckRevisionUpdate,
    email: str,
) -> DeckRevision:
    """Update title/note without changing the recorded transition."""
    fields = data.model_fields_set
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE deck_revisions r
            SET title = CASE WHEN $3 THEN $4 ELSE r.title END,
                note = CASE WHEN $5 THEN $6 ELSE r.note END
            FROM decks d
            WHERE r.id = $1 AND d.id = r.deck_id AND lower(d.owner_email) = $2
            RETURNING r.id
            """,
            revision_id,
            _normalize_email(email),
            "title" in fields,
            data.title,
            "note" in fields,
            data.note,
        )
    if row is None:
        raise RevisionNotFoundError(f"Revision {revision_id} not found")
    return await get_revision(pool, revision_id, email)
