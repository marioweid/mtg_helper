"""Tests for the deck description agent endpoint."""

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic_ai.models.test import TestModel

from mtg_helper.services.agents import describe_agent, extract_agent
from tests.conftest import HAZEL_SCRYFALL_ID


def _override_describe(custom_output_args: dict[str, Any]) -> Any:
    """Swap the describe agent's model for a TestModel emitting fixed output."""
    return describe_agent.get_agent().override(
        model=TestModel(custom_output_args=custom_output_args)
    )


def _override_extract(custom_output_args: dict[str, Any]) -> Any:
    return extract_agent.get_agent().override(
        model=TestModel(custom_output_args=custom_output_args)
    )


@pytest.mark.asyncio
async def test_describe_follow_up_question(client: AsyncClient) -> None:
    """Agent returns a follow-up question (done=False)."""
    with _override_describe(
        {
            "reply": "What win condition are you aiming for?",
            "done": False,
        }
    ):
        resp = await client.post(
            "/api/v1/decks/describe",
            json={
                "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
                "bracket": 3,
                "history": [],
                "message": "",
            },
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is False
    assert data["description"] is None
    assert "win condition" in data["reply"]


@pytest.mark.asyncio
async def test_describe_completion(client: AsyncClient) -> None:
    """Agent returns done=True with name and description."""
    with _override_describe(
        {
            "reply": "Got it!",
            "done": True,
            "suggested_name": "Hazel Tokens",
            "description": "token aristocrats deck with sacrifice payoffs and lifegain",
        }
    ):
        resp = await client.post(
            "/api/v1/decks/describe",
            json={
                "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
                "bracket": 2,
                "history": [
                    {"role": "assistant", "content": "What's your strategy?"},
                    {"role": "user", "content": "tokens and sacrifice"},
                ],
                "message": "tokens and sacrifice",
            },
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is True
    assert data["suggested_name"] == "Hazel Tokens"
    assert "aristocrats" in data["description"]


@pytest.mark.asyncio
async def test_describe_message_max_length_rejected(client: AsyncClient) -> None:
    """Over-long user message is rejected by Pydantic validation."""
    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": [],
            "message": "x" * 3000,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_describe_history_length_exceeded_rejected(client: AsyncClient) -> None:
    """Over-long history (>24 entries) is rejected by Pydantic validation."""
    too_long = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(25)
    ]
    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": too_long,
            "message": "hi",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_describe_unknown_commander(client: AsyncClient) -> None:
    """Returns 404 when commander scryfall_id is not in the DB."""
    import uuid

    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(uuid.uuid4()),
            "bracket": 3,
            "history": [],
            "message": "",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CARD_NOT_FOUND"


@pytest.mark.asyncio
async def test_extract_keywords_filters_unknown_tags(client: AsyncClient) -> None:
    """The KeywordExtractResponse validator drops tags outside the vocabulary."""
    with _override_extract(
        {
            "reply": "Locked in.",
            "done": True,
            "suggested_name": "Hazel Tokens",
            "archetype_tags": ["voltron", "not_a_real_tag", "aristocrats"],
        }
    ):
        resp = await client.post(
            "/api/v1/decks/extract-keywords",
            json={
                "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
                "bracket": 3,
                "history": [],
                "message": "voltron tokens",
            },
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is True
    assert data["archetype_tags"] == ["voltron", "aristocrats"]
