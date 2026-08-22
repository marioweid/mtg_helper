"""Tests for AI deck building endpoints."""

from decimal import Decimal
from uuid import UUID

from httpx import AsyncClient

from mtg_helper.services.ai_service import (
    _ALLOWED_CARD_TYPES,
    _ALLOWED_SUBTYPES,
    _BANGER_SCORE_THRESHOLD,
    _canonicalize,
    _compute_highlight_reasons,
    _merge_type_filters,
    _resolve_stage_query,
    _resolve_structured_type_filter,
)
from mtg_helper.services.deck_service import STAGES
from mtg_helper.services.retrieval_service import RetrievedCard, TypeFilter
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
        oracle_id=uid or UUID("aaaaaaaa-0000-0000-0000-000000000000"),
        name="Test Card",
        mana_cost="{1}",
        cmc=Decimal("1"),
        type_line="Instant",
        oracle_text="Draw a card.",
        color_identity=[],
        image_uri=None,
        tags=[],
        token_types=[],
        edhrec_rank=None,
        power=None,
        toughness=None,
        rarity="common",
        price_eur_cents=None,
        score=score,
        signals=signals,
    )


async def _create_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "AI Test Deck"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


# ── structured type filter helpers ────────────────────────────────────────────


def test_canonicalize_drops_unknown_terms() -> None:
    """Unknown values are silently dropped; known values are title-cased and deduped."""
    assert _canonicalize(["creature", "Creature", "wibble"], _ALLOWED_CARD_TYPES) == ["Creature"]


def test_canonicalize_empty_input_returns_empty() -> None:
    assert _canonicalize(None, _ALLOWED_CARD_TYPES) == []
    assert _canonicalize([], _ALLOWED_SUBTYPES) == []


def test_resolve_structured_type_filter_builds_strict_match_all() -> None:
    tf = _resolve_structured_type_filter(["Creature"], ["equipment"])
    assert tf is not None
    assert tf.card_types == ["Creature"]
    assert tf.subtypes == ["Equipment"]
    assert tf.strict is True
    assert tf.match_all_categories is True


def test_resolve_structured_type_filter_empty_returns_none() -> None:
    assert _resolve_structured_type_filter(None, None) is None
    assert _resolve_structured_type_filter([], []) is None
    # All-unknown values also collapse to None.
    assert _resolve_structured_type_filter(["wibble"], ["wobble"]) is None


def test_merge_type_filters_unions_categories_and_propagates_flags() -> None:
    structured = TypeFilter(
        card_types=["Creature"],
        subtypes=["Equipment"],
        strict=True,
        match_all_categories=True,
    )
    parsed = TypeFilter(card_types=["Artifact"], subtypes=[], keywords=["flying"])
    merged = _merge_type_filters(structured, parsed)
    assert merged is not None
    assert set(merged.card_types) == {"Creature", "Artifact"}
    assert merged.subtypes == ["Equipment"]
    assert merged.keywords == ["flying"]
    assert merged.strict is True
    assert merged.match_all_categories is True


# ── build_stage ───────────────────────────────────────────────────────────────


def test_stage_query_uses_stage_defaults_without_archetype_tags() -> None:
    query = _resolve_stage_query("ramp", "tokens matter", [], None)

    assert query == (
        "mana ramp acceleration mana rocks mana dorks tokens matter",
        ["ramp", "fast_mana"],
        False,
        None,
        None,
    )


def test_stage_query_merges_archetype_and_stage_tags_without_duplicates() -> None:
    query = _resolve_stage_query("ramp", None, ["tokens", "ramp"], None)

    assert query == (
        "mana ramp acceleration mana rocks mana dorks",
        ["tokens", "ramp", "fast_mana"],
        True,
        None,
        None,
    )


def test_theme_query_requires_and_normalizes_selected_archetype() -> None:
    query = _resolve_stage_query("theme", "artifact tokens", ["artifact_tokens"], "Artifact-Tokens")

    assert query == (
        "artifact tokens synergy theme artifact tokens",
        ["artifact_tokens"],
        True,
        "artifact_tokens",
        None,
    )


def test_theme_query_rejects_tag_outside_deck_archetypes() -> None:
    query = _resolve_stage_query("theme", "artifact tokens", ["artifact_tokens"], "spellslinger")

    assert query is None


def test_theme_etc_query_excludes_explicit_archetypes() -> None:
    query = _resolve_stage_query("theme", "artifact tokens", ["tokens", "artifacts"], "__etc")

    assert query == (
        "artifact tokens synergy theme commander staples support",
        ["tokens"],
        True,
        None,
        frozenset({"tokens", "artifacts"}),
    )


async def test_build_stage_returns_200_with_valid_structure(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)

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

    await client.post(f"/api/v1/decks/{deck_id}/build", json={})

    resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["stage"] == STAGES[0]


async def test_build_stage_deck_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/build",
        json={},
    )
    assert resp.status_code == 404


async def test_build_stage_invalid_stage_returns_422(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "not_a_valid_stage"},
    )
    assert resp.status_code == 422


async def test_build_stage_suggestion_fields_present(client: AsyncClient) -> None:
    """Each suggestion includes the expected fields from the new CardSuggestion model."""
    deck_id = await _create_deck(client)

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

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "give me ramp", "count": 5},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data["suggestions"], list)
    assert isinstance(data["unresolved"], list)


# ── feedback boosting ─────────────────────────────────────────────────────────


async def test_feedback_boosting_disabled_build_still_works(client: AsyncClient) -> None:
    """Build works normally even when feedback boosting is off."""
    account_id = await create_test_account(client, "No Boost User")
    deck_id = await create_test_deck(client, owner_id=account_id)

    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "down"},
    )

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={})
    assert resp.status_code == 200


# ── _compute_highlight_reasons ────────────────────────────────────────────────


def test_highlight_reasons_banger_two_signals() -> None:
    card = _make_candidate(["tag", "fts"], score=_BANGER_SCORE_THRESHOLD)
    reasons = _compute_highlight_reasons(card)
    assert reasons is not None
    assert "High tag relevance" in reasons
    assert "Strong text match" in reasons


def test_highlight_reasons_banger_known_signals() -> None:
    card = _make_candidate(["tag", "fts", "moxfield"], score=_BANGER_SCORE_THRESHOLD)
    reasons = _compute_highlight_reasons(card)
    assert reasons is not None
    assert reasons == ["High tag relevance", "Strong text match"]


def test_highlight_reasons_none_for_single_signal() -> None:
    card = _make_candidate(["tag"], score=_BANGER_SCORE_THRESHOLD)
    assert _compute_highlight_reasons(card) is None


def test_highlight_reasons_none_for_low_score() -> None:
    card = _make_candidate(["tag", "fts"], score=_BANGER_SCORE_THRESHOLD - 0.001)
    assert _compute_highlight_reasons(card) is None


def test_highlight_reasons_none_for_empty_signals() -> None:
    card = _make_candidate([], score=_BANGER_SCORE_THRESHOLD)
    assert _compute_highlight_reasons(card) is None
