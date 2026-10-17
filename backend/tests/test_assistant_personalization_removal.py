"""Assistant provider requests contain only the current deck and chat context."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import asyncpg
import pytest
from opentelemetry.trace import NoOpTracerProvider
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestParameters, ModelSettings
from pydantic_ai.models.test import TestModel

from mtg_helper.models.ai import CommanderCoachRequest, DeckDoctorResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import assistant_service, mtg_assistant
from mtg_helper.services.agents import deck_doctor_agent

pytestmark = pytest.mark.no_db

_SAVED_NOTE = "SAVED-MEMORY-SENTINEL"


class CapturingModel(TestModel):
    """Deterministic provider seam that retains the requests real orchestration sends."""

    requests: list[list[ModelMessage]]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.requests = []

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self.requests.append(messages)
        return await super().request(messages, model_settings, model_request_parameters)


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


async def test_assistant_forwards_chat_history_and_progress_without_saved_memory() -> None:
    """A real turn sends current-chat content but never a saved-memory sentinel."""
    model = CapturingModel(
        call_tools=[], custom_output_args={"mode": "chat", "reply": "Current-chat answer"}
    )
    request = CommanderCoachRequest(
        message="Remember this only for this chat.",
        history=[{"role": "user", "content": "Earlier instruction"}],
    )
    progress: list[str] = []

    async def record(event: str, _message: str) -> None:
        progress.append(event)

    service = assistant_service.AssistantService(
        cast(asyncpg.Pool, None), NoOpTracerProvider().get_tracer("test")
    )
    with mtg_assistant.get_agent().override(model=model):
        result = await service.run(_deck(), request, uuid4(), progress=record)

    captured = "\n".join(str(messages) for messages in model.requests)
    assert result.reply == "Current-chat answer"
    assert "Earlier instruction" in captured
    assert "Remember this only for this chat." in captured
    assert _SAVED_NOTE not in captured
    assert progress == [
        "assistant_routing",
        "assistant_routed",
        "assistant_thinking",
        "assistant_grounding",
    ]


async def test_remember_and_forget_are_ordinary_chat_and_doctor_has_no_saved_memory() -> None:
    """Neither Assistant route gives memory commands or saved notes special meaning."""
    assistant_model = CapturingModel(
        call_tools=[], custom_output_args={"mode": "chat", "reply": "Normal answer"}
    )
    doctor_model = CapturingModel(
        call_tools=[],
        custom_output_args={"summary": "Deck review", "game_plan": "Play tokens."},
    )
    deck = _deck()

    with mtg_assistant.get_agent().override(model=assistant_model):
        for message in ("remember use more removal", "forget the removal instruction"):
            response = await mtg_assistant.run_assistant(
                cast(asyncpg.Pool, None),
                deck,
                CommanderCoachRequest(message=message),
                account_id=uuid4(),
            )
            assert response.reply == "Normal answer"
    with deck_doctor_agent._get_agent().override(model=doctor_model):
        doctor = await deck_doctor_agent.doctor_deck(cast(asyncpg.Pool, None), deck)

    assistant_payloads = "\n".join(str(messages) for messages in assistant_model.requests)
    doctor_payloads = "\n".join(str(messages) for messages in doctor_model.requests)
    assert "remember use more removal" in assistant_payloads
    assert "forget the removal instruction" in assistant_payloads
    assert _SAVED_NOTE not in assistant_payloads
    assert _SAVED_NOTE not in doctor_payloads
    assert doctor == DeckDoctorResponse(summary="Deck review", game_plan="Play tokens.")
