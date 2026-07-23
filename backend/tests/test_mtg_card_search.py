"""Behavior tests for the MTG Assistant's typed card search."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg
import pytest
from pydantic import ValidationError

from mtg_helper.models.decks import CommanderCardSummary, DeckDetailResponse
from mtg_helper.services.mtg_card_search import (
    AssistantCardSearchInput,
    CardEvidenceSource,
    search_cards,
)


def test_search_input_normalizes_symbols_and_types() -> None:
    filters = AssistantCardSearchInput(
        mana_cost_symbols=["{x}", "{g/w}", "{w/p}"],
        card_types=["creature"],
        subtypes=["hydra"],
    )

    assert filters.mana_cost_symbols == ["{X}", "{G/W}", "{W/P}"]
    assert filters.card_types == ["Creature"]
    assert filters.subtypes == ["Hydra"]


@pytest.mark.parametrize(
    "values, message",
    [
        ({"mana_cost_symbols": ["X"]}, "invalid mana symbol"),
        ({"oracle_text_all": ["draw%"]}, "wildcard characters"),
        ({"mana_value_min": 5, "mana_value_max": 2}, "mana value minimum"),
        ({"min_price_eur_cents": 500, "max_price_eur_cents": 100}, "price minimum"),
        (
            {"required_tags": ["draw"], "excluded_tags": ["draw"]},
            "both required and excluded",
        ),
    ],
)
def test_search_input_rejects_invalid_or_contradictory_filters(
    values: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        AssistantCardSearchInput.model_validate(values)


async def _insert_search_cards(pool: asyncpg.Pool) -> dict[str, UUID]:
    cards = [
        (
            "Hydra Search Test",
            "{X}{G}",
            1,
            "Creature — Hydra",
            "Hydra Search Test enters with X +1/+1 counters.",
            ["G"],
            ["Creature"],
            ["Hydra"],
            ["counters", "payoff"],
            '{"eur":"2.50"}',
            100,
        ),
        (
            "Hybrid Search Test",
            "{X}{G/W}",
            1,
            "Creature — Avatar",
            "Hybrid Search Test enters with X +1/+1 counters.",
            ["G", "W"],
            ["Creature"],
            ["Avatar"],
            ["counters"],
            '{"eur":"4.00"}',
            200,
        ),
        (
            "Oracle X Search Test",
            "{2}{G}",
            3,
            "Creature — Elf",
            "Create X tokens, where X is the number of lands you control.",
            ["G"],
            ["Creature"],
            ["Elf"],
            ["tokens"],
            '{"eur":"1.00"}',
            300,
        ),
    ]
    inserted: dict[str, UUID] = {}
    async with pool.acquire() as conn:
        for card in cards:
            row = await conn.fetchrow(
                """
                INSERT INTO cards (
                    scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
                    color_identity, colors, card_types, subtypes, tags, legalities,
                    prices, edhrec_rank, is_canonical
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $7, $8, $9, $10,
                        '{"commander":"legal"}', $11, $12, true)
                RETURNING id
                """,
                uuid4(),
                *card,
            )
            inserted[card[0]] = row["id"]
    return inserted


async def _deck(pool: asyncpg.Pool) -> DeckDetailResponse:
    async with pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE name = 'Hazel of the Rootbloom'"
        )
    now = datetime.now(UTC)
    return DeckDetailResponse(
        id=uuid4(),
        name="Generic Search Test",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G", "W"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Hazel of the Rootbloom",
            mana_cost="{2}{G}{W}",
            oracle_text="Whenever you cast a spell with X in its mana cost, create X tokens.",
            color_identity=["G", "W"],
        ),
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        cards=[],
    )


async def test_search_enforces_exact_mana_symbol_and_combined_filters(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_search_cards(db_pool)
    deck = await _deck(db_pool)
    filters = AssistantCardSearchInput(
        mana_cost_symbols=["{X}"],
        mana_value_max=2,
        card_types=["Creature"],
        oracle_text_all=["counters"],
        required_tags=["counters"],
        excluded_tags=["tokens"],
        min_price_eur_cents=200,
        max_price_eur_cents=500,
        limit=8,
    )

    result = await search_cards(db_pool, deck, filters)

    assert result.evidence_source is CardEvidenceSource.GLOBAL_SEARCH
    assert [candidate.card.name for candidate in result.candidates] == [
        "Hydra Search Test",
        "Hybrid Search Test",
    ]
    assert all("mana_cost_symbols" in candidate.matched_filters for candidate in result.candidates)


async def _insert_x_theme(pool: asyncpg.Pool, cards: dict[str, UUID]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO moxfield_hubs (id, slug, tag, name)
            VALUES (9001, 'x-spells', 'x_spells', 'X Spells')
            """
        )
        await conn.executemany(
            """
            INSERT INTO moxfield_hub_card_stats (
                hub_id, card_id, hub_deck_count, baseline_deck_count,
                hub_deck_pct, baseline_deck_pct, synergy_score,
                hub_sample_size, baseline_sample_size
            ) VALUES (9001, $1, 20, 100, 0.5, 0.1, $2, 40, 1000)
            """,
            [
                (cards["Hydra Search Test"], 0.9),
                (cards["Oracle X Search Test"], 0.8),
            ],
        )


async def test_search_prefers_hub_stats_and_reports_matched_source(
    db_pool: asyncpg.Pool,
) -> None:
    cards = await _insert_search_cards(db_pool)
    await _insert_x_theme(db_pool, cards)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(theme_tags=["moxfield:x_spells"], mana_cost_symbols=["{X}"]),
    )

    assert result.evidence_source is CardEvidenceSource.HUB_STATS
    assert [candidate.card.name for candidate in result.candidates] == ["Hydra Search Test"]
    assert result.candidates[0].matched_theme_tags == ["moxfield:x_spells"]
    assert result.candidates[0].theme_score == 0.9


async def test_empty_hub_result_retries_identical_filters_globally(
    db_pool: asyncpg.Pool,
) -> None:
    cards = await _insert_search_cards(db_pool)
    await _insert_x_theme(db_pool, cards)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(
            theme_tags=["x_spells"],
            oracle_text_all=["under your control"],
        ),
    )

    assert result.evidence_source is CardEvidenceSource.GLOBAL_FALLBACK
    assert result.message is not None
    assert [candidate.card.name for candidate in result.candidates] == ["Doubling Season"]
    assert result.candidates[0].evidence_source is CardEvidenceSource.GLOBAL_FALLBACK


async def test_unknown_theme_returns_structured_empty_result(db_pool: asyncpg.Pool) -> None:
    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(theme_tags=["not_a_real_theme"]),
    )

    assert result.evidence_source is CardEvidenceSource.NONE
    assert result.candidates == []
    assert result.message is not None
