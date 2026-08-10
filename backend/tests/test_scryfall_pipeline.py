"""Tests for the Scryfall bulk data pipeline."""

import gzip
import json
from typing import Any

import httpx
import pytest

from mtg_helper.services.scryfall import (
    _extract_image_uri,
    _fetch_bulk_data_url,
    _is_commander_relevant,
    _map_card,
    _parse_bulk_cards,
    parse_type_line,
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


async def test_fetch_bulk_data_url_uses_jsonl_download_uri() -> None:
    download_uri = "https://data.scryfall.example/oracle-cards.jsonl.gz"
    metadata = {
        "data": [
            {
                "type": "oracle_cards",
                "jsonl_download_uri": download_uri,
            }
        ]
    }
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=metadata))

    async with httpx.AsyncClient(transport=transport) as client:
        assert await _fetch_bulk_data_url(client) == download_uri


async def test_fetch_bulk_data_url_rejects_missing_jsonl_uri() -> None:
    metadata = {"data": [{"type": "oracle_cards"}]}
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=metadata))

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="missing jsonl_download_uri"):
            await _fetch_bulk_data_url(client)


def test_parse_bulk_cards_reads_gzip_jsonl() -> None:
    cards = [_make_card(id="first"), _make_card(id="second")]
    jsonl = b"\n".join(json.dumps(card).encode() for card in cards)

    assert _parse_bulk_cards(gzip.compress(jsonl)) == cards


@pytest.mark.parametrize(
    "content",
    [
        b"not gzip data",
        gzip.compress(b"not json"),
    ],
)
def test_parse_bulk_cards_rejects_invalid_download(content: bytes) -> None:
    with pytest.raises(ValueError, match="not valid gzip-compressed JSONL"):
        _parse_bulk_cards(content)


def test_parse_bulk_cards_rejects_non_object_line() -> None:
    with pytest.raises(ValueError, match="line 1 is not a card object"):
        _parse_bulk_cards(gzip.compress(b"[]"))


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


# ── parse_type_line ────────────────────────────────────────────────────────────


def test_parse_type_line_creature_with_subtypes() -> None:
    card_types, subtypes = parse_type_line("Legendary Creature \u2014 Human Wizard")
    assert card_types == ["Creature"]
    assert subtypes == ["Human", "Wizard"]


def test_parse_type_line_artifact_with_subtype() -> None:
    card_types, subtypes = parse_type_line("Artifact \u2014 Equipment")
    assert card_types == ["Artifact"]
    assert subtypes == ["Equipment"]


def test_parse_type_line_instant_no_subtypes() -> None:
    card_types, subtypes = parse_type_line("Instant")
    assert card_types == ["Instant"]
    assert subtypes == []


def test_parse_type_line_multi_type_card() -> None:
    card_types, subtypes = parse_type_line("Legendary Artifact Creature \u2014 Golem")
    assert "Artifact" in card_types
    assert "Creature" in card_types
    assert subtypes == ["Golem"]


def test_parse_type_line_double_faced_merges_faces() -> None:
    card_types, subtypes = parse_type_line(
        "Creature \u2014 Human Werewolf // Creature \u2014 Werewolf"
    )
    assert card_types == ["Creature"]
    assert "Human" in subtypes
    assert "Werewolf" in subtypes
    assert subtypes.count("Werewolf") == 1  # deduplicated


def test_parse_type_line_none_returns_empty() -> None:
    card_types, subtypes = parse_type_line(None)
    assert card_types == []
    assert subtypes == []


def test_map_card_includes_card_types_and_subtypes() -> None:
    card = _make_card(type_line="Legendary Creature \u2014 Elf Druid")
    mapped = _map_card(card)
    assert mapped["card_types"] == ["Creature"]
    assert "Elf" in mapped["subtypes"]
    assert "Druid" in mapped["subtypes"]
