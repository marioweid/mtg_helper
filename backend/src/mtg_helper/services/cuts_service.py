"""AI-driven cuts suggester.

Ranks cards in an existing deck for removal. Combo pieces, the commander
(and partner if any), and basic lands are protected — never suggested.
"""

import json
import logging
import re
from typing import cast
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CutsResponse, CutSuggestion
from mtg_helper.models.combos import ComboListResponse
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import combo_service, deck_service
from mtg_helper.services.combo_service import ComboFetchError
from mtg_helper.services.llm_client import LLMClient

_log = logging.getLogger(__name__)

_BASIC_LANDS: frozenset[str] = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
)

_LLM_TEMPERATURE = 0.3
_LLM_MAX_OUTPUT_TOKENS = 2048


class DeckNotFoundError(ValueError):
    """Raised when the deck does not exist or is not owned by the caller."""


def _protected_names(
    deck: DeckDetailResponse,
    combos: ComboListResponse | None,
) -> set[str]:
    """Names (case-sensitive) that must never appear in cut suggestions.

    Includes commander(s), basic lands, and any in-deck piece of an active
    or almost-there combo.
    """
    protected: set[str] = set(_BASIC_LANDS)
    if deck.commander_card and deck.commander_card.name:
        protected.add(deck.commander_card.name)
    if deck.partner_card and deck.partner_card.name:
        protected.add(deck.partner_card.name)
    if combos is not None:
        for combo in [*combos.active, *combos.almost_there]:
            for piece in combo.pieces:
                if piece.in_deck and piece.card.name:
                    protected.add(piece.card.name)
    return protected


def _candidate_cards(
    deck: DeckDetailResponse,
    protected: set[str],
) -> list[DeckCardItem]:
    """Deck cards eligible to be cut (everything not in ``protected``)."""
    return [card for card in deck.cards if card.name and card.name not in protected]


def _build_system_prompt() -> str:
    return (
        "You are a Magic: The Gathering Commander (EDH) deck-tuning assistant. "
        "Given a deck list, a commander, and an explicit set of protected cards "
        "(combo pieces, the commander, basic lands), recommend which non-protected "
        "cards to cut from the deck. Prefer cutting the weakest cards for the "
        "deck's strategy: low-impact filler, redundant effects, cards that don't "
        "advance the commander's plan. Never recommend cutting a protected card."
    )


def _build_user_prompt(
    deck: DeckDetailResponse,
    candidates: list[DeckCardItem],
    protected: set[str],
    count: int,
) -> str:
    commander_name = deck.commander_card.name if deck.commander_card else "(unknown)"
    partner = deck.partner_card.name if deck.partner_card and deck.partner_card.name else None
    archetype = ", ".join(deck.archetype_tags) or "(none specified)"
    cand_lines = [f"- {c.name} ({c.type_line or 'Unknown'}, CMC {c.cmc or 0})" for c in candidates]
    parts = [
        f"Commander: {commander_name}" + (f" / {partner}" if partner else ""),
        f"Bracket: {deck.bracket or 'unspecified'}",
        f"Archetype tags: {archetype}",
        f"Total cards: {len(deck.cards)}",
        "",
        "PROTECTED — never suggest cutting these:",
        *(f"- {n}" for n in sorted(protected)),
        "",
        "Candidates (eligible to cut):",
        *cand_lines,
        "",
        f"Pick the {count} weakest cards to cut. Return ONLY a JSON object on a "
        "single line with this exact shape (no code fences, no prose):",
        '{"cuts": [{"name": "Card Name", "reasoning": "why it should be cut"}]}',
        "Use card names exactly as written in the candidates list.",
    ]
    return "\n".join(parts)


def _extract_json_object(raw: str) -> dict[str, object] | None:
    """Return the first valid JSON object found in ``raw`` (handles fences)."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            data, _ = decoder.raw_decode(raw[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _parse_cuts(
    raw: str,
    by_name: dict[str, DeckCardItem],
) -> list[CutSuggestion]:
    """Translate the LLM JSON output into ``CutSuggestion`` items.

    Names are matched case-insensitively against the candidate pool. Cards
    not in the candidate pool (hallucinated or protected) are dropped.
    """
    data = _extract_json_object(raw)
    if data is None:
        return []
    raw_cuts = data.get("cuts")
    if not isinstance(raw_cuts, list):
        return []
    out: list[CutSuggestion] = []
    for entry in raw_cuts:
        if not isinstance(entry, dict):
            continue
        entry_dict = cast(dict[str, object], entry)
        name_value = entry_dict.get("name")
        reasoning_value = entry_dict.get("reasoning") or ""
        if not isinstance(name_value, str) or not isinstance(reasoning_value, str):
            continue
        name = name_value
        reasoning = reasoning_value
        card = by_name.get(name.lower())
        if card is None:
            _log.debug("Cuts: dropped LLM-suggested name %r (not in candidates)", name)
            continue
        out.append(
            CutSuggestion(
                scryfall_id=card.scryfall_id,
                name=card.name,
                type_line=card.type_line,
                image_uri=card.image_uri,
                cmc=float(card.cmc) if card.cmc is not None else None,
                reasoning=reasoning,
            )
        )
    return out


async def suggest_cuts(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    deck_id: UUID,
    email: str,
    count: int,
) -> CutsResponse:
    """Recommend cards to cut from ``deck_id`` while protecting combo pieces.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter (chat only).
        deck_id: Target deck.
        email: Owner email used for ACL.
        count: Maximum number of cuts to return.

    Returns:
        CutsResponse with up to ``count`` suggestions and the size of the
        protected set used for the LLM prompt.

    Raises:
        DeckNotFoundError: If the deck does not exist or is not owned by ``email``.
    """
    deck = await deck_service.get_deck(pool, deck_id, email)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    combos: ComboListResponse | None
    try:
        combos = await combo_service.fetch_combos(pool, deck)
    except ComboFetchError as exc:
        _log.warning("Cuts: combo lookup failed (%s); falling back to commander-only", exc)
        combos = None

    protected = _protected_names(deck, combos)
    candidates = _candidate_cards(deck, protected)
    if not candidates:
        return CutsResponse(cuts=[], protected_count=len(protected))

    by_name = {c.name.lower(): c for c in candidates}
    raw = await ai_client.chat(
        system=_build_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(deck, candidates, protected, count),
            }
        ],
        temperature=_LLM_TEMPERATURE,
        max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
    )
    cuts = _parse_cuts(raw, by_name)[:count]
    return CutsResponse(cuts=cuts, protected_count=len(protected))
