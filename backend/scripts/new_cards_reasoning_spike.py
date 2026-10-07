"""Compare low/high reasoning on frozen candidate holdouts; never touch production.

Prepare/replay are offline. --live is separately authorized: eight calls, zero retries,
a $0.50 conservative estimated ceiling, and no overwrite/resume of a started experiment.
"""

import argparse
import copy
import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI

from scripts.new_cards_data_spike import CACHE, Card, iter_cards, write_json
from scripts.new_cards_evidence import EvaluationContext, enrich_cases
from scripts.new_cards_quality_spike import (
    BASELINE,
    PROMPT,
    PROMPT_VERSION,
    AssessmentBatch,
    card_facts,
    name_index,
    run_one,
    score_controls,
    usage_cost,
)

Effort = Literal["low", "high"]
MODEL = "gpt-5.6-luna"
MAX_OUTPUT = 16000
BUDGET_USD = 0.50
SPEC_PATH = BASELINE / "quality-v3-spec.json"


def load_json(path: Path) -> Any:
    """Load public experiment data with explicit UTF-8 on every platform."""
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_json(path: Path, value: object) -> None:
    """Preserve existing experiment inputs and refuse silently changed fixtures."""
    if path.exists():
        if load_json(path) != value:
            raise ValueError(f"Frozen artifact differs: {path}; do not overwrite the experiment")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def build_cases(baseline: list[Card], catalog: list[Card], spec: Card) -> list[Card]:
    """Select preregistered cards, forbidding holdout overlap with any earlier input."""
    seen = {
        card["oracle_id"]
        for case in baseline
        for card in (
            case["deck"]["commander"],
            *case["deck"]["physical_cards"],
            *case["candidates"],
        )
    }
    index = name_index(catalog)
    cases = []
    for previous in baseline:
        entries = spec["decks"][previous["deck"]["id"]]
        cards = [card_facts(index[entry["name"]]) for entry in entries]
        holdouts = [
            card["oracle_id"]
            for card, entry in zip(cards, entries, strict=True)
            if entry["kind"] == "holdout"
        ]
        if set(holdouts) & seen:
            raise ValueError("A holdout identity appeared in an earlier candidate or physical deck")
        cases.append(
            {
                "deck": copy.deepcopy(previous["deck"]),
                "candidates": cards,
                "expected": {
                    card["oracle_id"]: entry["labels"]
                    for card, entry in zip(cards, entries, strict=True)
                },
                "holdout_ids": holdouts,
                "review_checks": {
                    card["oracle_id"]: entry["check"]
                    for card, entry in zip(cards, entries, strict=True)
                },
            }
        )
    return cases


def prepare() -> list[Card]:
    """Freeze new candidate inputs from the original verified Scryfall snapshot."""
    spec = load_json(SPEC_PATH)
    if (spec["max_output_tokens"], spec["maximum_calls"], spec["estimated_budget_usd"]) != (
        MAX_OUTPUT,
        8,
        BUDGET_USD,
    ):
        raise ValueError("Protocol/settings mismatch; do not run a changed experiment")
    baseline = load_json(BASELINE / "quality-v2-cases.json")
    source = next(
        item
        for item in load_json(BASELINE / "data-report.json")["sources"]
        if item["type"] == "oracle_cards"
    )
    archive = CACHE / "oracle_cards.jsonl.gz"
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
            raise ValueError("Oracle archive differs from the original snapshot")
    cases = build_cases(baseline, load_json(CACHE / "catalog.json"), spec)
    enrich_cases(cases, iter_cards(archive))
    call_plan(cases)
    freeze_json(CACHE / "quality-v3-cases.json", cases)
    return cases


def call_plan(cases: list[Card]) -> list[tuple[Card, Effort]]:
    """Require four distinct eight-candidate cases; counterbalance which arm runs first."""
    if len(cases) != 4 or len({case["deck"]["id"] for case in cases}) != 4:
        raise ValueError("Expected exactly four distinct decks")
    plan = []
    for number, case in enumerate(cases):
        if len(case["candidates"]) != 8:
            raise ValueError("Expected exactly eight candidates per deck")
        EvaluationContext(case)
        order: tuple[Effort, Effort] = ("low", "high") if number % 2 == 0 else ("high", "low")
        plan.extend((case, effort) for effort in order)
    return plan


def reserved_cost(case: Card) -> float:
    """Conservatively reserve input bytes as tokens plus framing and maximum output.

    This is an estimated-spend guard, not a provider invoice guarantee. Hidden reasoning is
    included in the output-token cap. No tools, premium context tier, or separate service fees.
    """
    context = EvaluationContext(case)
    payload = json.dumps(context.payload(False), ensure_ascii=False)
    if len(payload.encode("utf-8")) > 180_000:
        raise ValueError("Input exceeds the fixed 180 KB request budget")
    body = {"model": MODEL, "instructions": PROMPT, "input": payload, "schema": context.schema()}
    input_bound = len(json.dumps(body, ensure_ascii=False).encode("utf-8")) + 2048
    return usage_cost({"input_tokens": input_bound, "output_tokens": MAX_OUTPUT})


