"""Hybrid candidate retrieval for targeted card replacement."""

from dataclasses import dataclass

import asyncpg

from mtg_helper.models.ai import CardSearchHit
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse

_MAX_CANDIDATES = 24
_FETCH_LIMIT = 900

_ROLE_TERMS: frozenset[str] = frozenset(
    {
        "anthem",
        "aristocrats",
        "blink",
        "counter",
        "counters",
        "dies",
        "draw",
        "etb",
        "food",
        "graveyard",
        "leaves",
        "ltb",
        "proliferate",
        "ramp",
        "recursion",
        "sacrifice",
        "squirrel",
        "storm",
        "token",
        "tokens",
        "treasure",
    }
)

_FLEX_TERMS: frozenset[str] = frozenset(
    {
        "choose",
        "draw",
        "exile",
        "graveyard",
        "may",
        "return",
        "sacrifice",
        "token",
        "tokens",
        "whenever",
    }
)


@dataclass(frozen=True)
class ReplacementCandidate:
    """Candidate with deterministic retrieval signals for the LLM reranker."""

    card: CardSearchHit
    lane: str
    score: float
    signals: list[str]


def _words(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned = text.lower().replace("+1/+1", "counter").replace("-", " ")
    return {word.strip(".,;:()[]{}\"'") for word in cleaned.split() if len(word) >= 3}


def _deck_colors(deck: DeckDetailResponse) -> list[str]:
    return [color for color in deck.commander_color_identity if color in {"W", "U", "B", "R", "G"}]


def _target_terms(target: DeckCardItem, deck: DeckDetailResponse, complaint: str) -> set[str]:
    terms = (
        set(target.tags or []) | set(target.categories or []) | set(target.qualifying_stages or [])
    )
    terms.update(deck.archetype_tags or [])
    terms.update(_words(target.oracle_text) & _ROLE_TERMS)
    terms.update(_words(target.type_line) & _ROLE_TERMS)
    terms.update(_words(complaint) & _ROLE_TERMS)
    if "squirrel" in _words(target.oracle_text) or "squirrel_tribal" in terms:
        terms.update({"squirrel", "token", "tokens"})
    if "food_matters" in terms:
        terms.update({"food", "token", "sacrifice"})
    return terms


def _cmc_score(target: DeckCardItem, row: asyncpg.Record) -> tuple[float, list[str]]:
    if target.cmc is None or row["cmc"] is None:
        return 0.0, []
    cmc_delta = abs(float(target.cmc) - float(row["cmc"]))
    score = max(0.0, 3.0 - cmc_delta)
    signals = ["similar mana value"] if cmc_delta <= 1 else []
    return score, signals


def _lane_and_score(
    row: asyncpg.Record,
    target: DeckCardItem,
    terms: set[str],
    complaint: str,
) -> tuple[str, float, list[str]]:
    tags = set(row["tags"] or [])
    token_types = set(row["token_types"] or [])
    oracle_words = _words(row["oracle_text"])
    type_words = _words(row["type_line"])
    row_terms = tags | token_types | oracle_words | type_words
    score = 0.0
    signals: list[str] = []

    overlap = terms & row_terms
    if overlap:
        score += len(overlap) * 3.0
        signals.append("matches " + ", ".join(sorted(overlap)[:5]))

    cmc_score, cmc_signals = _cmc_score(target, row)
    score += cmc_score
    signals.extend(cmc_signals)

    flexible = row_terms & _FLEX_TERMS
    if len(flexible) >= 2:
        score += 4.0
        signals.append("flexible Commander utility")

    if "underwhelming" in complaint.lower() and {"whenever", "token", "tokens"} & row_terms:
        score += 2.0
        signals.append("stronger board-presence/persistent value candidate")

    if row["edhrec_rank"] is not None:
        score += max(0.0, 3.0 - min(float(row["edhrec_rank"]), 30000.0) / 10000.0)

    same_type = bool(_words(target.type_line) & type_words)
    if same_type and overlap:
        return "direct_replacement", score + 2.0, signals
    if overlap and flexible:
        return "flexible_utility", score, signals
    return "theme_upgrade", score, signals


def _hit(row: asyncpg.Record) -> CardSearchHit:
    return CardSearchHit(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=float(row["cmc"]) if row["cmc"] is not None else None,
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        tags=list(row["tags"] or []),
        price_eur_cents=row["price_eur_cents"],
    )


async def get_replacement_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    target: DeckCardItem,
    complaint: str,
) -> list[ReplacementCandidate]:
    """Return curated direct, theme-upgrade, and flexible-utility candidates."""
    exclude_names = [card.name for card in deck.cards if "Basic Land" not in (card.type_line or "")]
    sql = """
        SELECT scryfall_id, name, mana_cost, cmc, type_line, oracle_text, color_identity,
               tags, token_types, edhrec_rank,
               ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents
        FROM cards
        WHERE color_identity <@ $1::text[]
          AND name <> ALL($2::text[])
          AND COALESCE(legalities->>'commander', '') = 'legal'
          AND type_line NOT ILIKE '%Land%'
        ORDER BY COALESCE(edhrec_rank, 999999) ASC NULLS LAST
        LIMIT $3
    """
    terms = _target_terms(target, deck, complaint)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, _deck_colors(deck), exclude_names, _FETCH_LIMIT)

    candidates: list[ReplacementCandidate] = []
    for row in rows:
        lane, score, signals = _lane_and_score(row, target, terms, complaint)
        if score < 4.0:
            continue
        candidates.append(
            ReplacementCandidate(card=_hit(row), lane=lane, score=score, signals=signals)
        )
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[:_MAX_CANDIDATES]
