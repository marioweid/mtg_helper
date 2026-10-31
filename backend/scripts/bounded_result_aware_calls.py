"""Fresh v3 four-call evaluation; reuse read-only observations, never earlier authorizations."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
from openai import APIError

from mtg_helper.services.recommendations import budget, pipeline, provider, term_selection
from mtg_helper.services.recommendations.profiles import Stage
from mtg_helper.services.recommendations.service import request_payload
from scripts import result_aware_calls as archive
from scripts import result_aware_eval as evaluation
from scripts.deck_recovery_check import DECKS, ROOT, freeze
from scripts.discover_relevance_check import local_database
from scripts.discover_role_calls import digest
from scripts.new_cards_data_spike import write_json

DESTINATION = ROOT / "docs/research/discover-bounded-result-aware"
PROTOCOL_FILE = DESTINATION / "README.md"
CALLS = [("yuna", "baseline"), ("meren", "baseline"), ("meren", "refined"), ("yuna", "refined")]
INPUT_BOUNDS = {"baseline": 80_000, "refined": 120_000}
OUTPUT_BOUND = 4_000
CAP_MICROUSD = 150_000
VERSION = "bounded-result-aware-four-call-v1"
CONTRIBUTIONS = {
    "engine": ("direct", 3),
    "requested": ("direct", 2),
    "generic": ("support", 1),
    "dependency": ("conditional", 0),
    "uncertain": ("uncertain", 0),
    "liability": ("off_plan", -1),
}
REFINEMENT = (
    archive.REFINEMENT
    + """
