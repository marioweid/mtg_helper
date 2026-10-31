"""Four authorized one-shot term calls; default mode prepares requests without spending."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from openai import APIError

from mtg_helper.services.recommendations import budget, pipeline, provider, terms
from mtg_helper.services.recommendations.service import request_payload
from mtg_helper.services.recommendations.source import Catalog, build_catalog
from scripts import discover_role_experiment as prototype
from scripts.deck_recovery_check import DECKS, FIXTURES, ROOT, freeze, prepare_cases
from scripts.discover_relevance_check import local_database
from scripts.new_cards_data_spike import write_json

DESTINATION = ROOT / "docs/research/discover-relevance/role-experiment"
CALLS = [("yuna", "baseline"), ("yuna", "roles"), ("meren", "roles"), ("meren", "baseline")]
CAP_MICROUSD = 100_000
OUTPUT_LIMIT = 4_000
INPUT_LIMIT = 80_000


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def code_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), Path(prototype.__file__))
    }


def role_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": budget.MODEL,
        "service_tier": "default",
        "instructions": prototype.PROMPT,
        "input": json.dumps(payload, ensure_ascii=False),
        "max_output_tokens": OUTPUT_LIMIT,
        "store": False,
        "reasoning": {"effort": "low"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "strict": True,
                "name": "discover_roles_v1",
                "schema": prototype.RolePlan.model_json_schema(),
            },
        },
    }


def reservation(calls: list[dict[str, Any]]) -> int:
    """Reserve every call conservatively and reject altered or oversized authorizations."""
    if [(call["deck"], call["arm"]) for call in calls] != CALLS:
        raise ValueError("Authorization permits exactly the four frozen deck/arm calls")
    total = 0
    for call in calls:
        request = call["request"]
        if request["model"] != budget.MODEL or request["max_output_tokens"] != OUTPUT_LIMIT:
            raise ValueError("Changed model/output bound; obtain new authorization")
        size = len(json.dumps(request, ensure_ascii=False).encode()) + 2_000
        if size > INPUT_LIMIT or call["input_bound"] != size:
            raise ValueError("Changed or oversized input reservation; do not call a provider")
        total += budget.cost(size, OUTPUT_LIMIT)
    if total > CAP_MICROUSD:
        raise ValueError("Four-call reservation exceeds the authorized $0.10 estimate ceiling")
    return total


async def publication(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT c.source_sha256,t.tag_sha256,c.published_at FROM new_card_catalog_state c "
        "JOIN scryfall_tag_state t ON t.source_sha256=c.source_sha256"
    )
    if row is None:
        raise ValueError("Matching local card/tag publication is required")
    return {key: str(value) for key, value in dict(row).items()}


async def prepare() -> dict[str, Any]:
    """Build provider inputs from commander facts/briefs, never reference-card identities."""
    conn = await asyncpg.connect(local_database(os.environ["DATABASE_URL"]))
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            source = await publication(conn)
            cases = {}
            for key, (name, brief) in DECKS.items():
                row = await conn.fetchrow(
                    "SELECT n.source_facts FROM new_card_catalog n "
                    "JOIN new_card_catalog_state s ON s.generation=n.generation "
                    "WHERE n.source_facts->>'name'=$1",
                    name,
                )
                if row is None:
                    raise ValueError(f"Missing commander facts for {key}; restore local sources")
                leader = json.loads(row["source_facts"])
                catalog = await prototype.source_terms(conn, prose=brief)
                context = {
                    "prose": brief,
                    "strategy_revision": None,
                    "source_hash": source["source_sha256"],
                    "oracle_tags": [tag | {"id": str(tag["id"])} for tag in catalog.oracle_tags],
                    "printed_keywords": catalog.printed_keywords,
                }
                baseline = terms.Workflow(context=context).payload("plan", {})
                fixed = pipeline.check_request("plan", baseline, profile=budget.TERMS_VERSION)
                roles = await prototype.improved_menu(conn, leader, brief)
                cases[key] = {
                    "baseline": {
                        "payload": baseline,
                        "context": context,
                        "request": request_payload("plan", baseline, fixed),
                    },
                    "roles": {"payload": roles, "request": role_request(roles)},
                }
            calls = []
            for key, arm in CALLS:
                call: dict[str, Any] = {"deck": key, "arm": arm} | cases[key][arm]
                call["input_bound"] = (
                    len(json.dumps(call["request"], ensure_ascii=False).encode()) + 2_000
                )
                calls.append(call)
            return {
                "version": "discover-roles-four-call-v1",
                "source": source,
                "fixture_hashes": {
                    key: hashlib.sha256((FIXTURES / f"{key}.txt").read_bytes()).hexdigest()
                    for key in DECKS
                },
                "code_hashes": code_hashes(),
                "calls": calls,
                "reserved_microusd": reservation(calls),
                "cap_microusd": CAP_MICROUSD,
                "pricing": {
                    "input_upper_usd_per_million": 0.25,
                    "output_usd_per_million": 1.2,
                    "checked_utc": "2026-10-29",
                    "url": budget.PRICING_URL,
                },
            }
    finally:
        await conn.close()


def validate_protocol(protocol: dict[str, Any]) -> None:
    """Refuse modified requests/code rather than silently changing the experiment."""
    if protocol["code_hashes"] != code_hashes():
        raise ValueError("Experiment code changed after freezing; do not reuse this authorization")
    if protocol["reserved_microusd"] != reservation(protocol["calls"]):
        raise ValueError("Frozen reservation changed")
    for call in protocol["calls"]:
        if call["arm"] == "roles":
            expected = role_request(call["payload"])
        else:
            fixed = pipeline.check_request("plan", call["payload"], profile=budget.TERMS_VERSION)
            expected = request_payload("plan", call["payload"], fixed)
        if call["request"] != expected:
            raise ValueError("Frozen provider request changed; no call is authorized")


async def run_live(
    protocol: dict[str, Any], path: Path, sender: provider.Provider
) -> dict[str, Any]:
    """Checkpoint each attempt exclusively; stop rather than retry or ignore unknown costs."""
    validate_protocol(protocol)
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "protocol_sha256": digest(protocol),
        "attempts": [],
        "reserved_microusd": protocol["reserved_microusd"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    for call in protocol["calls"]:
        attempt = {"deck": call["deck"], "arm": call["arm"], "state": "attempted"}
        report["attempts"].append(attempt)
        write_json(path, report)
        started = time.perf_counter()
        try:
            receipt = await sender.request(call["request"])
            attempt.update(receipt, state="returned", seconds=time.perf_counter() - started)
            attempt["estimated_cost_microusd"] = budget.usage_cost(
                receipt, (call["input_bound"], OUTPUT_LIMIT)
            )
        except (APIError, TimeoutError, ValueError) as exc:
            attempt.update(error=type(exc).__name__, seconds=time.perf_counter() - started)
            report["stopped"] = (
                "Unknown/provider-failed attempt; no retry or further calls authorized"
            )
        write_json(path, report)
        print(call["deck"], call["arm"], attempt.get("status", attempt.get("error")), flush=True)
        if "stopped" in report:
            break
    return report


async def summarize(protocol: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Resolve hidden answers only after requests; replay every failure without replacement."""
    if report["protocol_sha256"] != digest(protocol):
        raise ValueError("Ledger is not bound to these frozen inputs")
    conn = await asyncpg.connect(local_database(os.environ["DATABASE_URL"]))
    results = []
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            if await publication(conn) != protocol["source"]:
                raise ValueError("Source publication changed; do not score against different facts")
            hashes = {
                key: hashlib.sha256((FIXTURES / f"{key}.txt").read_bytes()).hexdigest()
                for key in DECKS
            }
            if hashes != protocol["fixture_hashes"]:
                raise ValueError(
                    "Reference fixtures changed; do not score against different answers"
                )
            rows = await conn.fetch(
                "SELECT n.source_facts FROM new_card_catalog n "
                "JOIN new_card_catalog_state s ON s.generation=n.generation"
            )
            catalog = build_catalog(json.loads(row["source_facts"]) for row in rows)
            _, answers = prepare_cases(catalog)
            for attempt in report["attempts"]:
                call = next(
                    c
                    for c in protocol["calls"]
                    if (c["deck"], c["arm"]) == (attempt["deck"], attempt["arm"])
                )
                row = {
                    key: attempt.get(key)
                    for key in ("deck", "arm", "status", "seconds", "estimated_cost_microusd")
                }
                try:
                    if attempt.get("status") != "completed":
                        raise ValueError("Provider output did not complete")
                    row.update(await score_attempt(conn, call, attempt["output"], catalog, answers))
                except ValueError as exc:
                    row["validation_error"] = str(exc)
                results.append(row)
        return {
            "source": protocol["source"],
            "attempts": len(report["attempts"]),
            "runs": results,
            "reserved_microusd": protocol["reserved_microusd"],
            "known_cost_microusd": sum(
                a.get("estimated_cost_microusd", 0) for a in report["attempts"]
            ),
            "has_unknown_cost": any("estimated_cost_microusd" not in a for a in report["attempts"]),
        }
    finally:
        await conn.close()


