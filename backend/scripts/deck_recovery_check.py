"""Recover hidden user-deck cards from commander/strategy alone; no database or community access.

Default execution prepares inputs and reserves cost offline. --live permits the four explicitly
approved Luna/Terra calls, with no retries or reruns. --summarize replays preserved outputs offline.
"""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field

from mtg_helper.services.recommendations.source import (
    Catalog,
    build_catalog,
    eligibility_error,
    is_land,
)
from scripts.new_cards_data_spike import Card, iter_cards, write_json

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend/evals/deck_recovery"
DESTINATION = ROOT / "docs/research/deck-recovery-smoke"
SOURCE = ROOT / "backend/.cache/new-cards-spike/oracle_cards.jsonl.gz"
SOURCE_REPORT = ROOT / "docs/research/new-cards-spike-2026-10-05/data-report.json"
MAX_OUTPUT = 7000
BUDGET_USD = 0.50
# Official model pages checked before authorization; input uses the cache-write upper rate.
RATES = {"gpt-5.6-luna": (0.25, 1.2), "gpt-5.6-terra": (2.5, 12.0)}
DECKS = {
    "yuna": (
        "Yuna, Grand Summoner",
        "Bant +1/+1 counter growth and redistribution, with creature-based acceleration.",
    ),
    "meren": (
        "Meren of Clan Nel Toth",
        "Golgari sacrifice and creature-recursion value, "
        "reusing enter/death effects and interaction.",
    ),
}
# Counterbalance model order. Each deck receives byte-identical facts/goals across models.
CALLS = [
    ("yuna", "gpt-5.6-luna"),
    ("yuna", "gpt-5.6-terra"),
    ("meren", "gpt-5.6-terra"),
    ("meren", "gpt-5.6-luna"),
]
PROMPT = """You are an experienced Commander brewer. Given the commander's source facts and
strategy, recommend a ranked package of exactly 50 unique nonland cards to build this deck.
Use your card knowledge; no tools, external decklists, or hidden reference list are available.
Prioritize strong engine connections, then an appropriate balance of acceleration, draw,
interaction, protection and finishers. Give each card's exact name and a short deck-specific reason.
Respect combined color identity and Commander legality. Do not suggest the commander itself.
Land-front cards, including Dryad Arbor, are excluded; spell-front modal double-faced cards are
allowed. Do not invent a budget, bracket or prohibition of infinite combos. Do not invent cards.
Rank your strongest recommendations first. Reasons are strategic advice, not official rules.
"""


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    reason: str = Field(min_length=1, max_length=250)


class Suggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cards: list[Suggestion] = Field(min_length=50, max_length=50)


