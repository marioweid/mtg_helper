"""Real worker shutdown behavior while PostgreSQL delays catalog activation."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import pytest

from mtg_helper.services.new_cards import catalog
from mtg_helper.services.new_cards.discovery import release_history
from mtg_helper.services.new_cards.repository import Owner
from mtg_helper.services.new_cards.service import NewCardsService, NewCardsWorker
from tests.new_cards_fixtures import ModelTransport

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("_trial", range(3))
async def test_shutdown_during_catalog_activation_starts_no_package(
    pilot: tuple[UUID, Owner, NewCardsService, list[dict[str, Any]]],
    db_pool: asyncpg.Pool,
    model: ModelTransport,
    _trial: int,
) -> None:
    _, _, service, _ = pilot
    await service.cancel()
    await service.configure(True)
    worker = NewCardsWorker(service)
    try:
        async with db_pool.acquire() as blocker, blocker.transaction():
            await blocker.execute("SELECT * FROM new_card_runs WHERE singleton FOR UPDATE")
            async with db_pool.acquire() as publisher:
                rows = await publisher.fetch(
                    "SELECT c.*, n.released_at FROM cards c JOIN new_card_catalog n "
                    "USING (oracle_id) WHERE c.is_canonical"
                )
                sources = [
                    dict(row)
                    | {
                        "object": "card",
                        "id": str(row["scryfall_id"]),
                        "oracle_id": str(row["oracle_id"]),
                        "legalities": json.loads(row["legalities"]),
                        "games": ["paper"],
                        "set_type": "expansion",
                        "reprint": False,
                        "released_at": (
                            row["released_at"] or datetime.now(UTC).date() - timedelta(days=500)
                        ).isoformat(),
                    }
                    for row in rows
                ]
                async with publisher.transaction():
                    await catalog.publish(
                        publisher, sources, release_history(sources), datetime.now(UTC)
                    )

            worker.start()
            async with asyncio.timeout(5):
                while True:
                    async with db_pool.acquire() as observer:
                        waiting = await observer.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                            "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                            "AND query LIKE 'SELECT * FROM new_card_runs%FOR UPDATE')"
                        )
                    if waiting:
                        break
                    await asyncio.sleep(0.01)

            stop = asyncio.create_task(worker.stop())
            await asyncio.sleep(0)
            assert not stop.done()
            assert model.calls == []

        await asyncio.wait_for(stop, timeout=5)
    finally:
        await worker.stop()

    assert model.calls == []
