"""Normalize export quantities and allocate selected binder stock without writes."""

from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CollectionMembership
from mtg_helper.models.card_exports import CardExportPreview, CardExportRequest, CardExportRow
from mtg_helper.services import collection_service


class ExportNotFoundError(ValueError):
    """A requested card or account-owned binder could not be found."""


async def _validate_binders(
    pool: asyncpg.Pool, account_id: UUID, collection_ids: set[UUID]
) -> None:
    count = await pool.fetchval(
        "SELECT count(*) FROM collections WHERE account_id = $1 AND id = ANY($2::uuid[])",
        account_id,
        list(collection_ids),
    )
    if count != len(collection_ids):
        raise ExportNotFoundError("Selected binders were not found; refresh and select again")


async def _requested_cards(pool: asyncpg.Pool, request: CardExportRequest) -> list[dict[str, Any]]:
    requested: dict[UUID, int] = {}
    for card in request.cards:
        requested[card.card_id] = requested.get(card.card_id, 0) + card.quantity
    rows = await pool.fetch(
        """
        SELECT id, scryfall_id, COALESCE(oracle_id, id) AS identity, name,
               CASE WHEN c.prices->>'eur' IS NULL THEN NULL
                    ELSE ROUND((c.prices->>'eur')::numeric * 100)::integer END AS price
        FROM cards c WHERE id = ANY($1::uuid[])
        ORDER BY is_canonical DESC, id
        """,
        list(requested),
    )
    if len(rows) != len(requested):
        raise ExportNotFoundError(
            "Export cards were not found; refresh the card list and try again"
        )
    grouped: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        identity = row["identity"]
        if identity not in grouped:
            grouped[identity] = {**dict(row), "quantity": 0}
        grouped[identity]["quantity"] += requested[row["id"]]
    return sorted(grouped.values(), key=lambda row: (row["name"].casefold(), str(row["id"])))


def _export_row(
    card: dict[str, Any], memberships: list[CollectionMembership], selected_ids: set[UUID]
) -> CardExportRow:
    selected = sorted(
        (item for item in memberships if item.id in selected_ids),
        key=lambda item: (item.name.casefold(), str(item.id)),
    )
    remaining = card["quantity"]
    pulls: list[CollectionMembership] = []
    for binder in selected:
        quantity = min(remaining, binder.quantity)
        if quantity > 0:
            pulls.append(binder.model_copy(update={"quantity": quantity}))
            remaining -= quantity
    return CardExportRow(
        card_id=card["id"],
        name=card["name"],
        needed_quantity=card["quantity"],
        available_quantity=sum(item.quantity for item in selected),
        export_quantity=remaining,
        price_eur_cents=card["price"],
        pulls=pulls,
    )


async def preview(
    pool: asyncpg.Pool, request: CardExportRequest, *, account_id: UUID
) -> CardExportPreview:
    """Preview quantity/name text, costs and pulls using only the selected owned binders.

    Args:
        pool: Application database pool.
        request: Card quantities and explicitly selected binder IDs; empty means no subtraction.
        account_id: Authenticated account whose inventory may be counted.

    Returns:
        One row per gameplay card with capped pull allocations and the remaining text export.

    Raises:
        ExportNotFoundError: A card or selected account-owned binder no longer exists.
    """
    selected_ids = set(request.collection_ids)
    await _validate_binders(pool, account_id, selected_ids)
    cards = await _requested_cards(pool, request)
    ownership = await collection_service.build_ownership_map(
        pool, account_id, [card["scryfall_id"] for card in cards]
    )
    rows = [
        _export_row(card, ownership.get(card["scryfall_id"], []), selected_ids) for card in cards
    ]
    return CardExportPreview(
        rows=rows,
        needed_quantity=sum(row.needed_quantity for row in rows),
        from_binders_quantity=sum(row.needed_quantity - row.export_quantity for row in rows),
        export_quantity=sum(row.export_quantity for row in rows),
        known_price_eur_cents=sum(
            row.export_quantity * row.price_eur_cents
            for row in rows
            if row.price_eur_cents is not None
        ),
        unpriced_quantity=sum(row.export_quantity for row in rows if row.price_eur_cents is None),
        text="\n".join(f"{row.export_quantity} {row.name}" for row in rows if row.export_quantity),
    )
