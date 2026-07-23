"""Unit tests for Oracle identity Commander copy rules."""

from mtg_helper.services.card_identity_service import commander_copy_limit


def test_singleton_is_default_copy_limit() -> None:
    assert commander_copy_limit("Artifact", "{T}: Add one mana of any color.") == 1


def test_basic_lands_and_explicit_any_number_are_unlimited() -> None:
    assert commander_copy_limit("Basic Land — Forest", "{T}: Add {G}.") is None
    assert commander_copy_limit("Basic Snow Land — Forest", "{T}: Add {G}.") is None
    assert (
        commander_copy_limit(
            "Creature — Rat",
            "A deck can have any number of cards named Rat Colony.",
        )
        is None
    )


def test_finite_copy_rule_supports_words_and_digits() -> None:
    assert (
        commander_copy_limit(
            "Creature — Dwarf",
            "A deck can have up to seven cards named Seven Dwarves.",
        )
        == 7
    )
    assert (
        commander_copy_limit(
            "Creature — Advisor",
            "A deck can have up to 12 cards named Persistent Petitioners.",
        )
        == 12
    )
