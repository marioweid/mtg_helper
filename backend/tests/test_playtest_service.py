"""Unit + endpoint tests for the goldfish playtest simulator."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import PlaytestSimulateRequest
from mtg_helper.services.playtest_service import (
    _can_cast,
    _expand_deck,
    _land_produces,
    parse_cost,
    simulate,
)
from tests.conftest import HAZEL_SCRYFALL_ID, SOL_RING_SCRYFALL_ID


def _make_card(
    name: str,
    *,
    mana_cost: str | None = None,
    cmc: float = 0,
    type_line: str = "Creature — Human",
    color_identity: list[str] | None = None,
    quantity: int = 1,
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost=mana_cost,
        cmc=Decimal(str(cmc)),
        type_line=type_line,
        oracle_text=None,
        color_identity=color_identity or [],
        image_uri=None,
        rarity=None,
        quantity=quantity,
        categories=[],
        added_by="ai",
        ai_reasoning=None,
        qualifying_stages=[],
        price_eur_cents=None,
    )


def _make_deck(cards: list[DeckCardItem], color_identity: list[str]) -> DeckDetailResponse:
    now = datetime(2026, 5, 18)
    return DeckDetailResponse(
        id=uuid4(),
        name="Sim",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=uuid4(),
        partner_id=None,
        commander_color_identity=color_identity,
        owner_email=None,
        created_at=now,
        updated_at=now,
        cards=cards,
    )


class TestParseCost:
    def test_none_returns_empty(self):
        cost = parse_cost(None)
        assert cost.generic == 0
        assert cost.colored == ()

    def test_generic_only(self):
        cost = parse_cost("{3}")
        assert cost.generic == 3
        assert cost.colored == ()

    def test_colored_only(self):
        cost = parse_cost("{G}{G}{W}")
        assert cost.generic == 0
        assert dict(cost.colored) == {"G": 2, "W": 1}

    def test_mixed(self):
        cost = parse_cost("{2}{R}{R}")
        assert cost.generic == 2
        assert dict(cost.colored) == {"R": 2}

    def test_x_treated_as_zero(self):
        cost = parse_cost("{X}{G}")
        assert cost.generic == 0
        assert dict(cost.colored) == {"G": 1}

    def test_hybrid_collapses_to_first(self):
        cost = parse_cost("{W/U}")
        assert dict(cost.colored) == {"W": 1}


class TestLandProduces:
    def test_basic_forest(self):
        land = _make_card("Forest", type_line="Basic Land — Forest", color_identity=["G"])
        assert _land_produces(land) == ("G",)

    def test_basic_island(self):
        land = _make_card("Island", type_line="Basic Land — Island", color_identity=["U"])
        assert _land_produces(land) == ("U",)

    def test_snow_covered_basic_resolves(self):
        land = _make_card(
            "Snow-Covered Forest",
            type_line="Basic Snow Land — Forest",
            color_identity=["G"],
        )
        assert _land_produces(land) == ("G",)

    def test_nonbasic_uses_color_identity(self):
        land = _make_card(
            "Temple Garden",
            type_line="Land — Forest Plains",
            color_identity=["G", "W"],
        )
        assert set(_land_produces(land)) == {"G", "W"}

    def test_colorless_land_defaults_to_colorless(self):
        land = _make_card("Wastes-like", type_line="Land", color_identity=[])
        assert _land_produces(land) == ("C",)


class TestCanCast:
    def _land(self, *colors: str):
        from mtg_helper.services.playtest_service import SimCard

        return SimCard(name="L", cmc=0, is_land=True, produces=tuple(colors), cost=None)

    def test_can_cast_single_colored_with_matching_land(self):
        assert _can_cast(parse_cost("{G}"), [self._land("G")]) is True

    def test_cannot_cast_when_wrong_color(self):
        assert _can_cast(parse_cost("{G}"), [self._land("R")]) is False

    def test_can_cast_generic_with_any_land(self):
        assert _can_cast(parse_cost("{2}"), [self._land("R"), self._land("U")]) is True

    def test_cannot_cast_when_short_on_lands(self):
        assert _can_cast(parse_cost("{3}"), [self._land("G"), self._land("G")]) is False

    def test_can_cast_dual_requirement(self):
        assert _can_cast(parse_cost("{G}{W}"), [self._land("G"), self._land("W")]) is True

    def test_dual_land_pays_either_color(self):
        dual = self._land("G", "W")
        assert _can_cast(parse_cost("{G}"), [dual]) is True
        assert _can_cast(parse_cost("{W}"), [dual]) is True

    def test_dual_land_cannot_pay_both_colors_alone(self):
        assert _can_cast(parse_cost("{G}{W}"), [self._land("G", "W")]) is False


class TestExpandDeck:
    def test_quantity_expansion(self):
        cards = [_make_card("Forest", type_line="Basic Land — Forest", quantity=10)]
        expanded = _expand_deck(cards)
        assert len(expanded) == 10
        assert all(c.is_land for c in expanded)


class TestSimulate:
    def test_pure_lands_deck_hits_all_land_drops(self):
        cards = [
            _make_card(
                "Forest",
                type_line="Basic Land — Forest",
                color_identity=["G"],
                quantity=99,
            )
        ]
        deck = _make_deck(cards, ["G"])
        stats = simulate(
            deck, PlaytestSimulateRequest(trials=50, turns=4, on_the_play=True, seed=42)
        )
        # Every turn should play a land — turn N has N lands in play.
        for i, turn in enumerate(stats.per_turn, start=1):
            assert turn.avg_lands_in_play == pytest.approx(float(i))
            assert turn.pct_land_drop == 1.0
            assert turn.avg_spells_cast_cumulative == 0.0

    def test_pure_spells_deck_never_casts(self):
        # No lands, only 4-drops — should never cast anything in 4 turns.
        cards = [_make_card(f"Spell{i}", mana_cost="{2}{G}{G}", cmc=4) for i in range(99)]
        deck = _make_deck(cards, ["G"])
        stats = simulate(
            deck, PlaytestSimulateRequest(trials=20, turns=4, on_the_play=True, seed=1)
        )
        assert stats.avg_total_spells_cast == 0.0
        for turn in stats.per_turn:
            assert turn.pct_cast_any == 0.0

    def test_seeded_runs_are_deterministic(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=40
        )
        elves = _make_card(
            "Llanowar Elves", mana_cost="{G}", cmc=1, color_identity=["G"], quantity=40
        )
        bear = _make_card("Bear", mana_cost="{1}{G}", cmc=2, color_identity=["G"], quantity=19)
        cards = [forest, elves, bear]
        deck = _make_deck(cards, ["G"])
        req = PlaytestSimulateRequest(trials=30, turns=4, seed=7)
        a = simulate(deck, req)
        b = simulate(deck, req)
        assert a.model_dump() == b.model_dump()

    def test_stats_shape(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=37
        )
        bear = _make_card("Bear", mana_cost="{1}{G}", cmc=2, color_identity=["G"], quantity=62)
        cards = [forest, bear]
        deck = _make_deck(cards, ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=10, turns=4, seed=3))
        assert stats.trials == 10
        assert stats.turns == 4
        assert len(stats.per_turn) == 4
        assert len(stats.mulligan_distribution) == 4  # max_mulligans default 3 → 4 buckets
        assert sum(stats.mulligan_distribution) == 10


@pytest.mark.asyncio
async def test_playtest_endpoint_returns_stats(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Sim Deck", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]
    # Add a single non-land card so the deck isn't empty.
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID)},
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/playtest/simulate",
        json={"trials": 25, "turns": 3, "seed": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["trials"] == 25
    assert data["turns"] == 3
    assert len(data["per_turn"]) == 3
    assert all("avg_lands_in_play" in t for t in data["per_turn"])


@pytest.mark.asyncio
async def test_playtest_endpoint_404_for_missing_deck(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/playtest/simulate",
        json={"trials": 5},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_playtest_endpoint_rejects_too_many_trials(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Cap Deck"},
    )
    deck_id = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/playtest/simulate",
        json={"trials": 100000},
    )
    assert resp.status_code == 422
