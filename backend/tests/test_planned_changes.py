"""Behavioral tests for physical deck state and planned-change overlays."""

from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_ORACLE_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_deck,
)


async def _add_now(client: AsyncClient, deck_id: str, quantity: int = 1) -> None:
    response = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "quantity": quantity},
    )
    assert response.status_code == 201


async def _plan(
    client: AsyncClient,
    deck_id: str,
    direction: str,
    quantity: int = 1,
) -> dict[str, object] | None:
    response = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={
            "card_scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "direction": direction,
            "quantity": quantity,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _plan_card(
    client: AsyncClient,
    deck_id: str,
    scryfall_id: str,
    quantity: int = 1,
) -> dict[str, object] | None:
    response = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={"card_scryfall_id": scryfall_id, "direction": "addition", "quantity": quantity},
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _create_collection(client: AsyncClient, name: str) -> str:
    response = await client.post("/api/v1/me/collections", json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _add_collection_card(
    client: AsyncClient,
    collection_id: str,
    scryfall_id: str,
    quantity: int = 1,
) -> None:
    response = await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={"scryfall_id": scryfall_id, "quantity": quantity},
    )
    assert response.status_code == 201


async def _shopping_list(
    client: AsyncClient,
    deck_id: str,
    collection_ids: list[str],
):
    return await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/shopping-list",
        json={"collection_ids": collection_ids},
    )


@pytest.mark.asyncio
async def test_planned_addition_is_excluded_from_physical_deck(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    plan = await _plan(client, deck_id, "addition", 2)
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]

    assert plan is not None
    assert deck["cards"] == []
    assert deck["physical_card_count"] == 1
    assert deck["planned_card_count"] == 3
    assert deck["planned_changes"][0]["direction"] == "addition"


@pytest.mark.asyncio
async def test_planned_cut_remains_in_physical_deck(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _add_now(client, deck_id)

    await _plan(client, deck_id, "cut")
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]

    assert [card["name"] for card in deck["cards"]] == ["Sol Ring"]
    assert deck["physical_card_count"] == 2
    assert deck["planned_card_count"] == 1


@pytest.mark.asyncio
async def test_opposite_plan_offsets_existing_quantity(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _add_now(client, deck_id, quantity=2)
    await _plan(client, deck_id, "cut", 2)

    remaining = await _plan(client, deck_id, "addition", 1)
    cancelled = await _plan(client, deck_id, "addition", 1)

    assert remaining is not None
    assert remaining["direction"] == "cut"
    assert remaining["quantity"] == 1
    assert cancelled is None


@pytest.mark.asyncio
async def test_partial_addition_completion_leaves_remainder(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    plan = await _plan(client, deck_id, "addition", 2)
    assert plan is not None

    response = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}/complete",
        json={"quantity": 1},
    )
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]

    assert response.status_code == 200
    assert response.json()["data"]["quantity"] == 1
    assert deck["cards"][0]["name"] == "Sol Ring"
    assert deck["cards"][0]["quantity"] == 1
    assert deck["planned_changes"][0]["quantity"] == 1


@pytest.mark.asyncio
async def test_addition_can_consume_selected_collection(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    collection = await client.post("/api/v1/me/collections", json={"name": "Binder A"})
    collection_id = collection.json()["data"]["id"]
    await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={"scryfall_id": str(SOL_RING_SCRYFALL_ID), "quantity": 2},
    )
    plan = await _plan(client, deck_id, "addition", 2)
    assert plan is not None
    assert plan["owned_in"] == [{"id": collection_id, "name": "Binder A", "quantity": 2}]
    selected = await client.patch(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}",
        json={"collection_id": collection_id},
    )
    assert selected.status_code == 200

    completed = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}/complete",
        json={"quantity": 1},
    )
    cards = (await client.get(f"/api/v1/collections/{collection_id}/cards")).json()["data"]

    assert completed.status_code == 200
    assert cards[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_cut_can_place_card_in_selected_collection(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _add_now(client, deck_id)
    collection = await client.post("/api/v1/me/collections", json={"name": "Binder A"})
    collection_id = collection.json()["data"]["id"]
    plan = await _plan(client, deck_id, "cut")
    assert plan is not None
    await client.patch(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}",
        json={"collection_id": collection_id},
    )

    completed = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}/complete",
        json={"quantity": 1},
    )
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]
    cards = (await client.get(f"/api/v1/collections/{collection_id}/cards")).json()["data"]

    assert completed.status_code == 200
    assert completed.json()["data"] is None
    assert deck["cards"] == []
    assert cards[0]["name"] == "Sol Ring"
    assert cards[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_selected_collection_is_revalidated_atomically(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    collection = await client.post("/api/v1/me/collections", json={"name": "Binder A"})
    collection_id = collection.json()["data"]["id"]
    await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={"scryfall_id": str(SOL_RING_SCRYFALL_ID), "quantity": 1},
    )
    plan = await _plan(client, deck_id, "addition", 2)
    assert plan is not None
    await client.patch(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}",
        json={"collection_id": collection_id},
    )

    response = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan['id']}/complete",
        json={"quantity": 2},
    )
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]
    cards = (await client.get(f"/api/v1/collections/{collection_id}/cards")).json()["data"]

    assert response.status_code == 409
    assert deck["cards"] == []
    assert deck["planned_changes"][0]["quantity"] == 2
    assert cards[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_commander_and_excessive_cut_are_rejected(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    commander = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={
            "card_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "direction": "addition",
        },
    )
    await _add_now(client, deck_id)
    excessive = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={
            "card_scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "direction": "cut",
            "quantity": 2,
        },
    )

    assert commander.status_code == 422
    assert excessive.status_code == 422


