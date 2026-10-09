"""One authorized, database-free Meren/Saheeli × Luna/Terra planning/discovery experiment.

Default prepares offline. --live permits up to eight requests, no retries, $1 estimated ceiling.
--summarize replays preserved outputs without requests. Existing results block repeat/resume.
"""

import argparse
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openai import APIError, OpenAI

from mtg_helper.services.recommendations.discovery import (
    Discovery,
    Plan,
    Query,
    Review,
    card_facts,
    discover,
    eligible_cards,
    matches,
    recent_sample,
    shared_pool,
    validate_review,
)
from mtg_helper.services.recommendations.profiles import PLAN_PROMPT, REVIEW_PROMPT, Stage
from scripts.deck_recovery_check import (
    RATES,
    ROOT,
    SOURCE,
    Catalog,
    build_catalog,
    eligibility_error,
    estimated_cost,
    freeze,
    source_metadata,
)
from scripts.new_cards_data_spike import Card, iter_cards, write_json

FIXTURES = ROOT / "backend/evals/commander_discovery"
DESTINATION = ROOT / "docs/research/commander-discovery-smoke"
DATES = SOURCE.parent / "catalog.json"
BUDGET_USD = 1.0
MODELS = ("gpt-5.6-luna", "gpt-5.6-terra")
CALLS = (
    ("plan", "meren", "gpt-5.6-terra"),
    ("plan", "meren", "gpt-5.6-luna"),
    ("plan", "saheeli", "gpt-5.6-luna"),
    ("plan", "saheeli", "gpt-5.6-terra"),
    ("review", "meren", "gpt-5.6-luna"),
    ("review", "meren", "gpt-5.6-terra"),
    ("review", "saheeli", "gpt-5.6-terra"),
    ("review", "saheeli", "gpt-5.6-luna"),
)


STAGES = {
    "plan": Stage(PLAN_PROMPT, Plan, 20_000, 5_000),
    "review": Stage(REVIEW_PROMPT, Review, 70_000, 10_000),
}


@dataclass(kw_only=True)
class Prepared:
    catalog: Catalog
    cases: Card
    payloads: Card
    dates: dict[str, str | None]
    rules: Card
    protocol: Card


def require_card(catalog: Catalog, name: str) -> Card:
    """Refuse missing/ambiguous source identities rather than substituting a card."""
    card = catalog.resolve(name)
    if card is None:
        raise ValueError(f"Unresolved source card {name!r}; correct the fixture before execution")
    return card


def reservation() -> float:
    """Reserve the exact eight authorized requests using bounded bytes as input tokens."""
    expected = {(s, d, m) for s in STAGES for d in ("meren", "saheeli") for m in MODELS}
    if len(CALLS) != 8 or set(CALLS) != expected:
        raise ValueError("Authorization permits eight distinct Meren/Saheeli Luna/Terra requests")
    if [phase for phase, _, _ in CALLS] != ["plan"] * 4 + ["review"] * 4:
        raise ValueError("All four plans must precede the paired common-pool reviews")
    total = sum(
        estimated_cost(m, STAGES[s].byte_limit, STAGES[s].output_limit) for s, _, m in CALLS
    )
    if total > BUDGET_USD:
        raise ValueError("Reservation exceeds authorized $1 estimated ceiling; do not execute")
    return total


def request_bytes(stage: Stage, payload: Card) -> int:
    """Include prompt, schema and framing; never silently truncate card facts to fit."""
    text = stage.prompt + json.dumps(stage.schema.model_json_schema(), ensure_ascii=False)
    return len(text.encode()) + len(json.dumps(payload, ensure_ascii=False).encode()) + 2000


