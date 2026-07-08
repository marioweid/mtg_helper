"""Tests for the MTGJSON sidecar metadata pipeline."""

import json
import zipfile
from io import BytesIO
from typing import Any

from mtg_helper.services import mtgjson


def _make_card(**kwargs: Any) -> dict[str, Any]:
    defaults = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "name": "Test Card",
        "keywords": ["Flying", "Flying", "Vigilance"],
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Human", "Wizard"],
        "edhrecSaltiness": 0.42,
        "isFunny": False,
        "isOnlineOnly": False,
        "isRebalanced": False,
        "isGameChanger": True,
        "leadershipSkills": {"commander": True},
        "relatedCards": {"reverseRelated": ["Token"]},
        "identifiers": {
            "scryfallId": "22222222-2222-2222-2222-222222222222",
            "scryfallOracleId": "33333333-3333-3333-3333-333333333333",
        },
    }
    return {**defaults, **kwargs}


def test_map_card_extracts_metadata() -> None:
    mapped = mtgjson._map_card(_make_card())

    assert mapped is not None
    assert mapped.scryfall_id == "22222222-2222-2222-2222-222222222222"
    assert mapped.name == "Test Card"
    assert mapped.keywords == ["Flying", "Vigilance"]
    assert mapped.types == ["Creature"]
    assert mapped.supertypes == ["Legendary"]
    assert mapped.subtypes == ["Human", "Wizard"]
    assert mapped.edhrec_saltiness == 0.42
    assert mapped.is_game_changer is True
    assert mapped.leadership_skills == {"commander": True}


def test_map_card_skips_rows_without_scryfall_id() -> None:
    card = _make_card(identifiers={})

    assert mtgjson._map_card(card) is None


def test_extract_cards_reads_all_printings_shape() -> None:
    payload = {
        "data": {
            "TST": {
                "cards": [
                    _make_card(name="Alpha"),
                    _make_card(
                        uuid="44444444-4444-4444-4444-444444444444",
                        name="No Scryfall",
                        identifiers={},
                    ),
                ]
            }
        }
    }

    cards = mtgjson._extract_cards(payload)

    assert len(cards) == 1
    assert cards[0].name == "Alpha"


def test_decode_payload_accepts_zip_archive() -> None:
    source = {"data": {"TST": {"cards": [_make_card()]}}}
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w") as archive:
        archive.writestr("AllPrintings.json", json.dumps(source))

    payload = mtgjson._decode_payload(buf.getvalue())

    assert payload == source


def test_same_values_ignores_order() -> None:
    assert mtgjson._same_values(["Flying", "Vigilance"], ["Vigilance", "Flying"]) is True
    assert mtgjson._same_values(["Flying"], ["Vigilance"]) is False


def test_extract_keyword_catalog_maps_all_mtgjson_groups() -> None:
    payload = {
        "meta": {"date": "2026-07-08", "version": "5.3.0+20260708"},
        "data": {
            "abilityWords": ["Landfall"],
            "keywordAbilities": ["Double strike"],
            "keywordActions": ["Surveil"],
        },
    }

    keywords = mtgjson._extract_keyword_catalog(payload)

    assert [(item.label, item.tag, item.category) for item in keywords] == [
        ("Landfall", "landfall", "ability_word"),
        ("Double strike", "double_strike", "keyword_ability"),
        ("Surveil", "surveil", "keyword_action"),
    ]
    assert keywords[0].mtgjson_version == "5.3.0+20260708"
    assert str(keywords[0].mtgjson_date) == "2026-07-08"
