"""Tests for Moxfield binder URL collection import."""

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient

from mtg_helper.services import collection_url_import_service
from mtg_helper.services.collection_url_import_service import (
    BinderFetchError,
    UnsupportedBinderUrlError,
    _binder_entry_row,
    _condition_title,
    fetch_moxfield_binder,
    parse_binder_url,
)
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)

# ── parse_binder_url ─────────────────────────────────────────────────────────


def test_parse_binder_url_basic() -> None:
    binder_id = parse_binder_url("https://www.moxfield.com/binders/abc123")
    assert binder_id == "abc123"


def test_parse_binder_url_no_www() -> None:
    binder_id = parse_binder_url("https://moxfield.com/binders/XYZ_-9")
    assert binder_id == "XYZ_-9"


def test_parse_binder_url_trailing_slash() -> None:
    binder_id = parse_binder_url("https://www.moxfield.com/binders/abc123/")
    assert binder_id == "abc123"


def test_parse_binder_url_trailing_path() -> None:
    binder_id = parse_binder_url("https://moxfield.com/binders/abc123/some-slug")
    assert binder_id == "abc123"


def test_parse_binder_url_rejects_raw_id() -> None:
    with pytest.raises(UnsupportedBinderUrlError):
        parse_binder_url("abc123")


def test_parse_binder_url_rejects_foreign_host() -> None:
    with pytest.raises(UnsupportedBinderUrlError):
        parse_binder_url("https://example.com/binders/abc123")


def test_parse_binder_url_rejects_deck_url() -> None:
    with pytest.raises(UnsupportedBinderUrlError):
        parse_binder_url("https://www.moxfield.com/decks/abc123")


# ── entry translation ────────────────────────────────────────────────────────


def test_condition_title_camel_case() -> None:
    assert _condition_title("nearMint") == "Near Mint"
    assert _condition_title("lightlyPlayed") == "Lightly Played"
    assert _condition_title("heavilyPlayed") == "Heavily Played"


def test_condition_title_missing() -> None:
    assert _condition_title(None) is None
    assert _condition_title("") is None
    assert _condition_title(42) is None


def _binder_entry(**overrides: Any) -> dict[str, Any]:
    """A realistic binder entry; pass card={...} to override card fields."""
    entry: dict[str, Any] = {
        "quantity": 2,
        "condition": "nearMint",
        "finish": "nonFoil",
        "isFoil": False,
        "purchasePrice": 0.0,
        "lastUpdatedAtUtc": "2025-06-19T15:41:18.607Z",
        "language": {"code": "en", "name": "English"},
        "card": {
            "scryfall_id": str(SOL_RING_SCRYFALL_ID),
            "set": "c19",
            "cn": "255",
            "name": "Sol Ring",
        },
    }
    card_overrides = overrides.pop("card", {})
    entry.update(overrides)
    entry["card"].update(card_overrides)
    return entry


def test_binder_entry_row_full_mapping() -> None:
    row = _binder_entry_row(
        _binder_entry(
            purchasePrice=2.5,
            condition="lightlyPlayed",
            card={"set": "c19", "cn": "255"},
        )
    )
    assert row is not None
    assert row.name == "Sol Ring"
    assert row.quantity == 2
    assert row.set_code == "c19"
    assert row.collector_number == "255"
    assert row.foil is False
    assert row.condition == "Lightly Played"
    assert row.language == "English"
    assert row.purchase_price is not None and str(row.purchase_price) == "2.5"
    assert row.last_modified is not None and row.last_modified.year == 2025
    assert row.scryfall_id == SOL_RING_SCRYFALL_ID
    assert row.tags == []


def test_binder_entry_row_foil_via_flag() -> None:
    row = _binder_entry_row(_binder_entry(isFoil=True))
    assert row is not None and row.foil is True


def test_binder_entry_row_foil_via_etched_finish() -> None:
    row = _binder_entry_row(_binder_entry(finish="etched"))
    assert row is not None and row.foil is True


def test_binder_entry_row_zero_price_becomes_none() -> None:
    row = _binder_entry_row(_binder_entry(purchasePrice=0.0))
    assert row is not None and row.purchase_price is None


