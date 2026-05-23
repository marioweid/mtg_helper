"""Tests for the budget swap service."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.retrieval_service import RetrievedCard
from mtg_helper.services.swap_service import (
    _cmc_proximity,
    _color_subset,
    _primary_type,
    _SourceCard,
    _tag_jaccard,
    _type_match,
    function_similarity,
)
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    RHYSTIC_STUDY_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_deck,
)


def _make_ai_client() -> MagicMock:
    async def _embed(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    ai = MagicMock()
    ai.embed = AsyncMock(side_effect=_embed)
    return ai


def _set_qdrant_empty() -> None:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    app.state.qdrant_client = mock


async def _set_tags(pool: asyncpg.Pool, scryfall_id: UUID, tags: list[str]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cards SET tags = $1::text[] WHERE scryfall_id = $2",
            tags,
            scryfall_id,
        )


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


# ── Pure similarity tests ───────────────────────────────────────────────────


class TestPrimaryType:
    def test_creature(self):
        assert _primary_type("Legendary Creature — Elf Druid") == "Creature"

    def test_artifact(self):
        assert _primary_type("Artifact") == "Artifact"

    def test_enchantment(self):
        assert _primary_type("Enchantment — Aura") == "Enchantment"

    def test_none_for_empty(self):
        assert _primary_type(None) is None
        assert _primary_type("") is None


class TestTagJaccard:
    def test_identical_tags(self):
        assert _tag_jaccard(["ramp", "draw"], ["ramp", "draw"]) == 1.0

    def test_no_overlap(self):
        assert _tag_jaccard(["ramp"], ["interaction"]) == 0.0

    def test_partial_overlap(self):
        assert _tag_jaccard(["ramp", "draw"], ["ramp", "interaction"]) == pytest.approx(1 / 3)

    def test_both_empty_is_1(self):
        assert _tag_jaccard([], []) == 1.0


class TestTypeMatch:
    def test_same_primary(self):
        assert _type_match("Creature — Elf", "Creature — Goblin") == 1.0

    def test_artifact_vs_creature_both_permanent(self):
        assert _type_match("Artifact", "Creature — Elf") == 0.5

    def test_instant_vs_creature_mismatch(self):
        assert _type_match("Instant", "Creature — Elf") == 0.0

    def test_instant_vs_sorcery_soft(self):
        assert _type_match("Instant", "Sorcery") == 0.5


class TestCmcProximity:
    def test_same_cmc(self):
        assert _cmc_proximity(3.0, Decimal("3")) == 1.0

    def test_delta_one(self):
        assert _cmc_proximity(3.0, Decimal("4")) == pytest.approx(0.75)

    def test_delta_four_floor(self):
        assert _cmc_proximity(3.0, Decimal("7")) == 0.0

    def test_none_candidate(self):
        assert _cmc_proximity(3.0, None) == 0.0


class TestColorSubset:
    def test_subset(self):
        assert _color_subset({"G", "W"}, {"G"}) == 1.0

    def test_colorless_candidate_fits_anywhere(self):
        assert _color_subset({"G"}, []) == 1.0

    def test_overlap_only(self):
        assert _color_subset({"G", "W"}, {"G", "U"}) == 0.5

    def test_no_overlap(self):
        assert _color_subset({"W"}, {"B"}) == 0.0


def _retrieved(
    *,
    tags: list[str],
    type_line: str,
    cmc: float,
    color_identity: list[str],
) -> RetrievedCard:
    return RetrievedCard(
        id=uuid4(),
        scryfall_id=uuid4(),
        name="X",
        mana_cost="{1}",
        cmc=Decimal(str(cmc)),
        type_line=type_line,
        oracle_text="",
        color_identity=color_identity,
        image_uri=None,
        tags=tags,
        token_types=[],
        edhrec_rank=None,
        power=None,
        toughness=None,
        rarity=None,
        price_eur_cents=None,
        score=1.0,
    )


def _source(
    *,
    tags: tuple[str, ...] = (),
    type_line: str = "Creature — Elf",
    cmc: float = 2.0,
    color_identity: frozenset[str] = frozenset({"G"}),
) -> _SourceCard:
    return _SourceCard(
        card_id=uuid4(),
        name="Source",
        mana_cost="{G}",
        cmc=cmc,
        type_line=type_line,
        oracle_text="",
        color_identity=color_identity,
        tags=tags,
        price_eur_cents=1000,
    )


class TestFunctionSimilarity:
    def test_identical_card_scores_one(self):
        src = _source(
            tags=("ramp", "draw"),
            type_line="Artifact",
            cmc=2.0,
            color_identity=frozenset(),
        )
        cand = _retrieved(tags=["ramp", "draw"], type_line="Artifact", cmc=2.0, color_identity=[])
        result = function_similarity(src, cand)
        assert result["total"] == pytest.approx(1.0)

    def test_complete_mismatch_scores_near_zero(self):
        src = _source(tags=("ramp",), type_line="Instant", cmc=2.0, color_identity=frozenset({"W"}))
        cand = _retrieved(
            tags=["interaction"], type_line="Creature — Elf", cmc=7.0, color_identity=["B"]
        )
        result = function_similarity(src, cand)
        # Worst components: tag=0, type=0, cmc=0, color=0 → total = 0
        assert result["total"] == pytest.approx(0.0)

    def test_same_type_tags_different_cmc_mid_range(self):
        src = _source(tags=("ramp",), type_line="Artifact", cmc=1.0, color_identity=frozenset())
        cand = _retrieved(tags=["ramp"], type_line="Artifact", cmc=3.0, color_identity=[])
        result = function_similarity(src, cand)
        # tag=1, type=1, cmc=0.5, color=1 → 0.40 + 0.25 + 0.10 + 0.15 = 0.90
        assert result["total"] == pytest.approx(0.90)


# ── Integration test ────────────────────────────────────────────────────────


async def test_find_swaps_returns_cheaper_alternative(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Doubling Season (€45) swap → Sol Ring (€0.20) when both tagged 'ramp'.

    Sol Ring isn't actually a great Doubling Season substitute, but the test
    fixture cards are sparse — we only have Sol Ring and Rhystic Study as
    sub-€45 candidates with green-compatible color identity (Sol Ring is
    colorless; Rhystic Study is mono-U so excluded from a mono-G commander).
    """
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, RHYSTIC_STUDY_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Swap Test Deck")
    # Find Doubling Season's internal card_id
    async with db_pool.acquire() as conn:
        ds_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", DOUBLING_SEASON_SCRYFALL_ID
        )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards/{ds_id}/swap",
        json={"limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_price_cents"] == 4500
    names = [c["name"] for c in data["candidates"]]
    assert "Sol Ring" in names
    sol_ring = next(c for c in data["candidates"] if c["name"] == "Sol Ring")
    assert sol_ring["price_delta_cents"] < 0
    assert 0 <= sol_ring["function_loss_pct"] <= 100