@pytest.mark.asyncio
async def test_immediate_add_consumes_matching_plan(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _plan(client, deck_id, "addition", 2)

    await _add_now(client, deck_id)
    deck = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]

    assert deck["cards"][0]["quantity"] == 1
    assert deck["planned_changes"][0]["quantity"] == 1


@pytest.mark.asyncio
async def test_shopping_list_uses_only_selected_collections(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _plan(client, deck_id, "addition", 2)
    await _plan_card(client, deck_id, str(DOUBLING_SEASON_SCRYFALL_ID))
    binder = await _create_collection(client, "Binder")
    proxies = await _create_collection(client, "Proxies")
    await _add_collection_card(client, binder, str(SOL_RING_SCRYFALL_ID))
    await _add_collection_card(client, proxies, str(SOL_RING_SCRYFALL_ID))

    none_selected = await _shopping_list(client, deck_id, [])
    binder_selected = await _shopping_list(client, deck_id, [binder])
    all_selected = await _shopping_list(client, deck_id, [binder, proxies])

    assert none_selected.text == "1 Doubling Season\n2 Sol Ring"
    assert binder_selected.text == "1 Doubling Season\n1 Sol Ring"
    assert all_selected.text == "1 Doubling Season"


@pytest.mark.asyncio
async def test_shopping_list_groups_alternate_printings_by_oracle(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    alternate_scryfall_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cards (
                scryfall_id, oracle_id, name, color_identity, set_code, legalities
            ) VALUES ($1, $2, 'Sol Ring', ARRAY[]::text[], 'cmm', '{"commander":"legal"}')
            """,
            alternate_scryfall_id,
            SOL_RING_ORACLE_ID,
        )
    deck_id = await create_test_deck(client)
    await _plan(client, deck_id, "addition")
    await _plan_card(client, deck_id, str(alternate_scryfall_id))
    binder = await _create_collection(client, "Binder")
    await _add_collection_card(client, binder, str(alternate_scryfall_id))

    response = await _shopping_list(client, deck_id, [binder])

    assert response.status_code == 200
    assert response.text == ""


@pytest.mark.asyncio
async def test_shopping_list_ignores_cuts_and_physical_cards(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await _add_now(client, deck_id)
    await _plan(client, deck_id, "cut")
    await _plan_card(client, deck_id, str(DOUBLING_SEASON_SCRYFALL_ID))

    response = await _shopping_list(client, deck_id, [])

    assert response.status_code == 200
    assert response.text == "1 Doubling Season"


@pytest.mark.asyncio
async def test_shopping_list_empty_and_unknown_deck(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    empty = await _shopping_list(client, deck_id, [])
    missing = await _shopping_list(client, str(uuid4()), [])

    assert empty.status_code == 200
    assert empty.text == ""
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_shopping_list_rejects_unowned_collection(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    deck_id = await create_test_deck(client)
    await _plan(client, deck_id, "addition")
    async with db_pool.acquire() as conn:
        other_account_id = await conn.fetchval(
            "INSERT INTO accounts (display_name, email) VALUES ('Other', 'other@test.local') "
            "RETURNING id"
        )
        other_collection_id = await conn.fetchval(
            "INSERT INTO collections (account_id, name) VALUES ($1, 'Other Binder') RETURNING id",
            other_account_id,
        )

    response = await _shopping_list(client, deck_id, [str(other_collection_id)])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_COLLECTION"
