"""Tests for `/me` profile endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_account

pytestmark = pytest.mark.asyncio


async def test_get_me(client: AsyncClient) -> None:
    """`GET /me` returns the authenticated account."""
    account_id = await create_test_account(client, "Alice")

    resp = await client.get("/api/v1/me")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == account_id
    assert data["display_name"] == "Alice"


async def test_patch_me_display_name(client: AsyncClient) -> None:
    """`PATCH /me` updates the authenticated account's display name."""
    await create_test_account(client, "Patch")

    resp = await client.patch("/api/v1/me", json={"display_name": "Patched"})

    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "Patched"
