"""Regression tests: assistant tools must not abort the run on oversized lists.

Root cause: when the model called ``inspect_deck_cards``/``check_game_changers``
with more names than the tool bound allows, the underlying service raised a plain
``ValueError`` *inside the tool body*. pydantic-ai 1.71 propagates tool-body
exceptions out of ``Agent.run``, so ``run_assistant`` returned its generic fallback
("I couldn't complete a verified answer...") for every follow-up turn that made such
a call. Fix: bound the tool arguments in the schema (validation rejects with a
retry prompt) and raise ``ModelRetry`` as a second line of defense.

These tests pin the tool layer: an over-limit call must become a ``ModelRetry``
(retryable by the model), never reach the service's ``ValueError`` guard, and the
advertised tool schema must carry the max-length bound.
"""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.models.test import TestModel

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services import mtg_assistant
from mtg_helper.services.mtg_assistant import AssistantDeps

pytestmark = pytest.mark.no_db

_NINE_NAMES = [f"Card {index}" for index in range(9)]
_ELEVEN_NAMES = [f"Card {index}" for index in range(11)]


def _card(name: str) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="A test creature.",
        color_identity=["B", "G"],
        image_uri=None,
        rarity="common",
        quantity=1,
        added_by="user",
        ai_reasoning=None,
    )


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Bound Test Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["B", "G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Test Commander",
            oracle_text="Test commander.",
            color_identity=["B", "G"],
        ),
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        cards=[_card("Food Engine"), _card("Medium Value Card")],
    )


def _ctx(deps: AssistantDeps) -> SimpleNamespace:
    # The assistant tools only touch ctx.deps.allow_tool() before the bound guard.
    return SimpleNamespace(deps=deps, model=TestModel())


def _deps() -> AssistantDeps:
    return AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck())


async def test_inspect_deck_cards_raises_model_retry_above_eight_names() -> None:
    ctx = _ctx(_deps())

    with pytest.raises(ModelRetry, match="at most 8 card names"):
        await mtg_assistant.inspect_deck_cards(ctx, _NINE_NAMES)


async def test_inspect_deck_cards_never_reaches_service_above_eight_names() -> None:
    ctx = _ctx(_deps())
    with patch.object(
        mtg_assistant, "inspect_deck_cards_service", new=AsyncMock(return_value=None)
    ) as service:
        with pytest.raises(ModelRetry):
            await mtg_assistant.inspect_deck_cards(ctx, _NINE_NAMES)
    service.assert_not_awaited()


async def test_check_game_changers_raises_model_retry_above_ten_names() -> None:
    ctx = _ctx(_deps())

    with pytest.raises(ModelRetry, match="at most 10 card names"):
        await mtg_assistant.check_game_changers(ctx, _ELEVEN_NAMES)


async def test_check_game_changers_never_reaches_service_above_ten_names() -> None:
    ctx = _ctx(_deps())
    with patch.object(
        mtg_assistant, "check_game_changers_service", new=AsyncMock(return_value=None)
    ) as service:
        with pytest.raises(ModelRetry):
            await mtg_assistant.check_game_changers(ctx, _ELEVEN_NAMES)
    service.assert_not_awaited()
