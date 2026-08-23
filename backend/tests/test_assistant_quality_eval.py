"""Tests for offline MTG Assistant quality evaluation contracts."""

from pathlib import Path

import pytest

from scripts.eval_assistant_quality import load_cases, score_run, score_text

pytestmark = pytest.mark.no_db

_CASES = Path(__file__).parents[1] / "evals" / "assistant_quality_cases.json"


def test_quality_corpus_contains_ten_unique_complete_cases() -> None:
    cases = load_cases(_CASES)

    assert len(cases) == 10
    assert len({case.id for case in cases}) == 10
    assert all(case.rubric for case in cases)
    assert all(case.required_phrases or case.forbidden_phrases for case in cases)


def test_quality_corpus_covers_required_behaviors() -> None:
    case_ids = {case.id for case in load_cases(_CASES)}

    assert case_ids == {
        "camellia-food-win-conditions",
        "camellia-food-draw-follow-up",
        "avoid-existing-card",
        "targeted-replacement",
        "mana-base-diagnosis",
        "memory-budget-limit",
        "no-infinite-combos",
        "camellia-altar-invalid-two-card-loop",
        "broad-value-theme",
        "ungrounded-recommendation",
    }


def test_score_text_detects_forbidden_claims_case_insensitively() -> None:
    case = next(
        case for case in load_cases(_CASES) if case.id == "camellia-altar-invalid-two-card-loop"
    )

    result = score_text(case, "CAMELLIA + ASHNOD'S ALTAR IS INFINITE and makes replacement Food.")

    assert result.passed is False
    assert result.forbidden_matches == [
        "Camellia + Ashnod's Altar is infinite",
        "replacement Food",
    ]


def test_score_run_checks_observable_tool_calls() -> None:
    case = next(case for case in load_cases(_CASES) if case.id == "broad-value-theme")

    result = score_run(case, "Food sacrifice draw fits Camellia.", ["search_themes"])

    assert result.passed is False
    assert result.missing_tools == ["find_cards"]
    assert result.unexpected_tools == ["search_themes"]
