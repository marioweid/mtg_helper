"""Tests for account preference endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import DOUBLING_SEASON_SCRYFALL_ID, SOL_RING_SCRYFALL_ID, create_test_account

pytestmark = pytest.mark.asyncio


async def test_create_pet_card_preference(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={
            "preference_type": "pet_card",
            "card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID),
        },
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["preference_type"] == "pet_card"
    assert data["card_name"] == "Doubling Season"
    assert data["account_id"] == account_id


async def test_create_avoid_card_preference(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={
            "preference_type": "avoid_card",
            "card_scryfall_id": str(SOL_RING_SCRYFALL_ID),
        },
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["preference_type"] == "avoid_card"
    assert data["card_name"] == "Sol Ring"


async def test_create_avoid_archetype_preference(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "avoid_archetype", "description": "stax"},
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["preference_type"] == "avoid_archetype"
    assert data["description"] == "stax"
    assert data["card_id"] is None
    assert data["card_name"] is None


async def test_create_general_preference(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "general", "description": "I prefer creature-based strategies"},
    )

    assert resp.status_code == 201
    assert resp.json()["data"]["description"] == "I prefer creature-based strategies"


async def test_create_pet_card_missing_card_id_is_invalid(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "pet_card"},
    )

    assert resp.status_code == 422


async def test_create_avoid_archetype_missing_description_is_invalid(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "avoid_archetype"},
    )

    assert resp.status_code == 422


async def test_list_preferences(client: AsyncClient) -> None:
    account_id = await create_test_account(client)
    await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "pet_card", "card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID)},
    )
    await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "avoid_archetype", "description": "infect"},
    )

    resp = await client.get(f"/api/v1/accounts/{account_id}/preferences")

    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 2
    types = {p["preference_type"] for p in items}
    assert types == {"pet_card", "avoid_archetype"}


async def test_delete_preference(client: AsyncClient) -> None:
    account_id = await create_test_account(client)
    create_resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "general", "description": "test note"},
    )
    pref_id = create_resp.json()["data"]["id"]

    del_resp = await client.delete(f"/api/v1/accounts/{account_id}/preferences/{pref_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/accounts/{account_id}/preferences")
    assert list_resp.json()["data"] == []


async def test_delete_preference_not_found(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.delete(
        f"/api/v1/accounts/{account_id}/preferences/00000000-0000-0000-0000-000000000000"
    )

    assert resp.status_code == 404


async def test_create_preference_account_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/accounts/00000000-0000-0000-0000-000000000000/preferences",
        json={"preference_type": "general", "description": "test"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"


async def test_create_preference_card_not_found(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={
            "preference_type": "pet_card",
            "card_scryfall_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "CARD_NOT_FOUND"


async def test_list_preferences_empty(client: AsyncClient) -> None:
    account_id = await create_test_account(client)

    resp = await client.get(f"/api/v1/accounts/{account_id}/preferences")

    assert resp.status_code == 200
    assert resp.json()["data"] == []
