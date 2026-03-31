"""Tests for deck feedback endpoints (thumbs up/down)."""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    DOCKSIDE_SCRYFALL_ID,
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_deck,
)

pytestmark = pytest.mark.asyncio


async def test_add_feedback_up(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "up"},
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["feedback"] == "up"
    assert data["card_name"] == "Sol Ring"
    assert data["deck_id"] == deck_id
    assert data["reason"] is None


async def test_add_feedback_down_with_reason(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={
            "card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID),
            "feedback": "down",
            "reason": "Too expensive",
        },
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["feedback"] == "down"
    assert data["reason"] == "Too expensive"


async def test_add_feedback_replaces_previous_vote(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    card_id = str(SOL_RING_SCRYFALL_ID)

    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": card_id, "feedback": "up"},
    )
    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": card_id, "feedback": "down"},
    )

    list_resp = await client.get(f"/api/v1/decks/{deck_id}/feedback")
    items = list_resp.json()["data"]
    sol_ring_feedback = [f for f in items if f["card_name"] == "Sol Ring"]
    assert len(sol_ring_feedback) == 1
    assert sol_ring_feedback[0]["feedback"] == "down"


async def test_list_feedback(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "up"},
    )
    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID), "feedback": "down"},
    )

    resp = await client.get(f"/api/v1/decks/{deck_id}/feedback")

    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 2
    names = {f["card_name"] for f in items}
    assert names == {"Sol Ring", "Doubling Season"}


async def test_delete_feedback(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    create_resp = await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "up"},
    )
    feedback_id = create_resp.json()["data"]["id"]

    del_resp = await client.delete(f"/api/v1/decks/{deck_id}/feedback/{feedback_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/decks/{deck_id}/feedback")
    assert list_resp.json()["data"] == []


async def test_delete_feedback_not_found(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    resp = await client.delete(
        f"/api/v1/decks/{deck_id}/feedback/00000000-0000-0000-0000-000000000000"
    )

    assert resp.status_code == 404


async def test_add_feedback_card_not_found(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={
            "card_scryfall_id": "00000000-0000-0000-0000-000000000000",
            "feedback": "up",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "CARD_NOT_FOUND"


async def test_add_feedback_deck_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "up"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DECK_NOT_FOUND"


async def test_add_feedback_color_outside_commander(client: AsyncClient) -> None:
    """Feedback can be submitted for any card (no color check on feedback)."""
    deck_id = await create_test_deck(client)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(DOCKSIDE_SCRYFALL_ID), "feedback": "down"},
    )

    assert resp.status_code == 201
    assert resp.json()["data"]["card_name"] == "Dockside Extortionist"


async def test_list_feedback_empty_deck(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    resp = await client.get(f"/api/v1/decks/{deck_id}/feedback")

    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_feedback_scoped_to_deck(client: AsyncClient) -> None:
    deck1_id = await create_test_deck(client, name="Deck 1")
    deck2_id = await create_test_deck(client, name="Deck 2")

    await client.post(
        f"/api/v1/decks/{deck1_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "up"},
    )

    resp = await client.get(f"/api/v1/decks/{deck2_id}/feedback")
    assert resp.json()["data"] == []
