"""Two newly authorized Sol assessment calls, $0.60 cap, 300s timeout, no automatic retries.

This separate receipt preserves the earlier timeout. Default prepares offline; --live executes
once; --summarize replays offline. No planning calls, pool changes or production changes.
"""

import argparse
import json
from dataclasses import replace

from openai import OpenAI

from scripts import commander_discovery_check as base
from scripts import commander_discovery_sol_check as sol
from scripts.deck_recovery_check import ROOT, freeze
from scripts.new_cards_data_spike import Card, write_json

CALLS = (("review", "meren", sol.MODEL), ("review", "saheeli", sol.MODEL))
BUDGET_USD = 0.60
TIMEOUT_SECONDS = 300
DESTINATION = ROOT / "docs/research/commander-discovery-sol-assessment"


def fixed_inputs(prepared: base.Prepared, report: Card) -> tuple[Card, Card]:
    """Reuse original assessment inputs without generating any additional planner output."""
    inputs = sol.read_assessments(prepared)
    records = {
        "planning_report_sha256": prepared.protocol.get("prior_sol_results_sha256"),
        "comparison": "assessment-only; independent discoveries remain in the prior Sol report",
    }
    return inputs, records


def reservation() -> float:
    """Validate this fresh, exact two-call authorization and its $0.60 estimated ceiling."""
    if CALLS != (("review", "meren", sol.MODEL), ("review", "saheeli", sol.MODEL)):
        raise ValueError("Authorization permits exactly two ordered Sol assessment calls")
    return base.Execution(
        calls=CALLS, price=sol.cost, build_reviews=fixed_inputs, ceiling_usd=BUDGET_USD
    ).reservation()


def execution(prepared: base.Prepared) -> base.Execution:
    """Check the frozen data and scope before opening the new single-use ledger."""
    reservation()
    sol.read_assessments(prepared)
    return base.Execution(
        calls=CALLS, price=sol.cost, build_reviews=fixed_inputs, ceiling_usd=BUDGET_USD
    )


def prepare() -> base.Prepared:
    """Preserve the incomplete receipt while freezing an explicitly authorized new attempt set."""
    prior = sol.prepare()
    path = sol.DESTINATION / "results.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    history = [(r["phase"], r["case_id"], r.get("status"), r.get("error")) for r in report["runs"]]
    expected = [
        ("plan", "meren", "completed", None),
        ("plan", "saheeli", "completed", None),
        ("review", "meren", None, "APITimeoutError"),
    ]
    if history != expected:
        raise ValueError("Prior Sol receipt differs from authorized timeout extension; no calls")
    old = ROOT / prior.protocol["assessment_file"]
    copied = DESTINATION / "assessment-inputs.json"
    copied.parent.mkdir(parents=True, exist_ok=True)
    if not copied.exists():
        with copied.open("xb") as stream:
            stream.write(old.read_bytes())
    if sol.digest(copied) != sol.digest(old):
        raise ValueError("New assessment copy differs from original; do not overwrite or request")
    protocol = {
        **prior.protocol,
        "version": "commander-discovery-sol-assessment-v1",
        "calls": CALLS,
        "settings": {**prior.protocol["settings"], "client_timeout_seconds": TIMEOUT_SECONDS},
        "budget_usd": BUDGET_USD,
        "reserved_usd": reservation(),
        "assessment_file": copied.relative_to(ROOT).as_posix(),
        "assessment_sha256": sol.digest(copied),
        "prior_sol_results_sha256": sol.digest(path),
        "prior_sol_spend": "two plans priced; one timeout potentially billed, usage unknown",
        "authorization": "two additional calls: Meren reissue once, Saheeli first attempt",
    }
    freeze(DESTINATION / "inputs.json", protocol)
    return replace(prior, protocol=protocol)


def main() -> None:
    """Prepare, make the two newly authorized requests once, or replay the separate receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    prepared = prepare()
    print("Assessment reserved upper estimated spend:", reservation())
    path = DESTINATION / "results.json"
    if args.live:
        from mtg_helper.config import settings

        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            max_retries=0,
            timeout=TIMEOUT_SECONDS,
        ) as client:
            report = base.Experiment(prepared, path, client, execution=execution(prepared)).run()
    elif args.summarize:
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        print("Assessment-only authorization prepared offline; no model calls made.")
        return
    summary = base.summarize(report, sol.read_assessments(prepared), authorized_maximum=2)
    write_json(DESTINATION / "summary.json", summary)
    print(
        "Assessment attempts:",
        summary["attempts"],
        "estimated spend:",
        summary["estimated_cost_usd"],
    )


if __name__ == "__main__":
    main()
