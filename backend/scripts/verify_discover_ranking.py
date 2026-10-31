"""Replay frozen Yuna/Meren selections through production matching, without paid calls or writes."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

import asyncpg

from mtg_helper.services.recommendations.repository import Owner
from mtg_helper.services.recommendations.search_sql import MATCH_SQL
from mtg_helper.services.recommendations.source import build_catalog
from mtg_helper.services.recommendations.strategy_discover import StrategyDiscover
from mtg_helper.services.recommendations.term_queries import Workflow
from scripts.deck_recovery_check import DECKS, FIXTURES, prepare_cases
from scripts.discover_relevance_check import EMPTY_ID, local_database, score
from scripts.discover_role_calls import DESTINATION, digest, publication


async def replay_case(
    conn: asyncpg.Connection,
    matcher: StrategyDiscover,
    call: dict,
    attempt: dict,
    answers: set[str],
) -> dict:
    """Use production validation, matching and response serialization for a frozen selection."""
    key = call["deck"]
    if attempt["status"] != "completed":
        raise ValueError(f"{key}: no completed frozen selection is available")
    context = {
        "prose": call["payload"]["strategy"],
        "strategy_revision": None,
        "source_hash": call["source_hash"],
        **call["payload"],
    }
    draft = Workflow(context=context).accept(
        "plan", json.dumps({"queries": json.loads(attempt["output"])["lanes"]}), {}
    )
    deck = await conn.fetchrow(
        "SELECT $1::uuid AS id,id AS commander_id,oracle_id AS commander_oracle_id,"
        "NULL::uuid AS partner_id FROM cards WHERE is_canonical AND name=$2",
        EMPTY_ID,
        DECKS[key][0],
    )
    if deck is None:
        raise ValueError(f"{key}: canonical commander is missing")
    strategy = await conn.fetchrow("SELECT $1::jsonb AS queries", json.dumps(draft["queries"]))
    assert strategy is not None
    page, total = await matcher._match_rows(
        conn, deck, Owner(EMPTY_ID, "replay@test.local"), strategy, limit=50
    )
    # Full-pool scoring has no pagination; bind the exact-identity slot consecutively.
    query = MATCH_SQL.split(", page AS MATERIALIZED (", 1)[0].replace("$11", "$6")
    query += (
        " SELECT oracle_id FROM eligible "
        "ORDER BY rank_missing,sort_rank,lower(name),oracle_id::text"
    )
    all_rows = [
        dict(row)
        for row in await conn.fetch(
            query,
            strategy["queries"],
            call["payload"]["commanders"][0]["color_identity"],
            [deck["commander_oracle_id"]],
            EMPTY_ID,
            EMPTY_ID,
            None,
        )
    ]
    assert total == len(all_rows)
    return score(all_rows, answers) | {
        "cards": [
            matcher._match(row).model_dump(mode="json")
            | {"reference_hit": str(row["oracle_id"]) in answers}
            for row in page
        ],
        "queries": draft["queries"],
    }


async def verify() -> dict:
    """Keep historical requests/receipts immutable while exercising production matching."""
    protocol = json.loads((DESTINATION / "inputs.json").read_text(encoding="utf-8"))
    ledger = json.loads((DESTINATION / "attempts.json").read_text(encoding="utf-8"))
    if digest(protocol) != ledger["protocol_sha256"]:
        raise ValueError("The preserved requests do not match the completed attempt ledger")
    hashes = {
        key: hashlib.sha256((FIXTURES / f"{key}.txt").read_bytes()).hexdigest() for key in DECKS
    }
    if hashes != protocol["fixture_hashes"]:
        raise ValueError("Restore the frozen reference fixtures before replaying the comparison")
    pool = await asyncpg.create_pool(
        local_database(os.environ["DATABASE_URL"]), min_size=1, max_size=1
    )
    try:
        async with (
            pool.acquire() as conn,
            conn.transaction(isolation="repeatable_read", readonly=True),
        ):
            source = await publication(conn)
            if source != protocol["source"]:
                raise ValueError(
                    "Restore the frozen local publication before replaying this comparison"
                )
            rows = await conn.fetch(
                "SELECT n.source_facts FROM new_card_catalog n "
                "JOIN new_card_catalog_state s ON s.generation=n.generation"
            )
            catalog = build_catalog(json.loads(row["source_facts"]) for row in rows)
            _, answers = prepare_cases(catalog)
            matcher = StrategyDiscover(pool)
            results = {}
            for key in DECKS:
                call = next(
                    c for c in protocol["calls"] if c["deck"] == key and c["arm"] == "roles"
                )
                attempt = next(
                    a for a in ledger["attempts"] if a["deck"] == key and a["arm"] == "roles"
                )
                results[key] = await replay_case(
                    conn,
                    matcher,
                    call | {"source_hash": source["source_sha256"]},
                    attempt,
                    answers[key],
                )
            return {
                "source": source,
                "paid_calls": 0,
                "method": "Frozen selections; production filters/popularity/front-face checks",
                "cases": results,
            }
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(verify())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for key, row in result["cases"].items():
        print(
            key,
            row["reference_hits_at_10"],
            "hits@10;",
            row["reference_hits_at_50"],
            "hits@50;",
            row["reference_hits_in_pool"],
            "targets in",
            row["total"],
            "matches",
        )


if __name__ == "__main__":
    main()
