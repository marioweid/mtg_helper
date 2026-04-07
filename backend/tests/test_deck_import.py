"""Tests for deck import: parser unit tests and endpoint integration tests."""

import pytest
from httpx import AsyncClient

from mtg_helper.services.import_service import parse_deck_list
from tests.conftest import (
    create_test_account,
)

# ── parse_deck_list unit tests ────────────────────────────────────────────────


def test_parse_basic_moxfield_format() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n\n1 Sol Ring\n1 Doubling Season"
    cards = parse_deck_list(text)
    assert len(cards) == 3
    commanders = [c for c in cards if c.is_commander]
    assert len(commanders) == 1
    assert commanders[0].name == "Hazel of the Rootbloom"
    assert commanders[0].quantity == 1


def test_parse_cmdr_tag_case_insensitive() -> None:
    text = "1 Sol Ring *cmdr*"
    cards = parse_deck_list(text)
    assert cards[0].is_commander is True


def test_parse_section_headers_set_category() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n\n// Ramp\n1 Sol Ring"
    cards = parse_deck_list(text)
    non_cmdr = [c for c in cards if not c.is_commander]
    assert non_cmdr[0].category == "ramp"


def test_parse_section_header_interaction() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n// Removal\n1 Swords to Plowshares"
    cards = parse_deck_list(text)
    non_cmdr = [c for c in cards if not c.is_commander]
    assert non_cmdr[0].category == "interaction"


def test_parse_section_header_lands() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n// Lands\n30 Plains"
    cards = parse_deck_list(text)
    non_cmdr = [c for c in cards if not c.is_commander]
    assert non_cmdr[0].category == "lands"
    assert non_cmdr[0].quantity == 30


def test_parse_strips_set_code_and_collector_number() -> None:
    text = "1 Sol Ring (C21) 255"
    cards = parse_deck_list(text)
    assert cards[0].name == "Sol Ring"
    assert cards[0].quantity == 1


def test_parse_strips_set_code_no_collector_number() -> None:
    text = "1 Rhystic Study (PCY)"
    cards = parse_deck_list(text)
    assert cards[0].name == "Rhystic Study"


def test_parse_split_card_name_preserved() -> None:
    # Split card: // mid-line with spaces; NOT a section header
    text = "1 Fire // Ice"
    cards = parse_deck_list(text)
    assert len(cards) == 1
    assert "Fire" in cards[0].name


def test_parse_sideboard_skipped() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring\n\nSideboard:\n1 Negate"
    cards = parse_deck_list(text)
    names = [c.name for c in cards]
    assert "Negate" not in names
    assert "Sol Ring" in names


def test_parse_maybeboard_skipped() -> None:
    text = "1 Sol Ring\n\nMaybeboard:\n1 Doubling Season"
    cards = parse_deck_list(text)
    assert all(c.name != "Doubling Season" for c in cards)


def test_parse_comment_sideboard_skipped() -> None:
    text = "1 Sol Ring\n// Sideboard\n1 Negate"
    cards = parse_deck_list(text)
    assert all(c.name != "Negate" for c in cards)


def test_parse_no_quantity_defaults_to_one() -> None:
    text = "Sol Ring"
    cards = parse_deck_list(text)
    assert cards[0].quantity == 1


def test_parse_high_quantity_basic_land() -> None:
    text = "30 Plains"
    cards = parse_deck_list(text)
    assert cards[0].quantity == 30
    assert cards[0].name == "Plains"


def test_parse_two_commanders_partner() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Atraxa Praetors Voice *CMDR*\n1 Sol Ring"
    cards = parse_deck_list(text)
    commanders = [c for c in cards if c.is_commander]
    assert len(commanders) == 2


def test_parse_empty_text_raises() -> None:
    with pytest.raises(ValueError, match="No valid card lines"):
        parse_deck_list("")


def test_parse_whitespace_only_raises() -> None:
    with pytest.raises(ValueError, match="No valid card lines"):
        parse_deck_list("   \n\n  ")


def test_parse_ignores_blank_lines() -> None:
    text = "\n\n1 Sol Ring\n\n\n1 Doubling Season\n\n"
    cards = parse_deck_list(text)
    assert len(cards) == 2


def test_parse_category_none_for_commander() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*"
    cards = parse_deck_list(text)
    assert cards[0].category is None


def test_parse_theme_section_for_creatures() -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n// Creatures\n1 Elvish Mystic"
    cards = parse_deck_list(text)
    non_cmdr = [c for c in cards if not c.is_commander]
    assert non_cmdr[0].category == "theme"


# ── import endpoint integration tests ────────────────────────────────────────


async def test_import_basic_deck(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n\n1 Sol Ring\n1 Doubling Season"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Hazel Import"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["deck"]["stage"] == "complete"
    assert data["imported_count"] == 2
    assert data["unresolved"] == []
    assert data["color_violations"] == []


async def test_import_stage_is_complete(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Stage Test"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["deck"]["stage"] == "complete"


async def test_import_no_commander_returns_422(client: AsyncClient) -> None:
    text = "1 Sol Ring\n1 Doubling Season"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "No Commander"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "PARSE_ERROR"
    assert "commander" in detail["message"].lower()


async def test_import_unresolved_cards_reported(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring\n1 ZZZNonexistentCardXXX"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Unresolved Test"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "ZZZNonexistentCardXXX" in data["unresolved"]
    assert data["imported_count"] == 1


async def test_import_color_violation_reported(client: AsyncClient) -> None:
    # Hazel is G/W; Rhystic Study is U → color violation
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring\n1 Rhystic Study"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Color Violation Test"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "Rhystic Study" in data["color_violations"]
    assert data["imported_count"] == 1  # Sol Ring added; Rhystic Study skipped


async def test_import_with_owner(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Import Owner")
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Owner Test", "owner_id": account_id},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["deck"]["owner_id"] == account_id


async def test_import_with_bracket(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Bracket Test", "bracket": 4},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["deck"]["bracket"] == 4


async def test_import_commander_not_in_db_returns_422(client: AsyncClient) -> None:
    text = "1 Completely Unknown Commander ZZZZZ *CMDR*\n1 Sol Ring"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Unknown Commander"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "COMMANDER_NOT_FOUND"


async def test_import_with_section_categories(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n\n// Ramp\n1 Sol Ring\n\n// Theme\n1 Doubling Season"
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Section Categories"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["imported_count"] == 2


async def test_import_empty_deck_list_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": "", "name": "Empty"},
    )
    # Pydantic min_length=1 validation
    assert resp.status_code == 422


async def test_import_deck_appears_in_deck_list(client: AsyncClient) -> None:
    text = "1 Hazel of the Rootbloom *CMDR*\n1 Sol Ring"
    import_resp = await client.post(
        "/api/v1/decks/import",
        json={"deck_list": text, "name": "Listed Deck"},
    )
    assert import_resp.status_code == 201
    deck_id = import_resp.json()["data"]["deck"]["id"]

    detail_resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["stage"] == "complete"
    card_names = [c["name"] for c in detail["cards"]]
    assert "Sol Ring" in card_names