def run_experiment(client: OpenAI, cases: list[Card], destination: Path) -> Card:
    """Checkpoint attempts before sending; never retry, resume, or exceed the approved plan."""
    if client.max_retries != 0:
        raise ValueError("The experiment requires max_retries=0")
    plan = call_plan(cases)
    reservation = sum(reserved_cost(case) for case, _ in plan)
    if reservation > BUDGET_USD:
        raise ValueError("Full plan exceeds the $0.50 estimated budget; no calls sent")
    report: Card = {
        "experiment": "new-cards-reasoning-v3",
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt": PROMPT,
        "started_at": datetime.now(UTC).isoformat(),
        "case_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "spec_sha256": hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest(),
        "settings": {
            "efforts": ["low", "high"],
            "max_output_tokens": MAX_OUTPUT,
            "verbosity": "low",
            "store": False,
            "max_retries": 0,
            "maximum_calls": 8,
        },
        "estimated_budget_usd": BUDGET_USD,
        "reserved_upper_usd": reservation,
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md",
        "runs": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also blocks a second process from starting the same experiment.
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for case, effort in plan:
        attempt = {
            "deck_id": case["deck"]["id"],
            "reasoning_effort": effort,
            "state": "attempt_started",
            "reserved_upper_usd": reserved_cost(case),
        }
        report["runs"].append(attempt)
        write_json(destination, report)
        attempt.update(
            run_one(
                client, MODEL, case, False, reasoning_effort=effort, max_output_tokens=MAX_OUTPUT
            )
        )
        attempt["state"] = "attempt_finished"
        write_json(destination, report)
        print(
            attempt["deck_id"],
            effort,
            attempt.get("controls", attempt.get("error")),
            attempt["seconds"],
            flush=True,
        )
        if stop := stop_reason(attempt):
            report["stopped"] = stop
            write_json(destination, report)
            break
    return report


def stop_reason(attempt: Card) -> str | None:
    """Stop paid work on provider/incomplete-output failure or invalid spend evidence."""
    if attempt.get("error"):
        return "Failed attempt; no retries or replacement calls"
    if not attempt.get("usage"):
        return "Missing usage; actual spend cannot be checked"
    if attempt["estimated_cost_upper_usd"] > attempt["reserved_upper_usd"]:
        return "Measured estimated cost exceeded its conservative reservation"
    return None


def arm_summary(cases: list[Card], runs: list[Card], effort: Effort) -> Card:
    """Keep missing judgments in denominators and separate holdouts from regressions."""
    matching = [run for run in runs if run["reasoning_effort"] == effort]
    groups = {kind: {"matched": 0, "total": 0} for kind in ("holdout", "regression")}
    for case in cases:
        run = next((run for run in matching if run["deck_id"] == case["deck"]["id"]), {})
        batch = AssessmentBatch.model_validate({"assessments": run.get("assessments", [])})
        for kind, totals in groups.items():
            expected = {
                key: value
                for key, value in case["expected"].items()
                if (key in case["holdout_ids"]) == (kind == "holdout")
            }
            score = score_controls(batch, expected)
            totals["matched"] += score["matched"]
            totals["total"] += score["total"]
    measured = [run for run in matching if run.get("usage")]
    seconds = [run["seconds"] for run in matching if "seconds" in run]
    return {
        "calls": len(matching),
        "completed": sum(r.get("status") == "completed" for r in matching),
        "contract_valid_runs": sum(
            r.get("status") == "completed" and not r.get("error") and not r.get("validation_errors")
            for r in matching
        ),
        "judgments": sum(len(r.get("assessments", [])) for r in matching),
        "broad_labels": groups,
        "seconds": seconds,
        "median_seconds": statistics.median(seconds) if seconds else None,
        "input_tokens": sum(r["usage"]["input_tokens"] for r in measured),
        "output_tokens": sum(r["usage"]["output_tokens"] for r in measured),
        "reasoning_tokens": sum(
            r["usage"]["output_tokens_details"]["reasoning_tokens"] for r in measured
        ),
        "estimated_cost_upper_usd": sum(usage_cost(r["usage"]) for r in measured),
    }


def summarize(cases: list[Card], report: Card) -> Card:
    """Calculate arm-level metrics offline; no claim of semantic correctness."""
    return {
        "arms": {effort: arm_summary(cases, report["runs"], effort) for effort in ("low", "high")},
        "note": "Broad labels are not semantic accuracy. All-label cases excluded. "
        "One observation per arm/deck; no statistical causal claim.",
    }


def main() -> None:
    """Prepare offline by default; paid work requires --live and fresh exclusive results."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    destination = CACHE / "quality-v3-results.json"
    if args.summarize:
        summary = summarize(load_json(CACHE / "quality-v3-cases.json"), load_json(destination))
        write_json(CACHE / "quality-v3-summary.json", summary)
        print(json.dumps(summary, indent=2))
        return
    cases = prepare()
    print(
        "Prepared four decks, 32 candidate judgments per arm; reserved estimate:",
        sum(reserved_cost(case) for case, _ in call_plan(cases)),
    )
    if args.live:
        from mtg_helper.config import settings
        from mtg_helper.services.agents._model import OPENAI_MODEL

        if OPENAI_MODEL != MODEL:
            raise ValueError("App model changed; do not silently change the experiment or pricing")
        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=180
        ) as client:
            run_experiment(client, cases, destination)


if __name__ == "__main__":
    main()
