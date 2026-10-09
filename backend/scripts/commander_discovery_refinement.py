"""Offline refinement replay; no provider calls."""

import hashlib
import json

from mtg_helper.services.recommendations.refinement import (
    RefinementPlan,
    parse_rules,
    planning_observation,
    review_type,
)
from scripts.deck_recovery_check import ROOT, freeze
from scripts.new_cards_data_spike import write_json


def main() -> None:
    """Replay old Luna plans into new offline observations; never load credentials or call AI."""
    from scripts import commander_discovery_check as base

    prepared = base.prepare()
    fixture = json.loads((base.FIXTURES / "rules.json").read_text(encoding="utf-8"))
    path = ROOT / "backend/.cache/commander-discovery/rules-20260925.txt"
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != fixture["sha256"]:
        raise ValueError(f"Missing/changed complete rules source: {path}; restore the pinned cache")
    entries = parse_rules(path.read_text(encoding="utf-8-sig"))
    report = json.loads((base.DESTINATION / "results.json").read_text(encoding="utf-8"))
    pools = json.loads((base.DESTINATION / "assessment-inputs.json").read_text(encoding="utf-8"))
    destination = ROOT / "docs/research/commander-discovery-refinement"
    freeze(
        destination / "protocol-v2.json",
        {
            "version": "offline-refinement-foundations-v2",
            "baseline_model": "gpt-5.6-luna",
            "paid_calls": 0,
            "rules_sha256": fixture["sha256"],
            "source": prepared.protocol["source"],
            "plan_schema": RefinementPlan.model_json_schema(),
            "review_schemas": {
                case: review_type(data).model_json_schema() for case, data in pools.items()
            },
            "scope": "offline prototype only; no app integration or improved-model-output claim",
        },
    )
    observations = {}
    for case_id, case in prepared.cases.items():
        old = base.decode_plans(report, case_id)["gpt-5.6-luna"]
        plan = RefinementPlan.model_validate(old.model_dump() | {"rule_searches": []})
        leader = base.require_card(prepared.catalog, case["commander"])
        seed = f"{prepared.protocol['source']['sha256']}|{case_id}|v1"
        observations[case_id] = planning_observation(plan, prepared.catalog, leader, entries, seed)
    write_json(destination / "feedback-v2.json", observations)
    print("Offline Luna feedback/schema preview ready; complete rules entries:", len(entries))
    print("No paid model calls or application changes.")


if __name__ == "__main__":
    main()
