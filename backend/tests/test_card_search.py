"""Tests for card search API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_search_by_name(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/search?q=Sol+Ring")
    assert resp.status_code == 200
    data = resp.json()
    assert any(c["name"] == "Sol Ring" for c in data["data"])


@pytest.mark.asyncio
async def test_search_by_color_identity_subset(client: AsyncClient) -> None:
    # Green+White commander — should find GW and G and W and colorless cards
    resp = await client.get("/api/v1/cards/search?color_identity=GW")
    assert resp.status_code == 200
    cards = resp.json()["data"]
    for card in cards:
        card_identity = set(card["color_identity"])
        assert card_identity <= {"G", "W"}, f"{card['name']} has identity {card_identity}"


@pytest.mark.asyncio
async def test_search_excludes_wrong_color(client: AsyncClient) -> None:
    # Blue cards should not appear in a GW search
    resp = await client.get("/api/v1/cards/search?color_identity=GW")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["data"]]
    assert "Rhystic Study" not in names
    assert "Dockside Extortionist" not in names


@pytest.mark.asyncio
async def test_search_by_type(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/search?type=Enchantment")
    assert resp.status_code == 200
    cards = resp.json()["data"]
    assert all("Enchantment" in c["type_line"] for c in cards)


@pytest.mark.asyncio
async def test_search_by_cmc_range(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/search?cmc_min=1&cmc_max=3")
    assert resp.status_code == 200
    for card in resp.json()["data"]:
        assert card["cmc"] is not None
        assert 1 <= float(card["cmc"]) <= 3


@pytest.mark.asyncio
async def test_search_commander_legal_filter(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/search?commander_legal=true")
    assert resp.status_code == 200
    for card in resp.json()["data"]:
        assert card["legalities"].get("commander") == "legal"


@pytest.mark.asyncio
async def test_search_pagination(client: AsyncClient) -> None:
    resp1 = await client.get("/api/v1/cards/search?limit=2&offset=0")
    resp2 = await client.get("/api/v1/cards/search?limit=2&offset=2")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    names1 = [c["name"] for c in resp1.json()["data"]]
    names2 = [c["name"] for c in resp2.json()["data"]]
    # Pages should not overlap
    assert not set(names1) & set(names2)
    # Meta should reflect pagination
    assert resp1.json()["meta"]["limit"] == 2
    assert resp1.json()["meta"]["offset"] == 0


@pytest.mark.asyncio
async def test_search_empty_results(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/search?q=xyznonexistentcard12345")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_get_card_by_scryfall_id(client: AsyncClient) -> None:
    scryfall_id = "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67"  # Sol Ring
    resp = await client.get(f"/api/v1/cards/{scryfall_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Sol Ring"


@pytest.mark.asyncio
async def test_get_card_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/cards/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
