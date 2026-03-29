"""Tests for the Scryfall bulk data pipeline."""

from typing import Any

from mtg_helper.services.scryfall import (
    _extract_image_uri,
    _is_commander_relevant,
    _map_card,
)


def _make_card(**kwargs: Any) -> dict[str, Any]:
    defaults = {
        "id": "abc123",
        "oracle_id": "oracle123",
        "name": "Test Card",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature — Elf",
        "oracle_text": "Flying",
        "color_identity": ["G"],
        "colors": ["G"],
        "keywords": ["Flying"],
        "power": "2",
        "toughness": "2",
        "legalities": {"commander": "legal"},
        "image_uris": {"normal": "https://scryfall.example/img.jpg"},
        "prices": {"usd": "1.00"},
        "rarity": "common",
        "set": "lea",
        "released_at": "1993-08-05",
        "edhrec_rank": 500,
    }
    return {**defaults, **kwargs}


def test_map_card_basic_fields() -> None:
    card = _make_card()
    mapped = _map_card(card)
    assert mapped["scryfall_id"] == "abc123"
    assert mapped["name"] == "Test Card"
    assert mapped["color_identity"] == ["G"]
    assert mapped["image_uri"] == "https://scryfall.example/img.jpg"
    assert mapped["set_code"] == "lea"


def test_map_card_empty_arrays() -> None:
    card = _make_card(color_identity=None, colors=None, keywords=None)
    mapped = _map_card(card)
    assert mapped["color_identity"] == []
    assert mapped["colors"] == []
    assert mapped["keywords"] == []


def test_extract_image_uri_normal() -> None:
    card = _make_card()
    assert _extract_image_uri(card) == "https://scryfall.example/img.jpg"


def test_extract_image_uri_double_faced() -> None:
    card = _make_card()
    del card["image_uris"]
    card["card_faces"] = [
        {"image_uris": {"normal": "https://scryfall.example/front.jpg"}},
        {"image_uris": {"normal": "https://scryfall.example/back.jpg"}},
    ]
    assert _extract_image_uri(card) == "https://scryfall.example/front.jpg"


def test_extract_image_uri_no_image() -> None:
    card = _make_card()
    del card["image_uris"]
    assert _extract_image_uri(card) is None


def test_is_commander_relevant_legal() -> None:
    assert _is_commander_relevant({"legalities": {"commander": "legal"}}) is True


def test_is_commander_relevant_banned() -> None:
    assert _is_commander_relevant({"legalities": {"commander": "banned"}}) is True


def test_is_commander_relevant_not_legal() -> None:
    assert _is_commander_relevant({"legalities": {"commander": "not_legal"}}) is False


def test_is_commander_relevant_no_legalities() -> None:
    assert _is_commander_relevant({}) is False
