"""Tests for deck CRUD and card management."""

import pytest
from httpx import AsyncClient

HAZEL_ID = "4d7b8d2c-36f5-40e7-91de-9c8c1b44da67"
SOL_RING_ID = "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67"
DOUBLING_SEASON_ID = "1d7b8d2c-36f5-40e7-91de-9c8c1b44da67"
RHYSTIC_STUDY_ID = "2d7b8d2c-36f5-40e7-91de-9c8c1b44da67"
DOCKSIDE_ID = "5d7b8d2c-36f5-40e7-91de-9c8c1b44da67"


@pytest.mark.asyncio
async def test_create_deck(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": HAZEL_ID,
            "name": "Hazel Tokens",
            "description": "Token copies and X spells",
            "bracket": 3,
        },
    )
    assert resp.status_code == 201
    deck = resp.json()["data"]
    assert deck["name"] == "Hazel Tokens"
    assert deck["bracket"] == 3
    assert deck["stage"] == "created"


@pytest.mark.asyncio
async def test_create_deck_invalid_commander(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": "00000000-0000-0000-0000-000000000000",
            "name": "Bad Deck",
            "bracket": 2,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_decks(client: AsyncClient) -> None:
    # Create a deck first
    await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "List Test Deck", "bracket": 2},
    )
    resp = await client.get("/api/v1/decks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total"] >= 1
    assert all("commander_name" in d for d in data["data"])


@pytest.mark.asyncio
async def test_get_deck_detail(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Detail Test Deck", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]

    resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 200
    deck = resp.json()["data"]
    assert deck["id"] == deck_id
    assert deck["cards"] == []


@pytest.mark.asyncio
async def test_get_deck_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/decks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_deck(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Update Me", "bracket": 2},
    )
    deck_id = create.json()["data"]["id"]

    resp = await client.patch(f"/api/v1/decks/{deck_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_add_card_valid(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Card Add Test", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]

    # Sol Ring is colorless — always legal
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": SOL_RING_ID, "category": "ramp"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "Sol Ring"


@pytest.mark.asyncio
async def test_add_card_valid_color_identity(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "GW Deck", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]

    # Doubling Season is G — legal in GW deck
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": DOUBLING_SEASON_ID, "category": "theme"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_add_card_color_identity_violation(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "GW Deck No Blue", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]

    # Rhystic Study is U — illegal in GW deck
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": RHYSTIC_STUDY_ID},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "COLOR_IDENTITY_VIOLATION"


@pytest.mark.asyncio
async def test_add_card_duplicate_upserts(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Duplicate Test", "bracket": 2},
    )
    deck_id = create.json()["data"]["id"]

    # Add Sol Ring twice — should upsert not error
    await client.post(f"/api/v1/decks/{deck_id}/cards", json={"card_scryfall_id": SOL_RING_ID})
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards", json={"card_scryfall_id": SOL_RING_ID}
    )
    assert resp.status_code == 201

    # Verify it's still just one card in the deck
    detail = await client.get(f"/api/v1/decks/{deck_id}")
    assert len(detail.json()["data"]["cards"]) == 1


@pytest.mark.asyncio
async def test_remove_card(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Remove Card Test", "bracket": 3},
    )
    deck_id = create.json()["data"]["id"]

    await client.post(f"/api/v1/decks/{deck_id}/cards", json={"card_scryfall_id": SOL_RING_ID})
    resp = await client.delete(f"/api/v1/decks/{deck_id}/cards/{SOL_RING_ID}")
    assert resp.status_code == 204

    detail = await client.get(f"/api/v1/decks/{deck_id}")
    assert len(detail.json()["data"]["cards"]) == 0


@pytest.mark.asyncio
async def test_delete_deck(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": HAZEL_ID, "name": "Delete Me", "bracket": 1},
    )
    deck_id = create.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 404
