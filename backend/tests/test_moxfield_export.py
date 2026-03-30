"""Tests for Moxfield export endpoint."""

from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID, SOL_RING_SCRYFALL_ID


async def _create_deck_with_card(client: AsyncClient) -> str:
    """Create a Hazel deck via HTTP with Sol Ring added."""
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Moxfield Test Deck"},
    )
    assert resp.status_code == 201
    deck_id = resp.json()["data"]["id"]

    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "category": "ramp"},
    )
    return deck_id


async def test_export_deck_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/decks/00000000-0000-0000-0000-000000000000/export/moxfield")
    assert resp.status_code == 404


async def test_export_returns_plain_text(client: AsyncClient) -> None:
    deck_id = await _create_deck_with_card(client)
    resp = await client.get(f"/api/v1/decks/{deck_id}/export/moxfield")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")


async def test_export_format_contains_cmdr_tag(client: AsyncClient) -> None:
    deck_id = await _create_deck_with_card(client)
    resp = await client.get(f"/api/v1/decks/{deck_id}/export/moxfield")

    assert resp.status_code == 200
    assert "Hazel of the Rootbloom *CMDR*" in resp.text


async def test_export_includes_all_cards(client: AsyncClient) -> None:
    deck_id = await _create_deck_with_card(client)
    resp = await client.get(f"/api/v1/decks/{deck_id}/export/moxfield")

    assert resp.status_code == 200
    assert "1 Sol Ring" in resp.text
