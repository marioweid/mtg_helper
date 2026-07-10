"""Tests for deckbuilder role derivation."""

from mtg_helper.services.builder_roles import derive_builder_roles


def test_derive_builder_roles_counts_wheels_as_card_draw() -> None:
    roles = derive_builder_roles(["wheels"], [], "Sorcery")

    assert roles.roles == ["draw"]
    assert roles.reasons == {"draw": ["wheels"]}


def test_derive_builder_roles_uses_edhrec_and_mtgjson_tags() -> None:
    roles = derive_builder_roles(["control"], ["cycling"], "Instant")

    assert roles.roles == ["draw", "interaction"]
    assert roles.reasons == {"draw": ["cycling"], "interaction": ["control"]}


def test_derive_builder_roles_counts_lands_by_type() -> None:
    roles = derive_builder_roles(["ramp"], [], "Legendary Land")

    assert roles.roles == ["lands"]
    assert roles.reasons == {"lands": ["type: land"]}
