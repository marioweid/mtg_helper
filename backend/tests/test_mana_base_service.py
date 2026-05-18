"""Unit tests for the mana_base_service pure functions."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services.mana_base_service import (
    _COLORS,
    analyze_mana_base,
    parse_pips,
)


def _make_card(
    name: str,
    *,
    mana_cost: str | None = None,
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
        cmc=Decimal("0"),
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
