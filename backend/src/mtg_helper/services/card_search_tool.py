"""Card-search tool used by the simulation analysis agent.

The LLM calls this with structural filters (types, tags, CMC, price); the
backend always overlays the deck's color identity so suggestions cannot
escape it. Reads from the ``cards`` table directly; semantic queries fall
through to ``retrieval_service.retrieve_candidates`` when ``text_query`` is
set.
"""

import asyncpg

from mtg_helper.models.ai import CardSearchHit, CardSearchInput

_MAX_LIMIT = 20

# Basic lands — agent may suggest these even if already in the deck, because
# decks legitimately run many copies. Snow-Covered variants share the names.
_SEARCH_STOP_WORDS: frozenset[str] = frozenset(
    {
        "and",
        "card",
        "cards",
        "for",
        "that",
        "the",
        "with",
    }
)

_BASIC_LANDS: frozenset[str] = frozenset(
    {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Wastes",
        "Snow-Covered Plains",
        "Snow-Covered Island",
        "Snow-Covered Swamp",
        "Snow-Covered Mountain",
        "Snow-Covered Forest",
    }
)


def _text_terms(query: str | None) -> list[str]:
    """Split a natural-language card search query into useful SQL terms."""
    if not query:
        return []
    terms = [term.strip().lower() for term in query.replace(",", " ").split()]
    return [term for term in terms if len(term) >= 3 and term not in _SEARCH_STOP_WORDS][:6]


def _apply_text_filter(query: str | None, where: list[str], args: list[object]) -> None:
    """Append a multi-term name/oracle search.

    A single ``ILIKE '%squirrel token%'`` misses oracle text like "create a 1/1
    Squirrel creature token". Searching each meaningful term is more useful for
    LLM tool calls such as "squirrel token", "food graveyard", or "etb draw".
    """
    terms = _text_terms(query)
    if not terms:
        return
    clauses: list[str] = []
    for term in terms:
        args.append(f"%{term}%")
        placeholder = f"${len(args)}"
        clauses.append(f"(name ILIKE {placeholder} OR oracle_text ILIKE {placeholder})")
    where.append("(" + " AND ".join(clauses) + ")")


def _apply_optional_filters(inp: CardSearchInput, where: list[str], args: list[object]) -> None:
    """Append the LLM-supplied filters onto ``where`` / ``args``."""

    def _add(clause: str, value: object) -> None:
        args.append(value)
        where.append(clause.replace("$$N", f"${len(args)}"))

    filters: tuple[tuple[bool, str, object], ...] = (
        (bool(inp.types), "type_line ILIKE ALL($$N::text[])", [f"%{t}%" for t in inp.types]),
        (bool(inp.tags), "tags && $$N::text[]", list(inp.tags)),
        (inp.min_cmc is not None, "cmc >= $$N", inp.min_cmc),
        (inp.max_cmc is not None, "cmc <= $$N", inp.max_cmc),
        (
            inp.max_price_eur_cents is not None,
            "COALESCE(ROUND((prices->>'eur')::numeric * 100)::integer, 0) <= $$N",
            inp.max_price_eur_cents,
        ),
    )
    for active, clause, value in filters:
        if active:
            _add(clause, value)
    _apply_text_filter(inp.text_query, where, args)


def _build_filters(
    inp: CardSearchInput,
    deck_color_identity: list[str],
    exclude_names: list[str] | None,
) -> tuple[list[str], list[object]]:
    """Compose the WHERE-clause fragments and positional args for the card
    search. Color identity is always first, optional exclusions and the
    LLM-supplied filters follow.
    """
    where: list[str] = ["color_identity <@ $1::text[]"]
    args: list[object] = [list(deck_color_identity)]
    excludable = [n for n in (exclude_names or []) if n not in _BASIC_LANDS]
    if excludable:
        args.append(excludable)
        where.append(f"name <> ALL(${len(args)}::text[])")
    _apply_optional_filters(inp, where, args)
    return where, args


async def search_cards(
    pool: asyncpg.Pool,
    *,
    deck_color_identity: list[str],
    inp: CardSearchInput,
    exclude_names: list[str] | None = None,
) -> list[CardSearchHit]:
    """Search the card pool with the LLM-supplied filters. The deck's color
    identity is enforced server-side as a strict subset check — only cards
    whose ``color_identity`` is a subset of the deck's colors are returned.

    ``exclude_names`` filters out cards already in the deck (basic lands are
    allowed through since decks legitimately run multiple copies).
    """
    limit = min(inp.limit, _MAX_LIMIT)
    where, args = _build_filters(inp, deck_color_identity, exclude_names)
    sql = (
        "SELECT scryfall_id, name, mana_cost, cmc, type_line, oracle_text, color_identity, tags, "
        "ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents "
        f"FROM cards WHERE {' AND '.join(where)} "
        "ORDER BY COALESCE(edhrec_rank, 999999) ASC NULLS LAST "
        f"LIMIT {limit}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [
        CardSearchHit(
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
        for row in rows
    ]
