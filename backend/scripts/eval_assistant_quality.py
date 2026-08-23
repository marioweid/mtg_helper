"""Validate and deterministically score versioned MTG Assistant evaluation cases."""

import argparse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter


class EvalHistoryTurn(BaseModel):
    """One role-aware turn in an evaluation conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class AssistantEvalCase(BaseModel):
    """One stable behavioral evaluation scenario."""

    id: str = Field(min_length=1)
    deck_fixture: str = Field(min_length=1)
    history: list[EvalHistoryTurn]
    message: str = Field(min_length=1)
    memory: str
    expected_tools: list[str]
    required_phrases: list[str]
    forbidden_phrases: list[str]
    rubric: list[str] = Field(min_length=1)


class AssistantEvalResult(BaseModel):
    """Deterministic phrase checks for one generated answer."""

    case_id: str
    passed: bool
    missing_required: list[str]
    forbidden_matches: list[str]


_CASE_ADAPTER = TypeAdapter(list[AssistantEvalCase])


def load_cases(path: Path) -> list[AssistantEvalCase]:
    """Load and validate a versioned evaluation corpus."""
    cases = _CASE_ADAPTER.validate_json(path.read_bytes())
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"evaluation case ids must be unique: {path}")
    return cases


def score_text(case: AssistantEvalCase, text: str) -> AssistantEvalResult:
    """Score observable required and forbidden phrases without judging prose."""
    normalized = text.casefold()
    missing = [phrase for phrase in case.required_phrases if phrase.casefold() not in normalized]
    forbidden = [phrase for phrase in case.forbidden_phrases if phrase.casefold() in normalized]
    return AssistantEvalResult(
        case_id=case.id,
        passed=not missing and not forbidden,
        missing_required=missing,
        forbidden_matches=forbidden,
    )


def main() -> None:
    """Validate the corpus without making model or database requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).parents[1] / "evals" / "assistant_quality_cases.json",
    )
    parser.add_argument("--validate", action="store_true", help="Validate and list case ids")
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.validate:
        print("\n".join(case.id for case in cases))


if __name__ == "__main__":
    main()
