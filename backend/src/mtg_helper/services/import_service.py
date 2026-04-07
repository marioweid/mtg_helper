"""Deck import service: parse text deck lists and create decks from them."""

import logging
import re
from dataclasses import dataclass

import asyncpg

from mtg_helper.models.decks import DeckCreate, DeckImportRequest, DeckImportResponse
from mtg_helper.services import card_service, deck_service
from mtg_helper.services.deck_service import CardNotFoundError

_log = logging.getLogger(__name__)

# Sections that signal sideboard / non-main-deck content — skip their cards.
_SKIP_SECTIONS = frozenset({"sideboard", "maybeboard", "sb", "maybe"})

# Map common section header names to deck categories.
_SECTION_TO_CATEGORY: dict[str, str | None] = {
    "commander": None,
    "ramp": "ramp",
    "draw": "draw",
    "card draw": "draw",
    "card advantage": "draw",
    "removal": "interaction",
    "interaction": "interaction",
    "instants": "interaction",
    "instant": "interaction",
    "theme": "theme",
    "core": "theme",
    "creatures": "theme",
    "creature": "theme",
    "enchantments": "theme",
    "enchantment": "theme",
    "artifacts": "theme",
    "artifact": "theme",
    "sorceries": "theme",
    "sorcery": "theme",
    "planeswalkers": "theme",
    "planeswalker": "theme",
    "utility": "utility",
    "lands": "lands",
    "land": "lands",
    "mana base": "lands",
}

# Match a card line: optional qty, name, optional (SET) num, optional *CMDR*
_CARD_LINE = re.compile(
    r"^(\d+)?\s*"
    r"(.+?)"
    r"(?:\s*\([A-Za-z0-9]+\)(?:\s+\d+)?)?"
    r"(\s*\*CMDR\*)?"
    r"\s*$",
    re.IGNORECASE,
)


@dataclass
class ParsedCard:
    """A single entry parsed from a deck list."""

    name: str
    quantity: int = 1
    is_commander: bool = False
    category: str | None = None


_BARE_SKIP = re.compile(r"^(sideboard|maybeboard|sb):?\s*$", re.IGNORECASE)


def _handle_section_header(line: str) -> tuple[str | None, bool]:
    """Parse a '//' section header line.

    Returns:
        Tuple of (category_or_none, is_skip_section).
    """
    section_text = line[2:].strip().lower()
    is_skip = section_text in _SKIP_SECTIONS
    category = None if is_skip else _SECTION_TO_CATEGORY.get(section_text, "theme")
    return category, is_skip


def _parse_card_entry(line: str, current_category: str | None) -> ParsedCard | None:
    """Parse a single card line into a ParsedCard, or return None if not a card line."""
    m = _CARD_LINE.match(line)
    if m is None:
        return None
    qty_str, raw_name, cmdr_tag = m.group(1), m.group(2), m.group(3)
    name = raw_name.strip()
    if not name:
        return None
    is_commander = bool(cmdr_tag)
    return ParsedCard(
        name=name,
        quantity=int(qty_str) if qty_str else 1,
        is_commander=is_commander,
        category=None if is_commander else current_category,
    )


def parse_deck_list(text: str) -> list[ParsedCard]:
    """Parse a deck list from common text formats into ParsedCard entries.

    Handles Moxfield, MTGO, TappedOut, and Archidekt formats.
    Lines matching ``// Header`` at the start of a line are section headers.
    Mid-line ``//`` (as in split card names like ``Fire // Ice``) are preserved.
    Sideboard/Maybeboard sections are skipped entirely.

    Args:
        text: Raw deck list text pasted by the user.

    Returns:
        List of ParsedCard entries (commander and non-commander).

    Raises:
        ValueError: If no valid card lines are found in the text.
    """
    cards: list[ParsedCard] = []
    current_category: str | None = None
    skip_section = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("//"):
            current_category, skip_section = _handle_section_header(line)
            continue
        if _BARE_SKIP.match(line):
            skip_section = True
            continue
        if skip_section:
            continue
        card = _parse_card_entry(line, current_category)
        if card is not None:
            cards.append(card)

    if not cards:
        raise ValueError(
            "No valid card lines found. Ensure your deck list uses the format "
            "'1 Card Name' per line."
        )
    return cards


async def _resolve_non_commanders(
    pool: asyncpg.Pool,
    entries: list[ParsedCard],
    commander_identity: set[str],
) -> tuple[list[tuple[str, int, str | None]], list[str], list[str]]:
    """Resolve non-commander card entries against the local DB.

    Args:
        pool: asyncpg connection pool.
        entries: Non-commander card entries from the parsed deck list.
        commander_identity: Commander's color identity as a set of color letters.

    Returns:
        Tuple of (resolved_cards, unresolved_names, color_violation_names).
        resolved_cards is a list of (scryfall_id_str, quantity, category).
    """
    resolved: list[tuple[str, int, str | None]] = []
    unresolved: list[str] = []
    violations: list[str] = []
    for entry in entries:
        card = await card_service.resolve_card_by_name(pool, entry.name)
        if card is None:
            _log.debug("Unresolved card: %s", entry.name)
            unresolved.append(entry.name)
            continue
        if set(card.color_identity) - commander_identity:
            _log.debug("Color violation: %s", card.name)
            violations.append(card.name)
            continue
        resolved.append((str(card.scryfall_id), entry.quantity, entry.category))
    return resolved, unresolved, violations


