"""Tests for moxfield_recs_service: card lookup, deck filtering, cache, scoring."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import httpx
import pytest

from mtg_helper.services import moxfield_recs_service
from mtg_helper.services.moxfield_recs_service import (
    _aggregate_payload,
    _is_precon,
    fetch_deck_cards,
    fetch_moxfield_card_id,
    fetch_top_decks,
    score_inclusion,
)
from tests.conftest import (
    DOCKSIDE_ORACLE_ID,
    HAZEL_ORACLE_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_ORACLE_ID,
    SOL_RING_SCRYFALL_ID,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _stub_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json = MagicMock(return_value=json_body or {})
    response.raise_for_status = MagicMock()
    return response


def _stub_client(*responses: MagicMock) -> MagicMock:
    """Return a client whose ``get`` yields the supplied responses in order."""
    client = MagicMock()
    if len(responses) == 1:
        client.get = AsyncMock(return_value=responses[0])
    else:
        client.get = AsyncMock(side_effect=list(responses))
    return client


# ── fetch_moxfield_card_id ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_moxfield_card_id_prefers_scryfall_match() -> None:
    body = {
        "cards": [
            {"id": "OTHER", "scryfall_id": "00000000-0000-0000-0000-000000000000"},
            {"id": "MATCH", "scryfall_id": str(HAZEL_SCRYFALL_ID)},
        ]
    }
    client = _stub_client(_stub_response(200, body))
    result = await fetch_moxfield_card_id(str(HAZEL_SCRYFALL_ID), "Hazel", client=client)
    assert result == "MATCH"


@pytest.mark.asyncio
async def test_fetch_moxfield_card_id_falls_back_to_first() -> None:
    body = {"cards": [{"id": "FIRST", "scryfall_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}]}
    client = _stub_client(_stub_response(200, body))
    result = await fetch_moxfield_card_id(str(HAZEL_SCRYFALL_ID), "Hazel", client=client)
    assert result == "FIRST"


@pytest.mark.asyncio
async def test_fetch_moxfield_card_id_returns_none_on_404() -> None:
    client = _stub_client(_stub_response(404))
    result = await fetch_moxfield_card_id("x", "Nope", client=client)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_moxfield_card_id_returns_none_on_empty_list() -> None:
    client = _stub_client(_stub_response(200, {"cards": []}))
    assert await fetch_moxfield_card_id("x", "Nope", client=client) is None


# ── precon filter ─────────────────────────────────────────────────────────────


def test_is_precon_by_author_username() -> None:
    deck = {"createdByUser": {"userName": "WotC_Official"}, "hubs": []}
    assert _is_precon(deck) is True


def test_is_precon_keeps_upgraded_precon_decks() -> None:
    """Hub names that contain 'precon' must NOT trigger the filter.

    Upgraded-precon decks are a primary source of real deck-building signal;
    they're authored by community members, not the official accounts.
    """
    deck = {"createdByUser": {"userName": "Random"}, "hubs": [{"name": "Precon Upgrades"}]}
    assert _is_precon(deck) is False


def test_is_precon_normal_deck() -> None:
    deck = {"createdByUser": {"userName": "Breezykiwi"}, "hubs": [{"name": "Budget"}]}
    assert _is_precon(deck) is False


# ── fetch_top_decks ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_top_decks_drops_precons_and_caps_at_ten() -> None:
    body = {
        "data": [
            {
                "publicId": f"deck{i}",
                "likeCount": 1000 - i,
                "createdByUser": {"userName": "Player"},
                "hubs": [],
            }
            for i in range(12)
        ]
        + [
            {
                "publicId": "preconA",
                "likeCount": 9000,
                "createdByUser": {"userName": "wotc_official"},
                "hubs": [],
            }
        ]
    }
    client = _stub_client(_stub_response(200, body))
    decks = await fetch_top_decks("MOX_ID", client=client)
    assert [d["id"] for d in decks] == [f"deck{i}" for i in range(10)]
    assert all(d["likes"] > 0 for d in decks)


@pytest.mark.asyncio
async def test_fetch_top_decks_returns_empty_on_404() -> None:
    client = _stub_client(_stub_response(404))
    assert await fetch_top_decks("MOX_ID", client=client) == []


# ── fetch_deck_cards ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_deck_cards_extracts_mainboard_only() -> None:
    body = {
        "boards": {
            "mainboard": {
                "cards": {
                    "a": {"card": {"scryfall_id": "sf-a"}},
                    "b": {"card": {"scryfall_id": "sf-b"}},
                }
            },
            "commanders": {"cards": {"c": {"card": {"scryfall_id": "sf-cmdr"}}}},
            "sideboard": {"cards": {"s": {"card": {"scryfall_id": "sf-side"}}}},
        }
    }
    client = _stub_client(_stub_response(200, body))
    cards = await fetch_deck_cards("deckid", client=client)
    assert sorted(cards) == ["sf-a", "sf-b"]


@pytest.mark.asyncio
async def test_fetch_deck_cards_returns_empty_on_404() -> None:
    client = _stub_client(_stub_response(404))
    assert await fetch_deck_cards("deckid", client=client) == []


# ── _aggregate_payload ────────────────────────────────────────────────────────


def test_aggregate_payload_counts_distinct_decks() -> None:
    deck_summaries = [{"id": "a", "likes": 10}, {"id": "b", "likes": 5}]
    deck_cards = [
        ["sf-1", "sf-2", "sf-1"],  # duplicate within deck counts once
        ["sf-1", "sf-3"],
    ]
    oracle_by_scryfall = {"sf-1": "oracle-1", "sf-2": "oracle-2", "sf-3": "oracle-3"}
    payload = _aggregate_payload("MOX", deck_summaries, deck_cards, oracle_by_scryfall)
    assert payload["moxfield_card_id"] == "MOX"
    assert payload["by_oracle"]["oracle-1"] == 2
    assert payload["by_oracle"]["oracle-2"] == 1
    assert payload["by_oracle"]["oracle-3"] == 1


def test_aggregate_payload_collapses_printings_of_same_oracle() -> None:
    """Two scryfall_ids resolving to the same oracle_id count as one card per deck."""
    deck_summaries = [{"id": "a", "likes": 10}]
    deck_cards = [["sf-alt-art", "sf-normal"]]
    oracle_by_scryfall = {"sf-alt-art": "oracle-1", "sf-normal": "oracle-1"}
    payload = _aggregate_payload("MOX", deck_summaries, deck_cards, oracle_by_scryfall)
    assert payload["by_oracle"] == {"oracle-1": 1}


def test_aggregate_payload_drops_unresolved_scryfall_ids() -> None:
    """scryfall_ids missing from the oracle map are silently dropped."""
    deck_summaries = [{"id": "a", "likes": 10}]
    deck_cards = [["sf-known", "sf-unknown"]]
    oracle_by_scryfall = {"sf-known": "oracle-1"}
    payload = _aggregate_payload("MOX", deck_summaries, deck_cards, oracle_by_scryfall)
    assert payload["by_oracle"] == {"oracle-1": 1}


# ── score_inclusion (DB integration) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_inclusion_resolves_oracle_to_id(db_pool: asyncpg.Pool) -> None:
    payload = {
        "moxfield_card_id": "MOX",
        "decks": [],
        "by_oracle": {
            str(SOL_RING_ORACLE_ID): 10,  # in all 10 decks → 1.0
            str(HAZEL_ORACLE_ID): 1,  # 1/10 → 0.1
        },
    }
    scores = await score_inclusion(db_pool, payload, ["G", "W"])
    sql = "SELECT id FROM cards WHERE scryfall_id = $1"
    async with db_pool.acquire() as conn:
        sol = await conn.fetchval(sql, SOL_RING_SCRYFALL_ID)
        hazel = await conn.fetchval(sql, HAZEL_SCRYFALL_ID)
    assert scores[sol] == pytest.approx(1.0)
    assert scores[hazel] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_score_inclusion_filters_color_identity(db_pool: asyncpg.Pool) -> None:
    # Dockside is red; commander mono-green → excluded.
    payload = {
        "moxfield_card_id": "MOX",
        "decks": [],
        "by_oracle": {str(DOCKSIDE_ORACLE_ID): 5},
    }
    assert await score_inclusion(db_pool, payload, ["G"]) == {}


@pytest.mark.asyncio
async def test_score_inclusion_empty_payload(db_pool: asyncpg.Pool) -> None:
    sentinel: dict[str, Any] = {"moxfield_card_id": None, "decks": [], "by_oracle": {}}
    assert await score_inclusion(db_pool, sentinel, ["G"]) == {}


# ── get_or_refresh (cache + http stub) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_refresh_inserts_row_on_first_call(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    named_resp = _stub_response(
        200, {"cards": [{"id": "MOX", "scryfall_id": str(HAZEL_SCRYFALL_ID)}]}
    )
    search_resp = _stub_response(
        200,
        {
            "data": [
                {
                    "publicId": "deckA",
                    "likeCount": 100,
                    "createdByUser": {"userName": "Alice"},
                    "hubs": [],
                }
            ]
        },
    )
    deck_resp = _stub_response(
        200,
        {
            "boards": {
                "mainboard": {"cards": {"x": {"card": {"scryfall_id": str(SOL_RING_SCRYFALL_ID)}}}}
            }
        },
    )
    client = _stub_client(named_resp, search_resp, deck_resp)

    async def _fake_resolve(sf_ids: list[str], *, client: Any) -> dict[str, str]:  # noqa: ARG001
        return {str(SOL_RING_SCRYFALL_ID).lower(): str(SOL_RING_ORACLE_ID).lower()}

    monkeypatch.setattr(moxfield_recs_service, "_resolve_oracle_ids", _fake_resolve)

    payload = await moxfield_recs_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload["moxfield_card_id"] == "MOX"
    assert payload["by_oracle"][str(SOL_RING_ORACLE_ID).lower()] == 1
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT moxfield_card_id, payload FROM moxfield_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    assert row is not None
    assert row["moxfield_card_id"] == "MOX"


@pytest.mark.asyncio
async def test_get_or_refresh_uses_cache_within_max_age(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
        await conn.execute(
            """
            INSERT INTO moxfield_commander_recs
                (commander_id, moxfield_card_id, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now())
            ON CONFLICT (commander_id) DO UPDATE SET
                moxfield_card_id = EXCLUDED.moxfield_card_id,
                payload = EXCLUDED.payload,
                fetched_at = now()
            """,
            commander_id,
            "CACHED",
            json.dumps(
                {
                    "moxfield_card_id": "CACHED",
                    "decks": [],
                    "by_oracle": {str(SOL_RING_ORACLE_ID): 3},
                }
            ),
        )

    client = _stub_client(_stub_response(500))  # would fail if called

    payload = await moxfield_recs_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload["moxfield_card_id"] == "CACHED"
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_refresh_writes_sentinel_on_404(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    client = _stub_client(_stub_response(404))

    payload = await moxfield_recs_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload == {"moxfield_card_id": None, "decks": [], "by_oracle": {}}
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT moxfield_card_id, payload FROM moxfield_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    assert row is not None
    assert row["moxfield_card_id"] is None


@pytest.mark.asyncio
async def test_get_or_refresh_refetches_after_max_age(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
        await conn.execute(
            """
            INSERT INTO moxfield_commander_recs
                (commander_id, moxfield_card_id, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now() - interval '40 days')
            ON CONFLICT (commander_id) DO UPDATE SET
                moxfield_card_id = EXCLUDED.moxfield_card_id,
                payload = EXCLUDED.payload,
                fetched_at = now() - interval '40 days'
            """,
            commander_id,
            "STALE",
            json.dumps({"moxfield_card_id": "STALE", "decks": [], "by_scryfall": {}}),
        )

    named_resp = _stub_response(
        200, {"cards": [{"id": "FRESH", "scryfall_id": str(HAZEL_SCRYFALL_ID)}]}
    )
    search_resp = _stub_response(200, {"data": []})
    client = _stub_client(named_resp, search_resp)

    await moxfield_recs_service.get_or_refresh(
        db_pool, commander_id, client=client, max_age=timedelta(days=28)
    )
    async with db_pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT moxfield_card_id FROM moxfield_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    assert row == "FRESH"


@pytest.mark.asyncio
async def test_get_or_refresh_returns_cached_on_transient_error(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
        await conn.execute(
            """
            INSERT INTO moxfield_commander_recs
                (commander_id, moxfield_card_id, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now() - interval '40 days')
            ON CONFLICT (commander_id) DO UPDATE SET
                moxfield_card_id = EXCLUDED.moxfield_card_id,
                payload = EXCLUDED.payload,
                fetched_at = now() - interval '40 days'
            """,
            commander_id,
            "OLD",
            json.dumps(
                {
                    "moxfield_card_id": "OLD",
                    "decks": [],
                    "by_oracle": {str(SOL_RING_ORACLE_ID): 3},
                }
            ),
        )

    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    payload = await moxfield_recs_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload["moxfield_card_id"] == "OLD"
    assert payload["by_oracle"][str(SOL_RING_ORACLE_ID)] == 3
