"""Account-scoped export previews never consume binder inventory."""

from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from mtg_helper.auth import get_current_account
from mtg_helper.main import app
from tests.conftest import SOL_RING_SCRYFALL_ID, create_test_account


async def _card_id(pool: asyncpg.Pool) -> str:
    return str(
        await pool.fetchval("SELECT id FROM cards WHERE scryfall_id = $1", SOL_RING_SCRYFALL_ID)
    )


async def _binder(client: AsyncClient, name: str, quantity: int) -> str:
    response = await client.post("/api/v1/me/collections", json={"name": name})
    binder_id = response.json()["data"]["id"]
    added = await client.post(
        f"/api/v1/collections/{binder_id}/cards",
        json={"scryfall_id": str(SOL_RING_SCRYFALL_ID), "quantity": quantity},
    )
    assert added.status_code == 201
    return binder_id


@pytest.mark.asyncio
async def test_preview_subtracts_only_selected_binders_without_moving_cards(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    binder_id = await _binder(client, "Real cards", 2)
    await _binder(client, "Proxies", 10)
    card_id = await _card_id(db_pool)
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": card_id, "quantity": 5}],
            "collection_ids": [binder_id, binder_id],
        },
    )
    assert response.status_code == 200
    preview = response.json()["data"]
    assert preview["text"] == "3 Sol Ring"
    assert preview["needed_quantity"] == 5
    assert preview["from_binders_quantity"] == 2
    assert preview["export_quantity"] == 3
    assert preview["known_price_eur_cents"] == 60
    assert preview["unpriced_quantity"] == 0
    assert preview["rows"][0]["pulls"] == [{"id": binder_id, "name": "Real cards", "quantity": 2}]
    cards = (await client.get(f"/api/v1/collections/{binder_id}/cards")).json()["data"]
    assert cards[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_no_binders_exports_full_quantity_and_empty_input_is_valid(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    await _binder(client, "Owned", 5)
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": await _card_id(db_pool), "quantity": 3}],
            "collection_ids": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["text"] == "3 Sol Ring"
    empty = await client.post("/api/v1/card-exports/preview", json={"cards": []})
    assert empty.status_code == 200
    assert empty.json()["data"]["rows"] == []
    assert empty.json()["data"]["text"] == ""


@pytest.mark.asyncio
async def test_pull_allocations_are_capped_and_printings_share_inventory(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    binder_a = await _binder(client, "A", 1)
    binder_b = await _binder(client, "B", 10)
    card_id = await _card_id(db_pool)
    alternate = await db_pool.fetchval(
        "INSERT INTO cards (scryfall_id, oracle_id, name, type_line) "
        "SELECT $1, oracle_id, name, type_line FROM cards WHERE id = $2 RETURNING id",
        uuid4(),
        UUID(card_id),
    )
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [
                {"card_id": card_id, "quantity": 2},
                {"card_id": str(alternate), "quantity": 1},
            ],
            "collection_ids": [binder_b, binder_a],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["rows"]) == 1
    assert data["needed_quantity"] == data["from_binders_quantity"] == 3
    assert data["export_quantity"] == 0
    assert data["text"] == ""
    assert data["rows"][0]["available_quantity"] == 11
    assert data["rows"][0]["pulls"] == [
        {"id": binder_a, "name": "A", "quantity": 1},
        {"id": binder_b, "name": "B", "quantity": 2},
    ]


@pytest.mark.asyncio
async def test_export_rejects_foreign_or_missing_binders(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    foreign = await _binder(client, "Private", 10)
    await create_test_account(client, "Other export user")
    for binder_id in [foreign, str(uuid4())]:
        response = await client.post(
            "/api/v1/card-exports/preview",
            json={
                "cards": [{"card_id": await _card_id(db_pool), "quantity": 1}],
                "collection_ids": [binder_id],
            },
        )
        assert response.status_code == 404
        assert "Private" not in response.text


@pytest.mark.asyncio
async def test_missing_prices_are_not_reported_as_free(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    card_id = await _card_id(db_pool)
    await db_pool.execute("UPDATE cards SET prices = '{}'::jsonb WHERE id = $1", UUID(card_id))
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": card_id, "quantity": 2}],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["known_price_eur_cents"] == 0
    assert data["unpriced_quantity"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [0, -1, 10001, 1.5, "invalid"])
async def test_invalid_export_quantities_are_rejected(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
    quantity: object,
) -> None:
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": await _card_id(db_pool), "quantity": quantity}],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_card_is_not_silently_dropped(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": str(uuid4()), "quantity": 1}],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_requires_authentication(client: AsyncClient) -> None:
    override = app.dependency_overrides.pop(get_current_account)
    try:
        response = await client.post("/api/v1/card-exports/preview", json={"cards": []})
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_account] = override


@pytest.mark.asyncio
async def test_duplicate_card_requests_do_not_reuse_inventory(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    binder_id = await _binder(client, "Owned", 2)
    card_id = await _card_id(db_pool)
    response = await client.post(
        "/api/v1/card-exports/preview",
        json={
            "cards": [{"card_id": card_id, "quantity": 2}, {"card_id": card_id, "quantity": 2}],
            "collection_ids": [binder_id],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["rows"]) == 1
    assert data["text"] == "2 Sol Ring"
    assert data["needed_quantity"] == 4
    assert data["from_binders_quantity"] == 2
