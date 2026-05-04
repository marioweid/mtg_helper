"""Tests for URL-based deck import (Moxfield + Archidekt)."""

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient

from mtg_helper.services import deck_url_import_service
from mtg_helper.services.deck_url_import_service import (
    DeckFetchError,
    UnsupportedDeckUrlError,
    _archidekt_category,
    _moxfield_category,
    fetch_archidekt_deck,
    fetch_moxfield_deck,
    parse_deck_url,
)

# ── parse_deck_url ───────────────────────────────────────────────────────────


def test_parse_deck_url_moxfield_basic() -> None:
    source, deck_id = parse_deck_url("https://www.moxfield.com/decks/abc123")
    assert source == "moxfield"
    assert deck_id == "abc123"


def test_parse_deck_url_moxfield_no_www() -> None:
    source, deck_id = parse_deck_url("https://moxfield.com/decks/XYZ_-9")
    assert source == "moxfield"
    assert deck_id == "XYZ_-9"


def test_parse_deck_url_moxfield_trailing_slash() -> None:
    source, deck_id = parse_deck_url("https://www.moxfield.com/decks/abc123/")
    assert source == "moxfield"
    assert deck_id == "abc123"


def test_parse_deck_url_archidekt_basic() -> None:
    source, deck_id = parse_deck_url("https://archidekt.com/decks/12345")
    assert source == "archidekt"
    assert deck_id == "12345"


def test_parse_deck_url_archidekt_with_slug() -> None:
    source, deck_id = parse_deck_url("https://archidekt.com/decks/12345/some-slug")
    assert source == "archidekt"
    assert deck_id == "12345"


def test_parse_deck_url_rejects_raw_id() -> None:
    with pytest.raises(UnsupportedDeckUrlError):
        parse_deck_url("abc123")


def test_parse_deck_url_rejects_foreign_host() -> None:
    with pytest.raises(UnsupportedDeckUrlError):
        parse_deck_url("https://example.com/decks/abc123")


def test_parse_deck_url_rejects_archidekt_non_numeric() -> None:
    with pytest.raises(UnsupportedDeckUrlError):
        parse_deck_url("https://archidekt.com/decks/abc")


# ── category mapping ─────────────────────────────────────────────────────────


def test_moxfield_category_creature_to_theme() -> None:
    assert _moxfield_category("Creature — Elf Druid") == "theme"


def test_moxfield_category_land_to_lands() -> None:
    assert _moxfield_category("Basic Land — Forest") == "lands"


def test_moxfield_category_instant_to_interaction() -> None:
    assert _moxfield_category("Instant") == "interaction"


def test_moxfield_category_unknown_returns_none() -> None:
    assert _moxfield_category("Tribal Sorcery") == "interaction"
    assert _moxfield_category(None) is None


def test_archidekt_category_skips_commander() -> None:
    assert _archidekt_category(["Commander", "Ramp"]) == "ramp"


def test_archidekt_category_lands() -> None:
    assert _archidekt_category(["Lands"]) == "lands"


def test_archidekt_category_unknown_returns_none() -> None:
    assert _archidekt_category(["Wibble"]) is None


# ── fetch_moxfield_deck ──────────────────────────────────────────────────────


def _moxfield_payload() -> dict[str, Any]:
    return {
        "name": "Hazel Tokens",
        "description": "Tokens go brrr",
        "boards": {
            "commanders": {
                "cards": {
                    "h1": {"card": {"name": "Hazel of the Rootbloom", "type": "Creature"}},
                }
            },
            "mainboard": {
                "cards": {
                    "c1": {
                        "quantity": 1,
                        "card": {"name": "Sol Ring", "type": "Artifact"},
                    },
                    "c2": {
                        "quantity": 1,
                        "card": {"name": "Doubling Season", "type": "Enchantment"},
                    },
                    "c3": {
                        "quantity": 30,
                        "card": {"name": "Plains", "type": "Basic Land — Plains"},
                    },
                }
            },
            "sideboard": {"cards": {"sb1": {"card": {"name": "Negate"}}}},
        },
    }


def _mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_fetch_moxfield_deck_basic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v3/decks/all/abc123")
        return httpx.Response(200, json=_moxfield_payload())

    async with _mock_client(httpx.MockTransport(handler)) as client:
        deck = await fetch_moxfield_deck("abc123", client=client)

    assert deck.source == "moxfield"
    assert deck.name == "Hazel Tokens"
    assert deck.commanders == ["Hazel of the Rootbloom"]
    names = [e.name for e in deck.entries]
    assert "Sol Ring" in names
    assert "Doubling Season" in names
    assert "Plains" in names
    assert "Negate" not in names  # sideboard skipped
    plains = next(e for e in deck.entries if e.name == "Plains")
    assert plains.quantity == 30
    assert plains.category == "lands"


async def test_fetch_moxfield_deck_404_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(DeckFetchError, match="not found"):
            await fetch_moxfield_deck("missing", client=client)


async def test_fetch_moxfield_deck_403_raises_friendly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(DeckFetchError, match="blocked"):
            await fetch_moxfield_deck("blocked", client=client)


async def test_fetch_moxfield_deck_5xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(DeckFetchError, match="503"):
            await fetch_moxfield_deck("flaky", client=client)


