"""Tests for deterministic card representation helpers."""

from decimal import Decimal

from mtg_helper.services import card_representation


def test_representation_embedding_text_includes_structured_labels() -> None:
    text = card_representation.build_embedding_text(
        name="Seedborn Muse",
        type_line="Creature - Spirit",
        oracle_text="Untap all permanents you control during each other players untap step.",
        color_identity=["G"],
        keywords=["Vigilance"],
        card_types=["Creature"],
        subtypes=["Spirit"],
        tags=["ramp"],
        traits=["activated"],
        token_types=["treasure"],
        mana_value=Decimal("5"),
        edhrec_rank=123,
    )

    assert "Name: Seedborn Muse" in text
    assert "Card types: Creature" in text
    assert "Commander role tags: ramp" in text
    assert "Produces tokens: treasure" in text
    assert "Mana value: 5" in text
    assert "EDHREC rank: 123" in text


def test_representation_feature_payload_is_structured() -> None:
    rep = card_representation.from_card_fields(
        name="Academy Manufactor",
        type_line="Artifact Creature - Assembly-Worker",
        oracle_text="If you would create a Clue, Food, or Treasure token...",
        color_identity=[],
        keywords=[],
        card_types=["Artifact", "Creature"],
        subtypes=["Assembly-Worker"],
        tags=["token", "treasure_matters"],
        traits=[],
        token_types=["clue", "food", "treasure"],
        mana_value=3,
        edhrec_rank=400,
    )

    assert rep.feature_payload()["card_types"] == ["Artifact", "Creature"]
    assert rep.feature_payload()["token_types"] == ["clue", "food", "treasure"]
    assert "tag:treasure_matters" in rep.feature_labels()
    assert "mana_value:2-3" in rep.feature_labels()


def test_representation_deduplicates_features_stably() -> None:
    rep = card_representation.from_card_fields(
        name="Test",
        type_line=None,
        oracle_text=None,
        keywords=["Flying", "Flying", "Vigilance"],
    )

    assert rep.keywords == ["Flying", "Vigilance"]
