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

COUNTERS_TAG = UUID("10000000-0000-0000-0000-000000000020")
TOKENS_TAG = UUID("10000000-0000-0000-0000-000000000021")


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
            {"required_tags": [str(COUNTERS_TAG)], "excluded_tags": [str(COUNTERS_TAG)]},
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
                    scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
                    color_identity, colors, card_types, subtypes, legalities,
                    prices, edhrec_rank, is_canonical
                )
                VALUES ($1, $1, $2, $3, $4, $5, $6, $7, $7, $8, $9,
                        '{"commander":"legal"}', $10, $11, true)
                RETURNING id
                """,
                uuid4(),
                *card[:8],
                *card[9:],
            )
            inserted[card[0]] = row["id"]
        await conn.executemany(
            "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, $2, $3)",
            [
                (COUNTERS_TAG, "counters-test", '{"label":"Counters test"}'),
                (TOKENS_TAG, "tokens-test", '{"label":"Tokens test"}'),
            ],
        )
        await conn.executemany(
            "INSERT INTO scryfall_tag_descendants (ancestor_id, descendant_id) VALUES ($1, $1)",
            [(COUNTERS_TAG,), (TOKENS_TAG,)],
        )
        await conn.executemany(
            "INSERT INTO scryfall_tag_memberships (tag_id, oracle_id, details) "
            "SELECT $1, oracle_id, '{}' FROM cards WHERE id = $2",
            [
                (COUNTERS_TAG, inserted["Hydra Search Test"]),
                (COUNTERS_TAG, inserted["Hybrid Search Test"]),
                (TOKENS_TAG, inserted["Oracle X Search Test"]),
            ],
        )
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
        required_tags=[str(COUNTERS_TAG)],
        excluded_tags=[str(TOKENS_TAG)],
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


async def _insert_game_changer(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cards (
                scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
                color_identity, colors, card_types, subtypes, legalities,
                prices, edhrec_rank, is_canonical, game_changer
            )
            VALUES (
                $1, 'Jeweled Lotus Search Test', '{0}', 0, 'Artifact',
                '{T}, Sacrifice Jeweled Lotus Search Test: Add three mana of any one color.',
                ARRAY[]::text[], ARRAY[]::text[], ARRAY['Artifact'], ARRAY[]::text[],
                '{"commander":"legal"}', '{"eur":"60.00"}', 10, true, true
            )
            """,
            uuid4(),
        )


async def test_search_excludes_game_changers_when_requested(db_pool: asyncpg.Pool) -> None:
    await _insert_search_cards(db_pool)
    await _insert_game_changer(db_pool)
    deck = await _deck(db_pool)

    without_filter = await search_cards(
        db_pool,
        deck,
        AssistantCardSearchInput(oracle_text_all=["add"]),
    )
    assert "Jeweled Lotus Search Test" in {c.card.name for c in without_filter.candidates}

    result = await search_cards(
        db_pool,
        deck,
        AssistantCardSearchInput(exclude_game_changers=True, oracle_text_all=["add"]),
    )

    assert "Jeweled Lotus Search Test" not in {c.card.name for c in result.candidates}
    assert result.candidates


async def test_source_tag_selection_filters_to_direct_memberships(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_search_cards(db_pool)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(theme_tags=[str(COUNTERS_TAG)], mana_cost_symbols=["{X}"]),
    )

    assert result.evidence_source is CardEvidenceSource.GLOBAL_SEARCH
    assert result.resolved_theme_tags == [str(COUNTERS_TAG)]
    assert [candidate.card.name for candidate in result.candidates] == [
        "Hydra Search Test",
        "Hybrid Search Test",
    ]


async def test_unknown_source_tag_is_rejected(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(ValueError, match="Unknown Scryfall Oracle-tag UUID"):
        await search_cards(
            db_pool,
            await _deck(db_pool),
            AssistantCardSearchInput(theme_tags=["10000000-0000-0000-0000-000000000099"]),
        )


async def test_search_collection_only_restricts_to_owned_cards(
    db_pool: asyncpg.Pool,
) -> None:
    cards = await _insert_search_cards(db_pool)
    owned = frozenset({cards["Hydra Search Test"]})

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(collection_only=True),
        owned_card_ids=owned,
    )

    assert result.evidence_source is CardEvidenceSource.GLOBAL_SEARCH
    assert [candidate.card.name for candidate in result.candidates] == ["Hydra Search Test"]


async def test_search_collection_only_with_owned_unmatched_returns_empty(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_search_cards(db_pool)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(collection_only=True),
        owned_card_ids=frozenset({uuid4()}),
    )

    assert result.candidates == []


async def test_search_none_owned_ids_means_no_filter(
    db_pool: asyncpg.Pool,
) -> None:
    """Service-level contract: ``owned_card_ids=None`` disables ownership filtering."""
    await _insert_search_cards(db_pool)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(collection_only=True),
        owned_card_ids=None,
    )

    assert result.candidates
    assert len(result.candidates) >= 2


async def test_collection_only_source_tag_remains_restricted_to_owned_members(
    db_pool: asyncpg.Pool,
) -> None:
    cards = await _insert_search_cards(db_pool)

    result = await search_cards(
        db_pool,
        await _deck(db_pool),
        AssistantCardSearchInput(collection_only=True, theme_tags=[str(COUNTERS_TAG)]),
        owned_card_ids=frozenset({cards["Hydra Search Test"]}),
    )

    assert result.evidence_source is CardEvidenceSource.GLOBAL_SEARCH
    assert [candidate.card.name for candidate in result.candidates] == ["Hydra Search Test"]