async def test_fetch_moxfield_deck_cloudflare_challenge_directs_to_paste() -> None:
    """Cloudflare-fronted 403 surfaces a paste-text suggestion."""
    cloudflare_html = (
        "<!DOCTYPE html><html><head>"
        "<title>Attention Required! | Cloudflare</title></head>"
        "<body><div id='challenge-platform'></div></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=cloudflare_html, headers={"content-type": "text/html"})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(DeckFetchError, match="Paste deck text"):
            await fetch_moxfield_deck("blocked", client=client)


# ── fetch_archidekt_deck ─────────────────────────────────────────────────────


def _archidekt_payload() -> dict[str, Any]:
    return {
        "name": "Hazel Tokens",
        "description": "tokens",
        "cards": [
            {
                "quantity": 1,
                "categories": ["Commander"],
                "card": {"oracleCard": {"name": "Hazel of the Rootbloom"}},
            },
            {
                "quantity": 1,
                "categories": ["Ramp"],
                "card": {"oracleCard": {"name": "Sol Ring"}},
            },
            {
                "quantity": 30,
                "categories": ["Lands"],
                "card": {"oracleCard": {"name": "Plains"}},
            },
            {
                "quantity": 1,
                "categories": ["Sideboard"],
                "card": {"oracleCard": {"name": "Negate"}},
            },
            {
                "quantity": 1,
                "categories": [],  # uncategorized — should still import as theme/None
                "card": {"oracleCard": {"name": "Doubling Season"}},
            },
        ],
    }


async def test_fetch_archidekt_deck_basic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/decks/12345/")
        return httpx.Response(200, json=_archidekt_payload())

    async with _mock_client(httpx.MockTransport(handler)) as client:
        deck = await fetch_archidekt_deck("12345", client=client)

    assert deck.source == "archidekt"
    assert deck.commanders == ["Hazel of the Rootbloom"]
    names = [e.name for e in deck.entries]
    assert "Sol Ring" in names
    assert "Plains" in names
    assert "Doubling Season" in names
    assert "Negate" not in names  # sideboard skipped
    plains = next(e for e in deck.entries if e.name == "Plains")
    assert plains.quantity == 30
    assert plains.category == "lands"
    sol_ring = next(e for e in deck.entries if e.name == "Sol Ring")
    assert sol_ring.category == "ramp"


async def test_fetch_archidekt_deck_defensive_against_missing_fields() -> None:
    payload = {
        "cards": [
            {},  # totally empty
            {"quantity": 1, "card": {}},  # no oracleCard
            {
                "quantity": 1,
                "categories": ["Commander"],
                "card": {"oracleCard": {"name": "Hazel of the Rootbloom"}},
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _mock_client(httpx.MockTransport(handler)) as client:
        deck = await fetch_archidekt_deck("12345", client=client)

    assert deck.commanders == ["Hazel of the Rootbloom"]
    assert deck.entries == []


async def test_fetch_archidekt_deck_404_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    async with _mock_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(DeckFetchError, match="not found"):
            await fetch_archidekt_deck("404id", client=client)


# ── endpoint integration ─────────────────────────────────────────────────────


def _patch_url_client(payload: dict[str, Any], status: int = 200) -> Any:
    """Return a context manager that patches deck_url_import_service._make_client."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return patch.object(deck_url_import_service, "_make_client", _factory)


async def test_import_url_endpoint_moxfield_success(client: AsyncClient) -> None:
    # Hazel-only payload using cards seeded by conftest.
    payload = {
        "name": "Mock Hazel",
        "boards": {
            "commanders": {"cards": {"h1": {"card": {"name": "Hazel of the Rootbloom"}}}},
            "mainboard": {
                "cards": {
                    "c1": {"quantity": 1, "card": {"name": "Sol Ring", "type": "Artifact"}},
                    "c2": {
                        "quantity": 1,
                        "card": {"name": "Doubling Season", "type": "Enchantment"},
                    },
                }
            },
        },
    }
    with _patch_url_client(payload):
        resp = await client.post(
            "/api/v1/decks/import-url",
            json={"url": "https://www.moxfield.com/decks/abc123"},
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["deck"]["stage"] == "complete"
    assert data["imported_count"] == 2


async def test_import_url_endpoint_unsupported_url(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks/import-url",
        json={"url": "https://example.com/decks/abc"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "UNSUPPORTED_URL"


async def test_import_url_endpoint_upstream_5xx_returns_502(client: AsyncClient) -> None:
    with _patch_url_client({}, status=503):
        resp = await client.post(
            "/api/v1/decks/import-url",
            json={"url": "https://www.moxfield.com/decks/flaky"},
        )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "UPSTREAM_FETCH_FAILED"


async def test_import_url_endpoint_color_violation_reported(client: AsyncClient) -> None:
    payload = {
        "boards": {
            "commanders": {"cards": {"h1": {"card": {"name": "Hazel of the Rootbloom"}}}},
            "mainboard": {
                "cards": {
                    "c1": {"quantity": 1, "card": {"name": "Sol Ring", "type": "Artifact"}},
                    # Rhystic Study is U; Hazel is G/W → violation
                    "c2": {
                        "quantity": 1,
                        "card": {"name": "Rhystic Study", "type": "Enchantment"},
                    },
                }
            },
        },
    }
    with _patch_url_client(payload):
        resp = await client.post(
            "/api/v1/decks/import-url",
            json={"url": "https://www.moxfield.com/decks/abc123", "name": "Color Test"},
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "Rhystic Study" in data["color_violations"]
    assert data["imported_count"] == 1
