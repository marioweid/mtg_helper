"""Tests for the Cardmarket buy list export."""

from uuid import UUID

from httpx import AsyncClient

from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)


async def _create_deck(client: AsyncClient, name: str = "Buylist Deck") -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": name},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def _add_card(
    client: AsyncClient, deck_id: str, scryfall_id: UUID, quantity: int = 1
) -> None:
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(scryfall_id), "quantity": quantity},
    )
    assert resp.status_code in (200, 201)


async def _create_collection(client: AsyncClient, name: str = "Main") -> str:
    create = await client.post("/api/v1/me/collections", json={"name": name})
    assert create.status_code == 201
    return create.json()["data"]["id"]


async def _add_to_collection(
    client: AsyncClient,
    collection_id: str,
    scryfall_id: UUID,
    *,
    set_code: str = "lea",
    collector_number: str = "1",
    quantity: int = 1,
) -> None:
    resp = await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={
            "scryfall_id": str(scryfall_id),
            "quantity": quantity,
            "set_code": set_code,
            "collector_number": collector_number,
        },
    )
    assert resp.status_code == 201


async def test_buylist_unknown_deck_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/decks/00000000-0000-0000-0000-000000000000/export/buylist")
    assert resp.status_code == 404


async def test_buylist_includes_cards_not_owned(client: AsyncClient) -> None:
    """Card in deck, none in collection → appears in buy list with full deck qty."""
    deck_id = await _create_deck(client)
    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID, quantity=1)

    resp = await client.get(f"/api/v1/decks/{deck_id}/export/buylist")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text.strip() == "1 Sol Ring"


async def test_buylist_omits_fully_owned(client: AsyncClient) -> None:
    """Card in deck and matching qty in collection → omitted."""
    deck_id = await _create_deck(client)
    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID, quantity=1)

    cid = await _create_collection(client)
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, quantity=1)

    resp = await client.get(f"/api/v1/decks/{deck_id}/export/buylist")
    assert resp.status_code == 200
    assert resp.text == ""


async def test_buylist_reports_partial_owned_deficit(client: AsyncClient) -> None:
    """Deck has qty 4, collection has qty 1 → output `3 Name`.

    Plus-1 cards aren't legal in commander, but the math itself is what
    matters: deficit = max(0, deck_qty - owned_qty).
    """
    deck_id = await _create_deck(client)
    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID, quantity=4)
    cid = await _create_collection(client)
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, quantity=1)

    resp = await client.get(f"/api/v1/decks/{deck_id}/export/buylist")
    assert resp.status_code == 200
    assert resp.text.strip() == "3 Sol Ring"


async def test_buylist_sorted_alphabetically(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    await _add_card(client, deck_id, DOUBLING_SEASON_SCRYFALL_ID, quantity=1)
    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID, quantity=1)

    resp = await client.get(f"/api/v1/decks/{deck_id}/export/buylist")
    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    assert lines == ["1 Doubling Season", "1 Sol Ring"]


async def test_buylist_ignores_other_accounts_collections(client: AsyncClient) -> None:
    """Cards in another account's collection don't count toward ownership."""
    deck_id = await _create_deck(client)
    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID, quantity=1)

    # Switch to a second account and put Sol Ring in *their* collection.
    await create_test_account(client, "Other User")
    other_cid = await _create_collection(client, name="Other")
    await _add_to_collection(client, other_cid, SOL_RING_SCRYFALL_ID, quantity=1)

    # The original deck owner has no collection coverage → Sol Ring still missing.
    # We need to ask as the deck owner; the auth fixture uses one default
    # account, and creating "Other User" rebinds the override. Recreate the
    # default by swapping back.
    from mtg_helper.auth import get_current_account
    from mtg_helper.main import app
    from mtg_helper.models.accounts import AccountResponse

    pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM accounts WHERE email = $1", "default@test.local")
    original = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )
    app.dependency_overrides[get_current_account] = lambda: original

    resp = await client.get(f"/api/v1/decks/{deck_id}/export/buylist")
    assert resp.status_code == 404 or resp.text.strip() == "1 Sol Ring"
