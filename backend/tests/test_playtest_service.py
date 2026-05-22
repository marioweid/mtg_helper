"""Unit + endpoint tests for the goldfish playtest simulator."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import (
    BoardStateThreshold,
    EngineClass,
    EngineThresholdConfig,
    ManaEngineThreshold,
    PlaytestSimulateRequest,
)
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
    tags: list[str] | None = None,
    power: int | None = None,
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
        tags=tags or [],
        power=power,
        price_eur_cents=None,
    )


def _make_commander(
    name: str = "Test Commander",
    *,
    mana_cost: str | None = "{2}{G}",
    cmc: int = 3,
    type_line: str = "Legendary Creature — Elf",
    color_identity: list[str] | None = None,
    power: int | None = 3,
    tags: list[str] | None = None,
    oracle_text: str | None = None,
) -> CommanderCardSummary:
    return CommanderCardSummary(
        id=uuid4(),
        name=name,
        mana_cost=mana_cost,
        cmc=Decimal(str(cmc)),
        type_line=type_line,
        oracle_text=oracle_text,
        image_uri=None,
        color_identity=color_identity or ["G"],
        power=power,
        tags=tags or [],
    )


def _make_deck(
    cards: list[DeckCardItem],
    color_identity: list[str],
    commander: CommanderCardSummary | None = None,
    partner: CommanderCardSummary | None = None,
) -> DeckDetailResponse:
    now = datetime(2026, 5, 18)
    return DeckDetailResponse(
        id=uuid4(),
        name="Sim",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=uuid4(),
        partner_id=uuid4() if partner is not None else None,
        commander_color_identity=color_identity,
        commander_card=commander,
        partner_card=partner,
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


class TestFloodScrew:
    def test_pure_lands_flagged_as_flood(self):
        cards = [
            _make_card("Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=99)
        ]
        deck = _make_deck(cards, ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=50, turns=5, seed=42))
        assert stats.pct_flood == 1.0
        assert stats.pct_screw == 0.0

    def test_pure_spells_flagged_as_screw(self):
        cards = [_make_card(f"Spell{i}", mana_cost="{2}{G}{G}", cmc=4) for i in range(99)]
        deck = _make_deck(cards, ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=30, turns=5, seed=1))
        assert stats.pct_screw == 1.0
        assert stats.pct_flood == 0.0


class TestManaUtilization:
    def test_utilization_climbs_on_curve_deck(self):
        forest = _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            quantity=37,
            qualifying_stages=["lands"],
        )
        one_drop = _make_card("1-Drop", mana_cost="{G}", cmc=1, color_identity=["G"], quantity=20)
        two_drop = _make_card(
            "2-Drop", mana_cost="{1}{G}", cmc=2, color_identity=["G"], quantity=20
        )
        three_drop = _make_card(
            "3-Drop", mana_cost="{2}{G}", cmc=3, color_identity=["G"], quantity=22
        )
        deck = _make_deck([forest, one_drop, two_drop, three_drop], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=300, turns=4, seed=7))
        # By T3 a curve deck should have at least some mana spent on average.
        assert stats.per_turn[2].avg_mana_spent > 0.5
        assert stats.per_turn[2].mana_utilization > 0.0


class TestOpeningHandStats:
    def test_kept_breakdown_sums_to_one(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=37
        )
        bear = _make_card("Bear", mana_cost="{1}{G}", cmc=2, color_identity=["G"], quantity=62)
        deck = _make_deck([forest, bear], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=200, turns=4, seed=3))
        oh = stats.opening_hand
        total = oh.pct_kept_7 + oh.pct_kept_6 + oh.pct_kept_5 + oh.pct_kept_le4
        assert total == pytest.approx(1.0)
        # Reasonable mana base → most hands keep at 7.
        assert oh.pct_kept_7 > 0.5


class TestDeadCardsAndInteraction:
    def test_interaction_excluded_from_dead_count(self):
        # Forest base + a single colored removal spell that won't be cast in
        # early turns (CMC 4) — it must NOT show up as dead because of tags.
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=37
        )
        removal = _make_card(
            "Beast Within",
            mana_cost="{2}{G}",
            cmc=3,
            color_identity=["G"],
            tags=["removal"],
            quantity=62,
        )
        deck = _make_deck([forest, removal], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=200, turns=2, seed=5))
        # Removal sits in hand for T1 — should be counted as interaction, not dead.
        assert stats.per_turn[0].avg_interaction_in_hand > 0.0
        assert stats.per_turn[0].avg_dead_cards == 0.0

    def test_untagged_uncastable_counted_as_dead(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=37
        )
        big = _make_card(
            "Big Beast",
            mana_cost="{4}{G}{G}{G}",
            cmc=7,
            color_identity=["G"],
            quantity=62,
        )
        deck = _make_deck([forest, big], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=100, turns=2, seed=9))
        # 7-drops are not castable by T2 and not tagged interaction → dead.
        assert stats.per_turn[0].avg_dead_cards > 0.0


class TestTutorAsDraw:
    def test_tutor_resolution_adds_to_cards_drawn_extra(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=37
        )
        # A 1-mana "tutor" — not tagged as draw, only as tutor — should pull one
        # card from the top of the library per resolution.
        tutor = _make_card(
            "Mock Tutor",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            tags=["tutor"],
            quantity=62,
        )
        deck = _make_deck([forest, tutor], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=200, turns=3, seed=13))
        assert stats.per_turn[2].avg_tutors_cast > 0.0
        assert stats.per_turn[2].avg_cards_drawn_extra > 0.0


class TestFirstMissedLand:
    def test_smooth_deck_never_misses_within_window(self):
        forest = _make_card(
            "Forest", type_line="Basic Land — Forest", color_identity=["G"], quantity=99
        )
        deck = _make_deck([forest], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=50, turns=4, seed=2))
        # Never misses → reported as turns + 1 sentinel value.
        assert stats.avg_first_missed_land_turn == pytest.approx(5.0)


class TestEngineThresholds:
    def _forests(self, quantity: int = 37) -> DeckCardItem:
        return _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            quantity=quantity,
            qualifying_stages=["lands"],
        )

    def test_pure_lands_never_hits_any_threshold(self):
        deck = _make_deck([self._forests(99)], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=30, turns=6, seed=11))
        # No creatures, no spells, mana plateaus at land count → no threshold.
        assert stats.engine_thresholds.pct_ever_any == 0.0
        assert stats.per_turn[-1].pct_any_threshold_hit_cum == 0.0

    def test_token_deck_hits_board_state_via_creature_count(self):
        # 99 free 1/1 creatures with {G} cost: deck floods the board fast.
        # Lower the threshold so the small-trial sim reliably crosses it.
        forest = self._forests(40)
        weenie = _make_card(
            "Weenie",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            quantity=59,
            power=1,
        )
        deck = _make_deck([forest, weenie], ["G"])
        cfg = EngineThresholdConfig(board_state=BoardStateThreshold(min_power=999, min_creatures=4))
        stats = simulate(
            deck,
            PlaytestSimulateRequest(trials=200, turns=6, seed=17, thresholds=cfg),
        )
        assert stats.engine_thresholds.pct_ever_board_state > 0.5

    def test_big_creatures_hit_board_state_via_power(self):
        forest = self._forests(40)
        # 6/6 for {G}{G} — power scales fast even with few bodies.
        beast = _make_card(
            "Mock Beast",
            mana_cost="{G}{G}",
            cmc=2,
            color_identity=["G"],
            quantity=59,
            power=6,
        )
        deck = _make_deck([forest, beast], ["G"])
        cfg = EngineThresholdConfig(
            board_state=BoardStateThreshold(min_power=18, min_creatures=999)
        )
        stats = simulate(
            deck,
            PlaytestSimulateRequest(trials=200, turns=6, seed=23, thresholds=cfg),
        )
        # By T6 the deck should have stacked enough power to cross 18.
        assert stats.engine_thresholds.pct_ever_board_state > 0.5

    def test_threshold_override_makes_mana_engine_easier(self):
        forest = self._forests(99)
        deck = _make_deck([forest], ["G"])
        # Override min_mana=4 + min_hand=0 so a lands-only deck on T4 qualifies.
        cfg = EngineThresholdConfig(mana_engine=ManaEngineThreshold(min_mana=4, min_hand=0))
        stats = simulate(
            deck,
            PlaytestSimulateRequest(trials=50, turns=6, seed=29, thresholds=cfg),
        )
        # Sentinel for never-hit is turns + 1 = 7. With the override every trial
        # should hit by T4 → average well below 7.
        assert stats.engine_thresholds.pct_ever_mana_engine == 1.0
        assert stats.engine_thresholds.avg_first_mana_engine_turn < 5.0

    def test_per_turn_cumulative_hit_is_monotonic(self):
        forest = self._forests(40)
        weenie = _make_card(
            "Weenie",
            mana_cost="{G}",
            cmc=1,
            color_identity=["G"],
            quantity=59,
            power=1,
        )
        deck = _make_deck([forest, weenie], ["G"])
        cfg = EngineThresholdConfig(board_state=BoardStateThreshold(min_power=999, min_creatures=3))
        stats = simulate(
            deck,
            PlaytestSimulateRequest(trials=100, turns=6, seed=31, thresholds=cfg),
        )
        cum_vals = [t.pct_board_state_hit_cum for t in stats.per_turn]
        for prev, nxt in zip(cum_vals, cum_vals[1:], strict=True):
            assert nxt >= prev


class TestCommanderAndEngine:
    def _forests(self, quantity: int = 99) -> DeckCardItem:
        return _make_card(
            "Forest",
            type_line="Basic Land — Forest",
            color_identity=["G"],
            quantity=quantity,
            qualifying_stages=["lands"],
        )

    def test_no_commander_means_no_stats_and_none_engine(self):
        deck = _make_deck([self._forests()], ["G"])
        stats = simulate(deck, PlaytestSimulateRequest(trials=20, turns=4, seed=1))
        assert stats.commander is None
        assert stats.partner is None
        assert stats.engine_class is EngineClass.NONE

    def test_commander_cast_turn_close_to_cmc(self):
        cmdr = _make_commander(name="Hazel", mana_cost="{2}{G}", cmc=3, power=2)
        deck = _make_deck([self._forests()], ["G"], commander=cmdr)
        stats = simulate(
            deck,
            PlaytestSimulateRequest(trials=200, turns=6, seed=51, on_the_play=True),
        )
        assert stats.commander is not None
        assert stats.commander.pct_ever_cast > 0.9
        assert stats.commander.avg_cast_turn < 4.0

    def test_token_commander_yields_extra_creatures(self):
        cmdr = _make_commander(
            name="Token Lord",
            mana_cost="{1}{G}",
            cmc=2,
            power=2,
            tags=["token"],
        )
        deck = _make_deck([self._forests()], ["G"], commander=cmdr)
        stats = simulate(deck, PlaytestSimulateRequest(trials=200, turns=6, seed=61))
        assert stats.engine_class is EngineClass.TOKEN_GENERATOR
        # Commander cast ~T2; from T3 onward yield adds +1 creature/turn.
        assert stats.per_turn[-1].avg_creatures_on_board > 1.5

    def test_ramp_commander_accelerates_mana_threshold(self):
        ramp_cmdr = _make_commander(
            name="Ramp Bot", mana_cost="{G}{G}", cmc=2, power=1, tags=["ramp"]
        )
        plain_cmdr = _make_commander(name="Plain Bot", mana_cost="{G}{G}", cmc=2, power=1, tags=[])
        ramp_deck = _make_deck([self._forests()], ["G"], commander=ramp_cmdr)
        plain_deck = _make_deck([self._forests()], ["G"], commander=plain_cmdr)
        cfg = EngineThresholdConfig(mana_engine=ManaEngineThreshold(min_mana=6, min_hand=0))
        req = PlaytestSimulateRequest(trials=300, turns=8, seed=71, thresholds=cfg)
        ramp_stats = simulate(ramp_deck, req)
        plain_stats = simulate(plain_deck, req)
        assert ramp_stats.engine_thresholds.avg_first_mana_engine_turn < (
            plain_stats.engine_thresholds.avg_first_mana_engine_turn
        )

    def test_partner_cast_turn_tracked_independently(self):
        cmdr_a = _make_commander(name="Captain", mana_cost="{1}{G}", cmc=2, power=2)
        cmdr_b = _make_commander(name="Mate", mana_cost="{2}{G}", cmc=3, power=2)
        deck = _make_deck([self._forests()], ["G"], commander=cmdr_a, partner=cmdr_b)
        stats = simulate(deck, PlaytestSimulateRequest(trials=200, turns=6, seed=81))
        assert stats.commander is not None
        assert stats.partner is not None
        assert stats.commander.pct_ever_cast > 0.9
        assert stats.partner.pct_ever_cast > 0.9
        assert stats.commander.avg_cast_turn < stats.partner.avg_cast_turn


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