def test_binder_entry_row_quantity_clamped() -> None:
    row = _binder_entry_row(_binder_entry(quantity=0))
    assert row is not None and row.quantity == 1
    row = _binder_entry_row(_binder_entry(quantity="many"))
    assert row is not None and row.quantity == 1


def test_binder_entry_row_defensive_against_missing_fields() -> None:
    assert _binder_entry_row({}) is None
    assert _binder_entry_row({"quantity": 1, "card": {}}) is None
    row = _binder_entry_row({"card": {"name": "Sol Ring"}})
    assert row is not None
    assert row.name == "Sol Ring"
    assert row.set_code == ""
    assert row.scryfall_id is None
    assert row.condition is None
    assert row.language is None


# ── fetch_moxfield_binder ────────────────────────────────────────────────────


def _binder_page(
    entries: list[dict[str, Any]],
    *,
    page: int = 1,
    total_pages: int = 1,
    name: str | None = "020 Box1",
) -> dict[str, Any]:
    return {
        "totalOverall": 100,
        "tradeBinder": {"id": "RB2mJ", "name": name, "publicId": "abc123"},
        "pageNumber": page,
        "pageSize": 100,
        "totalResults": len(entries),
        "totalPages": total_pages,
        "data": entries,
    }


def _mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


@pytest.fixture
def _no_page_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collection_url_import_service.settings, "moxfield_binder_page_delay_seconds", 0
    )


async def test_fetch_moxfield_binder_single_page() -> None:
    payload = _binder_page([_binder_entry(), _binder_entry(card={"name": "Plains"})])

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v1/trade-binders/abc123" in request.url.path
        return httpx.Response(200, json=payload)

    async with _mock_client(httpx.MockTransport(handler)) as client:
        binder = await fetch_moxfield_binder("abc123", client=client)

    assert binder.binder_id == "abc123"
    assert binder.name == "020 Box1"
    assert [r.name for r in binder.rows] == ["Sol Ring", "Plains"]


@pytest.mark.usefixtures("_no_page_delay")
async def test_fetch_moxfield_binder_paginates() -> None:
    pages = {
        1: _binder_page([_binder_entry()], page=1, total_pages=3),
        2: _binder_page([_binder_entry(card={"name": "Doubling Season"})], page=2, total_pages=3),
        3: _binder_page([_binder_entry(card={"name": "Plains"})], page=3, total_pages=3),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("pageNumber", "1"))
        return httpx.Response(200, json=pages[page])

    async with _mock_client(httpx.MockTransport(handler)) as client:
        binder = await fetch_moxfield_binder("abc123", client=client)

    assert [r.name for r in binder.rows] == ["Sol Ring", "Doubling Season", "Plains"]


@pytest.mark.usefixtures("_no_page_delay")
async def test_fetch_moxfield_binder_page_cap_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collection_url_import_service, "_MAX_BINDER_PAGES", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("pageNumber", "1"))
        return httpx.Response(200, json=_binder_page([], page=page, total_pages=99))

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(BinderFetchError, match="cap"):
            await fetch_moxfield_binder("huge", client=client)


async def test_fetch_moxfield_binder_404_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(BinderFetchError, match="not found"):
            await fetch_moxfield_binder("missing", client=client)


async def test_fetch_moxfield_binder_403_raises_private() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(BinderFetchError, match="private"):
            await fetch_moxfield_binder("blocked", client=client)


