"""Pilot-origin planning completion, transactional rollback, and catalog publication."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from mtg_helper.services import oracle_duplicate_repair_service
from mtg_helper.services.new_cards import catalog
from mtg_helper.services.new_cards.discovery import release_history
from tests import test_new_cards_pilot as fixtures
from tests.conftest import SCHEMA_PATH

model = fixtures.model
pilot = fixtures.pilot
pytestmark = pytest.mark.asyncio


async def saved_plans(pilot, db_pool):
    deck, owner, service, cards = pilot
    await service.run(await service.claim(owner, deck))
    await service.plan(owner, deck, UUID(cards[1]["oracle_id"]))
    # Context changed with the first explicit plan: second suggestion must be reassessed.
    await service.run(await service.claim(owner, deck))
    await service.plan(owner, deck, UUID(cards[2]["oracle_id"]))
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM deck_card_plans WHERE deck_id = $1 ORDER BY created_at", deck
        )


async def complete(client, deck, plans, batch):
    base = f"/api/v1/decks/{deck}"
    if batch:
        return await client.post(
            base + "/revisions",
            json={"title": "Experimental additions", "plan_ids": [str(p["id"]) for p in plans]},
        )
    return await client.post(
        base + f"/planned-changes/{plans[-1]['id']}/complete", json={"quantity": 1}
    )


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("change", ["banned", "color", "duplicate", "withdrawn", "commander"])
async def test_completion_revalidates_and_rolls_back_everything(
    pilot, db_pool, client, batch, change
):
    deck, _, _, cards = pilot
    plans = await saved_plans(pilot, db_pool)
    async with db_pool.acquire() as conn:
        target = UUID(cards[2]["oracle_id"])
        if change == "banned":
            await conn.execute(
                'UPDATE cards SET legalities = \'{"commander":"banned"}\' WHERE oracle_id = $1',
                target,
            )
        elif change == "color":
            await conn.execute(
                "UPDATE new_card_catalog SET facts = "
                "jsonb_set(facts, '{color_identity}', '[\"R\"]') WHERE oracle_id = $1",
                target,
            )
        elif change == "duplicate":
            await conn.execute(
                "INSERT INTO deck_cards (deck_id, card_id) VALUES ($1, $2)",
                deck,
                plans[-1]["card_id"],
            )
        elif change == "withdrawn":
            await conn.execute(
                "UPDATE new_card_catalog SET generation = $2 WHERE oracle_id = $1", target, uuid4()
            )
        else:
            await conn.execute(
                "UPDATE decks SET commander_id = $2 WHERE id = $1", deck, plans[-1]["card_id"]
            )
        before = await conn.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", deck)
    response = await complete(client, deck, plans, batch)
    assert response.status_code == 422, response.text
    async with db_pool.acquire() as conn:
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_card_plans WHERE deck_id = $1", deck)
            == 2
        )
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", deck)
            == before
        )
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_revisions WHERE deck_id = $1", deck) == 0
        )
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_snapshots WHERE deck_id = $1", deck) == 0
        )


@pytest.mark.parametrize("batch", [False, True])
async def test_saved_plan_survives_discovery_expiry_and_completes(pilot, db_pool, client, batch):
    deck, owner, service, _ = pilot
    plans = await saved_plans(pilot, db_pool)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE new_card_catalog SET released_at = $1",
            datetime.now(UTC).date() - timedelta(days=61),
        )
    assert (await service.view(owner, deck)).eligible_count == 0
    response = await complete(client, deck, plans, batch)
    assert response.status_code in (200, 201), response.text
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", deck)
        assert count == (2 if batch else 1)


async def test_canonical_repair_preserves_pilot_origin(pilot, db_pool):
    deck, _, _, _ = pilot
    plans = await saved_plans(pilot, db_pool)
    async with db_pool.acquire() as conn:
        original = plans[0]["card_id"]
        await conn.execute("UPDATE cards SET is_canonical = false WHERE id = $1", original)
        await conn.execute(
            "INSERT INTO cards "
            "(scryfall_id, oracle_id, name, type_line, oracle_text, is_canonical) "
            "SELECT $2, oracle_id, name, type_line, oracle_text, true FROM cards WHERE id = $1",
            original,
            uuid4(),
        )
    await oracle_duplicate_repair_service.repair_active_decks(db_pool)
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT card_id, new_cards_origin FROM deck_card_plans WHERE deck_id = $1", deck
        )
    assert len(rows) == 2 and all(row["new_cards_origin"] for row in rows)
    assert original not in {row["card_id"] for row in rows}


async def test_catalog_publication_tombstones_only_discovery_and_rolls_back(pilot, db_pool):
    deck, owner, service, cards = pilot
    plans = await saved_plans(pilot, db_pool)
    async with db_pool.acquire() as conn:
        with pytest.raises(RuntimeError, match="interrupted"):
            async with conn.transaction():
                await catalog.publish(conn, [], {}, datetime.now(UTC))
                raise RuntimeError("interrupted sync")
        assert (await service.view(owner, deck)).eligible_count == 7
        async with conn.transaction():
            await catalog.publish(conn, cards[:1], release_history(cards[:1]), datetime.now(UTC))
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_card_plans WHERE deck_id = $1", deck)
            == 2
        )
        assert (
            await conn.fetchval("SELECT count(*) FROM cards WHERE id = $1", plans[0]["card_id"])
            == 1
        )
    # A withdrawn commander's old facts must not continue to drive new assessments.
    assert (await service.view(owner, deck)).status == "unavailable"


async def test_schema_upgrade_is_idempotent_and_preserves_user_data(pilot, db_pool):
    deck, _, _, _ = pilot
    await saved_plans(pilot, db_pool)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert (
            await conn.fetchval("SELECT count(*) FROM deck_card_plans WHERE deck_id = $1", deck)
            == 2
        )


async def test_old_or_truncated_catalog_cannot_replace_current(pilot, db_pool):
    async with db_pool.acquire() as conn, conn.transaction():
        assert not await catalog.lock_generation(conn, datetime.now(UTC) - timedelta(days=1), 40000)
        with pytest.raises(ValueError, match="shrank"):
            await catalog.lock_generation(conn, datetime.now(UTC), 1)