def parse_fixture(text: str, commander: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Separate main and sideboard while recognizing the explicitly named commander."""
    main: list[tuple[int, str]] = []
    sideboard: list[tuple[int, str]] = []
    target = main
    commander_count = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if line == "SIDEBOARD:":
            target = sideboard
            continue
        count, name = line.split(" ", 1)
        quantity = int(count)
        if quantity <= 0 or not name.strip():
            raise ValueError("Fixture quantities must be positive and names nonempty")
        if name == commander:
            commander_count += quantity
        else:
            target.append((quantity, name))
    if commander_count != 1:
        raise ValueError("Fixture must contain exactly one explicitly named commander")
    return main, sideboard


def source_metadata() -> Card:
    """Refuse a changed or missing frozen source instead of quietly altering the experiment."""
    sources = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))["sources"]
    record = next(item for item in sources if item["type"] == "oracle_cards")
    with SOURCE.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
            raise ValueError("Source hash differs; do not replace the frozen recovery facts")
    return record


def prepare_cases(catalog: Catalog) -> tuple[dict[str, Card], dict[str, set[str]]]:
    """Keep recommender payloads separate from evaluator-only answer identities."""
    inputs: dict[str, Card] = {}
    answers: dict[str, set[str]] = {}
    for key, (commander, goal) in DECKS.items():
        main, _ = parse_fixture((FIXTURES / f"{key}.txt").read_text(encoding="utf-8"), commander)
        if sum(q for q, _ in main) != 99:
            raise ValueError(f"{key}: expected 99 main-deck cards plus commander")
        leader = catalog.resolve(commander)
        if leader is None:
            raise ValueError(f"{key}: unresolved commander")
        cards = [catalog.resolve(name) for _, name in main]
        if any(card is None for card in cards):
            raise ValueError(f"{key}: unresolved answer entry; do not silently drop targets")
        resolved = [card for card in cards if card is not None]
        colors = set(leader["color_identity"])
        invalid = [
            c["name"]
            for c in resolved
            if c["legalities"]["commander"] != "legal" or not set(c["color_identity"]) <= colors
        ]
        if invalid:
            raise ValueError(f"{key}: invalid answer entries: {invalid}")
        fields = (
            "name",
            "mana_cost",
            "type_line",
            "oracle_text",
            "color_identity",
            "power",
            "toughness",
        )
        inputs[key] = {"commander": {f: leader.get(f) for f in fields}, "strategy": goal}
        answers[key] = {c["oracle_id"] for c in resolved if not is_land(c)}
    return inputs, answers


def score_output(text: str, deck_id: str, catalog: Catalog, answers: set[str]) -> Card:
    """Score original ranks; duplicates/invalids never consume replacement attempts or hits."""
    parsed = Suggestions.model_validate_json(text)
    leader = catalog.resolve(DECKS[deck_id][0])
    if leader is None:
        raise ValueError("Commander facts unavailable for scoring")
    seen: set[str] = set()
    scored: list[Card] = []
    for rank, item in enumerate(parsed.cards, 1):
        card = catalog.resolve(item.name)
        error = eligibility_error(card, set(leader["color_identity"]), leader["oracle_id"])
        identity = card["oracle_id"] if card else None
        if identity in seen:
            error = "duplicate"
        if identity:
            seen.add(identity)
        scored.append(
            {
                "rank": rank,
                "name": item.name,
                "reason": item.reason,
                "oracle_id": identity,
                "error": error,
                "exact_hit": error is None and identity in answers,
            }
        )
    hits = [item for item in scored if item["exact_hit"]]
    return {
        "exact_hits": len(hits),
        "suggestion_count": len(scored),
        "target_count": len(answers),
        "top_ten_hits": sum(item["rank"] <= 10 for item in hits),
        "invalid_or_duplicate_count": sum(item["error"] is not None for item in scored),
        "off_list_count": sum(item["error"] is None and not item["exact_hit"] for item in scored),
        "cards": scored,
    }


def estimated_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = RATES[model]
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def reserve(inputs: dict[str, Card]) -> float:
    """Reserve all four calls using UTF-8 bytes as conservative tokens plus framing/schema."""
    if len(CALLS) != 4 or len(set(CALLS)) != 4:
        raise ValueError("Authorization permits four distinct deck/model requests only")
    framing = len((PROMPT + json.dumps(Suggestions.model_json_schema())).encode()) + 2000
    total = sum(
        estimated_cost(model, len(json.dumps(inputs[key]).encode()) + framing, MAX_OUTPUT)
        for key, model in CALLS
    )
    if total > BUDGET_USD:
        raise ValueError("Four-call reservation exceeds authorized $0.50 estimated ceiling")
    return total


def freeze(path: Path, value: Card) -> None:
    """Create immutable inputs, or refuse a different experiment at the same destination."""
    normalized = json.loads(json.dumps(value))
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != normalized:
            raise ValueError(f"Frozen input changed: {path}; do not overwrite")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def call_once(client: OpenAI, model: str, payload: Card) -> Card:
    """Make one no-tool request and retain failures without leaking provider exception bodies."""
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=model,
            instructions=PROMPT,
            input=json.dumps(payload, ensure_ascii=False),
            store=False,
            max_output_tokens=MAX_OUTPUT,
            reasoning={"effort": "low"},
            text={
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "deck_recovery",
                    "strict": True,
                    "schema": Suggestions.model_json_schema(),
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
        "usage": response.usage.model_dump() if response.usage else None,
        "incomplete_details": response.incomplete_details.model_dump()
        if response.incomplete_details
        else None,
    }


def run_live(inputs: dict[str, Card], path: Path) -> Card:
    """Checkpoint before each paid attempt; refuse repeat/resume and stop on unpriced failures."""
    from mtg_helper.config import settings

    report: Card = {
        "started_at": datetime.now(UTC).isoformat(),
        "runs": [],
        "reserved_usd": reserve(inputs),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental or concurrent reruns of the authorization.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    with OpenAI(
        api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=90
    ) as client:
        for key, model in CALLS:
            attempt: Card = {"deck_id": key, "model": model, "state": "attempted"}
            report["runs"].append(attempt)
            write_json(path, report)
            attempt.update(call_once(client, model, inputs[key]))
            attempt["state"] = "returned"
            usage = attempt.get("usage")
            if usage:
                attempt["estimated_cost_usd"] = estimated_cost(
                    model, usage["input_tokens"], usage["output_tokens"]
                )
            else:
                report["stopped"] = "Failure or missing usage; no retry or further paid calls"
            write_json(path, report)
            print(key, model, attempt.get("status", attempt.get("error")), flush=True)
            if report.get("stopped"):
                break
            if sum(run.get("estimated_cost_usd", 0) for run in report["runs"]) > BUDGET_USD:
                report["stopped"] = "Measured estimated spend exceeds authorized ceiling"
                write_json(path, report)
                break
    return report


def summarize(report: Card, catalog: Catalog, answers: dict[str, set[str]]) -> Card:
    """Replay every attempted run; incomplete/provider-failed outputs are not scored as success."""
    rows = []
    for run in report["runs"]:
        row = {
            k: run.get(k) for k in ("deck_id", "model", "status", "seconds", "estimated_cost_usd")
        }
        if run.get("status") != "completed":
            row["error"] = run.get("error", "not_completed")
        else:
            try:
                row.update(
                    score_output(run["output"], run["deck_id"], catalog, answers[run["deck_id"]])
                )
            except ValueError:
                row["error"] = "invalid_structured_output"
        rows.append(row)
    return {"attempts": len(report["runs"]), "planned_attempts": 4, "runs": rows}


def main() -> None:
    """Prepare offline by default; only --live consumes the user's four-call authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    source = source_metadata()
    catalog = build_catalog(iter_cards(SOURCE))
    inputs, answers = prepare_cases(catalog)
    protocol = {
        "prompt": PROMPT,
        "inputs": inputs,
        "call_plan": CALLS,
        "source": source,
        "schema": Suggestions.model_json_schema(),
        "fixture_sha256": {
            k: hashlib.sha256((FIXTURES / f"{k}.txt").read_bytes()).hexdigest() for k in DECKS
        },
        "settings": {
            "reasoning": "low",
            "max_output_tokens": MAX_OUTPUT,
            "retries": 0,
            "store": False,
        },
        "pricing": RATES,
        "budget_usd": BUDGET_USD,
        "reserved_usd": reserve(inputs),
        "pricing_sources": [f"https://developers.openai.com/api/docs/models/{m}.md" for m in RATES],
    }
    freeze(DESTINATION / "inputs.json", protocol)
    print("Reserved upper estimated spend:", round(reserve(inputs), 6))
    path = DESTINATION / "results.json"
    if args.live:
        report = run_live(inputs, path)
    elif args.summarize:
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        print("Inputs frozen. No model calls made.")
        return
    summary = summarize(report, catalog, answers)
    write_json(DESTINATION / "summary.json", summary)
    for row in summary["runs"]:
        print({k: v for k, v in row.items() if k != "cards"})


if __name__ == "__main__":
    main()