The previous_queries/observation searches use the persisted UUID/keyword representation.
Your response MUST use the current global-choice/index schema, exactly like the baseline.
Select shared terms anew; indices refer only to your returned selected lists, not prior searches
or input-catalog positions. This is a complete replacement, not additions to the previous plan.
"""
)


def code_hashes() -> dict[str, str]:
    source = ROOT / "backend/src/mtg_helper/services/recommendations/term_selection.py"
    if source.read_bytes() != Path(term_selection.__file__).read_bytes():
        raise ValueError("Imported term-selection code differs from the mounted checkout")
    paths = [Path(__file__), source, PROTOCOL_FILE]
    return archive.code_hashes() | {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def reservation() -> int:
    if CALLS != archive.CALLS or INPUT_BOUNDS != archive.INPUT_BOUNDS:
        raise ValueError("The frozen four-call scope changed")
    total = sum(budget.cost(INPUT_BOUNDS[arm], OUTPUT_BOUND) for _, arm in CALLS)
    if total > CAP_MICROUSD:
        raise ValueError("Reservation exceeds this experiment's voluntary cost guard")
    return total


def make_request(payload: dict[str, Any], arm: str) -> dict[str, Any]:
    if arm not in INPUT_BOUNDS:
        raise ValueError("Unknown evaluation arm")
    fixed = (
        pipeline.check_request("plan", payload, profile=budget.BOUNDED_TERMS_VERSION)
        if arm == "baseline"
        else Stage(
            term_selection.PROMPT + REFINEMENT,
            term_selection.selection_type(payload),
            INPUT_BOUNDS[arm],
            OUTPUT_BOUND,
        )
    )
    request = request_payload("plan", payload, fixed)
    if request["max_output_tokens"] != OUTPUT_BOUND:
        raise ValueError("Production output bound changed; stop before spending")
    if len(json.dumps(request, ensure_ascii=False).encode()) + 2_000 > INPUT_BOUNDS[arm]:
        raise ValueError(f"{arm} exceeds its frozen request byte bound; no truncation or call")
    return request


async def prepare() -> dict[str, Any]:
    """Obtain fresh public menus without resolving reference identities or freezing old requests."""
    protocol = await archive.prepare()
    for case in protocol["cases"].values():
        payload = term_selection.Workflow(context=case["context"]).payload("plan", {})
        case["request"] = make_request(payload, "baseline")
    return protocol | {
        "version": VERSION,
        "profile": budget.BOUNDED_TERMS_VERSION,
        "code_hashes": code_hashes(),
        "refinement_instructions": REFINEMENT,
        "contributions": CONTRIBUTIONS,
        "reserved_microusd": reservation(),
    }


def validate_protocol(protocol: dict[str, Any]) -> None:
    expected = {
        "version": VERSION,
        "profile": budget.BOUNDED_TERMS_VERSION,
        "call_order": CALLS,
        "input_bounds": INPUT_BOUNDS,
        "output_bound": OUTPUT_BOUND,
        "reserved_microusd": reservation(),
        "cap_microusd": CAP_MICROUSD,
        "code_hashes": code_hashes(),
        "fixture_hashes": archive.fixture_hashes(),
        "refinement_instructions": REFINEMENT,
        "contributions": CONTRIBUTIONS,
    }
    if any(protocol[key] != json.loads(json.dumps(value)) for key, value in expected.items()):
        raise ValueError("Frozen protocol changed; do not spend or reuse this authorization")
    if set(protocol["cases"]) != set(DECKS):
        raise ValueError("Expected exactly Yuna and Meren")
    for key, case in protocol["cases"].items():
        if (case["leader"]["name"], case["context"]["prose"]) != DECKS[key]:
            raise ValueError("Commander/brief changed")
        payload = term_selection.Workflow(context=case["context"]).payload("plan", {})
        if case["request"] != make_request(payload, "baseline"):
            raise ValueError("Frozen current-production baseline request changed")


async def build_request(
    conn: asyncpg.Connection,
    protocol: dict[str, Any],
    ledger: dict[str, Any],
    key: str,
    arm: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        if await archive.state(conn) != protocol["source"]:
            raise ValueError("Source/ranking changed; stop the comparison")
        case = protocol["cases"][key]
        payload = term_selection.Workflow(context=case["context"]).payload("plan", {})
        if arm == "refined":
            previous = next(
                a for a in ledger["attempts"] if a["deck"] == key and a["arm"] == "baseline"
            )
            queries = previous["accepted"]["queries"]
            payload |= {
                "previous_queries": queries,
                "observations": await evaluation.observe(conn, case["leader"], queries),
            }
    return payload, make_request(payload, arm)


async def send_once(
    conn: asyncpg.Connection,
    protocol: dict[str, Any],
    call: tuple[str, str],
    ledger: dict[str, Any],
    sender: provider.Provider,
) -> None:
    key, arm = call
    payload, request = await build_request(conn, protocol, ledger, key, arm)
    freeze(
        DESTINATION / "requests" / f"{key}-{arm}.json",
        {"deck": key, "arm": arm, "payload": payload, "request": request},
    )
    attempt: dict[str, Any] = {
        "deck": key,
        "arm": arm,
        "state": "attempted",
        "request_sha256": digest(request),
    }
    ledger["attempts"].append(attempt)
    write_json(DESTINATION / "attempts.json", ledger)
    started = time.perf_counter()
    try:
        receipt = await sender.request(request)
        attempt.update(receipt, state="returned", seconds=time.perf_counter() - started)
        write_json(DESTINATION / "attempts.json", ledger)
        attempt["estimated_cost_microusd"] = budget.usage_cost(
            receipt, (INPUT_BOUNDS[arm], OUTPUT_BOUND)
        )
        if receipt.get("status") != "completed":
            raise ValueError("Provider response incomplete")
        attempt["accepted"] = term_selection.Workflow(
            context=protocol["cases"][key]["context"]
        ).accept("plan", receipt["output"], {})
        attempt["local_results"] = await archive.collect_results(
            conn, protocol, key, attempt["accepted"]
        )
    except (APIError, TimeoutError, ValueError) as exc:
        attempt["error"] = type(exc).__name__
        ledger["stopped"] = "Invalid/failed/unknown-cost attempt; no retry or dependent calls"
    write_json(DESTINATION / "attempts.json", ledger)
    print(key, arm, "valid" if "local_results" in attempt else "stopped", flush=True)


async def run_live(protocol: dict[str, Any], sender: provider.Provider) -> dict[str, Any]:
    validate_protocol(protocol)
    ledger: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "protocol_sha256": digest(protocol),
        "attempts": [],
        "reserved_microusd": reservation(),
    }
    with (DESTINATION / "attempts.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(ledger, indent=2) + "\n")
    conn = await asyncpg.connect(local_database(os.environ["DATABASE_URL"]))
    try:
        for call in CALLS:
            try:
                await send_once(conn, protocol, call, ledger, sender)
            except (ValueError, asyncpg.PostgresError) as exc:
                ledger["stopped"] = f"Local preflight failed ({type(exc).__name__}); stop all calls"
                write_json(DESTINATION / "attempts.json", ledger)
            if "stopped" in ledger:
                break
    finally:
        await conn.close()
    return ledger


def validate_ratings(packet: dict[str, Any], ratings: dict[str, Any]) -> None:
    evaluation.validate_ratings(packet, ratings)
    for entries in ratings["cases"].values():
        for entry in entries:
            contribution = entry["contribution"]
            if (
                contribution not in CONTRIBUTIONS
                or CONTRIBUTIONS[contribution][0] != entry["rating"]
            ):
                raise ValueError("Rating and predeclared contribution must agree")


def grade_arms(report: dict[str, Any], ratings: dict[str, Any]) -> dict[str, Any]:
    graded = evaluation.grade_arms(report, ratings)
    for arm in graded["arms"]:
        labels = {entry["oracle_id"]: entry for entry in ratings["cases"][arm["deck"]]}
        run = next(r for r in report["runs"] if r["deck"] == arm["deck"] and r["arm"] == arm["arm"])
        contributions = [labels[c["oracle_id"]]["contribution"] for c in run["cards"][:20]]
        arm["contributions"] = dict(Counter(contributions))
        arm["fit_score"] = sum(CONTRIBUTIONS[value][1] for value in contributions)
    for key, gate in graded["gates"].items():
        if "fit_improved" not in gate:
            continue
        arms = {row["arm"]: row for row in graded["arms"] if row["deck"] == key}
        gate["fit_improved"] = arms["refined"]["fit_score"] > arms["baseline"]["fit_score"]
        gate["passed"] = (
            gate["fit_improved"]
            and gate["off_plan_not_increased"]
            and gate["coverage_guard_passed"]
        )
    graded["recommend_adoption"] = len(graded["gates"]) == 2 and all(
        g["passed"] for g in graded["gates"].values()
    )
    return graded


def save_packet(protocol: dict[str, Any], ledger: dict[str, Any]) -> None:
    runs = [
        a["local_results"] | {"deck": a["deck"]} for a in ledger["attempts"] if "local_results" in a
    ]
    write_json(
        DESTINATION / "review-packet.json",
        evaluation.review_packet({"runs": runs}, protocol["cases"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    mode.add_argument("--grade", action="store_true")
    args = parser.parse_args()
    if not any((args.live, args.summarize, args.grade)):
        freeze(DESTINATION / "inputs.json", asyncio.run(prepare()))
        print("Prepared v3 without provider calls; reserved estimated microUSD:", reservation())
        return
    protocol = json.loads((DESTINATION / "inputs.json").read_text(encoding="utf-8"))
    validate_protocol(protocol)
    if args.live:
        from mtg_helper.config import settings

        ledger = asyncio.run(
            run_live(protocol, provider.Provider(settings.openai_api_key.get_secret_value()))
        )
        save_packet(protocol, ledger)
        print(
            "Attempts:",
            len(ledger["attempts"]),
            "; complete local rankings:",
            sum("local_results" in a for a in ledger["attempts"]),
        )
        return
    ledger = json.loads((DESTINATION / "attempts.json").read_text(encoding="utf-8"))
    if args.grade:
        packet = json.loads((DESTINATION / "review-packet.json").read_text(encoding="utf-8"))
        ratings = json.loads((DESTINATION / "ratings.json").read_text(encoding="utf-8"))
        validate_ratings(packet, ratings)
    result = asyncio.run(archive.summarize(protocol, ledger))
    write_json(DESTINATION / "results.json", result)
    if args.grade:
        write_json(DESTINATION / "graded-results.json", grade_arms(result, ratings))
    print("No provider invoked; local results saved.")


if __name__ == "__main__":
    main()
