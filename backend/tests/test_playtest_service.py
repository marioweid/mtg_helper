"""Unit + endpoint tests for the goldfish playtest simulator."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import PlaytestSimulateRequest
from mtg_helper.services.playtest_service import (
    ManaSource,
    _can_cast,
    _expand_deck,
    _land_produces,
    _parse_draw_count,
    _to_sim_card,
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
    qualifying_stages: list[str] | None = None,
    oracle_text: str | None = None,
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost=mana_cost,
        cmc=Decimal(str(cmc)),
        type_line=type_line,
        oracle_text=oracle_text,
        color_identity=color_identity or [],
        image_uri=None,
        rarity=None,
        quantity=quantity,
        categories=[],
        added_by="ai",
        ai_reasoning=None,
        qualifying_stages=qualifying_stages or [],
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
    def _land(self, *colors: str) -> ManaSource:
        return ManaSource(produces=tuple(colors), available_from_turn=0)

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


class TestParseDrawCount:
    def test_default_when_no_oracle(self):
        assert _parse_draw_count(None) == 1
        assert _parse_draw_count("") == 1

    def test_default_when_no_match(self):
        assert _parse_draw_count("Counter target spell.") == 1

    def test_word_count(self):
        assert _parse_draw_count("Target player draws two cards.") == 2
        assert _parse_draw_count("Draw three cards.") == 3

    def test_digit_count(self):
        assert _parse_draw_count("Draw 4 cards.") == 4

    def test_caps_at_max(self):
        assert _parse_draw_count("Each player draws seven cards.") == 5
        assert _parse_draw_count("Draw 99 cards.") == 5

    def test_singular_card(self):
        assert _parse_draw_count("Draw a card.") == 1


class TestToSimCardEffects:
    def test_ramp_creature(self):
        card = _make_card(
            "Llanowar Elves",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            qualifying_stages=["ramp"],
        )
        sim = _to_sim_card(card)
        assert sim.is_ramp is True
        assert sim.is_draw is False
        assert sim.ramp_produces == ("G",)

    def test_ramp_artifact_colorless(self):
        card = _make_card(
            "Sol Ring",
            mana_cost="{1}",
            cmc=1,
            type_line="Artifact",
            color_identity=[],
            qualifying_stages=["ramp"],
        )
        sim = _to_sim_card(card)
        assert sim.is_ramp is True
        assert sim.ramp_produces == ("C",)

    def test_draw_spell(self):
        card = _make_card(
            "Sign in Blood",
            mana_cost="{B}{B}",
            cmc=2,
            type_line="Sorcery",
            color_identity=["B"],
            qualifying_stages=["draw"],
            oracle_text="Target player draws two cards and loses 2 life.",
        )
        sim = _to_sim_card(card)
        assert sim.is_draw is True
        assert sim.draw_count == 2

    def test_lands_never_get_effects(self):
        card = _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            qualifying_stages=["ramp"],  # bogus, but lands should ignore it
        )
        sim = _to_sim_card(card)
        assert sim.is_ramp is False
        assert sim.is_draw is False


class TestRampEffect:
    def test_ramp_adds_mana_next_turn(self):
        forest = _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            qualifying_stages=["lands"],
            quantity=40,
        )
        elves = _make_card(
            "Llanowar Elves",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            qualifying_stages=["ramp"],
            quantity=59,
        )
        deck = _make_deck([forest, elves], ["G"])
        stats = simulate(
            deck, PlaytestSimulateRequest(trials=200, turns=4, on_the_play=True, seed=11)
        )
        # By T4 the ramp deck should have meaningfully more mana available than
        # lands in play — every Llanowar cast on T1+ contributes +1 mana from
        # the following turn onwards.
        t4 = stats.per_turn[3]
        assert t4.avg_mana_available > t4.avg_lands_in_play + 0.3

    def test_lands_only_deck_mana_equals_lands(self):
        forest = _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            qualifying_stages=["lands"],
            quantity=99,
        )
        deck = _make_deck([forest], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=50, turns=4, seed=3))
        for turn in stats.per_turn:
            assert turn.avg_mana_available == pytest.approx(turn.avg_lands_in_play)


class TestDrawEffect:
    def test_cantrip_fills_hand(self):
        forest = _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            qualifying_stages=["lands"],
            quantity=40,
        )
        ponder = _make_card(
            "Ponder-like",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            qualifying_stages=["draw"],
            oracle_text="Draw a card.",
            quantity=59,
        )
        deck = _make_deck([forest, ponder], ["G"])
        # Compare against the same deck with the same shapes minus the draw tag.
        plain = _make_card(
            "Grizzly Bear",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            qualifying_stages=[],
            quantity=59,
        )
        plain_deck = _make_deck([forest, plain], ["G"])
        with_draw = simulate(deck, PlaytestSimulateRequest(trials=200, turns=4, seed=7))
        without_draw = simulate(plain_deck, PlaytestSimulateRequest(trials=200, turns=4, seed=7))
        # Both can cast their 1-drops on curve; the draw deck should also have
        # cast strictly more spells by T4 because each cantrip refills the hand.
        assert (
            with_draw.per_turn[3].avg_spells_cast_cumulative
            > without_draw.per_turn[3].avg_spells_cast_cumulative
        )


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
