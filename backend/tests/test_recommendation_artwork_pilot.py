"""Real database/API artwork projection, independent of frozen evidence and model input."""

import json

import pytest

from tests import test_recommendation_pilot
from tests.test_recommendation_pilot import path, request

pilot = test_recommendation_pilot.pilot
pytestmark = pytest.mark.asyncio


async def test_artwork_enriches_source_status_and_run_without_changing_facts_or_spending(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    card = await db_pool.fetchrow(
        "SELECT id, oracle_id, image_uri FROM cards WHERE name = 'Sol Ring'"
    )
    image = "https://cards.scryfall.io/normal/front/a/b/sol-ring.jpg"
    source_hash = await db_pool.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
    try:
        await db_pool.execute("UPDATE cards SET image_uri = $2 WHERE id = $1", card["id"], image)
        browse = await client.post(path(deck) + "/preview-query", json={"name": "Sol Ring"})
        page = browse.json()["data"]
        assert page["snapshot_hash"] == source_hash and len(transport.calls) == 0
        assert page["cards"][0]["image_uri"] == image
        assert "image_uri" not in page["cards"][0]["facts"]
        generated = await client.post(path(deck) + "/runs", json=request())
        run_id = generated.json()["data"]["id"]
        run = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
        selected = next(c for c in run["candidates"] if c["oracle_id"] == str(card["oracle_id"]))
        assert selected["image_uri"] == image and "image_uri" not in selected["facts"]
        status = (await client.get(path(deck) + "/status")).json()["data"]
        selected = next(
            c for c in status["run"]["candidates"] if c["oracle_id"] == str(card["oracle_id"])
        )
        assert selected["image_uri"] == image and len(transport.calls) == 3
        assert all("image_uri" not in json.dumps(call["input"]) for call in transport.calls)
        frozen = await db_pool.fetchval(
            "SELECT data FROM recommendation_runs WHERE id = $1", generated.json()["data"]["id"]
        )
        assert "image_uri" not in frozen
        await db_pool.execute("UPDATE cards SET image_uri = NULL WHERE id = $1", card["id"])
        missing = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
        selected = next(
            c for c in missing["candidates"] if c["oracle_id"] == str(card["oracle_id"])
        )
        assert selected["image_uri"] is None and selected["facts"] == page["cards"][0]["facts"] | {
            "key": selected["facts"]["key"]
        }
        assert missing["source_hash"] == source_hash and len(transport.calls) == 3
    finally:
        await db_pool.execute(
            "UPDATE cards SET image_uri = $2 WHERE id = $1", card["id"], card["image_uri"]
        )
