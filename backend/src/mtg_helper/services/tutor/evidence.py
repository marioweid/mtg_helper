"""Capture exact saved-list facts without treating missing coverage as absence."""

import asyncio
from hashlib import sha256
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.tutor import TutorCardFact, TutorComboFact, TutorEvidence, TutorRuleFact
from mtg_helper.services import combo_service, deck_service
from mtg_helper.services.combo_service import ComboFetchError
from mtg_helper.services.recommendations import source_repository
from mtg_helper.services.recommendations.snapshots import unpack


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
    conn: asyncpg.Connection,
    deck: asyncpg.Record,
    pool: asyncpg.Pool,
    owner_email: str,
    *,
    include_sources: bool = True,
) -> tuple[dict[str, Any], TutorEvidence]:
    """Freeze canonical list identity and exact local card facts for one guide request."""
    ids = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
    commander_rows = await conn.fetch(
        "SELECT oracle_id, name, type_line, oracle_text FROM cards "
        "WHERE id = ANY($1::uuid[]) "
        "ORDER BY COALESCE(oracle_id::text, lower(name)), lower(name)",
        ids,
    )
    card_rows = await conn.fetch(
        """
        SELECT DISTINCT ON (COALESCE(c.oracle_id::text, lower(c.name)))
            c.oracle_id, c.name, c.type_line, c.oracle_text,
            SUM(dc.quantity) OVER (
                PARTITION BY COALESCE(c.oracle_id::text, lower(c.name))
            ) AS quantity
        FROM deck_cards dc JOIN cards c ON c.id = dc.card_id
        WHERE dc.deck_id = $1
        ORDER BY COALESCE(c.oracle_id::text, lower(c.name)), c.scryfall_id
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
    rules, rules_status = _rules_evidence() if include_sources else ([], "not refreshed")
    combos, combo_status = (
        await _combo_evidence(pool, deck["id"], owner_email)
        if include_sources
        else ([], "not refreshed")
    )
    warnings = _warnings(commanders, cards, combo_status)
    evidence = TutorEvidence(
        commanders=commanders,
        cards=cards,
        rules=rules,
        combos=combos,
        warnings=warnings,
        sources={
            "cards": "local-card-catalog",
            "rules": rules_status,
            "combos": combo_status,
        },
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


def _rules_evidence() -> tuple[list[TutorRuleFact], str]:
    """Return one stable official rule excerpt and its immutable source identity."""
    try:
        blob, digest = source_repository.rules_resource()
        rules = unpack(blob, digest)
        text = rules["103.4c"]["text"]
        return [TutorRuleFact(identifier="103.4c", text=text)], f"pinned-rules:{digest}"
    except (KeyError, OSError, ValueError) as exc:
        return [], f"unavailable: rules resource {type(exc).__name__}"


async def _combo_evidence(
    pool: asyncpg.Pool, deck_id: UUID, owner_email: str
) -> tuple[list[TutorComboFact], str]:
    """Freeze active Commander Spellbook lines or preserve their specific failure state."""
    detail = await deck_service.get_deck(pool, deck_id, owner_email)
    if detail is None:
        return [], "unavailable: deck capture changed"
    try:
        async with asyncio.timeout(2):
            response = await combo_service.fetch_combos(pool, detail)
    except TimeoutError:
        return [], "timeout: Commander Spellbook"
    except ComboFetchError as exc:
        return [], f"unavailable: Commander Spellbook {exc}"
    combos = [
        TutorComboFact(
            identifier=combo.id,
            pieces=[piece.card.name for piece in combo.pieces],
            produces=combo.produces,
            description=combo.description,
        )
        for combo in response.active
        if combo.missing_count == 0 and all(piece.in_deck for piece in combo.pieces)
    ]
    return (
        combos,
        "Commander Spellbook: captured" if combos else "zero-results: Commander Spellbook",
    )


def _warnings(
    commanders: list[TutorCardFact], cards: list[TutorCardFact], combo_status: str
) -> list[str]:
    warnings: list[str] = []
    if any(card.oracle_text is None for card in commanders + cards):
        warnings.append("Some exact card rules text is unavailable; related claims are unverified.")
    total = len(commanders) + sum(card.quantity for card in cards)
    if total != 100:
        warnings.append(
            f"This saved list has {total} cards including commanders; it may be incomplete."
        )
    if combo_status.startswith(("timeout:", "unavailable:")):
        warnings.append("Combo coverage is unavailable; no missing line is treated as absent.")
    return warnings