def prepare() -> Prepared:
    """Freeze source, fixtures, requests and prices without loading secrets or contacting models."""
    source = source_metadata()
    catalog = build_catalog(iter_cards(SOURCE))
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    rules = json.loads((FIXTURES / "rules.json").read_text(encoding="utf-8"))
    dates = {
        c["oracle_id"]: c["first_paper_release"]
        for c in json.loads(DATES.read_text(encoding="utf-8"))
    }
    payloads = {}
    for key, case in cases.items():
        leader = require_card(catalog, case["commander"])
        if leader["legalities"].get("commander") != "legal":
            raise ValueError(f"Commander {case['commander']} is not source-legal")
        for name in case["diagnostics"]:
            error = eligibility_error(
                require_card(catalog, name), set(leader["color_identity"]), leader["oracle_id"]
            )
            if error:
                raise ValueError(f"Diagnostic {name!r} is ineligible: {error}")
        payloads[key] = {"commander": card_facts(leader), "goal": case["goal"]}
        if request_bytes(STAGES["plan"], payloads[key]) > STAGES["plan"].byte_limit:
            raise ValueError(f"{key}: planner payload exceeds authorized input bound")
    protocol = {
        "version": "commander-discovery-v1",
        "source": source,
        "planner_inputs": payloads,
        "cases": cases,
        "rules": rules,
        "calls": CALLS,
        "stages": {
            k: {
                "prompt": v.prompt,
                "schema": v.schema.model_json_schema(),
                "input_byte_bound": v.byte_limit,
                "max_output_tokens": v.output_limit,
            }
            for k, v in STAGES.items()
        },
        "fixture_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (FIXTURES / "cases.json", FIXTURES / "rules.json")
        },
        "derived_catalog_sha256": hashlib.sha256(DATES.read_bytes()).hexdigest(),
        "pricing": RATES,
        "pricing_sources": [
            f"https://developers.openai.com/api/docs/models/{m}.md" for m in MODELS
        ],
        "reserved_usd": reservation(),
        "budget_usd": BUDGET_USD,
        "settings": {"reasoning": "low", "verbosity": "low", "store": False, "retries": 0},
        "limits": {
            "independent_shortlist": 32,
            "shared_pool": 64,
            "query_sample": 8,
            "recent_sample": 8,
            "named_candidates": 12,
        },
    }
    freeze(DESTINATION / "inputs.json", protocol)
    return Prepared(
        catalog=catalog, cases=cases, payloads=payloads, dates=dates, rules=rules, protocol=protocol
    )


def decode_plans(report: Card, case_id: str) -> dict[str, Plan]:
    """Failed/incomplete plans remain failures, not substituted successful planners."""
    plans = {}
    for run in report["runs"]:
        if run["phase"] != "plan" or run["case_id"] != case_id:
            continue
        if run.get("status") != "completed":
            continue
        try:
            plans[run["model"]] = Plan.model_validate_json(run["output"])
        except ValueError:
            run["plan_error"] = "invalid_structured_plan"
    return plans


def discovery_record(found: Discovery, controls: list[Card]) -> Card:
    """Archive source-only selected facts and diagnostic admission, not community metadata."""
    return {
        "nominations": [card_facts(c) for c in found.nominations],
        "nomination_errors": found.nomination_errors,
        "shortlist": [card_facts(c) for c in found.shortlist],
        "matching_identity_count": len(found.matched_ids),
        "queries": [
            {k: v for k, v in r.items() if k != "selected"}
            | {
                "selected": [card_facts(c) for c in r["selected"]],
                "diagnostic_matches": [
                    c["name"]
                    for c in controls
                    if "error" not in r and matches(Query.model_validate(r["query"]), c)
                ],
            }
            for r in found.queries
        ],
    }


def review_inputs(prepared: Prepared, report: Card) -> tuple[Card, Card]:
    """Build identical paired inputs, keeping diagnostic/scout origin outside model payloads."""
    inputs, records = {}, {}
    for case_id, case in prepared.cases.items():
        leader = require_card(prepared.catalog, case["commander"])
        seed = f"{prepared.protocol.get('source', {}).get('sha256', 'test')}|{case_id}|v1"
        plans = decode_plans(report, case_id)
        found = {
            m: discover(plans[m], prepared.catalog, leader, seed) for m in MODELS if m in plans
        }
        controls = [require_card(prepared.catalog, name) for name in case["diagnostics"]]
        selected = {c["oracle_id"] for d in found.values() for c in d.shortlist}
        unexplored = [
            c
            for c in eligible_cards(prepared.catalog, leader)
            if c["oracle_id"] not in selected | {c["oracle_id"] for c in controls}
        ]
        recent = recent_sample(unexplored, prepared.dates, f"{seed}|recent")
        pool = shared_pool(found, controls, recent, seed)
        inputs[case_id] = prepared.payloads[case_id] | {
            "candidates": [
                card_facts(c) | {"key": f"C{i:02d}"} for i, c in enumerate(pool["cards"])
            ],
            "rules": prepared.rules["rules"],
        }
        records[case_id] = {
            "discoveries": {m: discovery_record(d, controls) for m, d in found.items()},
            "failed_planners": sorted(set(MODELS) - plans.keys()),
            "provenance": pool["provenance"],
            "recent_names": [c["name"] for c in recent],
            "eligible_count": len(eligible_cards(prepared.catalog, leader)),
        }
    return inputs, records


