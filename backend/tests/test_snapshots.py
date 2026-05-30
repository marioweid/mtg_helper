"""Tests for deck snapshots + deck comparison."""

import pytest
from httpx import AsyncClient

from mtg_helper.services.snapshot_service import diff_compositions
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)


@pytest.mark.asyncio
async def test_create_manual_snapshot_captures_current_state(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="Snap Source")
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "categories": ["ramp"]},
    )

    resp = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "pre-test"})
    assert resp.status_code == 201
    snap = resp.json()["data"]
    assert snap["label"] == "pre-test"
    assert snap["source"] == "manual"
    assert snap["deck_name"] == "Snap Source"

    # Mutate the live deck; snapshot remains stable.
    await client.delete(f"/api/v1/decks/{deck_id}/cards/{SOL_RING_SCRYFALL_ID}")

    detail = await client.get(f"/api/v1/snapshots/{snap['id']}")
    assert detail.status_code == 200
    cards = detail.json()["data"]["cards"]
    assert len(cards) == 1
    assert cards[0]["name"] == "Sol Ring"


@pytest.mark.asyncio
async def test_auto_snapshot_on_stage_advance(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="Auto Snap")

    # Stage 'created' -> 'ramp' should trigger an auto snapshot.
    resp = await client.patch(f"/api/v1/decks/{deck_id}", json={"stage": "ramp"})
    assert resp.status_code == 200

    listing = await client.get(f"/api/v1/decks/{deck_id}/snapshots")
    rows = listing.json()["data"]
    auto = [r for r in rows if r["source"] == "auto_stage"]
    assert len(auto) == 1
    assert auto[0]["stage"] == "ramp"
    assert auto[0]["label"] == "entered ramp"


@pytest.mark.asyncio
async def test_no_auto_snapshot_when_stage_unchanged(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="No Snap")

    # Touch a non-stage field; no auto-snapshot should fire.
    await client.patch(f"/api/v1/decks/{deck_id}", json={"name": "Renamed"})
    listing = await client.get(f"/api/v1/decks/{deck_id}/snapshots")
    assert listing.json()["data"] == []


@pytest.mark.asyncio
async def test_list_snapshots_newest_first(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="Ordered Snaps")
    a = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "a"})
    b = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "b"})
    a_id = a.json()["data"]["id"]
    b_id = b.json()["data"]["id"]

    listing = await client.get(f"/api/v1/decks/{deck_id}/snapshots")
    ids = [r["id"] for r in listing.json()["data"]]
    assert ids[0] == b_id
    assert ids[1] == a_id


@pytest.mark.asyncio
async def test_delete_snapshot(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="Delete Snap")
    create = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "tmp"})
    snap_id = create.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/snapshots/{snap_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/snapshots/{snap_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_snapshot_cross_account_returns_404(client: AsyncClient) -> None:
    await create_test_account(client, "Owner Snap")
    deck_id = await create_test_deck(client, name="Owner Snap Deck")
    create = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "mine"})
    snap_id = create.json()["data"]["id"]

    await create_test_account(client, "Stranger Snap")
    list_resp = await client.get(f"/api/v1/decks/{deck_id}/snapshots")
    assert list_resp.status_code == 404
    get_resp = await client.get(f"/api/v1/snapshots/{snap_id}")
    assert get_resp.status_code == 404
    del_resp = await client.delete(f"/api/v1/snapshots/{snap_id}")
    assert del_resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_deck_vs_snapshot(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client, name="Compare Deck")
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "categories": ["ramp"]},
    )
    snap = await client.post(f"/api/v1/decks/{deck_id}/snapshots", json={"label": "before edit"})
    snap_id = snap.json()["data"]["id"]

    # After snapshot: drop Sol Ring, add Doubling Season.
    await client.delete(f"/api/v1/decks/{deck_id}/cards/{SOL_RING_SCRYFALL_ID}")
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID), "categories": ["theme"]},
    )

    resp = await client.get(
        "/api/v1/decks/compare",
        params={
            "left": snap_id,
            "left_kind": "snapshot",
            "right": deck_id,
            "right_kind": "deck",
        },
    )
    assert resp.status_code == 200
    diff = resp.json()["data"]["diff"]
    added_names = [e["card"]["name"] for e in diff["added"]]
    removed_names = [e["card"]["name"] for e in diff["removed"]]
    assert "Doubling Season" in added_names
    assert "Sol Ring" in removed_names


