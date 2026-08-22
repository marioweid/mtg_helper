"""Tests for the onboarding quickstart pipeline."""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch
from uuid import UUID

import asyncpg
import pytest
from httpx import AsyncClient

from mtg_helper.models.ai import BuildResponse, CardSuggestion
from mtg_helper.services import ai_service, onboarding_service
from mtg_helper.services.deck_service import ColorIdentityError
from mtg_helper.services.onboarding_service import (
    QUICKSTART_STAGE_ORDER,
    QUICKSTART_TARGETS,
    quickstart,
)
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    RHYSTIC_STUDY_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
)


def _suggestion(scryfall_id: UUID, name: str) -> CardSuggestion:
    return CardSuggestion(
        scryfall_id=scryfall_id,
        name=name,
        mana_cost=None,
        type_line=None,
        image_uri=None,
        category="theme",
        reasoning=f"pick {name}",
        synergies=[],
    )


def _build_response(stage: str, suggestions: list[CardSuggestion]) -> BuildResponse:
    return BuildResponse(
        stage=stage,
        stage_number=1,
        total_stages=len(QUICKSTART_STAGE_ORDER),
        suggestions=suggestions,
        unresolved=[],
    )


def _make_mock_build_stage(
    per_stage: dict[str, list[CardSuggestion]] | None = None,
    *,
    record: list[dict[str, Any]] | None = None,
) -> Callable[..., Awaitable[BuildResponse]]:
    """Stub for ai_service.build_stage that captures call args + returns canned data."""

    async def _mock(
        pool: asyncpg.Pool,
        deck_id: UUID,
        account_id: UUID,
        email: str,
        *,
        stage: str | None = None,
        target: int | None = None,
        exclude: list[str] | None = None,
        collection_ids: list[UUID] | None = None,
        max_price_cents: int | None = None,
        min_price_cents: int | None = None,
        card_types: list[str] | None = None,
        subtypes: list[str] | None = None,
    ) -> BuildResponse:
        if record is not None:
            record.append(
                {
                    "stage": stage,
                    "target": target,
                    "max_price_cents": max_price_cents,
                    "min_price_cents": min_price_cents,
                }
            )
        suggestions = (per_stage or {}).get(stage or "", [])
        return _build_response(stage or "theme", suggestions)

    return _mock


@pytest.fixture
def hazel_pool(db_pool: asyncpg.Pool) -> asyncpg.Pool:
    """Alias to make tests self-documenting."""
    return db_pool


# ── happy path ───────────────────────────────────────────────────────────────


async def test_quickstart_calls_nonland_stages_in_order(
    hazel_pool: asyncpg.Pool,
    client: AsyncClient,
) -> None:
    """Nonland stages invoke build_stage in order with correct targets."""
    record: list[dict[str, Any]] = []
    per_stage = {s: [_suggestion(SOL_RING_SCRYFALL_ID, "Sol Ring")] for s in QUICKSTART_STAGE_ORDER}
    mock_build = _make_mock_build_stage(per_stage, record=record)

    # Get account id from the default test account.
    async with hazel_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM accounts WHERE email = $1", "default@test.local")
    account_id = row["id"]

    with patch.object(ai_service, "build_stage", mock_build):
        deck, results = await quickstart(
            hazel_pool,
            email="default@test.local",
            account_id=account_id,
            commander_scryfall_id=HAZEL_SCRYFALL_ID,
        )

    stages_called = [r["stage"] for r in record]
    assert stages_called == list(QUICKSTART_STAGE_ORDER[:-1])
    # Over-fetch multiplier: target = QUICKSTART_TARGETS[stage] * 2
    for r in record:
        assert r["target"] == QUICKSTART_TARGETS[r["stage"]] * 2
    assert deck.stage == QUICKSTART_STAGE_ORDER[0]
    assert len(results) == len(QUICKSTART_STAGE_ORDER)


async def test_quickstart_skips_color_violations(
    hazel_pool: asyncpg.Pool,
    client: AsyncClient,
) -> None:
    """Suggestions that violate color identity are skipped; loop accepts the next valid one."""
    # Hazel is G/W. Rhystic Study (U) is a violation; Sol Ring is colorless.
    per_stage = {
        "theme": [
            _suggestion(RHYSTIC_STUDY_SCRYFALL_ID, "Rhystic Study"),  # rejected
            _suggestion(DOUBLING_SEASON_SCRYFALL_ID, "Doubling Season"),
            _suggestion(SOL_RING_SCRYFALL_ID, "Sol Ring"),
        ],
    }
    # Other stages return empty so we focus on theme.
    for stage in QUICKSTART_STAGE_ORDER:
        per_stage.setdefault(stage, [])

    # Force theme target to 2 to exercise both accepted picks.
    with patch.dict(QUICKSTART_TARGETS, {"theme": 2}, clear=False):
        mock_build = _make_mock_build_stage(per_stage)
        async with hazel_pool.acquire() as conn:
            account_row = await conn.fetchrow(
                "SELECT id FROM accounts WHERE email = $1", "default@test.local"
            )
        with patch.object(ai_service, "build_stage", mock_build):
            deck, results = await quickstart(
                hazel_pool,
                email="default@test.local",
                account_id=account_row["id"],
                commander_scryfall_id=HAZEL_SCRYFALL_ID,
            )

    theme = next(r for r in results if r.stage == "theme")
    assert theme.accepted == 2  # Doubling Season + Sol Ring; Rhystic Study skipped


async def test_quickstart_endpoint_returns_201(client: AsyncClient) -> None:
    """End-to-end: POST /onboarding/quickstart returns deck + per-stage results."""
    per_stage = {s: [] for s in QUICKSTART_STAGE_ORDER}
    mock_build = _make_mock_build_stage(per_stage)
    with patch.object(ai_service, "build_stage", mock_build):
        resp = await client.post(
            "/api/v1/onboarding/quickstart",
            json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID)},
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["deck"]["stage"] == "theme"
    assert len(data["stages"]) == len(QUICKSTART_STAGE_ORDER)
    assert {s["stage"] for s in data["stages"]} == set(QUICKSTART_STAGE_ORDER)


async def test_quickstart_endpoint_unknown_commander_returns_422(
    client: AsyncClient,
) -> None:
    """A scryfall id not in the local DB is reported as 422 COMMANDER_NOT_FOUND."""
    bogus = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        "/api/v1/onboarding/quickstart",
        json={"commander_scryfall_id": bogus},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "COMMANDER_NOT_FOUND"


# Suppress unused-import warnings — these names are imported for fixture access.
_ = ColorIdentityError
_ = onboarding_service
