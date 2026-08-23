"""No-database tests for deterministic Coach memory command routing."""

from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest

from mtg_helper.models.ai import CoachMemoryResponse, CommanderCoachRequest
from mtg_helper.services.coach_memory_service import handle_memory_message

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    "message",
    [
        "I hate counterspells",
        "I prefer Food win conditions; what draw should I add?",
        "Please avoid tutors and suggest three replacements",
        "For Yuna I also want counters other than +1/+1 counters",
    ],
)
async def test_preference_bearing_questions_reach_assistant(message: str) -> None:
    deck_id = uuid4()
    account_id = uuid4()
    memory = CoachMemoryResponse(deck_id=deck_id, account_id=account_id, notes="")
    with patch(
        "mtg_helper.services.coach_memory_service.get_memory",
        AsyncMock(return_value=memory),
    ):
        result = await handle_memory_message(
            cast(asyncpg.Pool, None),
            deck_id,
            account_id,
            CommanderCoachRequest(message=message),
        )

    assert result is None