async def score_attempt(
    conn: asyncpg.Connection,
    call: dict[str, Any],
    text: str,
    catalog: Catalog,
    answers: dict[str, set[str]],
) -> dict[str, Any]:
    """Score one validated selection using the same source eligibility as the application."""
    leader = catalog.resolve(DECKS[call["deck"]][0])
    if leader is None:
        raise ValueError("Commander source facts are missing while replaying the frozen call")
    if call["arm"] == "baseline":
        accepted = terms.Workflow(context=call["context"]).accept("plan", text, {})
        criteria = {
            "oracle_tag_ids": [UUID(tag) for tag in accepted["oracle_tag_ids"]],
            "printed_keywords": accepted["printed_keywords"],
        }
        cards = await prototype.eligible_pool(conn, leader, criteria)
        return {
            "criteria": accepted,
            "arms": {"flat_or": prototype.scored_cards(cards, answers[call["deck"]])},
        }
    plan = prototype.validate_plan(text, call["payload"])
    criteria = prototype.flat_criteria(plan)
    cards = await prototype.eligible_pool(conn, leader, criteria)
    memberships = await prototype.source_memberships(conn, criteria["oracle_tag_ids"])
    return prototype.compare_roles(plan, cards, memberships, answers[call["deck"]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    inputs = DESTINATION / "inputs.json"
    if not args.live and not args.summarize:
        protocol = asyncio.run(prepare())
        freeze(inputs, protocol)
        print(
            "Frozen four requests; reserved estimated USD:",
            protocol["reserved_microusd"] / 1_000_000,
        )
        return
    protocol = json.loads(inputs.read_text(encoding="utf-8"))
    ledger = DESTINATION / "attempts.json"
    if args.live:
        from mtg_helper.config import settings

        report = asyncio.run(
            run_live(
                protocol, ledger, provider.Provider(settings.openai_api_key.get_secret_value())
            )
        )
    else:
        report = json.loads(ledger.read_text(encoding="utf-8"))
    summary = asyncio.run(summarize(protocol, report))
    write_json(DESTINATION / "summary.json", summary)
    for row in summary["runs"]:
        print(row["deck"], row["arm"], row.get("validation_error", "valid"))
        for arm, result in row.get("arms", {}).items():
            print(
                arm,
                result["reference_hits_at_10"],
                "hits@10;",
                result["reference_hits_at_50"],
                "hits@50;",
                result["total"],
                "matches",
            )


if __name__ == "__main__":
    main()
