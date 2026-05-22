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


async def search_cards(
    pool: asyncpg.Pool,
    *,
    deck_color_identity: list[str],
    inp: CardSearchInput,
) -> list[CardSearchHit]:
    """Search the card pool with the LLM-supplied filters. The deck's color
    identity is enforced server-side as a strict subset check — only cards
    whose ``color_identity`` is a subset of the deck's colors are returned.
    """
    limit = min(inp.limit, _MAX_LIMIT)
    where: list[str] = ["color_identity <@ $1::text[]"]
    args: list[object] = [list(deck_color_identity)]

    def _add(clause: str, value: object) -> None:
        args.append(value)
        where.append(clause.replace("$$N", f"${len(args)}"))

    if inp.types:
        _add("type_line ILIKE ALL($$N::text[])", [f"%{t}%" for t in inp.types])
    if inp.tags:
        _add("tags && $$N::text[]", list(inp.tags))
    if inp.min_cmc is not None:
        _add("cmc >= $$N", inp.min_cmc)
    if inp.max_cmc is not None:
        _add("cmc <= $$N", inp.max_cmc)
    if inp.max_price_eur_cents is not None:
        _add(
            "COALESCE(ROUND((prices->>'eur')::numeric * 100)::integer, 0) <= $$N",
            inp.max_price_eur_cents,
        )
    if inp.text_query:
        # Loose substring fallback over name + oracle text. Semantic retrieval
        # is a follow-on once we wire qdrant here.
        _add("(name ILIKE $$N OR oracle_text ILIKE $$N)", f"%{inp.text_query}%")

    sql = (
        "SELECT name, mana_cost, cmc, type_line, color_identity, tags, "
        "ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents "
        f"FROM cards WHERE {' AND '.join(where)} "
        "ORDER BY COALESCE(edhrec_rank, 999999) ASC NULLS LAST "
        f"LIMIT {limit}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [
        CardSearchHit(
            name=row["name"],
            mana_cost=row["mana_cost"],
            cmc=float(row["cmc"]) if row["cmc"] is not None else None,
            type_line=row["type_line"],
            color_identity=list(row["color_identity"] or []),
            tags=list(row["tags"] or []),
            price_eur_cents=row["price_eur_cents"],
        )
        for row in rows
    ]
