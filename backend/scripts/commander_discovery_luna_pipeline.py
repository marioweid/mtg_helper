"""Fixed, isolated Luna planning/feedback/revision workflow; no provider requests here."""

import hashlib
import json
from dataclasses import dataclass

from mtg_helper.services.recommendations import refinement as refined
from mtg_helper.services.recommendations.discovery import card_facts, discover, eligible_cards
from mtg_helper.services.recommendations.profiles import (
    CLOSED_REVIEW_PROMPT,
    REVISION_PROMPT,
    RULES_PROMPT,
)
from scripts import commander_discovery_check as base
from scripts.deck_recovery_check import ROOT, freeze
from scripts.new_cards_data_spike import Card

MODEL = "gpt-5.6-luna"
DESTINATION = ROOT / "docs/research/commander-discovery-luna-refined"
CALLS = tuple(
    (phase, case) for phase in ("plan", "revise", "review") for case in ("meren", "saheeli")
)
BUDGET_USD = 0.25
TIMEOUT_SECONDS = 300
BOUNDS = {"plan": (20_000, 5_000), "revise": (60_000, 5_000), "review": (95_000, 10_000)}


def reservation() -> float:
    """Validate the exact fresh six-call/$0.25 authorization and reserve upper input rates."""
    expected = tuple(
        (phase, case) for phase in ("plan", "revise", "review") for case in ("meren", "saheeli")
    )
    if CALLS != expected or MODEL != "gpt-5.6-luna" or BUDGET_USD != 0.25:
        raise ValueError("Fresh authorization permits six fixed Luna calls with a $0.25 cap")
    total = sum(base.estimated_cost(MODEL, *BOUNDS[phase]) for phase, _ in CALLS)
    if not 0 <= total <= BUDGET_USD:
        raise ValueError("Reservation exceeds $0.25; do not send requests")
    return total


def stage(phase: str, payload: Card) -> base.Stage:
    """Resolve the fixed phase prompt/schema; review coverage binds to this exact payload.

    Args:
        phase: Fixed plan, revise or review phase.
        payload: Exact source context including review candidate IDs.

    Returns:
        Prompt, schema and input/output bounds for this request.
    """
    schema = refined.review_type(payload) if phase == "review" else refined.RefinementPlan
    prompts = {
        "plan": base.PLAN_PROMPT + RULES_PROMPT,
        "revise": base.PLAN_PROMPT + RULES_PROMPT + REVISION_PROMPT,
        "review": base.REVIEW_PROMPT + CLOSED_REVIEW_PROMPT,
    }
    return base.Stage(prompts[phase], schema, *BOUNDS[phase])


def decode_plan(report: Card, phase: str, case_id: str) -> refined.RefinementPlan:
    """Refuse failed prerequisites; no fallback plan or automatic retry is invented.

    Args:
        report: Preserved receipt containing the prerequisite response.
        phase: Plan or revision prerequisite.
        case_id: Declared evaluation commander case.

    Returns:
        Validated complete plan, without repairing the raw response.
    """
    rows = [r for r in report["runs"] if r["phase"] == phase and r["case_id"] == case_id]
    if len(rows) != 1:
        raise ValueError(f"{case_id}/{phase}: missing/duplicate prerequisite; stop dependent calls")
    run = rows[0]
    if run.get("status") != "completed":
        raise ValueError(f"{case_id}/{phase}: prerequisite did not complete; stop dependent calls")
    return refined.RefinementPlan.model_validate(
        json.loads(run["output"], object_pairs_hook=refined.unique_object)
    )


@dataclass(kw_only=True)
class Workspace:
    """Own pinned sources and per-phase observations for this fixed evaluation."""

    prepared: base.Prepared
    entries: Card
    pools: Card
    initial: Card

    def observe(self, plan: refined.RefinementPlan, case_id: str) -> Card:
        """Execute declared operations without admission/ranking diagnostics in model inputs."""
        leader = base.require_card(self.prepared.catalog, self.prepared.cases[case_id]["commander"])
        seed = f"{self.prepared.protocol['source']['sha256']}|{case_id}|v1"
        return refined.planning_observation(plan, self.prepared.catalog, leader, self.entries, seed)

    def payload(self, phase: str, case_id: str, report: Card) -> tuple[Card, Card]:
        """Build request and separate provenance; replacement discovery uses only revision.

        Args:
            phase: Fixed plan, revise or review phase.
            case_id: Declared commander evaluation case.
            report: Preserved preceding responses.

        Returns:
            Exact model payload and separate execution/admission observations.
        """
        if phase == "plan":
            return self.initial[case_id], {}
        old = decode_plan(report, "plan", case_id)
        before = self.observe(old, case_id)
        if phase == "revise":
            return self.initial[case_id] | {
                "initial_plan": old.model_dump(),
                "observations": before,
            }, before
        new = decode_plan(report, "revise", case_id)
        after = self.observe(new, case_id)
        rules = {r["key"]: r for r in self.pools[case_id]["rules"]}
        for observation in (before, after):
            for result in observation["rule_searches"]:
                for entry in result["selected"]:
                    key = f"R:{entry['key']}"
                    rules[key] = {"key": key, "text": entry["text"]}
        inputs = self.pools[case_id] | {
            "revised_plan": new.model_dump(),
            "rules": list(rules.values()),
        }
        return inputs, {
            "before": before,
            "after": after,
            "admission": self.admission(old, new, case_id),
        }

    def admission(
        self, old: refined.RefinementPlan, new: refined.RefinementPlan, case_id: str
    ) -> Card:
        """Measure independent discovery before the unchanged diagnostic-rich review pool."""
        case = self.prepared.cases[case_id]
        leader = base.require_card(self.prepared.catalog, case["commander"])
        controls = [base.require_card(self.prepared.catalog, name) for name in case["diagnostics"]]
        seed = f"{self.prepared.protocol['source']['sha256']}|{case_id}|v1"
        return {
            label: base.discovery_record(
                discover(plan, self.prepared.catalog, leader, seed), controls
            )
            for label, plan in (("initial", old), ("replacement", new))
        }


