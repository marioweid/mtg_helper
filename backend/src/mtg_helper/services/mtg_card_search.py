"""Typed, deterministic card search for the conversational MTG Assistant."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Self
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field, field_validator, model_validator

from mtg_helper.models.ai import CardSearchHit
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.scryfall_tag_repository import require_tag_ids

_MAX_RESULTS = 20
_SEARCH_POOL_SIZE = 250
_MANA_SYMBOL_RE = re.compile(
    r"^\{(?:[0-9]+|[WUBRGCSXYZ]|[WUBRG]/[WUBRGP]|2/[WUBRG])\}$",
    re.IGNORECASE,
)


class CardSearchRanking(StrEnum):
    """Supported deterministic result orderings."""

    THEME_SYNERGY = "theme_synergy"
    COMMANDER_FIT = "commander_fit"
    POPULARITY = "popularity"
    PRICE = "price"
    MANA_VALUE = "mana_value"


class CardEvidenceSource(StrEnum):
    """Candidate-pool provenance exposed to the assistant."""

    GLOBAL_SEARCH = "global_search"
    GLOBAL_FALLBACK = "global_fallback"
    NONE = "none"


class AssistantCardSearchInput(BaseModel):
    """Bounded structural filters accepted by the assistant's search tool."""

    theme_hints: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Natural strategy phrases used only as ordinary text context.",
    )
    theme_tags: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Scryfall Oracle-tag UUIDs from the source catalog.",
    )
    mana_cost_symbols: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Exact symbols required in printed mana_cost, such as {X}, {U}, or {2/W}.",
    )
    mana_value_min: float | None = Field(
        default=None, ge=0, le=30, description="Minimum mana value, not a mana-cost symbol."
    )
    mana_value_max: float | None = Field(
        default=None, ge=0, le=30, description="Maximum mana value, not a mana-cost symbol."
    )
    card_types: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Required card types such as Creature, Instant, or Land.",
    )
    subtypes: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Required subtypes such as Hydra, Elf, or Aura.",
    )
    oracle_text_all: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Every phrase must occur in oracle text.",
    )
    oracle_text_any: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="At least one phrase must occur in oracle text.",
    )
    required_tags: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Every required Scryfall Oracle-tag UUID.",
    )
    excluded_tags: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Scryfall Oracle-tag UUIDs that the card must not have.",
    )
    exclude_game_changers: bool = Field(
        default=False,
        description="Exclude Game Changer cards so additions stay bracket-3 legal.",
    )
    collection_only: bool = Field(
        default=False,
        description=(
            "Restrict results to cards the user already owns in their linked "
            "collections. Set when the user asks for cards they own or wants "
            "to use only their collection."
        ),
    )
    min_price_eur_cents: int | None = Field(
        default=None, ge=0, le=1_000_000, description="Minimum known EUR price in cents."
    )
    max_price_eur_cents: int | None = Field(
        default=None, ge=0, le=1_000_000, description="Maximum known EUR price in cents."
    )
    exclude_deck_cards: bool = Field(
        default=True, description="Exclude cards already in the deck and command zone."
    )
    ranking: CardSearchRanking = Field(
        default=CardSearchRanking.THEME_SYNERGY,
        description="Deterministic primary ordering for matching cards.",
    )
    limit: int = Field(default=12, ge=1, le=_MAX_RESULTS, description="Maximum returned cards.")

    @field_validator("theme_tags", "required_tags", "excluded_tags")
    @classmethod
    def _validate_theme_tags(cls, value: list[str]) -> list[str]:
        tags = _normalize_list(value)
        try:
            return [str(UUID(tag)) for tag in tags]
        except ValueError as exc:
            raise ValueError("source tag filters must be Scryfall UUIDs") from exc

    @field_validator("theme_hints")
    @classmethod
    def _normalize_theme_hints(cls, value: list[str]) -> list[str]:
        hints = [" ".join(item.strip().split()) for item in value]
        return [item for item in hints if item]

    @field_validator("mana_cost_symbols")
    @classmethod
    def _validate_mana_symbols(cls, value: list[str]) -> list[str]:
        symbols = _normalize_list(value, upper=True)
        invalid = [symbol for symbol in symbols if not _MANA_SYMBOL_RE.fullmatch(symbol)]
        if invalid:
            raise ValueError(f"invalid mana symbol: {invalid[0]}")
        return symbols

    @field_validator("card_types", "subtypes")
    @classmethod
    def _normalize_types(cls, value: list[str]) -> list[str]:
        return [item.title() for item in _normalize_list(value)]

    @field_validator("oracle_text_all", "oracle_text_any")
    @classmethod
    def _normalize_oracle_terms(cls, value: list[str]) -> list[str]:
        terms = _normalize_list(value)
        if any(len(term) > 80 for term in terms):
            raise ValueError("oracle text filters must be at most 80 characters")
        if any(any(char in term for char in ("%", "_", "\\")) for term in terms):
            raise ValueError("oracle text filters cannot contain SQL wildcard characters")
        return terms

    @model_validator(mode="after")
    def _validate_ranges(self) -> Self:
        _validate_range("mana value", self.mana_value_min, self.mana_value_max)
        _validate_range("price", self.min_price_eur_cents, self.max_price_eur_cents)
        overlap = set(self.required_tags) & set(self.excluded_tags)
        if overlap:
            raise ValueError(f"tags cannot be both required and excluded: {min(overlap)}")
        return self