async def import_deck(pool: asyncpg.Pool, data: DeckImportRequest) -> DeckImportResponse:
    """Import a deck from a pasted text deck list.

    Parses the deck list, resolves card names against the local DB using fuzzy
    matching, creates the deck with stage 'complete', and bulk-inserts all cards.
    Color identity violations and unresolved names are collected and returned.

    Args:
        pool: asyncpg connection pool.
        data: Import request with deck list text and deck metadata.

    Returns:
        DeckImportResponse with the created deck and per-card results.

    Raises:
        ValueError: If no commander is found or the deck list contains no cards.
        CardNotFoundError: If the commander cannot be resolved in the local DB.
    """
    parsed = parse_deck_list(data.deck_list)
    commanders = [c for c in parsed if c.is_commander]
    non_commanders = [c for c in parsed if not c.is_commander]

    if not commanders:
        raise ValueError(
            "No commander found. Mark your commander with *CMDR* at the end of the line, "
            "e.g. '1 Hazel of the Rootbloom *CMDR*'."
        )

    # Resolve commander(s) — first is main, second is partner.
    commander_card = await card_service.resolve_card_by_name(pool, commanders[0].name)
    if commander_card is None:
        raise CardNotFoundError(
            f"Commander '{commanders[0].name}' not found in the local card database. "
            "Try syncing cards first."
        )

    partner_card = None
    if len(commanders) > 1:
        partner_card = await card_service.resolve_card_by_name(pool, commanders[1].name)
        if partner_card is None:
            _log.warning("Partner '%s' not found, ignoring", commanders[1].name)

    # Create the deck (stage defaults to "created"; we update it after import).
    deck = await deck_service.create_deck(
        pool,
        DeckCreate(
            commander_scryfall_id=commander_card.scryfall_id,
            partner_scryfall_id=partner_card.scryfall_id if partner_card else None,
            name=data.name,
            description=data.description,
            bracket=data.bracket,
            owner_id=data.owner_id,
        ),
    )

    commander_identity = set(commander_card.color_identity)
    resolved_cards, unresolved, color_violations = await _resolve_non_commanders(
        pool, non_commanders, commander_identity
    )

    # Bulk insert resolved cards directly to avoid N sequential round-trips.
    if resolved_cards:
        await _bulk_insert_cards(pool, deck.id, resolved_cards)

    # Advance stage to "complete" — imported decks skip the build wizard.
    await deck_service.update_deck(pool, deck.id, deck_service.DeckUpdate(stage="complete"))

    _log.info(
        "Imported deck '%s' (%s): %d cards, %d unresolved, %d color violations",
        data.name,
        deck.id,
        len(resolved_cards),
        len(unresolved),
        len(color_violations),
    )

    # Re-fetch to get updated stage.
    updated_deck = await deck_service._fetch_deck(pool, deck.id)

    return DeckImportResponse(
        deck=updated_deck,  # type: ignore[arg-type]
        imported_count=len(resolved_cards),
        unresolved=unresolved,
        color_violations=color_violations,
    )


async def _bulk_insert_cards(
    pool: asyncpg.Pool,
    deck_id: object,
    cards: list[tuple[str, int, str | None]],
) -> None:
    """Bulk-insert resolved cards into a deck using executemany.

    Args:
        pool: asyncpg connection pool.
        deck_id: UUID of the deck to insert into.
        cards: List of (scryfall_id_str, quantity, category) tuples.
    """
    async with pool.acquire() as conn:
        # Resolve scryfall_ids to internal card UUIDs in bulk.
        scryfall_ids = [row[0] for row in cards]
        id_rows = await conn.fetch(
            "SELECT id, scryfall_id FROM cards WHERE scryfall_id = ANY($1::uuid[])",
            scryfall_ids,
        )
        scryfall_to_id = {str(r["scryfall_id"]): r["id"] for r in id_rows}

        inserts: list[tuple] = []
        for scryfall_id_str, quantity, category in cards:
            card_id = scryfall_to_id.get(scryfall_id_str)
            if card_id is None:
                continue
            inserts.append((deck_id, card_id, quantity, category))

        if inserts:
            await conn.executemany(
                """
                INSERT INTO deck_cards (deck_id, card_id, quantity, category, added_by)
                VALUES ($1, $2, $3, $4, 'user')
                ON CONFLICT (deck_id, card_id)
                DO UPDATE SET quantity = EXCLUDED.quantity,
                              category = COALESCE(EXCLUDED.category, deck_cards.category)
                """,
                inserts,
            )
