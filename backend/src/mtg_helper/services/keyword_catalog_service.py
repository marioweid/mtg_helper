"""Helpers for optional MTGJSON mechanic filters."""

from dataclasses import dataclass

import asyncpg

from mtg_helper.models.ai import CommanderSuggestIntent
from mtg_helper.services.moxfield_hub_service import load_hub_tags

_CATEGORY_LABELS = {
    "ability_word": "ability word",
    "keyword_ability": "keyword ability",
    "keyword_action": "keyword action",
}

_DESCRIPTIONS = {
    "surveil": "graveyard setup and card selection by looking, binning, or keeping cards",
    "scry": "card selection without putting cards directly into the graveyard",
    "mill": "puts cards from a library into a graveyard; self-mill or opponent mill",
    "dredge": "graveyard recursion that replaces draws and fills the graveyard",
    "flashback": "casts spells from the graveyard once",
    "escape": "casts cards from the graveyard by exiling other cards",
    "descend": "rewards permanents going to your graveyard",
    "threshold": "rewards having seven or more cards in your graveyard",
    "delirium": "rewards having four or more card types in your graveyard",
    "undergrowth": "scales with creature cards in your graveyard",
    "unearth": "temporarily returns creatures from graveyard to battlefield",
    "encore": "graveyard recursion that makes token copies attacking opponents",
    "persist": "creature returns after dying with a -1/-1 counter",
    "undying": "creature returns after dying with a +1/+1 counter",
    "morbid": "checks whether a creature died this turn",
    "landfall": "rewards lands entering the battlefield",
    "proliferate": "adds counters to permanents or players that already have them",
    "investigate": "creates Clue tokens for delayed card draw",
    "connive": "loots, grows creatures, and can put cards into graveyard",
    "discover": "casts or draws into nonland cards from the top of library",
    "explore": "reveals the top card, grows creatures, and can put lands into hand",
    "cascade": "casts free spells from the top of library",
    "storm": "copies a spell for each spell cast before it this turn",
    "magecraft": "rewards casting or copying instants and sorceries",
    "sacrifice": "sacrifices permanents; use for outlets or death-value decks",
    "create": "creates tokens; pair with token type filters for treasures/clues/etc.",
    "treasure": "creates or references Treasure tokens for mana bursts",
    "food": "creates or references Food tokens for life and sacrifice value",
    "forage": "uses Food or graveyard cards as a resource",
    "exile": "moves cards to exile; often supports blink/flicker or cast-from-exile plans",
    "equip": "moves Equipment onto creatures; use for Voltron/equipment plans",
    "toxic": "poison counter combat keyword",
    "infect": "poison and -1/-1 counter combat keyword",
    "lifelink": "life gain through damage",
    "goad": "forces attacks away from you",
}

_ALIASES = {
    "surveil": "self-mill, graveyard setup, card selection",
    "mill": "self mill, graveyard fill",
    "unearth": "reanimate, recur creature",
    "encore": "reanimate, token copies",
    "morbid": "dies, death trigger",
    "landfall": "lands matter",
    "investigate": "clues, artifact tokens, card draw",
    "magecraft": "spellslinger, instants, sorceries",
    "sacrifice": "sac outlet, aristocrats",
    "create": "tokens",
    "exile": "blink, flicker",
    "equip": "equipment, voltron",
}

_TEXT_FILTER_DENYLIST = {
    "etb ping",
    "graveyard commander",
    "draw commander",
}


@dataclass(frozen=True)
class KeywordCatalogItem:
    """One synced MTGJSON keyword row with prompt metadata."""

    tag: str
    label: str
    category: str


async def load_keyword_tags(pool: asyncpg.Pool) -> set[str]:
    """Load the canonical set of MTGJSON keyword tags from the local DB."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT tag FROM mtgjson_keywords")
    return {row["tag"] for row in rows}


async def load_keyword_prompt_catalog(pool: asyncpg.Pool) -> str:
    """Return compact keyword descriptions for the commander suggestor prompt."""
    items = await _load_keywords(pool)
    if not items:
        return "No local MTGJSON keyword catalog is synced. Do not emit mechanic_tags."
    return "\n".join(_prompt_line(item) for item in items)


async def sanitize_commander_intent(
    pool: asyncpg.Pool,
    intent: CommanderSuggestIntent,
) -> CommanderSuggestIntent:
    """Drop invented mechanic tags and normalize dynamic filters."""
    allowed_mechanics = await load_keyword_tags(pool)
    allowed_themes = await load_hub_tags(pool)
    data = intent.model_dump()
    data["archetype_tags"] = [tag for tag in intent.archetype_tags if tag in allowed_themes]
    data["mechanic_tags"] = [tag for tag in intent.mechanic_tags if tag in allowed_mechanics]
    data["oracle_terms"] = _filter_text_terms(intent.oracle_terms)
    data["required_phrases"] = _filter_text_terms(intent.required_phrases)
    data["excluded_phrases"] = _filter_text_terms(intent.excluded_phrases)
    return CommanderSuggestIntent(**data)


async def _load_keywords(pool: asyncpg.Pool) -> list[KeywordCatalogItem]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, label, category
            FROM mtgjson_keywords
            ORDER BY category, label
            """
        )
    return [
        KeywordCatalogItem(tag=row["tag"], label=row["label"], category=row["category"])
        for row in rows
    ]


def _prompt_line(item: KeywordCatalogItem) -> str:
    category = _CATEGORY_LABELS.get(item.category, item.category)
    description = _DESCRIPTIONS.get(item.tag, f"official MTGJSON {category}")
    aliases = _ALIASES.get(item.tag)
    alias_text = f"; aliases: {aliases}" if aliases else ""
    return f"- {item.tag}: {item.label} ({category}) - {description}{alias_text}"


def _filter_text_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        normalized = " ".join(term.lower().split())
        if normalized in _TEXT_FILTER_DENYLIST or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
