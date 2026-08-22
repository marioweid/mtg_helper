"""Tests for persistent Commander Coach deck memory."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_account, create_test_deck

pytestmark = pytest.mark.asyncio


async def test_get_coach_memory_empty_default(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Memory Owner")
    deck_id = await create_test_deck(client, name="Memory Deck")

    resp = await client.get(f"/api/v1/decks/{deck_id}/coach/memory")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deck_id"] == deck_id
    assert data["account_id"] == account_id
    assert data["notes"] == ""
    assert data["created_at"] is None
    assert data["updated_at"] is None


async def test_update_coach_memory_round_trips(client: AsyncClient) -> None:
    await create_test_account(client, "Memory Writer")
    deck_id = await create_test_deck(client, name="Yuna Counters")
    notes = "Yuna cares about all counters, but don't suggest oil-counter mismatches."

    update = await client.put(f"/api/v1/decks/{deck_id}/coach/memory", json={"notes": notes})
    read = await client.get(f"/api/v1/decks/{deck_id}/coach/memory")

    assert update.status_code == 200
    assert update.json()["data"]["notes"] == notes
    assert update.json()["data"]["updated_at"] is not None
    assert read.status_code == 200
    assert read.json()["data"]["notes"] == notes


async def test_coach_memory_is_scoped_to_deck_owner(client: AsyncClient) -> None:
    await create_test_account(client, "First Owner")
    deck_id = await create_test_deck(client, name="Private Memory")
    await client.put(f"/api/v1/decks/{deck_id}/coach/memory", json={"notes": "private"})

    await create_test_account(client, "Second Owner")
    resp = await client.get(f"/api/v1/decks/{deck_id}/coach/memory")

    assert resp.status_code == 404


async def test_coach_can_show_memory_without_running_doctor(client: AsyncClient) -> None:
    await create_test_account(client, "Memory Reader")
    deck_id = await create_test_deck(client, name="Readable Memory")
    await client.put(f"/api/v1/decks/{deck_id}/coach/memory", json={"notes": "Protect squirrels"})

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/coach",
        json={"message": "What do you have in memory?", "mode": "auto"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "memory"
    assert data["doctor"] is None
    assert data["coach_memory"]["notes"] == "Protect squirrels"
    assert "Protect squirrels" in data["reply"]


async def test_coach_can_add_memory_after_memory_conversation(
    client: AsyncClient,
) -> None:
    await create_test_account(client, "Memory Adder")
    deck_id = await create_test_deck(client, name="Yuna Memory")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/coach",
        json={
            "message": (
                "User: what is in your memory?\n"
                "Coach: none\n"
                "User: add the yuna cares about all counters please"
            ),
            "mode": "auto",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "memory"
    assert data["memory_updated"] is True
    assert data["coach_memory"]["notes"] == "yuna cares about all counters"


async def test_coach_self_detects_preference_memory(
    client: AsyncClient,
) -> None:
    await create_test_account(client, "Self Memory")
    deck_id = await create_test_deck(client, name="Self Aware Memory")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/coach",
        json={"message": "I hate counterspells", "mode": "auto"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "memory"
    assert data["memory_updated"] is True
    assert data["coach_memory"]["notes"] == "I hate counterspells"


async def test_coach_self_detects_commander_interpretation_memory(
    client: AsyncClient,
) -> None:
    await create_test_account(client, "Interpretation Memory")
    deck_id = await create_test_deck(client, name="Yuna Interpretation")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/coach",
        json={
            "message": "please for Yuna I also want other counters than +1/+1 counters",
            "mode": "auto",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "memory"
    assert data["memory_updated"] is True
    assert data["coach_memory"]["notes"] == (
        "for Yuna I also want other counters than +1/+1 counters"
    )


async def test_coach_can_remove_matching_memory_line(
    client: AsyncClient,
) -> None:
    await create_test_account(client, "Memory Editor")
    deck_id = await create_test_deck(client, name="Editable Memory")
    await client.put(
        f"/api/v1/decks/{deck_id}/coach/memory",
        json={"notes": "Protect squirrels\nI don't like counterspells"},
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/coach",
        json={"message": "Remove the thing that I don't like counterspells", "mode": "auto"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "memory"
    assert data["memory_updated"] is True
    assert data["coach_memory"]["notes"] == "Protect squirrels"
