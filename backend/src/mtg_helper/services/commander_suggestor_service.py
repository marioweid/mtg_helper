"""Interactive local commander suggestion service."""

import json
import re
from dataclasses import dataclass
from typing import Any

import asyncpg

from mtg_helper.models.ai import (
    CommanderSuggestIntent,
    CommanderSuggestion,
    CommanderSuggestResponse,
)
from mtg_helper.models.cards import CardResponse

_WUBRG = ["W", "U", "B", "R", "G"]
_DEFAULT_STAGE_TARGETS = {"ramp": 12, "draw": 12, "interaction": 12, "lands": 38}

_ARCHETYPE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("graveyard", ("graveyard", "grave", "recursion", "yard")),
    ("reanimator", ("reanimator", "reanimate", "cheat in", "big value")),
    ("blink", ("blink", "flicker", "etb", "enter the battlefield")),
    ("aristocrats", ("aristocrat", "death trigger", "dies")),
    ("sacrifice", ("sacrifice", "sac outlet", "sac ")),
    ("token", ("token", "tokens")),
    ("landfall", ("landfall", "lands")),
    ("spellslinger", ("spellslinger", "instant", "sorcery")),
    ("storm", ("storm",)),
    ("cascade", ("cascade",)),
    ("wheels", ("wheel", "discard hand")),
    ("lifegain", ("lifegain", "life gain")),
    ("plus_one_counters", ("+1/+1", "counters")),
    ("voltron", ("voltron", "auras", "equipment")),
    ("equipment", ("equipment",)),
    ("mill", ("mill", "self mill", "self-mill")),
    ("treasure_matters", ("treasure",)),
    ("food_matters", ("food", "forage")),
    ("clue_matters", ("clue", "investigate")),
)

_MECHANIC_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dredge", ("dredge",)),
    ("escape", ("escape",)),
    ("flashback", ("flashback",)),
    ("disturb", ("disturb",)),
    ("encore", ("encore",)),
    ("descend", ("descend",)),
    ("forage", ("forage",)),
    ("plot", ("plot",)),
    ("saddle", ("saddle",)),
    ("discover", ("discover",)),
    ("explore", ("explore",)),
    ("proliferate", ("proliferate",)),
)

_TRAIT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("etb", ("etb", "enter the battlefield", "enters the battlefield")),
    ("activated", ("activated ability", "tap ability")),
    ("evasion", ("evasion", "flying", "unblockable")),
)

_TOKEN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("treasure", ("treasure",)),
    ("food", ("food",)),
    ("clue", ("clue", "investigate")),
    ("zombie", ("zombie",)),
    ("squirrel", ("squirrel",)),
    ("spirit", ("spirit",)),
    ("dragon", ("dragon",)),
)

_COLOR_WORDS = {
    "white": "W",
    "azorius": "WU",
    "blue": "U",
    "dimir": "UB",
    "black": "B",
    "rakdos": "BR",
    "red": "R",
    "gruul": "RG",
    "green": "G",
    "selesnya": "GW",
    "orzhov": "WB",
    "izzet": "UR",
    "golgari": "BG",
    "boros": "RW",
    "simic": "GU",
    "esper": "WUB",
    "grixis": "UBR",
    "jund": "BRG",
    "naya": "RGW",
    "bant": "GWU",
    "abzan": "WBG",
    "jeskai": "URW",
    "sultai": "BGU",
    "mardu": "RWB",
    "temur": "GUR",
    "five color": "WUBRG",
    "5 color": "WUBRG",
    "five-color": "WUBRG",
}


@dataclass(frozen=True)
class _Candidate:
    """Internal local commander candidate with ranking-only fields."""

    card: CardResponse
    tags: list[str]
    traits: list[str]
    token_types: list[str]