class CardSearchCandidate(BaseModel):
    """One grounded card with compact deterministic ranking evidence."""

    card: CardSearchHit
    evidence_source: CardEvidenceSource
    matched_theme_tags: list[str] = Field(default_factory=list)
    theme_score: float = 0.0
    matched_filters: list[str] = Field(default_factory=list)
    commander_matches: list[str] = Field(default_factory=list)
    role_matches: list[str] = Field(default_factory=list)
    game_changer: bool = False
    owned_quantity: int = 0


class CardSearchResult(BaseModel):
    """Search results plus enough provenance for honest fallback messaging."""

    evidence_source: CardEvidenceSource
    resolved_theme_tags: list[str] = Field(default_factory=list)
    candidates: list[CardSearchCandidate] = Field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True, slots=True)
class _ThemeEvidence:
    score: float
    tags: tuple[str, ...]


async def search_cards(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    filters: AssistantCardSearchInput,
    *,
    owned_card_ids: frozenset[UUID] | None = None,
) -> CardSearchResult:
    """Search legal cards globally and use resolved theme statistics as ranking evidence.

    Args:
        pool: Database pool.
        deck: The deck the search runs for (color identity, existing cards).
        filters: Structured search filters from the assistant.
        owned_card_ids: Optional canonical card ids owned by the account. When
            provided, results are restricted to these cards (collection-only).
    """
    selected_tags = list(dict.fromkeys([*filters.theme_tags, *filters.required_tags]))
    await require_tag_ids(pool, [UUID(tag) for tag in selected_tags])
    filters = filters.model_copy(update={"required_tags": selected_tags})
    resolved_tags = list(filters.theme_tags)
    evidence: dict[UUID, _ThemeEvidence] = {}
    source = CardEvidenceSource.GLOBAL_SEARCH
    candidates, actual_source = await _query_candidates(
        pool,
        deck,
        filters,
        source,
        evidence,
        fallback_tags=[],
        owned_card_ids=owned_card_ids,
    )
    return CardSearchResult(
        evidence_source=actual_source,
        resolved_theme_tags=resolved_tags,
        candidates=candidates,
        message=None,
    )


async def _resolve_discovery_themes(
    pool: asyncpg.Pool, filters: AssistantCardSearchInput
) -> list[str]:
    return list(filters.theme_tags)


async def _query_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    filters: AssistantCardSearchInput,
    source: CardEvidenceSource,
    evidence: dict[UUID, _ThemeEvidence],
    *,
    fallback_tags: list[str] | None = None,
    owned_card_ids: frozenset[UUID] | None = None,
) -> tuple[list[CardSearchCandidate], CardEvidenceSource]:
    hub_ids = sorted(evidence, key=lambda card_id: evidence[card_id].score, reverse=True)
    rows = await _fetch_candidates(pool, deck, filters, hub_ids, [], owned_card_ids=owned_card_ids)
    candidates = [_candidate(row, deck, filters, source, evidence) for row in rows]
    if not candidates and hub_ids:
        # Automatic global fallback: identical filters without theme evidence.
        rows = await _fetch_candidates(pool, deck, filters, [], [], owned_card_ids=owned_card_ids)
        candidates = [
            _candidate(row, deck, filters, CardEvidenceSource.GLOBAL_FALLBACK, {}) for row in rows
        ]
        return candidates[: filters.limit], CardEvidenceSource.GLOBAL_FALLBACK
    if fallback_tags and not hub_ids:
        # Local-tag fallback: no hub evidence, restrict to locally tagged theme cards.
        rows = await _fetch_candidates(
            pool, deck, filters, [], fallback_tags, owned_card_ids=owned_card_ids
        )
        candidates = [
            _candidate(row, deck, filters, CardEvidenceSource.GLOBAL_FALLBACK, {}) for row in rows
        ]
        if candidates or owned_card_ids is None:
            return candidates[: filters.limit], CardEvidenceSource.GLOBAL_FALLBACK
        # Collection-only: the user wants their cards; when the tagged pool has no
        # owned matches, retry without the tag restriction so owned cards that
        # match every other filter are still surfaced (fit is judged in prose).
        rows = await _fetch_candidates(pool, deck, filters, [], [], owned_card_ids=owned_card_ids)
        candidates = [
            _candidate(row, deck, filters, CardEvidenceSource.GLOBAL_FALLBACK, {}) for row in rows
        ]
        return candidates[: filters.limit], CardEvidenceSource.GLOBAL_FALLBACK
    if fallback_tags:
        # Theme-text supplement: locally tagged theme cards that the hub sample
        # missed (e.g. budget or casual payoffs), ranked after evidence cards.
        supplement = await _fetch_candidates(
            pool, deck, filters, [], fallback_tags, owned_card_ids=owned_card_ids
        )
        seen_ids = {row["id"] for row in rows}
        candidates.extend(
            _candidate(row, deck, filters, source, {})
            for row in supplement
            if row["id"] not in seen_ids
        )
    return candidates[: filters.limit], source