def call_once(
    client: OpenAI, phase: str, model: str, payload: Card, *, stage: Stage | None = None
) -> Card:
    """Make one request using the default or supplied fixed stage; retain provider failures."""
    if stage is None:
        stage = STAGES[phase]
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=model,
            service_tier="default",
            instructions=stage.prompt,
            input=json.dumps(payload, ensure_ascii=False),
            max_output_tokens=stage.output_limit,
            store=False,
            reasoning={"effort": "low"},
            text={
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "name": f"commander_{phase}",
                    "schema": stage.schema.model_json_schema(),
                },
            },
        )
    except APIError as exc:
        return {"seconds": time.perf_counter() - started, "error": type(exc).__name__}
    return {
        "seconds": time.perf_counter() - started,
        "status": response.status,
        "output": response.output_text,
        "response_model": response.model,
        "service_tier": response.service_tier,
        "usage": response.usage.model_dump() if response.usage else None,
        "incomplete_details": response.incomplete_details.model_dump()
        if response.incomplete_details
        else None,
    }


@dataclass(frozen=True, kw_only=True)
class Execution:
    """Internal dependencies for the two fixed experiments, not user-configurable options."""

    calls: tuple[tuple[str, str, str], ...]
    price: Callable[[str, int, int], float]
    build_reviews: Callable[[Prepared, Card], tuple[Card, Card]]
    ceiling_usd: float = BUDGET_USD

    def reservation(self) -> float:
        """Reject duplicate requests and reserve every call's full input/output bounds."""
        if not self.calls or len(set(self.calls)) != len(self.calls):
            raise ValueError("Call scope must contain distinct authorized requests")
        total = sum(
            self.price(model, STAGES[phase].byte_limit, STAGES[phase].output_limit)
            for phase, _, model in self.calls
        )
        if not 0 < self.ceiling_usd <= BUDGET_USD or not 0 <= total <= self.ceiling_usd:
            raise ValueError("Reservation exceeds the profile's authorized estimated ceiling")
        return total


