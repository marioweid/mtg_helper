"""Capture exact saved-list facts without treating missing coverage as absence."""

import asyncio
import gzip
import json
import zlib
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

import asyncpg

from mtg_helper.models.tutor import (
    TutorCardFace,
    TutorCardFact,
    TutorComboFact,
    TutorEvidence,
    TutorLineRequirement,
    TutorRuleFact,
)
from mtg_helper.services import combo_service, deck_service
from mtg_helper.services.combo_service import ComboFetchError, ComboResponseError
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
        "SELECT c.oracle_id, c.name, c.type_line, c.oracle_text, c.color_identity, c.legalities, "
        "nc.source_facts FROM cards c "
        "LEFT JOIN new_card_catalog nc ON nc.oracle_id = c.oracle_id "
        "WHERE id = ANY($1::uuid[]) "
        "ORDER BY COALESCE(c.oracle_id::text, lower(c.name)), lower(c.name)",
        ids,
    )
    card_rows = await conn.fetch(
        """
        SELECT DISTINCT ON (COALESCE(c.oracle_id::text, lower(c.name)))
            c.oracle_id, c.name, c.type_line, c.oracle_text, c.color_identity, c.legalities,
            nc.source_facts,
            SUM(dc.quantity) OVER (
                PARTITION BY COALESCE(c.oracle_id::text, lower(c.name))
            ) AS quantity
        FROM deck_cards dc JOIN cards c ON c.id = dc.card_id
        LEFT JOIN new_card_catalog nc ON nc.oracle_id = c.oracle_id
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
    warnings = _warnings(commanders, cards, rules_status, combo_status)
    card_source = await conn.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
    card_status = (
        f"pinned-cards:{card_source}"
        if isinstance(card_source, str) and len(card_source) == 64
        else "local-card-catalog"
    )
    evidence = TutorEvidence(
        commanders=commanders,
        cards=cards,
        rules=rules,
        combos=combos,
        warnings=warnings,
        sources={
            "cards": card_status,
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
        color_identity=list(row["color_identity"] or []),
        legalities=_string_object(row["legalities"]),
        faces=_faces(row["source_facts"]),
    )


def _faces(value: object) -> list[TutorCardFace]:
    """Return source-defined card faces without deriving them from flattened text."""
    source = _json_object(value)
    raw_faces = source.get("faces")
    if not isinstance(raw_faces, list):
        return []
    faces: list[TutorCardFace] = []
    for face in raw_faces:
        if isinstance(face, dict) and isinstance(face.get("name"), str):
            faces.append(
                TutorCardFace(
                    name=face["name"],
                    type_line=face.get("type_line")
                    if isinstance(face.get("type_line"), str)
                    else None,
                    oracle_text=(
                        face.get("oracle_text")
                        if isinstance(face.get("oracle_text"), str)
                        else None
                    ),
                )
            )
    return faces


def _json_object(value: object) -> dict[str, object]:
    """Decode a JSONB object while treating malformed saved source facts as unavailable."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_object(value: object) -> dict[str, str]:
    """Return known string-valued source facts without coercing malformed values."""
    return {key: item for key, item in _json_object(value).items() if isinstance(item, str)}


def _rules_evidence() -> tuple[list[TutorRuleFact], str]:
    """Return relevant stable official rule excerpts and immutable source identity."""
    try:
        blob, digest = source_repository.rules_resource()
        rules = unpack(blob, digest)
        identifiers = ("103.4c", "113.7a", "122.1", "603.10a", "608.2h", "700.5", "903.3")
        facts = [
            TutorRuleFact(identifier=identifier, text=rules[identifier]["text"])
            for identifier in identifiers
        ]
        return facts, f"pinned-rules:{digest}"
    except (
        gzip.BadGzipFile,
        EOFError,
        json.JSONDecodeError,
        zlib.error,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return [], f"malformed: rules resource {type(exc).__name__}"
    except OSError as exc:
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
    except ComboResponseError:
        return [], "malformed: Commander Spellbook response"
    except ComboFetchError as exc:
        return [], f"unavailable: Commander Spellbook {exc}"
    if not hasattr(response, "active"):
        return [], "malformed: Commander Spellbook response"
    combos = [
        TutorComboFact(
            identifier=combo.id,
            pieces=[piece.card.name for piece in combo.pieces],
            produces=combo.produces,
            description=combo.description,
            requirements=[
                TutorLineRequirement(
                    name=piece.card.name,
                    zone=_piece_zone(piece.card.name, detail),
                )
                for piece in combo.pieces
            ],
            outlet=combo.produces[0] if combo.produces else None,
            outlet_status="supported" if combo.produces else "unverified",
        )
        for combo in response.active
        if combo.missing_count == 0 and all(piece.in_deck for piece in combo.pieces)
    ]
    return (
        combos,
        "Commander Spellbook: captured" if combos else "zero-results: Commander Spellbook",
    )


def _piece_zone(name: str, deck: object) -> Literal["command_zone", "mainboard"]:
    """Translate a captured source piece to a deck zone without inferring availability."""
    commander_names = {
        card.name.casefold()
        for card in (getattr(deck, "commander_card", None), getattr(deck, "partner_card", None))
        if card is not None
    }
    return "command_zone" if name.casefold() in commander_names else "mainboard"


def _warnings(
    commanders: list[TutorCardFact],
    cards: list[TutorCardFact],
    rules_status: str,
    combo_status: str,
) -> list[str]:
    warnings: list[str] = []
    if any(card.oracle_text is None for card in commanders + cards):
        warnings.append("Some exact card rules text is unavailable; related claims are unverified.")
    if any("//" in (card.type_line or "") and not card.faces for card in commanders + cards):
        warnings.append(
            "Some exact card faces are unavailable; face-specific claims are unverified."
        )
    total = len(commanders) + sum(card.quantity for card in cards)
    if total != 100:
        warnings.append(
            f"This saved list has {total} cards including commanders; it may be incomplete."
        )
    banned = [
        card.name for card in commanders + cards if card.legalities.get("commander") == "banned"
    ]
    if banned:
        warnings.append(f"Known Commander-banned cards in this saved list: {', '.join(banned)}.")
    commander_colors = {color for commander in commanders for color in commander.color_identity}
    off_color = [
        card.name for card in cards if not set(card.color_identity).issubset(commander_colors)
    ]
    if off_color:
        warnings.append(
            "Known cards outside the saved commander color identity: " + ", ".join(off_color) + "."
        )
    if rules_status.startswith(("timeout:", "unavailable:", "malformed:")):
        warnings.append("Rules coverage is unavailable; rule-dependent claims are unverified.")
    if combo_status.startswith(("timeout:", "unavailable:", "malformed:")):
        warnings.append("Combo coverage is unavailable; no missing line is treated as absent.")
    return warnings
