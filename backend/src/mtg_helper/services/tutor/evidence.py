"""Capture exact saved-list facts without treating missing coverage as absence."""

from hashlib import sha256
from typing import Any

import asyncpg

from mtg_helper.models.tutor import TutorCardFact, TutorEvidence


def composition_hash(manifest: dict[str, Any]) -> str:
    """Return the stable identity of commanders plus canonical main-deck quantities."""
    payload = repr((manifest["commanders"], manifest["cards"])).encode()
    return sha256(payload).hexdigest()


def teaching_hash(manifest: dict[str, Any], mode: str) -> str:
    """Return the teaching identity including explicit saved teaching context."""
    payload = repr(
        (composition_hash(manifest), manifest["description"], manifest["bracket"], mode)
    ).encode()
    return sha256(payload).hexdigest()


async def capture(
    conn: asyncpg.Connection, deck: asyncpg.Record
) -> tuple[dict[str, Any], TutorEvidence]:
    """Freeze canonical list identity and exact local card facts for one guide request."""
    ids = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
    commander_rows = await conn.fetch(
        "SELECT oracle_id, name, type_line, oracle_text FROM cards "
        "WHERE id = ANY($1::uuid[]) ORDER BY id",
        ids,
    )
    card_rows = await conn.fetch(
        """
        SELECT c.oracle_id, c.name, c.type_line, c.oracle_text, dc.quantity
        FROM deck_cards dc JOIN cards c ON c.id = dc.card_id
        WHERE dc.deck_id = $1
        ORDER BY COALESCE(c.oracle_id::text, c.scryfall_id::text), c.scryfall_id
        """,
        deck["id"],
    )
    commanders = [_fact(row, 1) for row in commander_rows]
    cards = [_fact(row, int(row["quantity"])) for row in card_rows]
    manifest = {
        "commanders": [
            (str(f.oracle_id) if f.oracle_id else f.name, f.quantity) for f in commanders
        ],
        "cards": [(str(f.oracle_id) if f.oracle_id else f.name, f.quantity) for f in cards],
        "description": deck["description"],
        "bracket": deck["bracket"],
    }
    warnings = _warnings(commanders, cards)
    evidence = TutorEvidence(
        commanders=commanders,
        cards=cards,
        warnings=warnings,
        sources={"cards": "local-card-catalog", "rules": None, "combos": None},
    )
    return manifest, evidence


def _fact(row: asyncpg.Record, quantity: int) -> TutorCardFact:
    return TutorCardFact(
        oracle_id=row["oracle_id"],
        name=row["name"],
        quantity=quantity,
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
    )


def _warnings(commanders: list[TutorCardFact], cards: list[TutorCardFact]) -> list[str]:
    warnings: list[str] = []
    if any(card.oracle_text is None for card in commanders + cards):
        warnings.append("Some exact card rules text is unavailable; related claims are unverified.")
    total = len(commanders) + sum(card.quantity for card in cards)
    if total != 100:
        warnings.append(
            f"This saved list has {total} cards including commanders; it may be incomplete."
        )
    return warnings