class Experiment:
    """Own a single-use ledger; paid-call guards are shared by the two fixed experiments."""

    def __init__(
        self, prepared: Prepared, path: Path, client: OpenAI, *, execution: Execution | None = None
    ) -> None:
        if execution is None:
            reservation()
            execution = Execution(calls=CALLS, price=estimated_cost, build_reviews=review_inputs)
        self.execution = execution
        self.prepared = prepared
        self.path = path
        self.client = client
        self.report: Card = {
            "started_at": datetime.now(UTC).isoformat(),
            "runs": [],
            "reserved_usd": execution.reservation(),
        }
        self.reviews: Card = {}

    def run(self) -> Card:
        """Checkpoint before every attempt; refuse retries/resume and stop on unknown billing."""
        if self.client.max_retries != 0:
            raise ValueError("Paid experiment requires SDK max_retries=0")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(self.report, indent=2) + "\n")
        for index, (phase, case_id, model) in enumerate(self.execution.calls):
            if phase == "review" and not self.reviews:
                self.reviews, records = self.execution.build_reviews(self.prepared, self.report)
                freeze(self.path.parent / "assessment-inputs.json", self.reviews)
                freeze(self.path.parent / "retrieval.json", records)
            payload = self.prepared.payloads[case_id] if phase == "plan" else self.reviews[case_id]
            if not self._within_bounds(index, phase, payload):
                break
            attempt = {
                "phase": phase,
                "case_id": case_id,
                "model": model,
                "state": "attempted",
                "input_sha256": hashlib.sha256(
                    json.dumps(payload, ensure_ascii=False).encode()
                ).hexdigest(),
            }
            self.report["runs"].append(attempt)
            write_json(self.path, self.report)
            attempt.update(call_once(self.client, phase, model, payload))
            attempt["state"] = "returned"
            self._price(attempt)
            write_json(self.path, self.report)
            print(phase, case_id, model, attempt.get("status", attempt.get("error")), flush=True)
            if self.report.get("stopped"):
                break
        write_json(self.path, self.report)
        return self.report

    def _within_bounds(self, index: int, phase: str, payload: Card) -> bool:
        if request_bytes(STAGES[phase], payload) > STAGES[phase].byte_limit:
            self.report["stopped"] = "Input byte bound exceeded; no truncation or request"
        remaining = sum(
            self.execution.price(m, STAGES[s].byte_limit, STAGES[s].output_limit)
            for s, _, m in self.execution.calls[index:]
        )
        spent = sum(r.get("estimated_cost_usd", 0) for r in self.report["runs"])
        if spent + remaining > self.execution.ceiling_usd:
            self.report["stopped"] = "Remaining reservation exceeds authorized estimated ceiling"
        return not self.report.get("stopped")

    def _price(self, attempt: Card) -> None:
        usage = attempt.get("usage")
        if (
            not usage
            or attempt.get("response_model") != attempt["model"]
            or attempt.get("service_tier") != "default"
        ):
            self.report["stopped"] = (
                "Unknown usage, model or service-tier pricing; no further requests"
            )
            return
        counts = [usage.get("input_tokens"), usage.get("output_tokens")]
        if any(type(n) is not int or n < 0 for n in counts):
            self.report["stopped"] = "Invalid usage; no further requests"
            return
        attempt["estimated_cost_usd"] = self.execution.price(attempt["model"], *counts)
        stage = STAGES[attempt["phase"]]
        if counts[0] > stage.byte_limit or counts[1] > stage.output_limit:
            self.report["stopped"] = (
                "Reported usage exceeds reserved call bound; no further requests"
            )


def summarize(report: Card, inputs: Card, *, authorized_maximum: int = 8) -> Card:
    """Replay output identities/quotes offline; interpretation and usefulness require review."""
    rows = []
    for run in report["runs"]:
        row = {
            k: run.get(k)
            for k in (
                "phase",
                "case_id",
                "model",
                "status",
                "seconds",
                "estimated_cost_usd",
                "usage",
            )
        }
        if run.get("status") != "completed":
            row["error"] = run.get("error", "incomplete")
        elif run["phase"] == "review" and run["case_id"] not in inputs:
            row["error"] = "missing_assessment_inputs"
        else:
            try:
                if run["phase"] == "plan":
                    row["plan"] = Plan.model_validate_json(run["output"]).model_dump()
                else:
                    row.update(
                        validate_review(
                            Review.model_validate_json(run["output"]), inputs[run["case_id"]]
                        )
                    )
            except ValueError:
                row["error"] = "invalid_structured_output"
        rows.append(row)
    unpriced = sum("estimated_cost_usd" not in run for run in report["runs"])
    known_cost = sum(run.get("estimated_cost_usd", 0) for run in report["runs"])
    return {
        "attempts": len(rows),
        "authorized_maximum": authorized_maximum,
        "stopped": report.get("stopped"),
        "estimated_cost_usd": None if unpriced else known_cost,
        "known_estimated_cost_usd": known_cost,
        "unpriced_attempts": unpriced,
        "runs": rows,
    }


def main() -> None:
    """Resolve offline inputs, then delegate the authorized run or replay."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    prepared = prepare()
    print("Reserved upper estimated spend:", reservation())
    path = DESTINATION / "results.json"
    if args.live:
        from mtg_helper.config import settings

        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=120
        ) as client:
            report = Experiment(prepared, path, client).run()
    elif args.summarize:
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        print("Inputs frozen offline; no model calls made.")
        return
    input_path = DESTINATION / "assessment-inputs.json"
    inputs = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else {}
    result = summarize(report, inputs)
    write_json(DESTINATION / "summary.json", result)
    print("Attempts:", result["attempts"], "estimated spend:", result["estimated_cost_usd"])


if __name__ == "__main__":
    main()
