"""One separately authorized four-call Sol comparison with frozen Luna/Terra inputs.

Default prepares offline. --live allows two plans and two fixed-pool reviews, no retries,
$1 conservative estimated ceiling. --summarize is offline. Existing results prevent resume.
"""

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from openai import OpenAI

from mtg_helper.services.recommendations.discovery import discover
from scripts import commander_discovery_check as base
from scripts.deck_recovery_check import ROOT, freeze
from scripts.new_cards_data_spike import Card, write_json

MODEL = "gpt-6.1-sol"
RATES = (2.5, 10.0)
CALLS = (
    ("plan", "meren", MODEL),
    ("plan", "saheeli", MODEL),
    ("review", "meren", MODEL),
    ("review", "saheeli", MODEL),
)
DESTINATION = ROOT / "docs/research/commander-discovery-sol"


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Use the checked cache-write upper input rate, without assuming cache savings."""
    if model != MODEL:
        raise ValueError(f"Unpriced Sol comparison model {model!r}; do not request it")
    return (input_tokens * RATES[0] + output_tokens * RATES[1]) / 1_000_000


def reservation() -> float:
    """Validate the exact four authorized requests and their full bounded costs."""
    expected = (
        ("plan", "meren", MODEL),
        ("plan", "saheeli", MODEL),
        ("review", "meren", MODEL),
        ("review", "saheeli", MODEL),
    )
    if CALLS != expected:
        raise ValueError("Authorization permits exactly four ordered Meren/Saheeli Sol calls")
    return base.Execution(calls=CALLS, price=cost, build_reviews=fixed_reviews).reservation()


def digest(path: Path) -> str:
    """Fingerprint the actual frozen bytes, not a subsequently reformatted document."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_digest(payload: Card) -> str:
    """Match the exact request serialization recorded by the earlier experiment."""
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def read_assessments(prepared: base.Prepared) -> Card:
    """Fail before sending altered or missing frozen assessment data."""
    path = ROOT / prepared.protocol["assessment_file"]
    if not path.exists() or digest(path) != prepared.protocol["assessment_sha256"]:
        raise ValueError(
            f"Frozen assessment changed/missing: {path}; no new request or paid resume"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def fixed_reviews(prepared: base.Prepared, report: Card) -> tuple[Card, Card]:
    """Execute Sol discoveries independently, never adding them to the paired assessment pool."""
    inputs = read_assessments(prepared)
    records = {}
    for case_id, case in prepared.cases.items():
        plans = base.decode_plans(report, case_id)
        leader = base.require_card(prepared.catalog, case["commander"])
        seed = f"{prepared.protocol.get('source', {}).get('sha256', 'test')}|{case_id}|v1"
        controls = [base.require_card(prepared.catalog, name) for name in case["diagnostics"]]
        found = discover(plans[MODEL], prepared.catalog, leader, seed) if MODEL in plans else None
        records[case_id] = {
            "discoveries": {MODEL: base.discovery_record(found, controls)} if found else {},
            "failed_planners": [] if found else [MODEL],
            "assessment_pool": "unchanged Luna/Terra pool; Sol discoveries not injected",
        }
    return inputs, records


def execution(prepared: base.Prepared) -> base.Execution:
    """Verify frozen pools and call scope before opening any paid ledger."""
    reservation()
    read_assessments(prepared)
    return base.Execution(calls=CALLS, price=cost, build_reviews=fixed_reviews)


def verify_prior_requests(prior: base.Prepared, assessments: Card, report: Card) -> None:
    """Require identical payloads to the completed baseline, not merely equivalent card sets."""
    for case_id in prior.cases:
        for phase, payload in [("plan", prior.payloads[case_id]), ("review", assessments[case_id])]:
            rows = [r for r in report["runs"] if r["phase"] == phase and r["case_id"] == case_id]
            if len(rows) != 2 or any(
                r.get("status") != "completed" or r["input_sha256"] != payload_digest(payload)
                for r in rows
            ):
                raise ValueError(f"{case_id}/{phase}: baseline input/status mismatch; no Sol calls")


def prepare() -> base.Prepared:
    """Freeze a new authorization without editing prompts, schemas or exhausted old ledgers."""
    prior = base.prepare()
    path = base.DESTINATION / "assessment-inputs.json"
    assessments = json.loads(path.read_text(encoding="utf-8"))
    results_path = base.DESTINATION / "results.json"
    report = json.loads(results_path.read_text(encoding="utf-8"))
    verify_prior_requests(prior, assessments, report)
    for case_id, payload in assessments.items():
        if base.request_bytes(base.STAGES["review"], payload) > base.STAGES["review"].byte_limit:
            raise ValueError(
                f"{case_id}: frozen assessment exceeds authorized bytes; no truncation"
            )
    copied = DESTINATION / "assessment-inputs.json"
    copied.parent.mkdir(parents=True, exist_ok=True)
    if not copied.exists():
        with copied.open("xb") as stream:
            stream.write(path.read_bytes())
    if digest(copied) != digest(path):
        raise ValueError("Sol assessment bytes differ from baseline; do not overwrite or request")
    protocol = {
        **prior.protocol,
        "version": "commander-discovery-sol-v1",
        "settings": {**prior.protocol["settings"], "service_tier": "default"},
        "calls": CALLS,
        "pricing": {MODEL: RATES},
        "pricing_sources": [f"https://developers.openai.com/api/docs/models/{MODEL}.md"],
        "reserved_usd": reservation(),
        "assessment_file": copied.relative_to(ROOT).as_posix(),
        "assessment_sha256": digest(copied),
        "baseline_results_sha256": digest(results_path),
        "baseline_retrieval_sha256": digest(base.DESTINATION / "retrieval.json"),
        "baseline_model_cutoff": "2026-02-16",
        "sol_model_cutoff": "2026-04-30",
        "comparison": "same requests/pools; independent Sol discoveries recorded separately",
    }
    freeze(DESTINATION / "inputs.json", protocol)
    return replace(prior, protocol=protocol)


def main() -> None:
    """Prepare, execute once, or replay; only the explicit live mode loads API credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    prepared = prepare()
    print("Sol reserved upper estimated spend:", reservation())
    path = DESTINATION / "results.json"
    if args.live:
        from mtg_helper.config import settings

        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=120
        ) as client:
            report = base.Experiment(prepared, path, client, execution=execution(prepared)).run()
    elif args.summarize:
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        print("Sol inputs frozen offline; no model calls made.")
        return
    summary = base.summarize(report, read_assessments(prepared), authorized_maximum=4)
    write_json(DESTINATION / "summary.json", summary)
    print("Sol attempts:", summary["attempts"], "estimated spend:", summary["estimated_cost_usd"])


if __name__ == "__main__":
    main()
