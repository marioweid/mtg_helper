"""Commander Spellbook combo discovery for a deck.

Posts the deck's commander + mainboard to ``find-my-combos`` and translates
the response into the trimmed ``ComboListResponse`` the UI consumes.
"""

import logging
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from mtg_helper.models.combos import (
    Combo,
    ComboCardRef,
    ComboListResponse,
    ComboPiece,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import card_service

_log = logging.getLogger(__name__)

_COMMANDER_SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos/"
_REQUEST_TIMEOUT = 30.0
_ALMOST_MISSING_LIMIT = 1


class ComboFetchError(RuntimeError):
    """Raised when the Commander Spellbook API fails or returns garbage."""


async def fetch_combos(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    *,
    client: httpx.AsyncClient | None = None,
) -> ComboListResponse:
    """Return active and almost-there (1 missing) combos for ``deck``.

    Args:
        pool: asyncpg connection pool used to enrich CS card names with our
            local Scryfall ids and image URIs.
        deck: Full deck detail (commander, partner, mainboard).
        client: Optional injected httpx client for tests.

    Raises:
        ComboFetchError: On network failure, non-success status, or non-JSON
            response from Commander Spellbook.
    """
    commander_names = await _commander_names(pool, deck)
    body = _build_request_body(commander_names, deck)
    payload = await _call_spellbook(body, client=client)
    raw_results = (payload.get("results") or {}) if isinstance(payload, dict) else {}

    raw_active: list[dict[str, Any]] = list(raw_results.get("included") or [])
    raw_almost: list[dict[str, Any]] = list(raw_results.get("almostIncluded") or [])

    deck_names = _deck_card_names(deck, commander_names)
    referenced_names = _collect_referenced_names(raw_active + raw_almost)
    name_map = await _lookup_local_cards(pool, referenced_names)

    active = [_translate_combo(c, deck_names, name_map) for c in raw_active]
    almost: list[Combo] = []
    for combo in raw_almost:
        translated = _translate_combo(combo, deck_names, name_map)
        if translated.missing_count == _ALMOST_MISSING_LIMIT:
            almost.append(translated)

    return ComboListResponse(active=active, almost_there=almost)


async def _commander_names(pool: asyncpg.Pool, deck: DeckDetailResponse) -> list[str]:
    """Resolve commander + partner UUIDs on the deck to their card names."""
    ids = [deck.commander_id]
    if deck.partner_id is not None:
        ids.append(deck.partner_id)
    names: list[str] = []
    for cid in ids:
        card = await card_service.get_card_by_id(pool, cid)
        if card is not None:
            names.append(card.name)
    return names


def _build_request_body(
    commander_names: list[str],
    deck: DeckDetailResponse,
) -> dict[str, Any]:
    """Build the CS request body from commander names + deck mainboard.

    ``DeckDetailResponse.cards`` does not include commanders (they live in
    ``commander_id`` / ``partner_id`` on the deck row), so the two pools
    don't overlap and dedup-by-name on the mainboard is sufficient.
    """
    commanders = [{"card": name, "quantity": 1} for name in commander_names]
    main: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in deck.cards:
        if not card.name or card.name in seen:
            continue
        seen.add(card.name)
        main.append({"card": card.name, "quantity": max(1, card.quantity or 1)})
    return {"commanders": commanders, "main": main}


async def _call_spellbook(
    body: dict[str, Any],
    *,
    client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    """POST the request body to Commander Spellbook, return parsed JSON."""
    owned_client = client is None
    http_client = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
    try:
        try:
            response = await http_client.post(_COMMANDER_SPELLBOOK_URL, json=body)
        except httpx.HTTPError as exc:
            raise ComboFetchError(f"Could not reach Commander Spellbook: {exc}") from exc
        if response.status_code >= 400:
            raise ComboFetchError(f"Commander Spellbook returned status {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ComboFetchError("Commander Spellbook response was not valid JSON") from exc
    finally:
        if owned_client:
            await http_client.aclose()


def _deck_card_names(deck: DeckDetailResponse, commander_names: list[str]) -> set[str]:
    """Lowercased card names of everything CS may match (commanders + mainboard)."""
    names = {card.name.lower() for card in deck.cards if card.name}
    for cn in commander_names:
        names.add(cn.lower())
    return names


def _collect_referenced_names(combos: list[dict[str, Any]]) -> list[str]:
    """Distinct card names referenced by ``uses`` across all combos."""
    seen: set[str] = set()
    out: list[str] = []
    for combo in combos:
        for use in combo.get("uses") or []:
            card = use.get("card") or {}
            name = card.get("name")
            if isinstance(name, str) and name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


async def _lookup_local_cards(
    pool: asyncpg.Pool,
    names: list[str],
) -> dict[str, tuple[UUID, str | None]]:
    """One batched lookup mapping ``lower(name) → (scryfall_id, image_uri)``."""
    if not names:
        return {}
    lowered = list({n.lower() for n in names})
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (lower(name))
                lower(name) AS lname, scryfall_id, image_uri
            FROM cards
            WHERE lower(name) = ANY($1::text[])
            ORDER BY lower(name), released_at DESC NULLS LAST
            """,
            lowered,
        )
    return {row["lname"]: (row["scryfall_id"], row["image_uri"]) for row in rows}


def _translate_combo(
    raw: dict[str, Any],
    deck_names_lower: set[str],
    name_map: dict[str, tuple[UUID, str | None]],
) -> Combo:
    """Trim a raw CS combo to ``Combo`` and compute per-piece in-deck flags."""
    pieces: list[ComboPiece] = []
    missing = 0
    for use in raw.get("uses") or []:
        raw_card = use.get("card") or {}
        name = raw_card.get("name") or ""
        local = name_map.get(name.lower())
        scryfall_id, image_uri = local if local else (None, None)
        if image_uri is None:
            image_uri = raw_card.get("imageUriFrontNormal")
        in_deck = name.lower() in deck_names_lower
        if not in_deck:
            missing += 1
        pieces.append(
            ComboPiece(
                card=ComboCardRef(name=name, scryfall_id=scryfall_id, image_uri=image_uri),
                in_deck=in_deck,
            )
        )

    produces = [
        feat["feature"]["name"]
        for feat in raw.get("produces") or []
        if isinstance(feat.get("feature"), dict) and feat["feature"].get("name")
    ]

    return Combo(
        id=str(raw.get("id") or ""),
        pieces=pieces,
        produces=produces,
        description=raw.get("description") or None,
        popularity=_coerce_int(raw.get("popularity")),
        bracket_tag=raw.get("bracketTag") or None,
        missing_count=missing,
    )


def _coerce_int(value: Any) -> int | None:
    """Best-effort int coercion; returns None when the value isn't numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
