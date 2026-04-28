"""Tests for EDHREC service: slugify, payload normalization, cache, scoring."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import httpx
import pytest

from mtg_helper.services import edhrec_service
from mtg_helper.services.edhrec_service import (
    _collect_name_weights,
    _normalize_payload,
    score_inclusion,
    slugify,
)
from tests.conftest import HAZEL_SCRYFALL_ID, SOL_RING_SCRYFALL_ID

# ── slugify ───────────────────────────────────────────────────────────────────


def test_slugify_simple_two_word() -> None:
    assert slugify("Ms. Bumbleflower") == "ms-bumbleflower"


def test_slugify_strips_apostrophe_and_comma() -> None:
    assert slugify("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"


def test_slugify_double_faced_uses_front_face() -> None:
    name = "Bruna, the Fading Light // Brisela, Voice of Nightmares"
    assert slugify(name) == "bruna-the-fading-light"


def test_slugify_collapses_runs_of_punctuation() -> None:
    assert slugify("Mr.   Foo--Bar") == "mr-foo-bar"


# ── _normalize_payload ────────────────────────────────────────────────────────


def _raw_payload(*, tag: str = "topcards", names: list[str] | None = None) -> dict[str, Any]:
    return {
        "container": {
            "json_dict": {
                "cardlists": [
                    {"tag": tag, "cardviews": [{"name": n} for n in (names or ["Sol Ring"])]}
                ]
            }
        },
        "panels": {"combocounts": []},
    }


def test_normalize_payload_keeps_known_tags() -> None:
    raw = _raw_payload(tag="highsynergycards", names=["Sol Ring", "Cultivate"])
    normalized = _normalize_payload(raw)
    assert normalized["categories"]["highsynergycards"] == ["Sol Ring", "Cultivate"]


def test_normalize_payload_drops_unknown_tags() -> None:
    raw = _raw_payload(tag="some_future_tag", names=["X"])
    normalized = _normalize_payload(raw)
    assert normalized["categories"] == {}


def test_normalize_payload_extracts_combos_and_dedupes() -> None:
    raw = {
        "container": {"json_dict": {"cardlists": []}},
        "panels": {
            "combocounts": [
                {"value": "Sol Ring + Mana Vault"},
                {"value": "Sol Ring + Wheel of Fortune"},
                {"value": "See More..."},
            ]
        },
    }
    normalized = _normalize_payload(raw)
    assert normalized["combos"] == ["Sol Ring", "Mana Vault", "Wheel of Fortune"]


# ── _collect_name_weights ─────────────────────────────────────────────────────


def test_collect_name_weights_max_across_categories() -> None:
    payload = {
        "categories": {
            "highsynergycards": ["Sol Ring"],
            "creatures": ["Sol Ring"],
        },
        "combos": [],
    }
    weights = _collect_name_weights(payload, bracket=2)
    # highsynergycards (1.00) wins over creatures (0.60)
    assert weights["sol ring"] == pytest.approx(1.00)


def test_collect_name_weights_drops_gamechangers_for_low_bracket() -> None:
    payload = {"categories": {"gamechangers": ["Demonic Tutor"]}, "combos": []}
    assert _collect_name_weights(payload, bracket=2) == {}


def test_collect_name_weights_keeps_gamechangers_at_bracket_3() -> None:
    payload = {"categories": {"gamechangers": ["Demonic Tutor"]}, "combos": []}
    weights = _collect_name_weights(payload, bracket=3)
    assert weights["demonic tutor"] == pytest.approx(0.80)


def test_collect_name_weights_combos_score_above_categories() -> None:
    payload = {
        "categories": {"creatures": ["Thassa's Oracle"]},
        "combos": ["Thassa's Oracle"],
    }
    weights = _collect_name_weights(payload, bracket=2)
    assert weights["thassa's oracle"] == pytest.approx(0.95)


# ── score_inclusion (DB integration) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_inclusion_resolves_names_to_ids(db_pool: asyncpg.Pool) -> None:
    payload = {
        "categories": {"topcards": ["Sol Ring", "Hazel of the Rootbloom"]},
        "combos": [],
    }
    scores = await score_inclusion(db_pool, payload, ["G", "W"], bracket=2)
    # Both cards are in our test set; resolve to UUIDs.
    sql = "SELECT id FROM cards WHERE scryfall_id = $1"
    async with db_pool.acquire() as conn:
        sol = await conn.fetchval(sql, SOL_RING_SCRYFALL_ID)
        hazel = await conn.fetchval(sql, HAZEL_SCRYFALL_ID)
    assert scores[sol] == pytest.approx(0.85)
    assert scores[hazel] == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_score_inclusion_filters_by_color_identity(db_pool: asyncpg.Pool) -> None:
    # Dockside Extortionist is red; commander is mono-green → must be excluded.
    payload = {"categories": {"topcards": ["Dockside Extortionist"]}, "combos": []}
    scores = await score_inclusion(db_pool, payload, ["G"], bracket=2)
    assert scores == {}


@pytest.mark.asyncio
async def test_score_inclusion_empty_payload(db_pool: asyncpg.Pool) -> None:
    assert await score_inclusion(db_pool, {"categories": {}, "combos": []}, ["G"], bracket=2) == {}


# ── get_or_refresh (cache + http stub) ────────────────────────────────────────


def _stub_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json = MagicMock(return_value=json_body or {})
    response.raise_for_status = MagicMock()
    return response


def _stub_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_get_or_refresh_inserts_row_on_first_call(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    raw = _raw_payload(tag="topcards", names=["Sol Ring"])
    client = _stub_client(_stub_response(200, raw))

    payload = await edhrec_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload["categories"]["topcards"] == ["Sol Ring"]
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT slug, payload FROM edhrec_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    assert row is not None
    assert row["slug"] == "hazel-of-the-rootbloom"


@pytest.mark.asyncio
async def test_get_or_refresh_uses_cache_within_max_age(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    raw = _raw_payload(tag="topcards", names=["Sol Ring"])
    client = _stub_client(_stub_response(200, raw))

    await edhrec_service.get_or_refresh(db_pool, commander_id, client=client)
    assert client.get.await_count == 1

    # Second call within max_age must not hit the network again.
    await edhrec_service.get_or_refresh(db_pool, commander_id, client=client)
    assert client.get.await_count == 1


@pytest.mark.asyncio
async def test_get_or_refresh_writes_sentinel_on_403(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    client = _stub_client(_stub_response(403))

    payload = await edhrec_service.get_or_refresh(db_pool, commander_id, client=client)

    assert payload == {"categories": {}, "combos": []}
    async with db_pool.acquire() as conn:
        stored = await conn.fetchval(
            "SELECT payload FROM edhrec_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    parsed = json.loads(stored) if isinstance(stored, str) else stored
    assert parsed == {"categories": {}, "combos": []}


@pytest.mark.asyncio
async def test_get_or_refresh_refetches_after_max_age(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
    raw = _raw_payload(tag="topcards", names=["Sol Ring"])
    client = _stub_client(_stub_response(200, raw))

    # Seed with a stale row.
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO edhrec_commander_recs (commander_id, slug, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now() - interval '20 days')
            """,
            commander_id,
            "stale-slug",
            json.dumps({"categories": {}, "combos": []}),
        )

    await edhrec_service.get_or_refresh(
        db_pool, commander_id, client=client, max_age=timedelta(days=14)
    )
    assert client.get.await_count == 1
    async with db_pool.acquire() as conn:
        slug = await conn.fetchval(
            "SELECT slug FROM edhrec_commander_recs WHERE commander_id = $1", commander_id
        )
    assert slug == "hazel-of-the-rootbloom"


@pytest.mark.asyncio
async def test_get_or_refresh_returns_cached_on_transient_error(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        commander_id = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", HAZEL_SCRYFALL_ID
        )
        await conn.execute(
            """
            INSERT INTO edhrec_commander_recs (commander_id, slug, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now() - interval '20 days')
            """,
            commander_id,
            "old-slug",
            json.dumps({"categories": {"topcards": ["Sol Ring"]}, "combos": []}),
        )

    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    payload = await edhrec_service.get_or_refresh(db_pool, commander_id, client=client)

    # Stale cache returned, no sentinel written, no exception escaped.
    assert payload["categories"]["topcards"] == ["Sol Ring"]
