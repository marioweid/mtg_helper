"""Deterministic observation tests; no provider calls or production database writes."""

import pytest

from scripts import result_aware_eval as evaluation
from scripts.result_aware_eval import sample_positions

pytestmark = pytest.mark.no_db


def test_samples_include_top_middle_and_tail_without_repeating_small_pools() -> None:
    assert sample_positions(0) == []
    assert sample_positions(1) == [0]
    assert sample_positions(2) == [0, 1]
    assert sample_positions(3) == [0, 1, 2]
    assert sample_positions(20) == [0, 1, 10, 18, 19]


def test_negative_result_counts_fail_visibly() -> None:
    with pytest.raises(ValueError, match="negative"):
        sample_positions(-1)


def card(identity: str, *, name: str = "Candidate") -> dict:
    return {
        "oracle_id": identity,
        "name": name,
        "oracle_text": "Whenever a creature dies, draw a card.",
        "faces": [],
        "reference_hit": True,
    }


def packet() -> dict:
    return {"cases": {"yuna": {"cards": [card("a")]}, "meren": {"cards": [card("b")]}}}


def ratings() -> dict:
    return {
        "cases": {
            key: [
                {
                    "oracle_id": identity,
                    "rating": "direct",
                    "quote": "Whenever a creature dies",
                    "reason": "A concrete source-supported engine connection.",
                }
            ]
            for key, identity in (("yuna", "a"), ("meren", "b"))
        }
    }


def test_ratings_require_complete_unique_source_grounded_coverage() -> None:
    evaluation.validate_ratings(packet(), ratings())
    invalid = ratings()
    invalid["cases"]["yuna"][0]["quote"] = "Invented card ability"
    with pytest.raises(ValueError, match="literal source"):
        evaluation.validate_ratings(packet(), invalid)
    invalid = ratings()
    invalid["cases"]["yuna"] *= 2
    with pytest.raises(ValueError, match="exactly once"):
        evaluation.validate_ratings(packet(), invalid)


def test_review_packet_hides_arm_rank_and_reference_flags_and_deduplicates() -> None:
    report = {
        "runs": [
            {"deck": "yuna", "arm": "baseline", "cards": [card("a", name="Zed")]},
            {
                "deck": "yuna",
                "arm": "refined",
                "cards": [card("a", name="Zed"), card("b", name="Alpha")],
            },
        ]
    }
    leader = {"name": "Leader", "legalities": {"commander": "legal"}, "card_faces": []}
    result = evaluation.review_packet(
        report, {"yuna": {"leader": leader, "context": {"prose": "Plan"}}}
    )
    assert [row["name"] for row in result["cases"]["yuna"]["cards"]] == ["Alpha", "Zed"]
    assert all(
        "reference_hit" not in row and "arm" not in row and "rank" not in row
        for row in result["cases"]["yuna"]["cards"]
    )


def test_grade_gate_requires_both_decks_and_preserves_baseline_target_identities() -> None:
    report = {"runs": []}
    labels = {"cases": {}}
    for key in ("yuna", "meren"):
        report["runs"].extend(
            [
                {
                    "deck": key,
                    "arm": "baseline",
                    "cards": [card("a")],
                    "reference_ids_in_pool": ["x", "y"],
                },
                {
                    "deck": key,
                    "arm": "refined",
                    "cards": [card("b")],
                    "reference_ids_in_pool": ["x", "y"],
                },
            ]
        )
        labels["cases"][key] = [
            {"oracle_id": "a", "rating": "support"},
            {"oracle_id": "b", "rating": "direct"},
        ]
    assert evaluation.grade_arms(report, labels)["recommend_adoption"] is True
    report["runs"][-1]["reference_ids_in_pool"] = ["x", "different"]
    graded = evaluation.grade_arms(report, labels)
    assert graded["recommend_adoption"] is False
    assert graded["gates"]["meren"]["baseline_reference_retention"] == 0.5
    assert evaluation.grade_arms({"runs": []}, {"cases": {}})["recommend_adoption"] is False


def test_recovery_at_20_scores_ids_without_needing_card_facts() -> None:
    result = evaluation.recovery(
        [{"oracle_id": str(i)} for i in range(25)], {"0", "19", "20", "24"}
    )
    assert result["reference_hits_at_20"] == 2
    assert result["reference_hits_in_pool"] == 4
