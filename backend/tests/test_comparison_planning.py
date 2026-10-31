"""Batch planning from comparison deltas is idempotent and never applies cards."""

import asyncio
from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient, Response

from tests.conftest import (
    DOCKSIDE_SCRYFALL_ID,
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)

FOREST = "6d7b8d2c-36f5-40e7-91de-9c8c1b44da67"


def _change(card: object, direction: str, quantity: int = 1) -> dict[str, object]:
    return {"card_scryfall_id": str(card), "direction": direction, "quantity": quantity}


async def _batch(client: AsyncClient, deck_id: str, changes: list[dict[str, object]]) -> Response:
    return await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes/batch", json={"changes": changes}
    )


@pytest.mark.asyncio
async def test_batch_plans_additions_and_cuts_without_applying_cards(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "card_scryfall_id": str(SOL_RING_SCRYFALL_ID),
        },
    )
    collection = (await client.post("/api/v1/me/collections", json={"name": "Untouched"})).json()
    binder_id = collection["data"]["id"]
    await client.post(
        f"/api/v1/collections/{binder_id}/cards",
        json={
            "scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID),
            "quantity": 2,
        },
    )
    before = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]
    response = await _batch(
        client,
        deck_id,
        [
            _change(DOUBLING_SEASON_SCRYFALL_ID, "addition"),
            _change(SOL_RING_SCRYFALL_ID, "cut"),
        ],
    )
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["data"]["items"]] == ["planned", "planned"]
    after = (await client.get(f"/api/v1/decks/{deck_id}")).json()["data"]
    assert [(card["card_id"], card["quantity"]) for card in after["cards"]] == [
        (card["card_id"], card["quantity"]) for card in before["cards"]
    ]
    assert after["physical_card_count"] == before["physical_card_count"]
    assert len(after["planned_changes"]) == 2
    inventory = (await client.get(f"/api/v1/collections/{binder_id}/cards")).json()["data"]
    assert inventory[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_batch_ensures_quantities_and_does_not_duplicate_on_retry(
    client: AsyncClient,
) -> None:
    deck_id = await create_test_deck(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes", json=_change(FOREST, "addition", 2)
    )
    changes = [_change(FOREST, "addition", 3)]
    first = await _batch(client, deck_id, changes)
    second = await _batch(client, deck_id, changes)
    smaller = await _batch(client, deck_id, [_change(FOREST, "addition", 1)])
    assert first.status_code == second.status_code == smaller.status_code == 200
    assert first.json()["data"]["items"][0]["status"] == "planned"
    assert second.json()["data"]["items"][0]["status"] == "unchanged"
    assert smaller.json()["data"]["items"][0]["status"] == "unchanged"
    plans = (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"]
    assert len(plans) == 1
    assert plans[0]["quantity"] == 3


@pytest.mark.asyncio
async def test_partial_failures_report_every_card_and_preserve_conflicts(
    client: AsyncClient,
) -> None:
    deck_id = await create_test_deck(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "card_scryfall_id": FOREST,
            "quantity": 3,
        },
    )
    await client.post(f"/api/v1/decks/{deck_id}/planned-changes", json=_change(FOREST, "cut", 2))
    changes = [
        _change(FOREST, "addition"),
        _change(DOCKSIDE_SCRYFALL_ID, "addition"),
        _change(HAZEL_SCRYFALL_ID, "addition"),
        _change(SOL_RING_SCRYFALL_ID, "cut"),
        _change(uuid4(), "addition"),
        _change(DOUBLING_SEASON_SCRYFALL_ID, "addition"),
    ]
    response = await _batch(client, deck_id, changes)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == len(changes)
    assert [item["status"] for item in items] == ["failed"] * 5 + ["planned"]
    assert all(item["message"] for item in items)
    assert "opposite" in items[0]["message"].lower()
    plans = (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"]
    forest = next(plan for plan in plans if plan["name"] == "Forest")
    assert (forest["direction"], forest["quantity"]) == ("cut", 2)


@pytest.mark.asyncio
async def test_illegal_copy_count_fails_without_leaving_a_partial_plan(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    response = await _batch(client, deck_id, [_change(SOL_RING_SCRYFALL_ID, "addition", 2)])
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["status"] == "failed"
    assert (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"] == []


@pytest.mark.asyncio
async def test_top_up_preserves_existing_categories_and_collection(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    binder = (await client.post("/api/v1/me/collections", json={"name": "Selected"})).json()
    binder_id = binder["data"]["id"]
    await client.post(
        f"/api/v1/collections/{binder_id}/cards",
        json={
            "scryfall_id": FOREST,
            "quantity": 5,
        },
    )
    created = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={
            **_change(FOREST, "addition", 2),
            "categories": ["ramp"],
        },
    )
    plan_id = created.json()["data"]["id"]
    await client.patch(
        f"/api/v1/decks/{deck_id}/planned-changes/{plan_id}",
        json={
            "collection_id": binder_id,
        },
    )
    response = await _batch(
        client,
        deck_id,
        [
            {
                **_change(FOREST, "addition", 3),
                "categories": ["lands"],
            }
        ],
    )
    assert response.status_code == 200
    plans = (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"]
    assert plans[0]["quantity"] == 3
    assert plans[0]["categories"] == ["ramp"]
    assert plans[0]["collection_id"] == binder_id


@pytest.mark.asyncio
async def test_failed_top_up_keeps_the_original_plan(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    created = await client.post(
        f"/api/v1/decks/{deck_id}/planned-changes",
        json={
            **_change(SOL_RING_SCRYFALL_ID, "addition"),
            "categories": ["ramp"],
        },
    )
    before = created.json()["data"]
    response = await _batch(client, deck_id, [_change(SOL_RING_SCRYFALL_ID, "addition", 2)])
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["status"] == "failed"
    plans = (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"]
    assert plans == [before]


@pytest.mark.asyncio
async def test_batch_cannot_access_another_accounts_deck(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    await create_test_account(client, "Foreign planner")
    response = await _batch(client, deck_id, [_change(FOREST, "addition")])
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_batches_do_not_multiply_pending_quantities(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)
    responses = await asyncio.gather(
        *(_batch(client, deck_id, [_change(FOREST, "addition", 3)]) for _ in range(3))
    )
    assert all(response.status_code == 200 for response in responses)
    plans = (await client.get(f"/api/v1/decks/{deck_id}/planned-changes")).json()["data"]
    assert [plan["quantity"] for plan in plans] == [3]


@pytest.mark.asyncio
async def test_alternate_printings_share_the_same_pending_plan(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    alternate = uuid4()
    await db_pool.execute(
        "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, type_line) "
        "SELECT $1, oracle_id, name, color_identity, type_line FROM cards WHERE scryfall_id = $2",
        alternate,
        SOL_RING_SCRYFALL_ID,
    )
    deck_id = await create_test_deck(client)
    response = await _batch(
        client,
        deck_id,
        [
            _change(SOL_RING_SCRYFALL_ID, "addition"),
            _change(alternate, "addition"),
        ],
    )
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["data"]["items"]] == ["planned", "unchanged"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [[], [_change(FOREST, "addition", 0)], [_change(FOREST, "invalid")]]
)
async def test_invalid_batch_requests_are_rejected(
    client: AsyncClient,
    changes: list[dict[str, object]],
) -> None:
    deck_id = await create_test_deck(client)
    response = await _batch(client, deck_id, changes)
    assert response.status_code == 422