def verify_pools(pools: Card) -> None:
    """Require exact assessment facts used by both completed baseline models, not edited pools."""
    if set(pools) != {"meren", "saheeli"}:
        raise ValueError("Assessment pools must contain exactly Meren and Saheeli; no calls")
    receipt = json.loads((base.DESTINATION / "results.json").read_text(encoding="utf-8"))
    for case_id, payload in pools.items():
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
        rows = [r for r in receipt["runs"] if r["phase"] == "review" and r["case_id"] == case_id]
        if len(rows) != 2 or any(
            r.get("status") != "completed" or r["input_sha256"] != digest for r in rows
        ):
            raise ValueError(f"{case_id}: assessment facts differ from baseline receipt; no calls")


def prepare() -> Workspace:
    """Freeze fresh experiment inputs and provenance without loading credentials or making calls."""
    reservation()
    prepared = base.prepare()
    fixture = prepared.rules
    path = ROOT / "backend/.cache/commander-discovery/rules-20260925.txt"
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != fixture["sha256"]:
        raise ValueError(
            f"Missing/changed pinned full rules: {path}; restore source before execution"
        )
    entries = refined.parse_rules(path.read_text(encoding="utf-8-sig"))
    pool_path = base.DESTINATION / "assessment-inputs.json"
    pools = json.loads(pool_path.read_text(encoding="utf-8"))
    verify_pools(pools)
    initial = {}
    for case_id, case in prepared.cases.items():
        leader = base.require_card(prepared.catalog, case["commander"])
        if pools[case_id]["commander"] != card_facts(leader):
            raise ValueError(f"{case_id}: original review commander differs from pinned source")
        initial[case_id] = prepared.payloads[case_id] | {
            "source_prefixes": refined.source_prefixes(eligible_cards(prepared.catalog, leader)),
            "rules_source": {
                "url": fixture["source"],
                "sha256": fixture["sha256"],
                "entry_count": len(entries),
            },
        }
    protocol = {
        "version": "luna-refined-pipeline-v1",
        "model": MODEL,
        "calls": CALLS,
        "budget_usd": BUDGET_USD,
        "reserved_usd": reservation(),
        "input_bounds": BOUNDS,
        "source": prepared.protocol["source"],
        "rules_sha256": fixture["sha256"],
        "rules_source": fixture["source"],
        "initial_inputs": initial,
        "assessment_source": pool_path.relative_to(ROOT).as_posix(),
        "assessment_source_sha256": hashlib.sha256(pool_path.read_bytes()).hexdigest(),
        "candidate_policy": "Original 64 identities/facts per case unchanged; discoveries separate",
        "revision_policy": "Complete replacement, not union; preserve initial and final admission",
        "prompts": {p: stage(p, pools["meren"]).prompt for p in BOUNDS},
        "plan_schema": refined.RefinementPlan.model_json_schema(),
        "review_schemas": {
            key: refined.review_type(pool).model_json_schema() for key, pool in pools.items()
        },
        "pricing": {MODEL: base.RATES[MODEL]},
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md",
        "pricing_basis": "$0.20/M input, $0.25/M cache-write upper, $1.20/M output; no savings",
        "settings": {
            "service_tier": "default",
            "reasoning": "low",
            "verbosity": "low",
            "retries": 0,
            "store": False,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "authorization": "Fresh six-call Luna run, estimated $0.25 cap; never resume old ledgers",
    }
    freeze(DESTINATION / "inputs.json", protocol)
    return Workspace(prepared=prepared, entries=entries, pools=pools, initial=initial)