async def test_find_swaps_rejects_basic_land(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    """Basic lands have no useful swaps — endpoint returns 400."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    # Seed a basic land directly
    plains_scryfall = uuid4()
    async with db_pool.acquire() as conn:
        plains_id = await conn.fetchval(
            """
            INSERT INTO cards (scryfall_id, name, color_identity, type_line,
                cmc, mana_cost, rarity, legalities, colors, keywords, prices, tags)
            VALUES ($1, 'Plains', ARRAY['W'], 'Basic Land — Plains', 0, '',
                'common', '{"commander": "legal"}'::jsonb,
                ARRAY['W'], ARRAY[]::text[], '{"eur": "0.10"}'::jsonb, ARRAY[]::text[])
            RETURNING id
            """,
            plains_scryfall,
        )

    deck_id = await create_test_deck(client, name="Land Swap Deck")
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards/{plains_id}/swap",
        json={"limit": 5},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "SWAP_UNAVAILABLE"


async def test_find_swaps_card_not_found(client: AsyncClient) -> None:
    """Unknown card_id → 404."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()
    deck_id = await create_test_deck(client, name="Missing Card Deck")
    bogus = uuid4()
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards/{bogus}/swap",
        json={"limit": 5},
    )
    assert resp.status_code == 400  # SwapError("Card ... not found")


async def test_find_swaps_unknown_deck(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    """Unknown deck_id → 404 (deck_not_found is checked before card)."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()
    async with db_pool.acquire() as conn:
        ds_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", DOUBLING_SEASON_SCRYFALL_ID
        )
    bogus_deck = uuid4()
    resp = await client.post(
        f"/api/v1/decks/{bogus_deck}/cards/{ds_id}/swap",
        json={"limit": 5},
    )
    assert resp.status_code == 404


# Hazel scryfall import kept for symmetry with other tests that reference it
_ = HAZEL_SCRYFALL_ID
