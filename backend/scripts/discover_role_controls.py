"""Offline popularity controls for the completed four-call experiment; no provider requests."""

import asyncio
import hashlib
import json
import os
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.services.recommendations.source import build_catalog
from mtg_helper.services.recommendations.terms import Workflow
from scripts import discover_role_calls as calls
from scripts import discover_role_experiment as prototype
from scripts.deck_recovery_check import DECKS, FIXTURES, freeze, prepare_cases
from scripts.discover_relevance_check import local_database


def global_popularity(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank the same eligible pool by existing popularity, without any overlap-count boost."""
    return sorted(
        cards,
        key=lambda row: (
            row["edhrec_rank"] is None,
            row["edhrec_rank"] or 0,
            row["name"].lower(),
            str(row["oracle_id"]),
        ),
    )


async def controls_for_call(
    conn: asyncpg.Connection,
    call: dict[str, Any],
    output: str,
    context: tuple[dict[str, Any], set[str]],
) -> dict[str, Any]:
    """Compare global ordering on unchanged frozen selections, with and without lane filters."""
    leader, answers = context
    plan = None
    if call["arm"] == "baseline":
        accepted = Workflow(context=call["context"]).accept("plan", output, {})
        criteria = {
            "oracle_tag_ids": [UUID(tag) for tag in accepted["oracle_tag_ids"]],
            "printed_keywords": accepted["printed_keywords"],
        }
    else:
        plan = prototype.validate_plan(output, call["payload"])
        criteria = prototype.flat_criteria(plan)
    cards = await prototype.eligible_pool(conn, leader, criteria)
    result = {
        "flat_popularity": prototype.scored_cards(global_popularity(cards), answers),
        "ranking_input_sha256": calls.digest(
            [(str(card["oracle_id"]), card["edhrec_rank"]) for card in cards]
        ),
    }
    if plan is not None:
        memberships = await prototype.source_memberships(conn, criteria["oracle_tag_ids"])
        union = set().union(
            *[prototype.lane_members(lane, cards, memberships) for lane in plan.lanes]
        )
        filtered = [card for card in cards if str(card["oracle_id"]) in union]
        result["lane_filtered_popularity"] = prototype.scored_cards(
            global_popularity(filtered), answers
        )
    return result


async def run_controls() -> dict[str, Any]:
    """Replay completed selections locally; this module never creates or sends provider work."""
    protocol = json.loads((calls.DESTINATION / "inputs.json").read_text(encoding="utf-8"))
    ledger = json.loads((calls.DESTINATION / "attempts.json").read_text(encoding="utf-8"))
    if calls.digest(protocol) != ledger["protocol_sha256"]:
        raise ValueError("Frozen inputs do not match the spent four-call ledger")
    conn = await asyncpg.connect(local_database(os.environ["DATABASE_URL"]))
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            if await calls.publication(conn) != protocol["source"]:
                raise ValueError("Restore the measured source publication before local replay")
            hashes = {
                key: hashlib.sha256((FIXTURES / f"{key}.txt").read_bytes()).hexdigest()
                for key in DECKS
            }
            if hashes != protocol["fixture_hashes"]:
                raise ValueError("Restore the measured reference fixtures before local replay")
            rows = await conn.fetch(
                "SELECT n.source_facts FROM new_card_catalog n "
                "JOIN new_card_catalog_state s ON s.generation=n.generation"
            )
            catalog = build_catalog(json.loads(row["source_facts"]) for row in rows)
            _, answers = prepare_cases(catalog)
            results = []
            for call in protocol["calls"]:
                attempt = next(
                    a
                    for a in ledger["attempts"]
                    if (a["deck"], a["arm"]) == (call["deck"], call["arm"])
                )
                if attempt.get("status") != "completed":
                    raise ValueError("Incomplete model output is not a successful control")
                leader = catalog.resolve(DECKS[call["deck"]][0])
                if leader is None:
                    raise ValueError("Restore missing commander source facts")
                result = await controls_for_call(
                    conn, call, attempt["output"], (leader, answers[call["deck"]])
                )
                results.append({"deck": call["deck"], "selection": call["arm"]} | result)
            return {
                "source": protocol["source"],
                "paid_calls": 0,
                "runs": results,
                "method": "Post-hoc popularity controls; original paid artifacts unchanged",
            }
    finally:
        await conn.close()


def main() -> None:
    report = asyncio.run(run_controls())
    freeze(calls.DESTINATION / "controls.json", report)
    for row in report["runs"]:
        for arm in ("flat_popularity", "lane_filtered_popularity"):
            if arm in row:
                value = row[arm]
                print(
                    row["deck"],
                    row["selection"],
                    arm,
                    value["reference_hits_at_10"],
                    "hits@10;",
                    value["reference_hits_at_50"],
                    "hits@50",
                )


if __name__ == "__main__":
    main()