async def test_fetch_moxfield_binder_cloudflare_directs_to_csv() -> None:
    cloudflare_html = (
        "<!DOCTYPE html><html><head>"
        "<title>Attention Required! | Cloudflare</title></head>"
        "<body><div id='challenge-platform'></div></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=cloudflare_html, headers={"content-type": "text/html"})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(BinderFetchError, match="CSV import"):
            await fetch_moxfield_binder("blocked", client=client)


async def test_fetch_moxfield_binder_invalid_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(BinderFetchError, match="not valid JSON"):
            await fetch_moxfield_binder("abc123", client=client)


# ── endpoint integration ─────────────────────────────────────────────────────


def _patch_binder_client(payload: dict[str, Any], status: int = 200) -> Any:
    """Patch collection_url_import_service._make_client to serve `payload`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return patch.object(collection_url_import_service, "_make_client", _factory)


def _integration_payload() -> dict[str, Any]:
    return _binder_page(
        [
            _binder_entry(purchasePrice=2.5),
            _binder_entry(
                quantity=1,
                card={
                    "scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID),
                    "set": "rav",
                    "cn": "262",
                    "name": "Doubling Season",
                },
            ),
            _binder_entry(card={"scryfall_id": None, "name": "Not A Real Card"}),
        ]
    )


async def test_import_url_endpoint_merge_success(client: AsyncClient) -> None:
    await create_test_account(client, "Binder User")
    create = await client.post("/api/v1/me/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]

    with _patch_binder_client(_integration_payload()):
        resp = await client.post(
            f"/api/v1/collections/{cid}/import-url",
            json={"url": "https://www.moxfield.com/binders/abc123", "mode": "merge"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert data["unresolved"] == ["Not A Real Card"]

    cards = await client.get(f"/api/v1/collections/{cid}/cards")
    items = {c["name"]: c for c in cards.json()["data"]}
    sol_ring = items["Sol Ring"]
    assert sol_ring["quantity"] == 2
    assert sol_ring["condition"] == "Near Mint"
    assert sol_ring["language"] == "English"
    assert sol_ring["set_code"] == "c19"
    assert sol_ring["collector_number"] == "255"
    assert float(sol_ring["purchase_price"]) == 2.5


async def test_import_url_endpoint_unsupported_url(client: AsyncClient) -> None:
    await create_test_account(client, "Binder User")
    create = await client.post("/api/v1/me/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/collections/{cid}/import-url",
        json={"url": "https://www.moxfield.com/decks/abc123"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "UNSUPPORTED_URL"


async def test_import_url_endpoint_upstream_5xx_returns_502(client: AsyncClient) -> None:
    await create_test_account(client, "Binder User")
    create = await client.post("/api/v1/me/collections", json={"name": "Box"})
    cid = create.json()["data"]["id"]
    with _patch_binder_client({}, status=503):
        resp = await client.post(
            f"/api/v1/collections/{cid}/import-url",
            json={"url": "https://www.moxfield.com/binders/flaky"},
        )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "UPSTREAM_FETCH_FAILED"


async def test_import_url_endpoint_unknown_collection_404(client: AsyncClient) -> None:
    await create_test_account(client, "Binder User")
    missing = "00000000-0000-0000-0000-000000000000"
    with _patch_binder_client(_integration_payload()):
        resp = await client.post(
            f"/api/v1/collections/{missing}/import-url",
            json={"url": "https://www.moxfield.com/binders/abc123"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "COLLECTION_NOT_FOUND"


async def test_create_from_url_endpoint_creates_and_imports(client: AsyncClient) -> None:
    await create_test_account(client, "New Binder User")
    with _patch_binder_client(_integration_payload()):
        resp = await client.post(
            "/api/v1/me/collections/import-url",
            json={"url": "https://www.moxfield.com/binders/abc123"},
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["collection"]["name"] == "020 Box1"
    assert data["collection"]["card_count"] == 3  # 2 + 1 quantities
    assert data["import"]["imported"] == 2
    assert data["import"]["unresolved"] == ["Not A Real Card"]


async def test_create_from_url_endpoint_name_override(client: AsyncClient) -> None:
    await create_test_account(client, "Override User")
    with _patch_binder_client(_integration_payload()):
        resp = await client.post(
            "/api/v1/me/collections/import-url",
            json={"url": "https://www.moxfield.com/binders/abc123", "name": "My Box"},
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["collection"]["name"] == "My Box"


async def test_create_from_url_endpoint_duplicate_name_409(client: AsyncClient) -> None:
    await create_test_account(client, "Dupe User")
    await client.post("/api/v1/me/collections", json={"name": "020 Box1"})
    with _patch_binder_client(_integration_payload()):
        resp = await client.post(
            "/api/v1/me/collections/import-url",
            json={"url": "https://www.moxfield.com/binders/abc123"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DUPLICATE_COLLECTION"
