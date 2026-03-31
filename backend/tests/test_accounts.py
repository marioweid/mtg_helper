"""Tests for account management endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_account(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/accounts", json={"display_name": "Alice"})

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["display_name"] == "Alice"
    assert "id" in data
    assert "created_at" in data


async def test_create_account_name_too_short(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/accounts", json={"display_name": ""})

    assert resp.status_code == 422


async def test_get_account(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/accounts", json={"display_name": "Bob"})
    account_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/accounts/{account_id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == account_id
    assert data["display_name"] == "Bob"


async def test_get_account_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/accounts/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"
