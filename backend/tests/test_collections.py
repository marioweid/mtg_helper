"""Tests for collection CRUD, CSV parser, import/export, card management."""

from decimal import Decimal

import pytest
from httpx import AsyncClient

from mtg_helper.services.collection_service import parse_moxfield_csv
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)

# ── parse_moxfield_csv unit tests ────────────────────────────────────────────


def test_parse_basic_moxfield_row() -> None:
    text = (
        '"Count","Tradelist Count","Name","Edition","Condition","Language","Foil",'
        '"Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"\n'
        '"1","1","Sol Ring","c19","Near Mint","English","","",'
        '"2026-04-04 14:39:47.307000","255","False","False","2.50"'
    )
    rows = parse_moxfield_csv(text)
    assert len(rows) == 1
    r = rows[0]
    assert r.name == "Sol Ring"
    assert r.quantity == 1
    assert r.set_code == "c19"
    assert r.collector_number == "255"
    assert r.foil is False
    assert r.condition == "Near Mint"
    assert r.language == "English"
    assert r.purchase_price == Decimal("2.50")
    assert r.last_modified is not None


def test_parse_foil_flag() -> None:
    text = '"Count","Name","Edition","Foil","Collector Number"\n"1","Sol Ring","c19","foil","255"'
    rows = parse_moxfield_csv(text)
    assert rows[0].foil is True


def test_parse_blank_purchase_price() -> None:
    text = (
        '"Count","Name","Edition","Collector Number","Purchase Price"\n'
        '"1","Sol Ring","c19","255",""'
    )
    rows = parse_moxfield_csv(text)
    assert rows[0].purchase_price is None


def test_parse_multiple_rows() -> None:
    text = (
        '"Count","Name","Edition","Collector Number"\n'
        '"1","Sol Ring","c19","255"\n'
        '"2","Doubling Season","rav","262"\n'
        '"1","Rhystic Study","pcy","45"'
    )
    rows = parse_moxfield_csv(text)
    assert len(rows) == 3
    assert rows[1].quantity == 2
    assert rows[2].name == "Rhystic Study"


def test_parse_tags_split_on_comma() -> None:
    text = (
        '"Count","Name","Edition","Collector Number","Tags"\n'
        '"1","Sol Ring","c19","255","binder,trade"'
    )
    rows = parse_moxfield_csv(text)
    assert rows[0].tags == ["binder", "trade"]


def test_parse_skips_blank_name() -> None:
    text = (
        '"Count","Name","Edition","Collector Number"\n'
        '"1","Sol Ring","c19","255"\n'
        '"1","","c19","255"'
    )
    rows = parse_moxfield_csv(text)
    assert len(rows) == 1


def test_parse_missing_header_raises() -> None:
    with pytest.raises(ValueError, match="Count"):
        parse_moxfield_csv('"Name"\n"Sol Ring"')


def test_parse_empty_raises() -> None:
    with pytest.raises(ValueError):
        parse_moxfield_csv("")


def test_parse_header_only_raises() -> None:
    text = '"Count","Name","Edition","Collector Number"'
    with pytest.raises(ValueError, match="no valid"):
        parse_moxfield_csv(text)


# ── collection CRUD integration tests ────────────────────────────────────────


async def test_create_collection(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Coll User")
    resp = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Paper Binder"}
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Paper Binder"
    assert data["card_count"] == 0
    assert data["account_id"] == account_id


async def test_create_collection_duplicate_name_conflict(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Dup User")
    await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Main"})
    resp = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Main"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DUPLICATE_COLLECTION"


async def test_create_collection_account_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/accounts/00000000-0000-0000-0000-000000000000/collections",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"


async def test_list_collections(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "List User")
    await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "A"})
    await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "B"})
    resp = await client.get(f"/api/v1/accounts/{account_id}/collections")
    assert resp.status_code == 200
    items = resp.json()["data"]
    names = {i["name"] for i in items}
    assert names == {"A", "B"}


