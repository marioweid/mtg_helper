"""Revalidate only pilot-origin additions; preserve existing manual/Rule 0 policy."""

from uuid import UUID

import asyncpg

from mtg_helper.models.new_cards import CardFacts
from mtg_helper.services.card_identity_service import commander_copy_limit
from mtg_helper.services.new_cards.repository import json_value
from mtg_helper.services.planned_change_service import InvalidPlanError


async def validate_addition(
    conn: asyncpg.Connection,
    deck_id: UUID,
    card_id: UUID,
    quantity: int,
) -> None:
    """Check current identity, legality and copy limits inside the physical mutation transaction.

    Release-window expiry is intentionally irrelevant after a card has been saved as a plan.
    The caller holds the deck row lock; a failed batch transaction preserves every plan and card.
    """
    # Serialize the legality decision with atomic Scryfall catalog publication.
    await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
    row = await conn.fetchrow(
        """
        SELECT c.oracle_id, n.facts, canonical.legalities FROM cards c
        JOIN new_card_catalog n ON n.oracle_id = c.oracle_id
        JOIN new_card_catalog_state s ON s.generation = n.generation
        JOIN LATERAL (
            SELECT p.legalities FROM cards p WHERE p.oracle_id = c.oracle_id AND p.is_canonical
            ORDER BY p.id LIMIT 1
        ) canonical ON true
        WHERE c.id = $1
        """,
        card_id,
    )
    if row is None:
        raise InvalidPlanError(
            "Discovery card facts are unavailable. Sync cards before completion."
        )
    facts = CardFacts.model_validate(json_value(row["facts"]))
    commanders = await conn.fetch(
        "SELECT c.oracle_id, n.facts FROM decks d "
        "JOIN cards c ON c.id IN (d.commander_id, d.partner_id) "
        "LEFT JOIN new_card_catalog n ON n.oracle_id = c.oracle_id "
        "AND n.generation = (SELECT generation FROM new_card_catalog_state WHERE singleton) "
        "WHERE d.id = $1",
        deck_id,
    )
    if any(c["facts"] is None for c in commanders):
        raise InvalidPlanError(
            "Commander source facts are unavailable. Sync cards before completion."
        )
    colors = {color for c in commanders for color in json_value(c["facts"])["color_identity"]}
    legal = facts.commander_legality == json_value(row["legalities"]).get("commander") == "legal"
    if not legal or not set(facts.color_identity) <= colors:
        raise InvalidPlanError(
            f"{facts.name} is no longer legal for this deck. Remove or revise the plan."
        )
    if row["oracle_id"] in {c["oracle_id"] for c in commanders}:
        raise InvalidPlanError("The planned card is now a commander or partner; revise the plan.")
    present = await conn.fetchval(
        "SELECT COALESCE(sum(dc.quantity), 0) FROM deck_cards dc JOIN cards c ON c.id = dc.card_id "
        "WHERE dc.deck_id = $1 AND c.oracle_id = $2",
        deck_id,
        row["oracle_id"],
    )
    limit = commander_copy_limit(facts.type_line, facts.oracle_text)
    if limit is not None and present + quantity > limit:
        raise InvalidPlanError(f"Completing {facts.name} would exceed its Commander copy limit.")
