"""Assistant turns use current chat context without persistent memory."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from opentelemetry.trace import NoOpTracerProvider

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import assistant_service

pytestmark = pytest.mark.no_db


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    return DeckDetailResponse(
        id=uuid4(),
        name="Current chat deck",
        description="Tokens",
        bracket=3,
        stage="complete",
        commander_id=uuid4(),
        partner_id=None,
        owner_email="assistant@test.local",
        created_at=now,
        updated_at=now,
        cards=[],
    )


async def test_turn_forwards_current_history_without_persistent_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A turn reaches the unified Assistant without querying saved memory."""
    request = CommanderCoachRequest(
        message="Keep this turn focused on tokens.",
        history=[{"role": "user", "content": "Earlier instruction"}],
    )
    expected = CommanderCoachResponse(mode="chat", reply="Current-chat answer")
    run = AsyncMock(return_value=expected)
    monkeypatch.setattr(assistant_service, "run_assistant", run)
    service = assistant_service.AssistantService(
        SimpleNamespace(), NoOpTracerProvider().get_tracer("test")
    )

    result = await service.run(_deck(), request, uuid4())

    assert result.reply == "Current-chat answer"
    assert run.await_args.args[2] == request
    assert "coach_memory_notes" not in CommanderCoachRequest.model_fields
    assert "coach_memory" not in CommanderCoachResponse.model_fields
    assert "memory_updated" not in CommanderCoachResponse.model_fields
