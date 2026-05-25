"""Unit tests for the mana_base_service pure functions."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mtg_helper.models.ai import CardSuggestion
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import mana_base_service
from mtg_helper.services.mana_base_service import (
    _COLORS,
    _karsten_requirement,
    _recommend_land_count,
    analyze_mana_base,
    candidate_lands,
    parse_pips,
)


def _make_card(
    name: str,
    *,
    mana_cost: str | None = None,
    type_line: str = "Creature — Human",
    color_identity: list[str] | None = None,
    quantity: int = 1,
    cmc: float = 0.0,
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
        name="Test",
        description=None,
        bracket=3,
        stage="lands",
        commander_id=uuid4(),
        partner_id=None,
        commander_color_identity=color_identity,
        owner_email=None,
        created_at=now,
        updated_at=now,
        cards=cards,
    )


class TestParsePips:
    def test_no_cost_returns_zeros(self):
        pips = parse_pips(None)
        assert pips == {c: 0.0 for c in _COLORS}

    def test_empty_cost_returns_zeros(self):
        assert parse_pips("") == {c: 0.0 for c in _COLORS}

    def test_mono_colored_pips_count_one_each(self):
        pips = parse_pips("{W}{W}{U}")
        assert pips["W"] == 2.0
        assert pips["U"] == 1.0
        assert pips["B"] == 0.0

    def test_generic_and_x_do_not_contribute(self):
        pips = parse_pips("{X}{2}{R}")
        assert pips["R"] == 1.0
        assert sum(pips[c] for c in "WUBG") == 0.0

    def test_hybrid_splits_half_each(self):
        pips = parse_pips("{W/U}")
        assert pips["W"] == 0.5
        assert pips["U"] == 0.5

    def test_phyrexian_half_pip(self):
        pips = parse_pips("{W/P}")
        assert pips["W"] == 0.5

    def test_twobrid_half_pip(self):
        pips = parse_pips("{2/G}")
        assert pips["G"] == 0.5

    def test_mixed_realistic_cost(self):
        pips = parse_pips("{1}{G}{G}{W/U}")
        assert pips["G"] == 2.0
        assert pips["W"] == 0.5
        assert pips["U"] == 0.5


class TestAnalyzeManaBase:
    def test_mono_color_balanced_no_deficit(self):
        cards = [
            _make_card("Llanowar Elves", mana_cost="{G}"),
            _make_card("Cultivate", mana_cost="{2}{G}"),
        ] + [
            _make_card("Forest", type_line="Basic Land — Forest", color_identity=["G"])
            for _ in range(20)
        ]
        report = analyze_mana_base(_make_deck(cards, ["G"]))
        assert report.total_lands == 20
        assert len(report.colors) == 1
        green = report.colors[0]
        assert green.color == "G"
        assert green.pip_count == 2.0
        assert green.source_count == 20
        assert green.deficit == 0

    def test_two_color_imbalanced_flags_deficit(self):
        # 10 colored spells in white, 0 colored sources for white → deficit
        cards = [_make_card(f"WhiteSpell{i}", mana_cost="{W}{W}") for i in range(5)]
        cards += [_make_card(f"BlueSpell{i}", mana_cost="{U}") for i in range(3)]
        cards += [
            _make_card("Island", type_line="Basic Land — Island", color_identity=["U"])
            for _ in range(20)
        ]
        report = analyze_mana_base(_make_deck(cards, ["W", "U"]))
        white = next(c for c in report.colors if c.color == "W")
        blue = next(c for c in report.colors if c.color == "U")
        assert white.pip_count == 10.0
        assert white.source_count == 0
        assert white.deficit > 0
        assert blue.deficit == 0

    def test_quantity_multiplies_pips_and_sources(self):
        cards = [
            _make_card("Lightning Bolt", mana_cost="{R}", quantity=4),
            _make_card(
                "Mountain",
                type_line="Basic Land — Mountain",
                color_identity=["R"],
                quantity=18,
            ),
        ]
        report = analyze_mana_base(_make_deck(cards, ["R"]))
        assert report.colors[0].pip_count == 4.0
        assert report.colors[0].source_count == 18
        assert report.total_lands == 18

    def test_non_land_with_color_identity_does_not_count_as_source(self):
        cards = [
            _make_card("Sol Ring", mana_cost="{1}", type_line="Artifact", color_identity=[]),
            _make_card("Plains", type_line="Basic Land — Plains", color_identity=["W"]),
        ]
        report = analyze_mana_base(_make_deck(cards, ["W"]))
        assert report.colors[0].source_count == 1
        assert report.total_lands == 1

    def test_non_basic_land_uses_color_identity_as_source(self):
        cards = [
            _make_card(
                "Hallowed Fountain",
                type_line="Land — Plains Island",
                color_identity=["W", "U"],
            ),
            _make_card(
                "Plains",
                type_line="Basic Land — Plains",
                color_identity=["W"],
                quantity=10,
            ),
            _make_card(
                "Island",
                type_line="Basic Land — Island",
                color_identity=["U"],
                quantity=10,
            ),
            _make_card("WhiteSpell", mana_cost="{W}"),
            _make_card("BlueSpell", mana_cost="{U}"),
        ]
        report = analyze_mana_base(_make_deck(cards, ["W", "U"]))
        white = next(c for c in report.colors if c.color == "W")
        blue = next(c for c in report.colors if c.color == "U")
        # Dual counts toward both colors
        assert white.source_count == 11
        assert blue.source_count == 11

    def test_colorless_basic_does_not_produce_color(self):
        cards = [
            _make_card("Wastes", type_line="Basic Land — Wastes", color_identity=[]),
            _make_card("Plains", type_line="Basic Land — Plains", color_identity=["W"]),
            _make_card("Spell", mana_cost="{W}"),
        ]
        report = analyze_mana_base(_make_deck(cards, ["W"]))
        assert report.total_lands == 2
        assert report.colors[0].source_count == 1


class TestRecommendLandCount:
    def test_low_cmc_heavy_ramp_clamped_to_min(self):
        assert _recommend_land_count(avg_cmc=2.0, ramp_count=10) == 32

    def test_high_cmc_no_ramp_clamped_to_max(self):
        assert _recommend_land_count(avg_cmc=5.0, ramp_count=0) == 42

    def test_typical_midrange_value(self):
        # 31.42 + 3.13*3.0 - 0.28*8 = 31.42 + 9.39 - 2.24 = 38.57 → 39
        assert _recommend_land_count(avg_cmc=3.0, ramp_count=8) == 39


class TestKarstenRequirement:
    def test_double_white_turn_4_is_20(self):
        assert _karsten_requirement(4, 2) == 20

    def test_single_pip_turn_3_is_16(self):
        assert _karsten_requirement(3, 1) == 16

    def test_clamp_high_turn(self):
        # turn 9 clamped to 6
        assert _karsten_requirement(9, 2) == 18

    def test_unreachable_returns_zero(self):
        # Double-pip on turn 1 is impossible
        assert _karsten_requirement(1, 2) == 0


class TestTurnNAnalysis:
    def test_double_pip_4drop_with_few_sources_is_risky(self):
        # Wrath-like cost {2}{W}{W}, only 10 W sources → Karsten says need 20
        cards = [
            _make_card(
                "Pseudo-Wrath",
                mana_cost="{2}{W}{W}",
                type_line="Sorcery",
                cmc=4.0,
            ),
        ] + [
            _make_card("Plains", type_line="Basic Land — Plains", color_identity=["W"])
            for _ in range(10)
        ]
        report = analyze_mana_base(_make_deck(cards, ["W"]))
        white = report.colors[0]
        assert white.turn_demand == 20
        assert white.turn_deficit == 10  # 20 required - 10 available
        names = [r.name for r in white.risky_cards]
        assert "Pseudo-Wrath" in names
        risky = next(r for r in white.risky_cards if r.name == "Pseudo-Wrath")
        assert risky.pips_required == 2
        assert risky.sources_available == 10
        assert risky.sources_required == 20

    def test_safe_when_sources_meet_requirement(self):
        cards = [
            _make_card(
                "Pseudo-Wrath",
                mana_cost="{2}{W}{W}",
                type_line="Sorcery",
                cmc=4.0,
            ),
        ] + [
            _make_card("Plains", type_line="Basic Land — Plains", color_identity=["W"])
            for _ in range(22)
        ]
        report = analyze_mana_base(_make_deck(cards, ["W"]))
        white = report.colors[0]
        assert white.turn_deficit == 0
        assert white.risky_cards == []


class TestAggregateRecommendations:
    def test_land_delta_reflects_recommendation(self):
        cards = [
            _make_card("Cheap", mana_cost="{1}{G}", type_line="Creature — Elf", cmc=2.0),
        ] + [
            _make_card("Forest", type_line="Basic Land — Forest", color_identity=["G"])
            for _ in range(30)
        ]
        # Pass empty card_tags to enable land recommendation path
        report = analyze_mana_base(_make_deck(cards, ["G"]), card_tags={})
        # avg_cmc = 2.0, ramp = 0 → 31.42 + 6.26 = 37.68 → 38, clamped no
        assert report.recommended_lands == 38
        assert report.land_delta == 38 - 30
        assert report.avg_cmc == 2.0
        assert report.ramp_count == 0

    def test_ramp_count_uses_tags(self):
        ramp_card = _make_card("Llanowar Elves", mana_cost="{G}", cmc=1.0)
        cards = [
            ramp_card,
            _make_card("Beast", mana_cost="{4}{G}", cmc=5.0),
        ] + [
            _make_card("Forest", type_line="Basic Land — Forest", color_identity=["G"])
            for _ in range(20)
        ]
        tags = {ramp_card.card_id: ["ramp"]}
        report = analyze_mana_base(_make_deck(cards, ["G"]), card_tags=tags)
        assert report.ramp_count == 1


class TestCandidateLands:
    @pytest.mark.asyncio
    async def test_filters_to_lands_and_forwards_price_and_limit(self, monkeypatch):
        land = SimpleNamespace(type_line="Land", scryfall_id=uuid4(), name="Temple Garden")
        nonland = SimpleNamespace(
            type_line="Creature — Elf", scryfall_id=uuid4(), name="Llanowar Elves"
        )
        captured: dict[str, object] = {}

        async def fake_retrieve(*_args, **kwargs):
            captured.update(kwargs)
            return [land, nonland]

        def fake_card_from_retrieved(card, *_a, **_k):
            return CardSuggestion(
                scryfall_id=card.scryfall_id,
                name=card.name,
                mana_cost=None,
                type_line=card.type_line,
                image_uri=None,
                category="lands",
                reasoning="",
                synergies=[],
            )

        monkeypatch.setattr(mana_base_service, "retrieve_candidates", fake_retrieve)
        monkeypatch.setattr(mana_base_service, "card_from_retrieved", fake_card_from_retrieved)
        monkeypatch.setattr(
            mana_base_service.collection_service,
            "build_ownership_map",
            AsyncMock(return_value={}),
        )

        deck = _make_deck([], ["G", "W"])
        result = await candidate_lands(
            MagicMock(), MagicMock(), MagicMock(), deck, max_price_cents=500, limit=40
        )
        assert [c.name for c in result] == ["Temple Garden"]
        assert captured["limit"] == 40
        assert captured["price_filter"].max_cents == 500
        assert captured["stage"] == "lands"

    @pytest.mark.asyncio
    async def test_no_price_filter_when_cap_none(self, monkeypatch):
        captured: dict[str, object] = {}

        async def fake_retrieve(*_args, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(mana_base_service, "retrieve_candidates", fake_retrieve)
        monkeypatch.setattr(
            mana_base_service.collection_service,
            "build_ownership_map",
            AsyncMock(return_value={}),
        )
        deck = _make_deck([], ["G"])
        await candidate_lands(MagicMock(), MagicMock(), MagicMock(), deck, max_price_cents=None)
        assert captured["price_filter"] is None