def _parse_jsonb(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _row_to_candidate(row: asyncpg.Record) -> _Candidate:
    card = CardResponse(
        id=row["id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        colors=list(row["colors"] or []),
        keywords=list(row["keywords"] or []),
        power=row["power"],
        toughness=row["toughness"],
        legalities=_parse_jsonb(row["legalities"]),
        image_uri=row["image_uri"],
        prices=_parse_jsonb(row["prices"]),
        rarity=row["rarity"],
        set_code=row["set_code"],
        released_at=row["released_at"],
        edhrec_rank=row["edhrec_rank"],
        game_changer=bool(row["game_changer"]),
    )
    return _Candidate(
        card=card,
        tags=list(row["tags"] or []),
        traits=list(row["traits"] or []),
        token_types=list(row["token_types"] or []),
    )


def _ordered_colors(colors: set[str]) -> list[str]:
    return [color for color in _WUBRG if color in colors]


def parse_intent_fallback(
    message: str,
    previous: CommanderSuggestIntent | None,
) -> CommanderSuggestIntent:
    """Infer useful intent from obvious words when the LLM is unavailable."""
    merged = previous.model_copy(deep=True) if previous else CommanderSuggestIntent()
    text = message.lower()
    merged.archetype_tags = _merge_vocab(
        merged.archetype_tags,
        _match_hints(text, _ARCHETYPE_HINTS),
    )
    merged.mechanic_tags = _merge_vocab(merged.mechanic_tags, _match_hints(text, _MECHANIC_HINTS))
    merged.traits = _merge_vocab(merged.traits, _match_hints(text, _TRAIT_HINTS))
    merged.token_types = _merge_vocab(merged.token_types, _match_hints(text, _TOKEN_HINTS))
    colors = _extract_colors(text)
    if colors:
        merged.color_identity = colors
    if text.strip():
        merged.direction = text.strip()[:500]
    return merged


def _match_hints(text: str, hints: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    return [tag for tag, needles in hints if any(needle in text for needle in needles)]


def _merge_vocab(current: list[str], additions: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in (*current, *additions):
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _extract_colors(text: str) -> list[str] | None:
    found: set[str] = set()
    for word, colors in _COLOR_WORDS.items():
        if word in text:
            found.update(colors)
    if not found:
        return None
    return _ordered_colors(found)


async def suggest_commanders(
    pool: asyncpg.Pool,
    intent: CommanderSuggestIntent,
    *,
    limit: int = 8,
) -> list[CommanderSuggestion]:
    """Rank local legal commander candidates for a structured intent."""
    candidates = await _fetch_candidates(pool)
    ranked = [_score_candidate(candidate, intent) for candidate in candidates]
    filtered = [item for item in ranked if item.score > 0 or not _has_specific_intent(intent)]
    filtered.sort(key=lambda item: (-item.score, item.card.edhrec_rank or 999999, item.card.name))
    return filtered[:limit]


async def build_response(
    pool: asyncpg.Pool,
    *,
    reply: str,
    done: bool,
    intent: CommanderSuggestIntent,
    limit: int,
) -> CommanderSuggestResponse:
    """Build a complete suggestor response from intent plus deterministic ranking."""
    commanders = await suggest_commanders(pool, intent, limit=limit)
    return CommanderSuggestResponse(
        reply=reply,
        done=done,
        intent=intent,
        commanders=commanders,
        stage_targets=_stage_targets(intent),
        suggested_name=_suggested_name(intent),
    )


async def _fetch_candidates(pool: asyncpg.Pool) -> list[_Candidate]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM cards
            WHERE legalities->>'commander' = 'legal'
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND COALESCE(type_line, '') NOT ILIKE '%Conspiracy%'
              AND COALESCE(type_line, '') ILIKE '%Legendary%'
              AND (
                COALESCE(type_line, '') ILIKE '%Creature%'
                OR COALESCE(oracle_text, '') ILIKE '%can be your commander%'
              )
            ORDER BY edhrec_rank ASC NULLS LAST, name ASC
            LIMIT 1500
            """
        )
    return [_row_to_candidate(row) for row in rows]


def _score_candidate(candidate: _Candidate, intent: CommanderSuggestIntent) -> CommanderSuggestion:
    reasons: list[str] = []
    score = _color_score(candidate.card.color_identity, intent, reasons)
    matched_tags = _intersection(candidate.tags, [*intent.archetype_tags, *intent.mechanic_tags])
    matched_traits = _intersection(candidate.traits, intent.traits)
    matched_tokens = _intersection(candidate.token_types, intent.token_types)

    score += len(matched_tags) * 10
    score += len(matched_traits) * 8
    score += len(matched_tokens) * 6
    reasons.extend(_match_reasons(matched_tags, matched_traits, matched_tokens))
    advantage_reasons = _card_advantage_reasons(candidate.card.oracle_text)
    if advantage_reasons:
        score += 14 + min(len(advantage_reasons), 3) * 3
        reasons.append("Card advantage in command zone")
    if candidate.card.edhrec_rank:
        score += max(0, 8 - candidate.card.edhrec_rank / 10000)
    score += _text_intent_score(candidate.card.oracle_text, intent, reasons)

    return CommanderSuggestion(
        card=candidate.card,
        score=round(float(score), 3),
        score_reasons=_dedupe(reasons)[:6],
        matched_tags=matched_tags,
        matched_traits=matched_traits,
        matched_token_types=matched_tokens,
        card_advantage_reasons=advantage_reasons,
    )


def _color_score(colors: list[str], intent: CommanderSuggestIntent, reasons: list[str]) -> float:
    color_set = set(colors)
    if color_set & set(intent.excluded_colors):
        return -100
    requested = set(intent.color_identity or [])
    if not requested:
        return 2
    if not color_set <= requested:
        return -100
    if color_set == requested:
        reasons.append("Matches requested colors")
        return 14
    reasons.append("Fits within requested colors")
    return 8


def _intersection(left: list[str], right: list[str]) -> list[str]:
    allowed = set(right)
    return [item for item in left if item in allowed]


def _match_reasons(tags: list[str], traits: list[str], tokens: list[str]) -> list[str]:
    reasons: list[str] = []
    if tags:
        reasons.append("Theme overlap")
    if "graveyard" in tags or "reanimator" in tags:
        reasons.append("Graveyard engine")
    if "etb" in traits or "blink" in tags:
        reasons.append("ETB payoff")
    if tokens:
        reasons.append("Token synergy")
    return reasons


def _card_advantage_reasons(oracle_text: str | None) -> list[str]:
    text = (oracle_text or "").lower()
    patterns = (
        ("Draws cards", r"\bdraw (?:a card|two cards|three cards|x cards|\d+ cards)"),
        ("Filters cards", r"\bscry\b|\bsurveil\b|\binvestigate\b|\bdiscover\b|\bexplore\b"),
        ("Reuses graveyard", r"from your graveyard|from a graveyard|return .* graveyard"),
        ("Plays extra cards", r"play .* exile|cast .* exile|cast .* graveyard|copy .* spell"),
        ("Makes resources", r"create .* token|create .* treasure|create .* clue|create .* food"),
    )
    return [label for label, pattern in patterns if re.search(pattern, text)]


def _text_intent_score(
    oracle_text: str | None,
    intent: CommanderSuggestIntent,
    reasons: list[str],
) -> float:
    text = (oracle_text or "").lower()
    score = 0.0
    if "graveyard" in intent.archetype_tags and "graveyard" in text:
        score += 6
        reasons.append("Mentions graveyard")
    if "etb" in intent.traits and "enters" in text:
        score += 6
        reasons.append("Mentions entering the battlefield")
    if "reanimator" in intent.archetype_tags and "battlefield" in text and "graveyard" in text:
        score += 5
        reasons.append("Supports reanimation")
    if "sacrifice" in intent.archetype_tags and "sacrifice" in text:
        score += 5
        reasons.append("Sacrifice outlet or payoff")
    return score


def _stage_targets(intent: CommanderSuggestIntent) -> dict[str, int]:
    targets = dict(_DEFAULT_STAGE_TARGETS)
    if "spellslinger" in intent.archetype_tags or "storm" in intent.archetype_tags:
        targets["draw"] = 14
    if "reanimator" in intent.archetype_tags or "graveyard" in intent.archetype_tags:
        targets["interaction"] = 10
    return targets


def _suggested_name(intent: CommanderSuggestIntent) -> str | None:
    if not intent.archetype_tags:
        return None
    label = intent.archetype_tags[0].replace("_", " ").title()
    return f"{label} Brew"


def _has_specific_intent(intent: CommanderSuggestIntent) -> bool:
    return bool(
        intent.archetype_tags
        or intent.mechanic_tags
        or intent.traits
        or intent.token_types
        or intent.color_identity
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