@pytest.mark.asyncio
async def test_compare_two_decks(client: AsyncClient) -> None:
    deck_a = await create_test_deck(client, name="Deck A")
    deck_b = await create_test_deck(client, name="Deck B")
    await client.post(
        f"/api/v1/decks/{deck_a}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID)},
    )
    await client.post(
        f"/api/v1/decks/{deck_b}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID)},
    )
    await client.post(
        f"/api/v1/decks/{deck_b}/cards",
        json={"card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID)},
    )

    resp = await client.get(
        "/api/v1/decks/compare",
        params={"left": deck_a, "right": deck_b},
    )
    assert resp.status_code == 200
    diff = resp.json()["data"]["diff"]
    common = [e["card"]["name"] for e in diff["common"]]
    added = [e["card"]["name"] for e in diff["added"]]
    assert "Sol Ring" in common
    assert "Doubling Season" in added


@pytest.mark.asyncio
async def test_compare_includes_price_and_collection_ownership(client: AsyncClient) -> None:
    create_collection = await client.post("/api/v1/me/collections", json={"name": "Binder"})
    collection_id = create_collection.json()["data"]["id"]
    await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={"scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID)},
    )

    deck_a = await create_test_deck(client, name="No Double")
    deck_b = await create_test_deck(client, name="With Double")
    await client.post(
        f"/api/v1/decks/{deck_b}/cards",
        json={"card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID)},
    )

    resp = await client.get(
        "/api/v1/decks/compare",
        params={"left": deck_a, "right": deck_b},
    )
    assert resp.status_code == 200
    added = resp.json()["data"]["diff"]["added"][0]["card"]
    assert added["name"] == "Doubling Season"
    assert added["price_eur_cents"] == 4500
    assert [c["name"] for c in added["owned_in"]] == ["Binder"]


@pytest.mark.asyncio
async def test_compare_cross_account_404(client: AsyncClient) -> None:
    await create_test_account(client, "Owner Cmp")
    deck_id = await create_test_deck(client, name="Mine")
    other_deck = await create_test_deck(client, name="Mine Too")

    await create_test_account(client, "Stranger Cmp")
    resp = await client.get(
        "/api/v1/decks/compare",
        params={"left": deck_id, "right": other_deck},
    )
    assert resp.status_code == 404


def test_diff_compositions_treats_same_name_different_printing_as_common() -> None:
    import uuid

    left_id = uuid.uuid4()
    right_id = uuid.uuid4()
    left = {
        left_id: {
            "card_id": left_id,
            "scryfall_id": uuid.uuid4(),
            "name": "Forest",
            "quantity": 6,
            "categories": ["lands"],
            "color_identity": ["G"],
        }
    }
    right = {
        right_id: {
            "card_id": right_id,
            "scryfall_id": uuid.uuid4(),
            "name": "Forest",
            "quantity": 6,
            "categories": ["lands"],
            "color_identity": ["G"],
        }
    }

    diff = diff_compositions(left, right)
    assert diff.added == []
    assert diff.removed == []
    assert [(e.card.name, e.left_quantity, e.right_quantity) for e in diff.common] == [
        ("Forest", 6, 6)
    ]


def test_diff_compositions_pure() -> None:
    import uuid

    a = uuid.uuid4()
    b = uuid.uuid4()
    c = uuid.uuid4()
    common_row = {
        "card_id": a,
        "scryfall_id": uuid.uuid4(),
        "name": "Alpha",
        "quantity": 1,
        "categories": ["ramp"],
        "color_identity": [],
    }
    qty_left = {**common_row, "card_id": b, "name": "Bravo", "quantity": 1}
    qty_right = {**qty_left, "quantity": 2}
    only_right = {**common_row, "card_id": c, "name": "Charlie"}

    left = {a: dict(common_row), b: qty_left}
    right = {a: dict(common_row), b: qty_right, c: only_right}

    diff = diff_compositions(left, right)
    assert [e.card.name for e in diff.common] == ["Alpha"]
    assert [e.card.name for e in diff.quantity_changed] == ["Bravo"]
    assert [e.card.name for e in diff.added] == ["Charlie"]
    assert diff.removed == []
