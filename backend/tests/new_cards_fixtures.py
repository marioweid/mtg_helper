"""Shared New Cards fixtures registered before test modules are collected."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from openai import AsyncOpenAI

from mtg_helper.services.new_cards import catalog, evaluator
from mtg_helper.services.new_cards.discovery import release_history
from mtg_helper.services.new_cards.evaluator import NewCardEvaluator
from mtg_helper.services.new_cards.repository import Owner
from mtg_helper.services.new_cards.service import NewCardsService
from tests.conftest import create_test_deck


class ModelTransport:
    """Supply deterministic provider responses while recording the real request payload."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.status = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        payload = json.loads(body["input"])
        support = payload["physical"][0]
        judgments = {}
        for card in payload["candidates"]:
            judgments[card["key"]] = {
                "label": "reject" if card["name"] == "New 0" else "strong",
                "reason": "Fits the supplied physical support",
                "caveat": "Unverified interaction",
                "required_changes": [],
                "evidence": [
                    {
                        "key": item["key"],
                        "field": "oracle_text",
                        "face_index": None,
                        "quote": item["oracle_text"],
                    }
                    for item in (card, support)
                ],
            }
        return httpx.Response(
            self.status,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": body["model"],
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(judgments),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> ModelTransport:
    """Replace only the external model transport, leaving evaluation logic intact."""
    transport = ModelTransport()
    monkeypatch.setattr(
        evaluator,
        "AsyncOpenAI",
        lambda **kwargs: AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport.handle)),
        ),
    )
    return transport


@pytest_asyncio.fixture
async def pilot(
    client: httpx.AsyncClient, db_pool: asyncpg.Pool, model: ModelTransport
) -> tuple[UUID, Owner, NewCardsService, list[dict[str, Any]]]:
    """Publish an owned synthetic deck and released cards against the disposable database."""
    deck_id = UUID(await create_test_deck(client))
    async with db_pool.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
        )
        assert account is not None
        rows = await conn.fetch("SELECT * FROM cards")
        old = (datetime.now(UTC).date() - timedelta(days=500)).isoformat()
        sources = [
            dict(row)
            | {
                "object": "card",
                "id": str(row["scryfall_id"]),
                "oracle_id": str(row["oracle_id"]),
                "legalities": json.loads(row["legalities"]),
                "games": ["paper"],
                "released_at": old,
                "set_type": "expansion",
                "reprint": False,
            }
            for row in rows
        ]
        recent = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        for index in range(9):
            card = {
                "object": "card",
                "id": str(uuid4()),
                "oracle_id": str(uuid4()),
                "name": f"New {index}",
                "color_identity": ["G"],
                "oracle_text": "Draw a card.",
                "type_line": "Instant",
                "legalities": {"commander": "legal"},
                "games": ["paper"],
                "set_type": "expansion",
                "reprint": False,
                "released_at": recent,
            }
            await conn.execute(
                "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, oracle_text, "
                "type_line, legalities, is_canonical) VALUES ($1, $2, $3, $4, $5, $6, $7, true)",
                card["id"],
                card["oracle_id"],
                card["name"],
                card["color_identity"],
                card["oracle_text"],
                card["type_line"],
                json.dumps(card["legalities"]),
            )
            sources.append(card)
        async with conn.transaction():
            await catalog.publish(conn, sources, release_history(sources), datetime.now(UTC))
    owner = Owner(account["id"], account["email"])
    service = NewCardsService(db_pool, NewCardEvaluator("test"))
    return deck_id, owner, service, sources[-9:]
