"""Idempotent repair of active deck state after Oracle identity migration."""

import logging
from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

import asyncpg

from mtg_helper.services.card_identity_service import clamp_quantity, commander_copy_limit

_log = logging.getLogger(__name__)


def _group_rows(rows: Iterable[asyncpg.Record]) -> dict[tuple[UUID, UUID], list[asyncpg.Record]]:
    grouped: dict[tuple[UUID, UUID], list[asyncpg.Record]] = defaultdict(list)
    for row in rows:
        grouped[(row["deck_id"], row["oracle_key"])].append(row)
    return grouped


def _merged_metadata(rows: list[asyncpg.Record]) -> tuple[list[str], str, str | None]:
    categories = list(dict.fromkeys(category for row in rows for category in row["categories"]))
    added_by = "user" if any(row["added_by"] == "user" for row in rows) else "ai"
    reasoning = next((row["ai_reasoning"] for row in rows if row["ai_reasoning"]), None)
    return categories, added_by, reasoning


async def _repair_commanders(conn: asyncpg.Connection) -> int:
    commander_result = await conn.execute(
        """
        UPDATE decks d
        SET commander_id = canonical.id
        FROM cards commander
        JOIN cards canonical
          ON COALESCE(canonical.oracle_id, canonical.id)
           = COALESCE(commander.oracle_id, commander.id)
         AND canonical.is_canonical
        WHERE commander.id = d.commander_id
          AND d.commander_id != canonical.id
        """
    )
    partner_result = await conn.execute(
        """
        UPDATE decks d
        SET partner_id = canonical.id
        FROM cards partner
        JOIN cards canonical
          ON COALESCE(canonical.oracle_id, canonical.id)
           = COALESCE(partner.oracle_id, partner.id)
         AND canonical.is_canonical
        WHERE partner.id = d.partner_id
          AND d.partner_id != canonical.id
        """
    )
    return sum(int(result.rsplit(" ", 1)[-1]) for result in (commander_result, partner_result))


async def _repair_deck_cards(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch(
        """
        SELECT dc.*, COALESCE(c.oracle_id, c.id) AS oracle_key,
               canonical.id AS canonical_card_id,
               canonical.type_line, canonical.oracle_text
        FROM deck_cards dc
        JOIN cards c ON c.id = dc.card_id
        JOIN cards canonical
          ON COALESCE(canonical.oracle_id, canonical.id) = COALESCE(c.oracle_id, c.id)
         AND canonical.is_canonical
        ORDER BY dc.deck_id, dc.id
        """
    )
    groups = _group_rows(rows)
    repaired = 0
    for group in groups.values():
        first = group[0]
        limit = commander_copy_limit(first["type_line"], first["oracle_text"])
        original_quantity = sum(int(row["quantity"]) for row in group)
        quantity = clamp_quantity(original_quantity, limit)
        if (
            len(group) == 1
            and first["card_id"] == first["canonical_card_id"]
            and quantity == original_quantity
        ):
            continue
        repaired += 1
        categories, added_by, reasoning = _merged_metadata(group)
        await conn.execute(
            "DELETE FROM deck_cards WHERE id = ANY($1::uuid[])", [r["id"] for r in group]
        )
        if quantity:
            await conn.execute(
                """
                INSERT INTO deck_cards (
                    deck_id, card_id, quantity, categories, added_by, ai_reasoning
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                first["deck_id"],
                first["canonical_card_id"],
                quantity,
                categories,
                added_by,
                reasoning,
            )
    return repaired


async def _physical_quantity(conn: asyncpg.Connection, deck_id: UUID, card_id: UUID) -> int:
    value = await conn.fetchval(
        "SELECT quantity FROM deck_cards WHERE deck_id = $1 AND card_id = $2",
        deck_id,
        card_id,
    )
    return int(value or 0)


async def _repair_plans(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch(
        """
        SELECT p.*, COALESCE(c.oracle_id, c.id) AS oracle_key,
               canonical.id AS canonical_card_id,
               canonical.type_line, canonical.oracle_text
        FROM deck_card_plans p
        JOIN cards c ON c.id = p.card_id
        JOIN cards canonical
          ON COALESCE(canonical.oracle_id, canonical.id) = COALESCE(c.oracle_id, c.id)
         AND canonical.is_canonical
        ORDER BY p.deck_id, p.created_at, p.id
        """
    )
    groups = _group_rows(rows)
    repaired = 0
    for group in groups.values():
        first = group[0]
        physical = await _physical_quantity(conn, first["deck_id"], first["canonical_card_id"])
        net = sum(
            int(row["quantity"]) * (1 if row["direction"] == "addition" else -1) for row in group
        )
        limit = commander_copy_limit(first["type_line"], first["oracle_text"])
        normalized = clamp_quantity(physical + net, limit) - physical
        direction = "addition" if normalized > 0 else "cut"
        if (
            len(group) == 1
            and first["card_id"] == first["canonical_card_id"]
            and normalized != 0
            and first["direction"] == direction
            and int(first["quantity"]) == abs(normalized)
        ):
            continue
        await _replace_plan_group(conn, group)
        repaired += 1
    return repaired


async def _replace_plan_group(conn: asyncpg.Connection, rows: list[asyncpg.Record]) -> None:
    first = rows[0]
    physical = await _physical_quantity(conn, first["deck_id"], first["canonical_card_id"])
    net = sum(int(row["quantity"]) * (1 if row["direction"] == "addition" else -1) for row in rows)
    limit = commander_copy_limit(first["type_line"], first["oracle_text"])
    projected = clamp_quantity(physical + net, limit)
    normalized = projected - physical
    await conn.execute(
        "DELETE FROM deck_card_plans WHERE id = ANY($1::uuid[])", [row["id"] for row in rows]
    )
    if normalized == 0:
        return
    direction = "addition" if normalized > 0 else "cut"
    matching = [row for row in rows if row["direction"] == direction] or rows
    categories, added_by, reasoning = _merged_metadata(matching)
    await conn.execute(
        """
        INSERT INTO deck_card_plans (
            deck_id, card_id, direction, quantity, collection_id,
            categories, added_by, ai_reasoning, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        first["deck_id"],
        first["canonical_card_id"],
        direction,
        abs(normalized),
        matching[0]["collection_id"],
        categories if direction == "addition" else [],
        added_by,
        reasoning,
        min(row["created_at"] for row in rows),
    )


async def repair_active_decks(pool: asyncpg.Pool) -> dict[str, int]:
    """Canonicalize active decks and plans in one retry-safe transaction."""
    async with pool.acquire() as conn, conn.transaction():
        result = {
            "commanders": await _repair_commanders(conn),
            "deck_card_groups": await _repair_deck_cards(conn),
            "plan_groups": await _repair_plans(conn),
        }
    if any(result.values()):
        _log.info("Oracle card identity repair complete: %s", result)
    return result
