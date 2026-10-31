"""Source observations and lead-review accounting for the result-aware experiment."""

import json
from collections import Counter
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.services.recommendations.discovery import card_facts
from mtg_helper.services.recommendations.search_sql import MATCH_SQL
from scripts.discover_relevance_check import EMPTY_ID, score

WEIGHTS = {"direct": 2, "support": 1, "conditional": 0, "uncertain": 0, "off_plan": -1}
_POOL_SQL = MATCH_SQL.split(", page AS MATERIALIZED (", 1)[0].replace("$11", "$6") + (
    " SELECT e.*,n.source_facts FROM eligible e "
    "JOIN new_card_catalog n ON n.oracle_id=e.oracle_id "
    "ORDER BY e.rank_missing,e.sort_rank,lower(e.name),e.oracle_id::text"
)


def sample_positions(count: int) -> list[int]:
    """Select fixed rank quantiles without inspecting names, grades or reference overlap."""
    if count < 0:
        raise ValueError("A result count cannot be negative")
    return sorted({p for p in (0, 1, count // 2, count - 2, count - 1) if 0 <= p < count})


async def ranked_pool(
    conn: asyncpg.Connection, leader: dict[str, Any], queries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Use unchanged production eligibility/order with empty-deck exclusions for recovery."""
    rows = await conn.fetch(
        _POOL_SQL,
        json.dumps(queries),
        leader["color_identity"],
        [UUID(leader["oracle_id"])],
        EMPTY_ID,
        EMPTY_ID,
        None,
    )
    return [
        dict(row)
        | {"oracle_id": str(row["oracle_id"]), "source_facts": json.loads(row["source_facts"])}
        for row in rows
    ]


def facts(row: dict[str, Any]) -> dict[str, Any]:
    """Expose public gameplay facts, not popularity, evaluator labels or deck membership."""
    return card_facts(row["source_facts"])


async def observe(
    conn: asyncpg.Connection, leader: dict[str, Any], queries: list[dict[str, Any]]
) -> dict[str, Any]:
    """Show actual counts and source samples, without labeling any match as a good inclusion."""
    searches = []
    for index, query in enumerate(queries):
        rows = await ranked_pool(conn, leader, [query])
        positions = sample_positions(len(rows))
        searches.append(
            {
                "query_index": index,
                "query": query,
                "total": len(rows),
                "sample_ranks": [position + 1 for position in positions],
                "samples": [facts(rows[position]) for position in positions],
            }
        )
    combined = await ranked_pool(conn, leader, queries)
    return {
        "searches": searches,
        "combined_total": len(combined),
        "combined_top_ten": [facts(row) for row in combined[:10]],
        "sampling": "first, second, middle, penultimate, last; no replacements or relevance labels",
    }


def recovery(rows: list[dict[str, Any]], answers: set[str]) -> dict[str, Any]:
    """Separate exact-list recovery from strategic judgments, retaining reachable identities."""
    return score(rows, answers) | {
        "reference_hits_at_20": sum(row["oracle_id"] in answers for row in rows[:20]),
        "reference_ids_in_pool": sorted({row["oracle_id"] for row in rows} & answers),
    }


def review_packet(report: dict[str, Any], cases: dict[str, Any]) -> dict[str, Any]:
    """Hide arm, rank and answer flags while applying one grade to each card/deck identity."""
    packet: dict[str, Any] = {"cases": {}}
    for key, context in cases.items():
        unique = {}
        for run in report["runs"]:
            if run["deck"] == key and "cards" in run:
                for card in run["cards"][:20]:
                    unique[card["oracle_id"]] = {
                        k: v for k, v in card.items() if k != "reference_hit"
                    }
        packet["cases"][key] = {
            "commander": card_facts(context["leader"]),
            "strategy": context["context"]["prose"],
            "cards": sorted(unique.values(), key=lambda card: card["name"].lower()),
        }
    return packet


def oracle_text(card: dict[str, Any]) -> str:
    return "\n".join(
        [
            card.get("oracle_text") or "",
            *(face.get("oracle_text") or "" for face in card.get("faces", [])),
        ]
    )


def validate_ratings(packet: dict[str, Any], ratings: dict[str, Any]) -> None:
    """Require complete, unique grading with literal source quotations before comparing arms."""
    if set(ratings["cases"]) != set(packet["cases"]):
        raise ValueError("Ratings must cover exactly the two review-packet decks")
    for key, case in packet["cases"].items():
        cards = {card["oracle_id"]: card for card in case["cards"]}
        entries = ratings["cases"][key]
        identities = [entry["oracle_id"] for entry in entries]
        if len(identities) != len(set(identities)) or set(identities) != set(cards):
            raise ValueError(f"{key}: ratings must cover every packet card exactly once")
        for entry in entries:
            if entry["rating"] not in WEIGHTS or len(entry["reason"].strip()) < 20:
                raise ValueError(f"{key}/{entry['oracle_id']}: invalid rating or missing rationale")
            text = oracle_text(cards[entry["oracle_id"]])
            quote = entry["quote"]
            missing = not text.strip() and entry["rating"] == "uncertain" and not quote
            if not missing and (len(quote) < 10 or quote not in text):
                raise ValueError(
                    f"{key}/{entry['oracle_id']}: quotation is not literal source text"
                )


def grade_arms(report: dict[str, Any], ratings: dict[str, Any]) -> dict[str, Any]:
    """Score the same card consistently across arms; these grades never affect matching."""
    results: list[dict[str, Any]] = []
    for run in report["runs"]:
        if "cards" not in run:
            continue
        by_id = {entry["oracle_id"]: entry for entry in ratings["cases"][run["deck"]]}
        grades = [by_id[card["oracle_id"]]["rating"] for card in run["cards"][:20]]
        results.append(
            {
                "deck": run["deck"],
                "arm": run["arm"],
                "reviewed": len(grades),
                "counts": dict(Counter(grades)),
                "fit_score": sum(WEIGHTS[g] for g in grades),
            }
        )
    gates = {}
    for key in ratings["cases"]:
        pair = {row["arm"]: row for row in results if row["deck"] == key}
        runs = {row["arm"]: row for row in report["runs"] if row["deck"] == key}
        if set(pair) != {"baseline", "refined"}:
            gates[key] = {"passed": False, "reason": "Missing a complete pair"}
            continue
        baseline = set(runs["baseline"]["reference_ids_in_pool"])
        refined = set(runs["refined"]["reference_ids_in_pool"])
        retention = len(baseline & refined) / len(baseline) if baseline else None
        improved = pair["refined"]["fit_score"] > pair["baseline"]["fit_score"]
        off_plan = pair["refined"]["counts"].get("off_plan", 0) <= pair["baseline"]["counts"].get(
            "off_plan", 0
        )
        coverage = retention is not None and retention >= 0.9
        gates[key] = {
            "fit_improved": improved,
            "off_plan_not_increased": off_plan,
            "baseline_reference_retention": retention,
            "coverage_guard_passed": coverage,
            "passed": improved and off_plan and coverage,
        }
    return {
        "arms": results,
        "gates": gates,
        "recommend_adoption": len(gates) == 2 and all(g["passed"] for g in gates.values()),
        "grading": "Lead assistant judgment, not independent human truth or accuracy",
    }
