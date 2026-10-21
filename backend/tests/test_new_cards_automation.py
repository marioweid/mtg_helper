"""Acceptance seams for globally shared Commander-Konstellation assessments."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mtg_helper.services.new_cards.service import NewCardsService
from tests.conftest import SCHEMA_PATH, create_test_deck

pytestmark = pytest.mark.asyncio


async def drain(service: NewCardsService) -> None:
    """Run the real one-package worker boundary until its durable queue is empty."""
    while await service.drain_one():
        pass


async def test_ac01_shared_context_is_the_only_provider_input(pilot, model) -> None:
    deck, owner, service, _ = pilot
    await service.start_manual()
    await drain(service)
    assert (await service.view(owner, deck)).assessed_count == 9
    assert len(model.calls) == 2
    assert set(json.loads(model.calls[0]["input"])) == {"commanders", "candidates"}


async def test_ac02_missing_context_does_not_block_other_decks(
    pilot, db_pool, client, model
) -> None:
    deck, owner, service, _ = pilot
    other = UUID(await create_test_deck(client))
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE decks SET commander_id = (SELECT id FROM cards WHERE name = 'Doubling Season') "
            "WHERE id = $1",
            other,
        )
        await conn.execute(
            "DELETE FROM new_card_catalog WHERE oracle_id = "
            "(SELECT oracle_id FROM cards WHERE id = "
            "(SELECT commander_id FROM decks WHERE id = $1))",
            deck,
        )
    await service.start_manual()
    await drain(service)
    assert (await service.view(owner, other)).assessed_count == 9
    assert len(model.calls) == 2


async def test_ac03_worker_drains_all_delta_without_repeat_work(pilot, model) -> None:
    _, _, service, _ = pilot
    await service.start_manual()
    await drain(service)
    assert len(model.calls) == 2
    await service.start_manual()
    await drain(service)
    assert len(model.calls) == 2


async def test_ac04_empty_pool_never_calls_provider(pilot, db_pool, model) -> None:
    _, _, service, _ = pilot
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE new_card_catalog SET released_at = $1",
            datetime.now(UTC).date() - timedelta(days=60),
        )
    await service.start_manual()
    await drain(service)
    assert model.calls == []


async def test_ac05_catalog_publication_activates_automatic_work_once(
    pilot, db_pool, model
) -> None:
    _, _, service, _ = pilot
    await service.configure(True, None)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE new_card_runs SET last_catalog_day = NULL WHERE singleton")
    await service.activate_published_day()
    await drain(service)
    await service.activate_published_day()
    assert len(model.calls) == 2


async def test_ac06_simultaneous_workers_share_one_claim(pilot) -> None:
    _, _, service, _ = pilot
    await service.start_manual()
    first, second = await asyncio.gather(service.drain_one(), service.drain_one())
    assert first and second


async def test_ac07_limit_rejects_the_second_package(pilot, model) -> None:
    _, _, service, _ = pilot
    await service.configure(None, 1)
    await service.start_manual()
    await drain(service)
    assert len(model.calls) == 1


async def test_ac08_disabling_automation_prevents_a_new_claim(pilot, model) -> None:
    _, _, service, _ = pilot
    await service.cancel()
    await service.configure(True, None)
    await service.activate_published_day()
    await service.configure(False, None)
    assert not await service.drain_one()
    assert model.calls == []


async def test_ac09_provider_failure_stays_recorded_until_another_start(pilot, model) -> None:
    deck, owner, service, _ = pilot
    model.status = 500
    await service.start_manual()
    await drain(service)
    result = await service.view(owner, deck)
    assert result.status == "error"
    assert len(model.calls) == 1


async def test_ac10_stale_sources_hide_cached_picks(pilot, db_pool) -> None:
    deck, owner, service, _ = pilot
    await service.start_manual()
    await drain(service)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE new_card_catalog_state SET published_at = now() - interval '3 days'"
        )
    result = await service.view(owner, deck)
    assert result.status == "source_stale" and result.picks == []


async def test_ac11_picks_appear_only_after_the_complete_delta(pilot, model) -> None:
    deck, owner, service, _ = pilot
    await service.start_manual()
    assert await service.drain_one()
    assert (await service.view(owner, deck)).picks == []
    assert await service.drain_one()
    result = await service.view(owner, deck)
    assert result.remaining_count == 0 and len(result.picks) == 8 and len(model.calls) == 2


async def test_ac14_disabled_process_rejects_global_start(pilot, monkeypatch) -> None:
    _, _, service, _ = pilot
    monkeypatch.setattr(
        "mtg_helper.services.new_cards.service.settings.enable_new_cards_worker", False
    )
    with pytest.raises(ValueError, match="disabled"):
        await service.start_manual()


async def test_ac15_real_evaluator_receives_only_evidence_facts(pilot, model) -> None:
    _, _, service, _ = pilot
    await service.start_manual()
    assert await service.drain_one()
    payload = json.loads(model.calls[0]["input"])
    assert payload["commanders"] and payload["candidates"]


async def test_ac16_schema_upgrade_preserves_shared_assessments(pilot, db_pool) -> None:
    _, _, service, _ = pilot
    await service.start_manual()
    await drain(service)
    async with db_pool.acquire() as conn:
        before = await conn.fetchval("SELECT count(*) FROM new_card_shared_assessments")
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert await conn.fetchval("SELECT count(*) FROM new_card_shared_assessments") == before