async def _fetch_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    filters: AssistantCardSearchInput,
    hub_ids: list[UUID],
    fallback_tags: list[str],
    *,
    owned_card_ids: frozenset[UUID] | None = None,
) -> list[asyncpg.Record]:
    where, args = _build_filters(
        deck, filters, fallback_tags=fallback_tags, owned_card_ids=owned_card_ids
    )
    if hub_ids:
        _add_filter(where, args, "id = ANY($N::uuid[])", hub_ids)
    order_by = _build_order(filters.ranking, deck, hub_ids, args)
    sql = _CARD_SELECT + " WHERE " + " AND ".join(where) + order_by
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


def _build_filters(
    deck: DeckDetailResponse,
    filters: AssistantCardSearchInput,
    *,
    fallback_tags: list[str] | None = None,
    owned_card_ids: frozenset[UUID] | None = None,
) -> tuple[list[str], list[object]]:
    where = [
        "is_canonical",
        "color_identity <@ $1::text[]",
        "legalities->>'commander' = 'legal'",
        "COALESCE(border_color, '') != 'gold'",
        "COALESCE(security_stamp, '') != 'acorn'",
        "type_line NOT LIKE '%Conspiracy%'",
    ]
    args: list[object] = [list(deck.commander_color_identity)]
    if filters.exclude_deck_cards:
        _add_filter(where, args, "NOT (id = ANY($N::uuid[]))", _deck_card_ids(deck))
    if owned_card_ids is not None:
        _add_filter(where, args, "id = ANY($N::uuid[])", list(owned_card_ids))
    _add_optional_filters(where, args, filters)
    return where, args


def _add_optional_filters(
    where: list[str], args: list[object], filters: AssistantCardSearchInput
) -> None:
    if filters.exclude_game_changers:
        where.append("NOT game_changer")
    values: tuple[tuple[bool, str, object], ...] = (
        (
            bool(filters.mana_cost_symbols),
            "mana_cost LIKE ALL($N::text[])",
            _patterns(filters.mana_cost_symbols),
        ),
        (filters.mana_value_min is not None, "cmc >= $N", filters.mana_value_min),
        (filters.mana_value_max is not None, "cmc <= $N", filters.mana_value_max),
        (bool(filters.card_types), "card_types @> $N::text[]", filters.card_types),
        (bool(filters.subtypes), "subtypes @> $N::text[]", filters.subtypes),
        (
            bool(filters.oracle_text_all),
            "oracle_text ILIKE ALL($N::text[])",
            _patterns(filters.oracle_text_all),
        ),
        (
            bool(filters.oracle_text_any),
            "oracle_text ILIKE ANY($N::text[])",
            _patterns(filters.oracle_text_any),
        ),
        (
            filters.min_price_eur_cents is not None,
            _PRICE_SQL + " >= $N",
            filters.min_price_eur_cents,
        ),
        (
            filters.max_price_eur_cents is not None,
            _PRICE_SQL + " <= $N",
            filters.max_price_eur_cents,
        ),
    )
    for active, clause, value in values:
        if active:
            _add_filter(where, args, clause, value)
    if filters.required_tags:
        _add_filter(
            where,
            args,
            "(SELECT count(DISTINCT tag_id) FROM scryfall_tag_memberships "
            "WHERE oracle_id = cards.oracle_id AND tag_id = ANY($N::uuid[])) = $M",
            [UUID(tag) for tag in filters.required_tags],
        )
        where[-1] = where[-1].replace("$M", str(len(filters.required_tags)))
    if filters.excluded_tags:
        _add_filter(
            where,
            args,
            "NOT EXISTS (SELECT 1 FROM scryfall_tag_memberships WHERE oracle_id = cards.oracle_id "
            "AND tag_id = ANY($N::uuid[]))",
            [UUID(tag) for tag in filters.excluded_tags],
        )


