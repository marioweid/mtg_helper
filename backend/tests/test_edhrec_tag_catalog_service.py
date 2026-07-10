"""Tests for EDHREC tag catalog normalization."""

from mtg_helper.services.edhrec_tag_catalog_service import _slug_to_tag


def test_slug_to_tag_normalizes_plus_one_counter_slug() -> None:
    assert _slug_to_tag("plus-1-plus-1-counters") == "plus_one_plus_one_counters"


def test_slug_to_tag_keeps_singular_treasure_slug() -> None:
    assert _slug_to_tag("treasure") == "treasure"
