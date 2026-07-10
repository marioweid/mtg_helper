"""Tests for EDHREC theme index mapping, caching, and scoring."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import httpx
import pytest

from mtg_helper.services import edhrec_theme_index_service as service
from mtg_helper.services.edhrec_theme_index_service import (
    _collect_name_weights,
    _normalize_payload,
    _normalize_tag_page,
    score_themes,
    theme_slugs_for_tags,
)
from tests.conftest import DOCKSIDE_SCRYFALL_ID, SOL_RING_SCRYFALL_ID


def _raw_payload(*, tag: str = "topcards", names: list[str] | None = None) -> dict[str, Any]:
    return {
        "container": {
            "json_dict": {
                "cardlists": [
                    {"tag": tag, "cardviews": [{"name": n} for n in (names or ["Sol Ring"])]}
                ]
            }
        }
    }


def _stub_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = ""
    response.json = MagicMock(return_value=json_body or {})
    response.raise_for_status = MagicMock()
    return response


def _stub_client(*responses: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(side_effect=responses)
    return client


def test_theme_slugs_for_tags_maps_and_dedupes() -> None:
    assert theme_slugs_for_tags(["sacrifice", "aristocrats", "unknown"]) == [
        "sacrifice",
        "aristocrats",
    ]


def test_theme_slugs_for_tags_maps_legacy_plus_one_shape() -> None:
    assert theme_slugs_for_tags(["plus_one_plus_1_counters"]) == [
        "plus-1-plus-1-counters"
    ]


def test_theme_slugs_for_tags_maps_legacy_draw_shape() -> None:
    assert theme_slugs_for_tags(["draw", "card_advantage", "card_draw"]) == ["card-draw"]


def test_theme_slugs_for_tags_normalizes_display_labels() -> None:
    assert theme_slugs_for_tags(["Card Draw", "Control", "Pingers"]) == [
        "card-draw",
        "control",
        "pingers",
    ]


def test_theme_slugs_for_tags_maps_treasure_to_singular_slug() -> None:
    assert theme_slugs_for_tags(["treasure", "treasures", "treasure_matters"]) == ["treasure"]


def test_normalize_payload_keeps_dynamic_categories() -> None:
    payload = _normalize_payload(_raw_payload(tag="highsynergycards", names=["Blood Artist"]))
    assert payload == {"categories": {"highsynergycards": ["Blood Artist"]}}


def test_normalize_payload_skips_commander_lists() -> None:
    payload = _normalize_payload(
        {
            "container": {
                "json_dict": {
                    "cardlists": [
                        {"tag": "topcommanders", "cardviews": [{"name": "Yarok, the Desecrated"}]},
                        {"tag": "topcards", "cardviews": [{"name": "Panharmonicon"}]},
                    ]
                }
            }
        }
    )

    assert payload == {"categories": {"topcards": ["Panharmonicon"]}}


def test_normalize_payload_skips_tag_directory_lists() -> None:
    payload = _normalize_payload(
        {
            "container": {
                "json_dict": {
                    "cardlists": [
                        {"tag": "tagsbypopularitysort", "cardviews": [{"name": "Artifacts"}]},
                        {"tag": "topcards", "cardviews": [{"name": "Hardened Scales"}]},
                    ]
                }
            }
        }
    )

    assert payload == {"categories": {"topcards": ["Hardened Scales"]}}


def test_normalize_tag_page_extracts_next_data_cardlists() -> None:
    next_data = {
        "props": {
            "pageProps": {
                "data": _raw_payload(tag="highsynergycards", names=["Seat of the Synod"])
            }
        }
    }
    markup = (
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(next_data)}"
        "</script>"
    )

    payload = _normalize_tag_page(markup)

    assert payload == {"categories": {"highsynergycards": ["Seat of the Synod"]}}


def test_collect_name_weights_uses_max_weight() -> None:
    weights = _collect_name_weights(
        {
            "categories": {
                "creatures": ["Sol Ring"],
                "highsynergycards": ["Sol Ring"],
            }
        }
    )
    assert weights["sol ring"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_get_or_refresh_inserts_theme_row(db_pool: asyncpg.Pool) -> None:
    tag_response = _stub_response(200)
    tag_response.text = (
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps({'props': {'pageProps': {'data': _raw_payload(names=['Sol Ring'])}}})}"
        "</script>"
    )
    client = _stub_client(tag_response)

    payload = await service.get_or_refresh(db_pool, "aristocrats", client=client)

    assert payload["categories"]["topcards"] == ["Sol Ring"]
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT display_name FROM edhrec_theme_index WHERE slug = $1", "aristocrats"
        )
    assert row is not None
    assert row["display_name"] == "Aristocrats"


@pytest.mark.asyncio
async def test_get_or_refresh_uses_fresh_cache(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO edhrec_theme_index (slug, display_name, source_type, payload, fetched_at)
            VALUES ($1, $2, $3, $4::jsonb, now())
            """,
            "tokens",
            "Tokens",
            "theme",
            json.dumps({"categories": {"topcards": ["Sol Ring"]}}),
        )
    client = _stub_client(_stub_response(200, _raw_payload(names=["Dockside Extortionist"])))

    payload = await service.get_or_refresh(db_pool, "tokens", client=client)

    assert payload["categories"]["topcards"] == ["Sol Ring"]
    assert client.get.await_count == 0


@pytest.mark.asyncio
async def test_get_or_refresh_writes_sentinel_on_404(db_pool: asyncpg.Pool) -> None:
    payload = await service.get_or_refresh(
        db_pool,
        "missing-theme",
        client=_stub_client(_stub_response(404), _stub_response(404)),
        max_age=timedelta(seconds=0),
    )

    assert payload == {"categories": {}}


@pytest.mark.asyncio
async def test_get_or_refresh_refreshes_cached_sentinel(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO edhrec_theme_index (slug, display_name, source_type, payload, fetched_at)
            VALUES ($1, $2, $3, $4::jsonb, now())
            """,
            "artifacts",
            "Artifacts",
            "theme",
            json.dumps({"categories": {}}),
        )
    tag_response = _stub_response(200)
    tag_response.text = (
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps({'props': {'pageProps': {'data': _raw_payload(names=['Seat of the Synod'])}}})}"
        "</script>"
    )

    payload = await service.get_or_refresh(db_pool, "artifacts", client=_stub_client(tag_response))

    assert payload["categories"]["topcards"] == ["Seat of the Synod"]


@pytest.mark.asyncio
async def test_score_themes_resolves_theme_cards(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO edhrec_theme_index (slug, display_name, source_type, payload, fetched_at)
            VALUES ($1, $2, $3, $4::jsonb, now())
            """,
            "treasures",
            "Treasures",
            "theme",
            json.dumps({"categories": {"highsynergycards": ["Sol Ring", "Dockside Extortionist"]}}),
        )
        sol = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", SOL_RING_SCRYFALL_ID
        )
        dockside = await conn.fetchval(
            "SELECT id FROM cards WHERE scryfall_id = $1", DOCKSIDE_SCRYFALL_ID
        )

    red_scores = await score_themes(db_pool, ["treasure_matters"], ["R"])
    green_scores = await score_themes(db_pool, ["treasure_matters"], ["G"])

    assert red_scores[dockside] == pytest.approx(1.0)
    assert red_scores[sol] == pytest.approx(1.0)
    assert dockside not in green_scores
    assert green_scores[sol] == pytest.approx(1.0)