async def test_rename_collection(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Rename User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Old"})
    cid = create.json()["data"]["id"]
    resp = await client.patch(f"/api/v1/collections/{cid}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "New"


async def test_delete_collection(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Del User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Trash"})
    cid = create.json()["data"]["id"]
    resp = await client.delete(f"/api/v1/collections/{cid}")
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/v1/collections/{cid}")
    assert get_resp.status_code == 404


# ── card management ───────────────────────────────────────────────────────────


async def test_add_card_to_collection(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Add User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={
            "scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "quantity": 2,
            "set_code": "c19",
            "collector_number": "255",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Sol Ring"
    assert data["quantity"] == 2


async def test_add_card_increments_on_duplicate_printing(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Inc User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    payload = {
        "scryfall_id": str(SOL_RING_SCRYFALL_ID),
        "quantity": 1,
        "set_code": "c19",
        "collector_number": "255",
    }
    await client.post(f"/api/v1/collections/{cid}/cards", json=payload)
    await client.post(f"/api/v1/collections/{cid}/cards", json=payload)
    list_resp = await client.get(f"/api/v1/collections/{cid}/cards")
    items = list_resp.json()["data"]
    assert len(items) == 1
    assert items[0]["quantity"] == 2


async def test_list_cards_pagination(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Page User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    for sid, sc, cn in [
        (SOL_RING_SCRYFALL_ID, "c19", "255"),
        (DOUBLING_SEASON_SCRYFALL_ID, "rav", "262"),
    ]:
        await client.post(
            f"/api/v1/collections/{cid}/cards",
            json={
                "scryfall_id": str(sid),
                "quantity": 1,
                "set_code": sc,
                "collector_number": cn,
            },
        )
    resp = await client.get(f"/api/v1/collections/{cid}/cards?limit=1&offset=0")
    body = resp.json()
    assert body["meta"]["total"] == 2
    assert len(body["data"]) == 1


async def test_update_card_quantity(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Patch User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    add = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={
            "scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "quantity": 1,
            "set_code": "c19",
            "collector_number": "255",
        },
    )
    card_id = add.json()["data"]["card_id"]
    resp = await client.patch(f"/api/v1/collections/{cid}/cards/{card_id}", json={"quantity": 4})
    assert resp.status_code == 200
    assert resp.json()["data"]["quantity"] == 4


async def test_remove_card_from_collection(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Rem User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    add = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={
            "scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "quantity": 1,
            "set_code": "c19",
            "collector_number": "255",
        },
    )
    card_id = add.json()["data"]["card_id"]
    resp = await client.delete(f"/api/v1/collections/{cid}/cards/{card_id}")
    assert resp.status_code == 204
    list_resp = await client.get(f"/api/v1/collections/{cid}/cards")
    assert list_resp.json()["data"] == []


# ── add by name (Phase 2 search-bar flow) ────────────────────────────────────


async def test_add_card_by_name(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Name User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={"name": "Sol Ring", "quantity": 3},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Sol Ring"
    assert data["quantity"] == 3
    assert data["scryfall_id"] == str(SOL_RING_SCRYFALL_ID)


async def test_add_card_by_fuzzy_name(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Fuzzy User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={"name": "sol ring"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "Sol Ring"


async def test_add_card_by_name_not_found(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Miss User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={"name": "ZZZNonexistentCardXXX"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "CARD_NOT_FOUND"


async def test_add_card_requires_identifier(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "None User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(f"/api/v1/collections/{cid}/cards", json={"quantity": 1})
    assert resp.status_code == 422


async def test_add_card_rejects_both_identifiers(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Both User")
    create = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={"scryfall_id": str(SOL_RING_SCRYFALL_ID), "name": "Sol Ring"},
    )
    assert resp.status_code == 422


# ── CSV import/export integration ─────────────────────────────────────────────


async def test_import_merge_basic(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Import User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    csv_text = (
        '"Count","Tradelist Count","Name","Edition","Condition","Language","Foil",'
        '"Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"\n'
        '"1","1","Sol Ring","c19","Near Mint","English","","",'
        '"2026-04-04 14:39:47.307000","255","False","False","2.50"\n'
        '"1","1","Doubling Season","rav","Near Mint","English","","",'
        '"2026-04-04 14:39:47.307000","262","False","False","50.00"'
    )
    resp = await client.post(
        f"/api/v1/collections/{cid}/import", json={"csv": csv_text, "mode": "merge"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert data["unresolved"] == []


async def test_import_merge_second_time_increments(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Inc2 User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    csv_text = '"Count","Name","Edition","Collector Number"\n"1","Sol Ring","c19","255"'
    await client.post(f"/api/v1/collections/{cid}/import", json={"csv": csv_text, "mode": "merge"})
    resp = await client.post(
        f"/api/v1/collections/{cid}/import", json={"csv": csv_text, "mode": "merge"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["updated"] == 1
    list_resp = await client.get(f"/api/v1/collections/{cid}/cards")
    items = list_resp.json()["data"]
    assert items[0]["quantity"] == 2


async def test_import_replace_clears_previous(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Replace User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    await client.post(
        f"/api/v1/collections/{cid}/import",
        json={
            "csv": '"Count","Name","Edition","Collector Number"\n"1","Sol Ring","c19","255"',
            "mode": "merge",
        },
    )
    resp = await client.post(
        f"/api/v1/collections/{cid}/import",
        json={
            "csv": (
                '"Count","Name","Edition","Collector Number"\n"1","Doubling Season","rav","262"'
            ),
            "mode": "replace",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["removed"] == 1
    list_resp = await client.get(f"/api/v1/collections/{cid}/cards")
    items = list_resp.json()["data"]
    assert [i["name"] for i in items] == ["Doubling Season"]


async def test_import_unresolved_reported(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Unres User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    csv_text = (
        '"Count","Name","Edition","Collector Number"\n'
        '"1","Sol Ring","c19","255"\n'
        '"1","ZZZNonexistentCardXXX","xxx","999"'
    )
    resp = await client.post(
        f"/api/v1/collections/{cid}/import",
        json={"csv": csv_text, "mode": "merge"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"] == 1
    assert "ZZZNonexistentCardXXX" in data["unresolved"]


async def test_import_malformed_csv_returns_422(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Bad User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/import",
        json={"csv": '"Name"\n"Sol Ring"', "mode": "merge"},
    )
    assert resp.status_code == 422


async def test_export_round_trip(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "RT User")
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": "Binder"}
    )
    cid = create.json()["data"]["id"]
    original = (
        '"Count","Tradelist Count","Name","Edition","Condition","Language","Foil",'
        '"Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"\n'
        '"2","2","Sol Ring","c19","Near Mint","English","","",'
        '"2026-04-04 14:39:47.307000","255","False","False","2.50"'
    )
    await client.post(f"/api/v1/collections/{cid}/import", json={"csv": original, "mode": "merge"})
    resp = await client.get(f"/api/v1/collections/{cid}/export")
    assert resp.status_code == 200
    text = resp.text
    assert "Sol Ring" in text
    assert "c19" in text
    assert "255" in text

    # Import the export into a fresh collection and verify contents match.
    create2 = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": "RT2"})
    cid2 = create2.json()["data"]["id"]
    import2 = await client.post(
        f"/api/v1/collections/{cid2}/import", json={"csv": text, "mode": "merge"}
    )
    assert import2.status_code == 200
    list_resp = await client.get(f"/api/v1/collections/{cid2}/cards")
    items = list_resp.json()["data"]
    assert len(items) == 1
    assert items[0]["name"] == "Sol Ring"
    assert items[0]["quantity"] == 2
