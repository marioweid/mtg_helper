"""Assay session contracts for independent assistant turn traces."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from mtg_helper import observability
from mtg_helper.auth import get_current_account
from mtg_helper.config import Settings
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.ai import CoachMemoryResponse, CommanderCoachRequest
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.observability import assistant_turn
from mtg_helper.routers import ai
from mtg_helper.services import coach_memory_service, deck_service, mtg_assistant

pytestmark = pytest.mark.no_db


def _text(span: ReadableSpan, key: str) -> str:
    value = (span.attributes or {}).get(key)
    assert isinstance(value, str)
    return value


def _trace_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.trace_id


def test_conversation_id_is_validated_and_defaults_to_a_fresh_chat() -> None:
    first = CommanderCoachRequest()
    second = CommanderCoachRequest()
    assert first.conversation_id != second.conversation_id
    with pytest.raises(ValidationError):
        CommanderCoachRequest(conversation_id="not-a-uuid")


async def test_session_groups_turns_without_inheriting_http_trace() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    account, deck, conversation = uuid4(), uuid4(), uuid4()
    try:
        with tracer.start_as_current_span("HTTP request"):
            for message in ("First question", "Follow-up"):
                with assistant_turn(
                    tracer,
                    account_id=account,
                    deck_id=deck,
                    conversation_id=conversation,
                    message=message,
                ) as turn:
                    await asyncio.sleep(0)
                    turn.set_reply("A reply")
        spans = exporter.get_finished_spans()
        turns = [s for s in spans if s.name == "assistant.turn"]
        assert len(turns) == 2
        assert _trace_id(turns[0]) != _trace_id(turns[1])
        assert all(s.parent is None for s in turns)
        assert _text(turns[0], "session.id") == _text(turns[1], "session.id")
        assert all(str(account) not in _text(s, "session.id") for s in turns)
        inputs = [json.loads(_text(s, "gen_ai.input.messages")) for s in turns]
        assert [value[0]["parts"][0]["content"] for value in inputs] == [
            "First question",
            "Follow-up",
        ]
        assert all("A reply" in _text(s, "gen_ai.output.messages") for s in turns)
    finally:
        provider.shutdown()


@dataclass
class SessionApp:
    app: FastAPI
    client: httpx.AsyncClient
    provider: TracerProvider
    exporter: InMemorySpanExporter
    deck_id: UUID
    account: AccountResponse

    async def turns(self) -> list[ReadableSpan]:
        assert await asyncio.to_thread(self.provider.force_flush)
        return [s for s in self.exporter.get_finished_spans() if s.name == "assistant.turn"]


@pytest.fixture
async def session_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SessionApp]:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr(observability, "_ReportingAssayExporter", lambda *_: exporter)
    app = FastAPI()
    app.include_router(ai.router, prefix="/api/v1")
    app.state.db_pool = None
    app.state.coach_jobs = {}
    now = datetime.now(UTC)
    account = AccountResponse(
        id=uuid4(), display_name="Tester", email="test@example.com", created_at=now
    )
    deck = DeckDetailResponse(
        id=uuid4(),
        name="Test deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=uuid4(),
        partner_id=None,
        owner_email=account.email,
        created_at=now,
        updated_at=now,
        cards=[],
    )
    app.dependency_overrides[get_current_account] = lambda: account
    monkeypatch.setattr(deck_service, "get_deck", AsyncMock(return_value=deck))
    memory = CoachMemoryResponse(deck_id=deck.id, account_id=account.id, notes="Keep Sol Ring")
    monkeypatch.setattr(coach_memory_service, "get_memory", AsyncMock(return_value=memory))
    settings = Settings(
        _env_file=None,
        database_url="unused",
        openai_api_key="test",
        assay_endpoint="http://unused.test",
        assay_api_key="asy_test",
        assay_application="mtg",
    )
    provider = observability.configure_assay(app, settings)
    assert provider is not None
    model = TestModel(call_tools=[], custom_output_args={"mode": "chat", "reply": "Test answer"})
    try:
        with mtg_assistant.get_agent().override(model=model):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                yield SessionApp(
                    app=app,
                    client=client,
                    provider=provider,
                    exporter=exporter,
                    deck_id=deck.id,
                    account=account,
                )
    finally:
        await observability.shutdown_assay(app)


async def test_sync_assistant_turns_share_session_and_capture_only_current_content(
    session_app: SessionApp,
) -> None:
    chat = session_app
    conversation = str(uuid4())
    path = f"/api/v1/decks/{chat.deck_id}/coach"
    for prompt in ("Hello", "Any more advice?"):
        response = await chat.client.post(
            path,
            json={
                "conversation_id": conversation,
                "message": prompt,
                "history": [{"role": "user", "content": "Earlier question"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["reply"] == "Test answer"
    turns = await chat.turns()
    assert len(turns) == 2
    assert _text(turns[0], "session.id") == _text(turns[1], "session.id")
    assert _trace_id(turns[0]) != _trace_id(turns[1])
    for turn in turns:
        assert turn.parent is None
        assert "Earlier question" not in _text(turn, "gen_ai.input.messages")
        assert "Test answer" in _text(turn, "gen_ai.output.messages")
        models = [
            s
            for s in chat.exporter.get_finished_spans()
            if _trace_id(s) == _trace_id(turn)
            and (s.attributes or {}).get("gen_ai.operation.name") == "chat"
        ]
        assert models
        assert all(_text(s, "gen_ai.conversation.id") == _text(turn, "session.id") for s in models)
    http_roots = [
        s
        for s in chat.exporter.get_finished_spans()
        if s.parent is None and s.name != "assistant.turn"
    ]
    assert http_roots
    assert all("session.id" not in (s.attributes or {}) for s in http_roots)


@pytest.mark.parametrize("message", ["Hello", "What do you have in memory?"])
async def test_background_turn_completes_after_start_response(
    session_app: SessionApp,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    chat = session_app
    started_work, release = asyncio.Event(), asyncio.Event()
    memory = CoachMemoryResponse(deck_id=chat.deck_id, account_id=chat.account.id, notes="Sol Ring")

    async def delayed_memory(*args: object) -> CoachMemoryResponse:
        started_work.set()
        await release.wait()
        return memory

    monkeypatch.setattr(coach_memory_service, "get_memory", delayed_memory)
    path = f"/api/v1/decks/{chat.deck_id}/coach"
    response = await chat.client.post(path + "/start", json={"message": message})
    assert response.status_code == 200
    await asyncio.wait_for(started_work.wait(), timeout=2)
    assert await chat.turns() == []
    release.set()
    job_id = response.json()["data"]["job_id"]
    stream = await asyncio.wait_for(chat.client.get(f"{path}/{job_id}/stream"), timeout=3)
    assert "event: done" in stream.text
    turns = await chat.turns()
    assert len(turns) == 1
    assert turns[0].parent is None
    assert message in _text(turns[0], "gen_ai.input.messages")
    assert _text(turns[0], "gen_ai.output.messages")
    if message.startswith("What"):
        assert "Sol Ring" in _text(turns[0], "gen_ai.output.messages")
    assert "event: progress" in stream.text


async def test_background_failure_records_failed_turn(
    session_app: SessionApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = session_app
    monkeypatch.setattr(
        coach_memory_service, "get_memory", AsyncMock(side_effect=RuntimeError("offline"))
    )
    path = f"/api/v1/decks/{chat.deck_id}/coach"
    response = await chat.client.post(path + "/start", json={"message": "Hello"})
    job_id = response.json()["data"]["job_id"]
    stream = await asyncio.wait_for(chat.client.get(f"{path}/{job_id}/stream"), timeout=3)
    assert "event: failed" in stream.text
    turns = await chat.turns()
    assert len(turns) == 1
    assert turns[0].status.is_ok is False
    assert "gen_ai.output.messages" not in (turns[0].attributes or {})


async def test_unauthorized_deck_and_invalid_conversation_never_create_turn(
    session_app: SessionApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = session_app
    path = f"/api/v1/decks/{chat.deck_id}/coach"
    invalid = await chat.client.post(path, json={"conversation_id": "bad", "message": "Hello"})
    assert invalid.status_code == 422
    monkeypatch.setattr(deck_service, "get_deck", AsyncMock(return_value=None))
    for suffix in ("", "/start"):
        denied = await chat.client.post(path + suffix, json={"message": "Hello"})
        assert denied.status_code == 404
    assert await chat.turns() == []


async def test_sessions_isolate_accounts_decks_and_parallel_chats(
    session_app: SessionApp,
) -> None:
    chat = session_app
    tracer = chat.provider.get_tracer("test")
    account, deck, conversation = uuid4(), uuid4(), uuid4()

    async def run(owner: UUID, deck_id: UUID, conversation_id: UUID) -> None:
        with assistant_turn(
            tracer,
            account_id=owner,
            deck_id=deck_id,
            conversation_id=conversation_id,
            message="Question",
        ) as turn:
            await asyncio.sleep(0)
            with tracer.start_as_current_span(
                "child", attributes={"gen_ai.operation.name": "chat"}
            ):
                turn.set_reply("Reply")

    await asyncio.gather(
        run(account, deck, conversation),
        run(uuid4(), deck, conversation),
        run(account, uuid4(), conversation),
        run(account, deck, uuid4()),
    )
    turns = await chat.turns()
    assert len({_text(s, "session.id") for s in turns}) == 4
    for root in turns:
        child = next(
            s
            for s in chat.exporter.get_finished_spans()
            if s.name == "child" and _trace_id(s) == _trace_id(root)
        )
        assert _text(child, "gen_ai.conversation.id") == _text(root, "session.id")
    with pytest.raises(ValueError, match="failed turn"):
        with assistant_turn(
            tracer, account_id=account, deck_id=deck, conversation_id=conversation, message="Fail"
        ):
            raise ValueError("failed turn")
    with tracer.start_as_current_span("outside"):
        pass
    await chat.turns()
    outside = next(s for s in chat.exporter.get_finished_spans() if s.name == "outside")
    assert "session.id" not in (outside.attributes or {})


async def test_assistant_still_works_with_tracing_disabled(session_app: SessionApp) -> None:
    chat = session_app
    await observability.shutdown_assay(chat.app)
    response = await chat.client.post(
        f"/api/v1/decks/{chat.deck_id}/coach", json={"message": "Hello"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["reply"] == "Test answer"
    assert not chat.exporter.get_finished_spans()
