"""Tests for the local Commander suggestor ranker and endpoint."""

import json
from uuid import UUID

import asyncpg
from httpx import AsyncClient

from mtg_helper.models.ai import CommanderSuggestIntent
from mtg_helper.services import commander_suggestor_service

MULDROTHA_ID = UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
GENERIC_ID = UUID("bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")
BANNED_ID = UUID("cccccccc-3333-4333-8333-cccccccccccc")


async def _insert_card(
    pool: asyncpg.Pool,
    *,
    scryfall_id: UUID,
    name: str,
    type_line: str,
    oracle_text: str,
    colors: list[str],
    tags: list[str],
    keywords: list[str] | None = None,
    traits: list[str] | None = None,
    legality: str = "legal",
    edhrec_rank: int | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cards (
                scryfall_id, oracle_id, name, color_identity, colors, oracle_text,
                type_line, cmc, mana_cost, rarity, set_code, legalities, prices,
                tags, keywords, traits, token_types, edhrec_rank
            )
            VALUES (
                $1, $2, $3, $4, $4, $5, $6, 4, '{2}{B}{G}', 'mythic', 'test',
                $7, '{}', $8, $9, $10, '{}', $11
            )
            ON CONFLICT (scryfall_id) DO UPDATE
            SET oracle_text = EXCLUDED.oracle_text,
                type_line = EXCLUDED.type_line,
                legalities = EXCLUDED.legalities,
                tags = EXCLUDED.tags,
                keywords = EXCLUDED.keywords,
                traits = EXCLUDED.traits,
                edhrec_rank = EXCLUDED.edhrec_rank
            """,
            scryfall_id,
            scryfall_id,
            name,
            colors,
            oracle_text,
            type_line,
            json.dumps({"commander": legality}),
            tags,
            keywords or [],
            traits or [],
            edhrec_rank,
        )


async def test_suggest_commanders_marks_card_advantage_without_score_boost(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_card(
        db_pool,
        scryfall_id=MULDROTHA_ID,
        name="Muldrotha Test",
        type_line="Legendary Creature - Elemental Avatar",
        oracle_text="During each of your turns, you may play a card from your graveyard.",
        colors=["B", "G", "U"],
        tags=["escape"],
        keywords=["Escape"],
        traits=["etb"],
        edhrec_rank=100,
    )
    await _insert_card(
        db_pool,
        scryfall_id=GENERIC_ID,
        name="Generic Graveyard Legend",
        type_line="Legendary Creature - Zombie",
        oracle_text="Whenever a creature dies, each opponent loses 1 life.",
        colors=["B", "G"],
        tags=["morbid"],
        keywords=["Morbid"],
        edhrec_rank=200,
    )

    intent = CommanderSuggestIntent(mechanic_tags=["escape"], traits=["etb"], direction="graveyard")
    results = await commander_suggestor_service.suggest_commanders(db_pool, intent)

    assert results[0].card.scryfall_id == MULDROTHA_ID
    assert "Card advantage signal" in results[0].score_reasons
    assert "escape" in results[0].matched_tags


async def test_suggest_commanders_prioritizes_selected_keyword(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_card(
        db_pool,
        scryfall_id=MULDROTHA_ID,
        name="Popular Draw Legend",
        type_line="Legendary Creature - Wizard",
        oracle_text="Whenever you cast a spell, draw a card.",
        colors=["U"],
        tags=[],
        edhrec_rank=1,
    )
    await _insert_card(
        db_pool,
        scryfall_id=GENERIC_ID,
        name="Surveil Grave Legend",
        type_line="Legendary Creature - Zombie",
        oracle_text="Whenever you surveil, return a card from your graveyard.",
        colors=["B", "U"],
        tags=[],
        keywords=["Surveil"],
        edhrec_rank=20000,
    )

    intent = CommanderSuggestIntent(mechanic_tags=["surveil"])
    results = await commander_suggestor_service.suggest_commanders(db_pool, intent)

    assert results[0].card.scryfall_id == GENERIC_ID
    assert "Keyword overlap" in results[0].score_reasons
    assert "surveil" in results[0].matched_tags


async def test_suggest_commanders_filters_illegal_and_off_color(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_card(
        db_pool,
        scryfall_id=MULDROTHA_ID,
        name="Legal Sultai Legend",
        type_line="Legendary Creature - Elemental Avatar",
        oracle_text="Draw a card from your graveyard.",
        colors=["B", "G", "U"],
        tags=["escape"],
        keywords=["Escape"],
    )
    await _insert_card(
        db_pool,
        scryfall_id=BANNED_ID,
        name="Banned Legend",
        type_line="Legendary Creature - Horror",
        oracle_text="Draw a card.",
        colors=["B"],
        tags=["escape"],
        keywords=["Escape"],
        legality="banned",
    )

    intent = CommanderSuggestIntent(mechanic_tags=["escape"], color_identity=["B"])
    results = await commander_suggestor_service.suggest_commanders(db_pool, intent)
    result_ids = {item.card.scryfall_id for item in results}

    assert MULDROTHA_ID in result_ids
    assert BANNED_ID not in result_ids


async def test_suggest_commanders_exact_color_match_requires_same_identity(
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_card(
        db_pool,
        scryfall_id=MULDROTHA_ID,
        name="Sultai Graveyard Legend",
        type_line="Legendary Creature - Elemental Avatar",
        oracle_text="Draw a card from your graveyard.",
        colors=["B", "G", "U"],
        tags=["escape"],
        keywords=["Escape"],
    )
    await _insert_card(
        db_pool,
        scryfall_id=GENERIC_ID,
        name="Mono Black Graveyard Legend",
        type_line="Legendary Creature - Zombie",
        oracle_text="Draw a card from your graveyard.",
        colors=["B"],
        tags=["escape"],
        keywords=["Escape"],
    )

    loose = CommanderSuggestIntent(mechanic_tags=["escape"], color_identity=["B"])
    exact = CommanderSuggestIntent(
        mechanic_tags=["escape"],
        color_identity=["B"],
        exact_color_identity=True,
    )

    loose_results = await commander_suggestor_service.suggest_commanders(db_pool, loose)
    exact_results = await commander_suggestor_service.suggest_commanders(db_pool, exact)
    loose_ids = {item.card.scryfall_id for item in loose_results}
    exact_ids = {item.card.scryfall_id for item in exact_results}

    assert MULDROTHA_ID in loose_ids
    assert GENERIC_ID in loose_ids
    assert MULDROTHA_ID not in exact_ids
    assert GENERIC_ID in exact_ids


async def test_suggest_commanders_endpoint_reranks_from_intent_override(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    await _insert_card(
        db_pool,
        scryfall_id=MULDROTHA_ID,
        name="Endpoint Graveyard Legend",
        type_line="Legendary Creature - Elemental Avatar",
        oracle_text="You may cast creature cards from your graveyard. Draw a card.",
        colors=["B", "G", "U"],
        tags=["escape"],
        keywords=["Escape"],
        traits=["etb"],
    )

    resp = await client.post(
        "/api/v1/decks/suggest-commanders",
        json={
            "message": "",
            "intent_override": {
                "archetype_tags": [],
                "mechanic_tags": ["escape"],
                "traits": ["etb"],
                "token_types": [],
                "color_identity": ["B", "G", "U"],
                "exact_color_identity": False,
                "excluded_colors": [],
                "bracket": 3,
                "direction": "graveyard etb value",
                "must_have": [],
                "avoid": [],
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["commanders"][0]["card"]["scryfall_id"] == str(MULDROTHA_ID)
    assert data["intent"]["mechanic_tags"] == ["escape"]
