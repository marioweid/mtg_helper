"""Behavior tests for deterministic MTG Assistant tools."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from mtg_helper.models.ai import CardSuggestion, ColorStatus, ManaBaseReport, ManaFixResponse
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.mtg_assistant_tools import (
    _compose_mana_base_analysis,
    _structural_issues,
    _theme_match_score,
    check_bracket,
    check_game_changers,
)


def _card(name: str, *, quantity: int = 1, game_changer: bool = False) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="Create a token.",
        color_identity=["G"],
        image_uri=None,
        rarity="rare",
        quantity=quantity,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        game_changer=game_changer,
    )


def _land(
    name: str,
    colors: list[str],
    *,
    oracle_text: str = "",
    quantity: int = 1,
) -> DeckCardItem:
    card = _card(name, quantity=quantity)
    return card.model_copy(
        update={
            "mana_cost": None,
            "cmc": Decimal("0"),
            "type_line": "Basic Land" if name in {"Forest", "Island"} else "Land",
            "oracle_text": oracle_text,
            "color_identity": colors,
        }
    )


def _mana_fix(suggestions: list[CardSuggestion]) -> ManaFixResponse:
    return ManaFixResponse(
        report=ManaBaseReport(
            total_lands=36,
            total_colored_pips=30,
            colors=[ColorStatus(color="G", pip_count=30, source_count=12, target=16, deficit=4)],
            avg_cmc=3.0,
            ramp_count=8,
            recommended_lands=36,
            land_delta=0,
        ),
        suggestions=suggestions,
    )


def _suggestion(name: str) -> CardSuggestion:
    return CardSuggestion(
        scryfall_id=uuid4(),
        name=name,
        mana_cost=None,
        type_line="Land",
        image_uri=None,
        oracle_text="{T}: Add {G}.",
        cmc=0,
        color_identity=["G"],
        category="lands",
        reasoning="Adds a needed green source.",
        synergies=["lands"],
    )


def _deck(cards: list[DeckCardItem], *, bracket: int = 3) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Assistant Test",
        description=None,
        bracket=bracket,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Test Commander",
            color_identity=["G"],
        ),
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        cards=cards,
    )


class _ThemeRow(dict[str, object]):
    def __getitem__(self, key: str) -> object:
        return super().__getitem__(key)


def test_theme_match_uses_aliases_and_description() -> None:
    row = _ThemeRow(
        tag="x_spells",
        label="X Spells",
        description="Variable-cost spells and scalable mana payoffs.",
        aliases=["big x spells", "variable mana"],
        source="group",
    )

    assert _theme_match_score("big x spells", row) == 1.0
    assert _theme_match_score("scalable mana", row) > 0.0


def test_structural_legality_rejects_wrong_size_and_duplicates() -> None:
    deck = _deck([_card("Repeated Card", quantity=2)])

    issues = _structural_issues(deck)

    assert {issue.code for issue in issues} == {"deck_size", "singleton"}


def test_mana_analysis_pairs_grounded_candidate_with_safe_in_deck_land() -> None:
    colorless = _land("Reliquary Tower", [], oracle_text="You have no maximum hand size.")
    green = _land("Forest", ["G"], quantity=12)
    deck = _deck([colorless, green])
    candidate = _suggestion("Llanowar Wastes")

    result = _compose_mana_base_analysis(deck, _mana_fix([candidate]))

    assert result.swaps[0].remove_card == "Reliquary Tower"
    assert result.swaps[0].add.scryfall_id == candidate.scryfall_id
    assert result.swaps[0].add.name == "Llanowar Wastes"


def test_mana_analysis_does_not_remove_a_deficient_color_source() -> None:
    deck = _deck([_land("Forest", ["G"], quantity=12)])

    result = _compose_mana_base_analysis(deck, _mana_fix([_suggestion("Llanowar Wastes")]))

    assert result.swaps == []
    assert result.unresolved


@pytest.mark.parametrize("bracket", [1, 2])
def test_bracket_check_is_deterministic_for_game_changers(bracket: int) -> None:
    cards = [_card("Power Card", game_changer=True)]

    report = check_bracket(_deck(cards, bracket=bracket))

    assert not report.acceptable
    assert report.ruleset == "project-commander-brackets-v1"
    assert any("Game Changers" in warning for warning in report.warnings)


def test_bracket_report_lists_game_changers_and_limit() -> None:
    cards = [
        _card("Mana Crypt", game_changer=True),
        _card("Rhystic Study", game_changer=True),
        _card("Jeweled Lotus", game_changer=True),
        _card("Dockside Extortionist", game_changer=True),
    ]

    report = check_bracket(_deck(cards, bracket=3))

    assert report.game_changers == [
        "Dockside Extortionist",
        "Jeweled Lotus",
        "Mana Crypt",
        "Rhystic Study",
    ]
    assert report.game_changer_limit == 3
    assert report.game_changer_overage == 1
    assert not report.acceptable


def test_bracket_report_allow_three_game_changers_at_bracket_three() -> None:
    cards = [
        _card("Mana Crypt", game_changer=True),
        _card("Rhystic Study", game_changer=True),
        _card("Dockside Extortionist", game_changer=True),
    ]

    report = check_bracket(_deck(cards, bracket=3))

    assert report.acceptable
    assert report.game_changer_overage == 0
    assert report.game_changers == ["Dockside Extortionist", "Mana Crypt", "Rhystic Study"]


def test_bracket_report_unlimited_at_bracket_four() -> None:
    cards = [
        _card("Mana Crypt", game_changer=True),
        _card("Rhystic Study", game_changer=True),
        _card("Jeweled Lotus", game_changer=True),
        _card("Dockside Extortionist", game_changer=True),
    ]

    report = check_bracket(_deck(cards, bracket=4))

    assert report.acceptable
    assert report.game_changer_limit is None
    assert report.game_changer_overage == 0


def test_bracket_report_target_bracket_overrides_declared() -> None:
    cards = [
        _card("Mana Crypt", game_changer=True),
        _card("Rhystic Study", game_changer=True),
        _card("Jeweled Lotus", game_changer=True),
        _card("Dockside Extortionist", game_changer=True),
    ]

    report = check_bracket(_deck(cards, bracket=5), target_bracket=3)

    assert report.declared_bracket == 3
    assert report.game_changer_limit == 3
    assert report.game_changer_overage == 1
    assert not report.acceptable


async def _flag_game_changer(pool: asyncpg.Pool, name: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE cards SET game_changer = true WHERE name = $1", name)


async def test_check_game_changers_returns_deterministic_flags(db_pool: asyncpg.Pool) -> None:
    await _flag_game_changer(db_pool, "Rhystic Study")

    result = await check_game_changers(db_pool, ["Doubling Season", "Rhystic Study"])

    assert result.ruleset == "project-commander-brackets-v1"
    assert {item.name: item.is_game_changer for item in result.results} == {
        "Doubling Season": False,
        "Rhystic Study": True,
    }
    assert result.unknown_names == []


async def test_check_game_changers_reports_unknown_names(db_pool: asyncpg.Pool) -> None:
    result = await check_game_changers(db_pool, ["Doubling Season", "Not a Real Card"])

    assert {item.name: item.is_game_changer for item in result.results} == {
        "Doubling Season": False
    }
    assert result.unknown_names == ["Not a Real Card"]


async def test_check_game_changers_matches_mdfc_front_face(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, oracle_text,
                type_line, cmc, mana_cost, rarity, set_code, legalities,
                power, toughness, colors, keywords, prices, is_canonical, game_changer)
            VALUES ($1, $2, $3, ARRAY['B'], 'Tergrid text.', 'Legendary Creature', 4,
                    '{2}{B}{B}', 'rare', 'khm', '{}', '4', '5', ARRAY['B'], ARRAY[]::text[],
                    '{}', true, true)
            """,
            "8d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
            "8d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
            "Tergrid, God of Fright // Tergrid's Lantern",
        )

    result = await check_game_changers(db_pool, ["Tergrid, God of Fright"])

    assert len(result.results) == 1
    assert result.results[0].name == "Tergrid, God of Fright // Tergrid's Lantern"
    assert result.results[0].is_game_changer is True
    assert result.unknown_names == []


async def test_check_game_changers_rejects_too_many_names(db_pool: asyncpg.Pool) -> None:
    names = [f"Card {i}" for i in range(11)]

    with pytest.raises(ValueError, match="at most 10 names"):
        await check_game_changers(db_pool, names)