def _build_order(
    ranking: CardSearchRanking,
    deck: DeckDetailResponse,
    hub_ids: list[UUID],
    args: list[object],
) -> str:
    commander_terms = sorted(_commander_words(deck))
    args.append(commander_terms)
    match_sql = _COMMANDER_MATCH_SQL.replace("$N", f"${len(args)}")
    if hub_ids:
        hub_arg = next(i for i, value in enumerate(args, start=1) if value is hub_ids)
        return (
            f" ORDER BY array_position(${hub_arg}::uuid[], id), {match_sql} DESC, "
            f"COALESCE(edhrec_rank, 999999) LIMIT {_SEARCH_POOL_SIZE}"
        )
    orders = {
        CardSearchRanking.PRICE: _PRICE_SQL + " ASC NULLS LAST",
        CardSearchRanking.MANA_VALUE: "cmc ASC NULLS LAST",
        CardSearchRanking.POPULARITY: "COALESCE(edhrec_rank, 999999)",
    }
    order = orders.get(ranking, f"{match_sql} DESC, COALESCE(edhrec_rank, 999999)")
    return f" ORDER BY {order} LIMIT {_SEARCH_POOL_SIZE}"


def _candidate(
    row: asyncpg.Record,
    deck: DeckDetailResponse,
    filters: AssistantCardSearchInput,
    source: CardEvidenceSource,
    evidence: dict[UUID, _ThemeEvidence],
) -> CardSearchCandidate:
    hit = CardSearchHit(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=float(row["cmc"]) if row["cmc"] is not None else None,
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        tags=list(row["all_tags"] or []),
        price_eur_cents=row["price_eur_cents"],
    )
    card_evidence = evidence.get(row["id"])
    blob = _card_blob(hit)
    return CardSearchCandidate(
        card=hit,
        evidence_source=source,
        matched_theme_tags=list(card_evidence.tags) if card_evidence else [],
        theme_score=round(card_evidence.score, 3) if card_evidence else 0.0,
        matched_filters=_matched_filter_names(filters),
        commander_matches=sorted(_commander_words(deck) & set(blob.split()))[:6],
        role_matches=_roles(blob),
        game_changer=bool(row["game_changer"]),
    )


def _normalize_list(values: list[str], *, upper: bool = False) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = " ".join(value.strip().split())
        item = item.upper() if upper else item.lower()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _validate_range(label: str, minimum: float | int | None, maximum: float | int | None) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{label} minimum cannot exceed maximum")


def _add_filter(where: list[str], args: list[object], clause: str, value: object) -> None:
    args.append(value)
    where.append(clause.replace("$N", f"${len(args)}"))


def _patterns(values: list[str]) -> list[str]:
    return [f"%{value}%" for value in values]


def _deck_card_ids(deck: DeckDetailResponse) -> list[UUID]:
    ids = [card.card_id for card in deck.cards]
    ids.extend(card_id for card_id in (deck.commander_id, deck.partner_id) if card_id is not None)
    return ids


def _commander_words(deck: DeckDetailResponse) -> set[str]:
    cards = [card for card in (deck.commander_card, deck.partner_card) if card is not None]
    text = " ".join(f"{card.name} {card.oracle_text or ''}" for card in cards)
    return {word for word in _normalize(text).split() if len(word) >= 5}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _card_blob(card: CardSearchHit) -> str:
    return _normalize(
        " ".join([card.name, card.type_line or "", card.oracle_text or "", *card.tags])
    )


def _roles(blob: str) -> list[str]:
    terms = {
        "draw": ("draw", "card advantage"),
        "interaction": ("destroy", "exile", "counter target"),
        "ramp": ("add mana", "search your library for a land"),
        "protection": ("hexproof", "indestructible", "protection"),
        "payoff": ("whenever", "double", "additional", "each opponent"),
    }
    return [role for role, needles in terms.items() if any(term in blob for term in needles)]


def _matched_filter_names(filters: AssistantCardSearchInput) -> list[str]:
    payload = filters.model_dump()
    ignored = {
        "theme_tags",
        "theme_hints",
        "exclude_deck_cards",
        "exclude_game_changers",
        "ranking",
        "limit",
    }
    return [
        name
        for name, value in payload.items()
        if name not in ignored and value not in (None, [], False)
    ]


_PRICE_SQL = "ROUND((prices->>'eur')::numeric * 100)::integer"
_COMMANDER_MATCH_SQL = """(
    SELECT count(*) FROM unnest($N::text[]) term
    WHERE lower(concat_ws(' ', name, type_line, oracle_text, array_to_string(keywords, ' ')))
          LIKE '%' || term || '%'
)"""

_CARD_SELECT = """
SELECT id, scryfall_id, name, mana_cost, cmc, type_line, oracle_text, color_identity,
        keywords AS all_tags, game_changer, edhrec_rank,
       ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents
FROM cards
"""
