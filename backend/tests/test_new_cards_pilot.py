"""Real PostgreSQL/API workflows with only the external model transport replaced."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from openai import AsyncOpenAI

from mtg_helper.services.new_cards import catalog, evaluator
from mtg_helper.services.new_cards.discovery import release_history
from mtg_helper.services.new_cards.evaluator import NewCardEvaluator
from mtg_helper.services.new_cards.repository import NewCardsError, Owner
from mtg_helper.services.new_cards.service import NewCardsService
from tests.conftest import create_test_account, create_test_deck

pytestmark = pytest.mark.asyncio


class ModelTransport:
    def __init__(self):
        self.calls = []
        self.status = 200

    def handle(self, request):
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
def model(monkeypatch):
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
async def pilot(client, db_pool, model):
    deck_id = UUID(await create_test_deck(client))
    async with db_pool.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
        )
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


def path(deck_id):
    return f"/api/v1/decks/{deck_id}/new-cards"


async def test_read_is_free_analyze_is_bounded_and_rejects_count(pilot, client, model, db_pool):
    deck, owner, service, _ = pilot
    initial = await service.view(owner, deck)
    assert initial.remaining_count == initial.eligible_count == 9
    assert initial.assessed_count == 0 and initial.status == "idle"
    assert model.calls == []
    response = await client.post(path(deck) + "/analyze")
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "running"
    after = (await client.get(path(deck))).json()["data"]
    assert (after["assessed_count"], after["remaining_count"], len(after["picks"])) == (8, 1, 7)
    assert len(model.calls) == 1
    assert model.calls[0]["store"] is False
    assert model.calls[0]["reasoning"] == {"effort": "low"}
    assert model.calls[0]["max_output_tokens"] == 7000
    await client.post(path(deck) + "/analyze")
    await client.post(path(deck) + "/analyze")
    assert len(model.calls) == 2
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", deck) == 0
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_card_plans WHERE deck_id = $1", deck)
            == 0
        )


async def test_owner_checks_every_route_even_cached(pilot, client, model):
    deck, owner, service, cards = pilot
    work = await service.claim(owner, deck)
    await service.run(work)
    await create_test_account(client, "Foreign")
    oracle = cards[1]["oracle_id"]
    for method, suffix in [
        ("GET", ""),
        ("POST", "/analyze"),
        ("POST", f"/{oracle}/plan"),
        ("POST", f"/{oracle}/dismiss"),
        ("DELETE", f"/{oracle}/dismiss"),
    ]:
        response = await client.request(method, path(deck) + suffix)
        assert response.status_code == 404
    assert len(model.calls) == 1


async def test_dismiss_undo_and_planning_are_explicit_idempotent(pilot, client, db_pool):
    deck, owner, service, cards = pilot
    work = await service.claim(owner, deck)
    await service.run(work)
    oracle = cards[1]["oracle_id"]
    await client.post(path(deck) + f"/{oracle}/dismiss")
    dismissed = await service.view(owner, deck)
    assert dismissed.dismissed_count == 1 and dismissed.eligible_count == 8
    await client.delete(path(deck) + f"/{oracle}/dismiss")
    assert (await service.view(owner, deck)).dismissed_count == 0
    responses = await asyncio.gather(
        *[client.post(path(deck) + f"/{oracle}/plan") for _ in range(2)]
    )
    assert [r.status_code for r in responses] == [200, 200]
    async with db_pool.acquire() as conn:
        plans = await conn.fetch("SELECT * FROM deck_card_plans WHERE deck_id = $1", deck)
        assert len(plans) == 1 and plans[0]["new_cards_origin"] and plans[0]["quantity"] == 1
        assert await conn.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", deck) == 0
    response = await service.view(owner, deck)
    assert response.eligible_count == 8 and response.assessed_count == 0 and response.stale
    next_work = await service.claim(owner, deck)
    assert all(card["name"] != "New 1" for card in next_work.request.support.values())
    assert next_work.request.context["planned_changes"][0]["name"] == "New 1"


@pytest.mark.parametrize("change", ["quantity", "notes", "preference", "goal", "rules"])
async def test_context_changes_hide_cache_without_relying_on_updated_at(pilot, db_pool, change):
    deck, owner, service, cards = pilot
    await service.run(await service.claim(owner, deck))
    async with db_pool.acquire() as conn:
        if change == "quantity":
            await conn.execute(
                "INSERT INTO deck_cards (deck_id, card_id, quantity) "
                "SELECT $1, id, 2 FROM cards WHERE name = 'Sol Ring'",
                deck,
            )
        elif change == "notes":
            await conn.execute(
                "INSERT INTO deck_coach_memory (deck_id, account_id, notes) "
                "VALUES ($1, $2, 'No infinite combos')",
                deck,
                owner.account_id,
            )
        elif change == "preference":
            await conn.execute(
                "INSERT INTO preferences (account_id, preference_type, description) "
                "VALUES ($1, 'general', 'No infinite combos')",
                owner.account_id,
            )
        elif change == "goal":
            await conn.execute("UPDATE decks SET description = 'New goal' WHERE id = $1", deck)
        else:
            await conn.execute(
                "UPDATE new_card_catalog SET facts = "
                "jsonb_set(facts, '{oracle_text}', '\"Corrected rules\"') "
                "WHERE oracle_id = $1",
                UUID(cards[1]["oracle_id"]),
            )
    response = await service.view(owner, deck)
    assert response.stale
    assert response.assessed_count == (7 if change == "rules" else 0)
    assert all(p.name != "New 1" for p in response.picks)


async def test_live_filters_expiry_legality_avoid_and_physical_identity(pilot, db_pool):
    deck, owner, service, cards = pilot
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE new_card_catalog SET released_at = $2 WHERE oracle_id = $1",
            UUID(cards[0]["oracle_id"]),
            datetime.now(UTC).date() - timedelta(days=60),
        )
        await conn.execute(
            "UPDATE new_card_catalog SET released_at = $2 WHERE oracle_id = $1",
            UUID(cards[1]["oracle_id"]),
            datetime.now(UTC).date() + timedelta(days=1),
        )
        await conn.execute(
            'UPDATE cards SET legalities = \'{"commander":"banned"}\' WHERE oracle_id = $1',
            UUID(cards[2]["oracle_id"]),
        )
        await conn.execute(
            "INSERT INTO preferences (account_id, preference_type, card_id) "
            "SELECT $1, 'avoid_card', id FROM cards WHERE oracle_id = $2",
            owner.account_id,
            UUID(cards[3]["oracle_id"]),
        )
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id) "
            "SELECT $1, id FROM cards WHERE oracle_id = $2",
            deck,
            UUID(cards[4]["oracle_id"]),
        )
        await conn.execute(
            "UPDATE cards SET color_identity = ARRAY['R'] WHERE oracle_id = $1",
            UUID(cards[5]["oracle_id"]),
        )
    assert (await service.view(owner, deck)).eligible_count == 3


async def test_durable_account_lease_blocks_duplicates_and_other_decks(pilot, db_pool, client):
    deck, owner, service, _ = pilot
    works = await asyncio.gather(service.claim(owner, deck), service.claim(owner, deck))
    assert sum(work is not None for work in works) == 1
    other = UUID(await create_test_deck(client, name="Other"))
    with pytest.raises(NewCardsError, match="Another deck"):
        await NewCardsService(db_pool, NewCardEvaluator("test")).claim(owner, other)
    async with db_pool.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT calls FROM new_card_jobs WHERE account_id = $1", owner.account_id
            )
            == 1
        )


async def test_expired_worker_cannot_overwrite_newer_results(pilot, db_pool):
    deck, owner, service, _ = pilot
    old = await service.claim(owner, deck)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE new_card_jobs SET lease_until = now() - interval '1 second'")
    assert (await service.view(owner, deck)).status == "error"
    new = await service.claim(owner, deck)
    await service.run(new)
    before = await service.view(owner, deck)
    await service.run(old)
    after = await service.view(owner, deck)
    assert before == after


async def test_failures_preserve_cache_no_retries_and_quota_is_durable(pilot, db_pool, model):
    deck, owner, service, _ = pilot
    await service.run(await service.claim(owner, deck))
    model.status = 500
    await service.run(await service.claim(owner, deck))
    view = await service.view(owner, deck)
    assert view.status == "error" and view.assessed_count == 8
    assert len(model.calls) == 2
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE new_card_jobs SET calls = 30 WHERE account_id = $1", owner.account_id
        )
    with pytest.raises(NewCardsError, match="Daily") as error:
        await service.claim(owner, deck)
    assert error.value.status == 429
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE new_card_jobs SET quota_day = quota_day - 1")
    assert await service.claim(owner, deck) is not None


async def test_context_changed_during_call_is_not_published(pilot, db_pool):
    deck, owner, service, _ = pilot
    work = await service.claim(owner, deck)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE decks SET description = 'Changed goal' WHERE id = $1", deck)
    await service.run(work)
    result = await service.view(owner, deck)
    assert result.assessed_count == 0 and result.status == "error"
    assert "changed" in result.error


async def test_unavailable_catalog_does_not_claim_or_call_model(pilot, db_pool, model, client):
    deck, _, _, _ = pilot
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE new_card_catalog_state")
    assert (await client.get(path(deck))).json()["data"]["status"] == "unavailable"
    assert (await client.post(path(deck) + "/analyze")).status_code == 503
    assert model.calls == []


async def test_partner_identity_and_pending_cut_evidence(pilot, db_pool, client):
    deck, owner, service, cards = pilot
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE cards SET color_identity = ARRAY['U'] WHERE oracle_id = $1",
            UUID(cards[7]["oracle_id"]),
        )
        await conn.execute(
            "UPDATE new_card_catalog SET facts = "
            "jsonb_set(facts, '{color_identity}', '[\"U\"]') WHERE oracle_id = $1",
            UUID(cards[7]["oracle_id"]),
        )
    assert (await service.view(owner, deck)).eligible_count == 8
    async with db_pool.acquire() as conn:
        # Exercise identity union independently of the partner selection UI.
        await conn.execute(
            "UPDATE decks SET partner_id = "
            "(SELECT id FROM cards WHERE name = 'Rhystic Study') WHERE id = $1",
            deck,
        )
        ring = await conn.fetchrow("SELECT * FROM cards WHERE name = 'Sol Ring'")
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id) VALUES ($1, $2)", deck, ring["id"]
        )
    assert (await service.view(owner, deck)).eligible_count == 9
    response = await client.post(
        f"/api/v1/decks/{deck}/planned-changes",
        json={"card_scryfall_id": str(ring["scryfall_id"]), "direction": "cut", "quantity": 1},
    )
    assert response.status_code == 201
    work = await service.claim(owner, deck)
    cut = next(c for c in work.request.support.values() if c["name"] == "Sol Ring")
    assert cut["pending_cut"] and cut["quantity"] == 1


async def test_read_only_cache_rejects_future_planning_and_oversized_notes(pilot, db_pool, client):
    deck, owner, service, cards = pilot
    response = await client.post(path(deck) + f"/{cards[0]['oracle_id']}/plan")
    assert response.status_code == 409
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE decks SET description = $2 WHERE id = $1", deck, "x" * 180001)
    response = await client.post(path(deck) + "/analyze")
    assert response.status_code == 422
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM new_card_jobs") == 0
    assert (await service.view(owner, deck)).assessed_count == 0


async def test_source_publication_waits_for_guarded_plan_transaction(pilot, db_pool):
    entered = asyncio.Event()

    async def writer():
        async with db_pool.acquire() as conn, conn.transaction():
            entered.set()
            return await catalog.lock_generation(conn, datetime.now(UTC), 40000)

    async with db_pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
        task = asyncio.create_task(writer())
        await entered.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
    assert await asyncio.wait_for(task, timeout=2)
