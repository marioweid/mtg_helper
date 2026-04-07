"""Tests for AI deck building endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.ai_service import (
    _BANGER_SCORE_THRESHOLD,
    _compute_highlight_reasons,
)
from mtg_helper.services.deck_service import STAGES
from mtg_helper.services.retrieval_service import RetrievedCard
from tests.conftest import (
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)


def _make_candidate(
    signals: list[str],
    score: float,
    uid: UUID | None = None,
) -> RetrievedCard:
    """Build a minimal RetrievedCard for unit tests."""
    return RetrievedCard(
        id=uid or UUID("aaaaaaaa-0000-0000-0000-000000000000"),
        scryfall_id=uid or UUID("aaaaaaaa-0000-0000-0000-000000000000"),
        name="Test Card",
        mana_cost="{1}",
        cmc=Decimal("1"),
        type_line="Instant",
        oracle_text="Draw a card.",
        color_identity=[],
        image_uri=None,
        tags=[],
        edhrec_rank=None,
        power=None,
        toughness=None,
        rarity="common",
        score=score,
        signals=signals,
    )


def _make_ai_client(response_text: str = "[]") -> MagicMock:
    """Build a mock OpenAI client (used for embeddings and chat)."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = response_text

    response = MagicMock()
    response.choices = [choice]

    emb_item = MagicMock()
    emb_item.embedding = [0.0] * 1536
    emb_item.index = 0
    emb_response = MagicMock()
    emb_response.data = [emb_item]

    ai = MagicMock()
    ai.chat = MagicMock()
    ai.chat.completions = MagicMock()
    ai.chat.completions.create = AsyncMock(return_value=response)
    ai.embeddings = MagicMock()
    ai.embeddings.create = AsyncMock(return_value=emb_response)
    return ai


async def _create_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "AI Test Deck"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


# ── build_stage ───────────────────────────────────────────────────────────────


async def test_build_stage_returns_200_with_valid_structure(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client()

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stage"] == STAGES[0]
    assert data["stage_number"] == 1
    assert data["total_stages"] > 0
    assert isinstance(data["suggestions"], list)
    assert isinstance(data["unresolved"], list)


async def test_build_stage_advances_deck_stage(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client()

    await client.post(f"/api/v1/decks/{deck_id}/build", json={})

    resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["stage"] == STAGES[0]


async def test_build_stage_deck_not_found(client: AsyncClient) -> None:
    app.state.ai_client = _make_ai_client()
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/build",
        json={},
    )
    assert resp.status_code == 404


async def test_build_stage_invalid_stage_returns_422(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client()
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "not_a_valid_stage"},
    )
    assert resp.status_code == 422


async def test_build_stage_suggestion_fields_present(client: AsyncClient) -> None:
    """Each suggestion includes the expected fields from the new CardSuggestion model."""
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client()

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={})
    assert resp.status_code == 200
    for s in resp.json()["data"]["suggestions"]:
        assert "scryfall_id" in s
        assert "name" in s
        assert "category" in s
        assert "reasoning" in s
        assert "synergies" in s
        # New fields from Phase D
        assert "oracle_text" in s
        assert "rarity" in s
        assert "cmc" in s


# ── suggest_cards ─────────────────────────────────────────────────────────────


async def test_suggest_cards_returns_200(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client()

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "give me ramp", "count": 5},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data["suggestions"], list)
    assert isinstance(data["unresolved"], list)


# ── chat_about_deck ───────────────────────────────────────────────────────────


async def test_chat_about_deck_returns_reply(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client("This is a great commander for a token strategy!")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat",
        json={"message": "What do you think?"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "token" in data["reply"].lower()
    assert data["suggestions"] == []


async def test_chat_returns_suggestions_when_llm_outputs_card_json(client: AsyncClient) -> None:
    """Chat endpoint still uses LLM and returns parsed card suggestions."""
    import json

    deck_id = await _create_deck(client)
    card_json = json.dumps(
        [{"name": "Sol Ring", "category": "ramp", "reasoning": "fast mana", "synergies": []}]
    )
    app.state.ai_client = _make_ai_client(card_json)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat",
        json={"message": "Give me ramp"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data["suggestions"]]
    assert "Sol Ring" in names


# ── feedback boosting ─────────────────────────────────────────────────────────


async def test_feedback_boosting_disabled_build_still_works(client: AsyncClient) -> None:
    """Build works normally even when feedback boosting is off."""
    account_id = await create_test_account(client, "No Boost User")
    deck_id = await create_test_deck(client, owner_id=account_id)

    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "down"},
    )

    app.state.ai_client = _make_ai_client()
    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={})
    assert resp.status_code == 200


# ── _compute_highlight_reasons ────────────────────────────────────────────────


def test_highlight_reasons_banger_two_signals() -> None:
    card = _make_candidate(["semantic", "tag"], score=_BANGER_SCORE_THRESHOLD)
    reasons = _compute_highlight_reasons(card)
    assert reasons is not None
    assert "Strong semantic match" in reasons
    assert "High tag relevance" in reasons


def test_highlight_reasons_banger_all_three_signals() -> None:
    card = _make_candidate(["semantic", "tag", "fts"], score=_BANGER_SCORE_THRESHOLD)
    reasons = _compute_highlight_reasons(card)
    assert reasons is not None
    assert len(reasons) == 3


def test_highlight_reasons_none_for_single_signal() -> None:
    card = _make_candidate(["semantic"], score=_BANGER_SCORE_THRESHOLD)
    assert _compute_highlight_reasons(card) is None


def test_highlight_reasons_none_for_low_score() -> None:
    card = _make_candidate(["semantic", "tag"], score=_BANGER_SCORE_THRESHOLD - 0.001)
    assert _compute_highlight_reasons(card) is None


def test_highlight_reasons_none_for_empty_signals() -> None:
    card = _make_candidate([], score=_BANGER_SCORE_THRESHOLD)
    assert _compute_highlight_reasons(card) is None
