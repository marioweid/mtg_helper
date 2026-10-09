"""Offline checks for the hidden-answer recovery experiment."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from scripts import deck_recovery_check as check
from scripts.deck_recovery_check import parse_fixture

pytestmark = pytest.mark.no_db


def test_commander_after_sideboard_is_not_a_sideboard_card() -> None:
    main, sideboard = parse_fixture(
        "1 Main Card\n\nSIDEBOARD:\n1 Side Card\n\n1 Commander", "Commander"
    )

    assert main == [(1, "Main Card")]
    assert sideboard == [(1, "Side Card")]


@pytest.mark.parametrize("text", ["1 Card", "2 Commander", "0 Card\n1 Commander"])
def test_invalid_fixture_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_fixture(text, "Commander")


def card(name: str, *, type_line: str = "Creature", colors: list[str] | None = None) -> dict:
    return {
        "name": name,
        "oracle_id": name,
        "games": ["paper"],
        "type_line": type_line,
        "color_identity": colors or [],
        "legalities": {"commander": "legal"},
    }


def test_whole_name_wins_over_associated_back_face_and_front_alias_is_supported() -> None:
    original = card("Reanimate", type_line="Sorcery")
    prepared = card("Researcher // Reanimate") | {
        "card_faces": [{"name": "Researcher", "type_line": "Creature"}, {"name": "Reanimate"}]
    }
    modal = card("Awakening // Land") | {
        "card_faces": [{"name": "Awakening", "type_line": "Sorcery"}, {"name": "Land"}]
    }
    catalog = check.build_catalog([prepared, original, modal])

    assert catalog.resolve("Reanimate") == original
    assert catalog.resolve("Awakening") == modal
    assert catalog.resolve("Land") is None
    assert check.is_land(modal) is False
    assert check.is_land(card("Dryad Arbor", type_line="Land Creature")) is True


def test_duplicate_wrong_color_land_and_unknown_suggestions_never_count_as_hits() -> None:
    names = ["Hit", "Hit", "Wrong", "Land", "Unknown", *[f"Other{i}" for i in range(45)]]
    catalog = check.build_catalog(
        [
            card(check.DECKS["yuna"][0], colors=["G", "W", "U"]),
            card("Hit"),
            card("Wrong", colors=["B"]),
            card("Land", type_line="Land"),
            *[card(f"Other{i}") for i in range(45)],
        ]
    )
    output = json.dumps({"cards": [{"name": name, "reason": "A role"} for name in names]})

    result = check.score_output(output, "yuna", catalog, {"Hit", "Wrong", "Land"})

    assert result["exact_hits"] == 1
    assert result["top_ten_hits"] == 1
    assert result["invalid_or_duplicate_count"] == 4
    assert [c["error"] for c in result["cards"][:5]] == [
        None,
        "duplicate",
        "off_color",
        "land",
        "unresolved_or_ambiguous",
    ]
    with pytest.raises(ValueError):
        check.score_output('{"cards": []}', "yuna", catalog, set())


def test_answer_cards_do_not_reach_model_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check, "FIXTURES", tmp_path)
    monkeypatch.setattr(check, "DECKS", {"test": ("Commander", "Counter strategy")})
    (tmp_path / "test.txt").write_text("99 Hidden Answer\n1 Commander", encoding="utf-8")
    catalog = check.build_catalog([card("Commander"), card("Hidden Answer")])

    inputs, answers = check.prepare_cases(catalog)

    assert answers == {"test": {"Hidden Answer"}}
    assert "Hidden Answer" not in json.dumps(inputs)
    assert set(inputs["test"]) == {"commander", "strategy"}


def test_reservation_covers_four_calls_and_rejects_oversized_payloads() -> None:
    assert check.reserve({"yuna": {}, "meren": {}}) < check.BUDGET_USD
    with pytest.raises(ValueError, match="ceiling"):
        check.reserve({"yuna": {"notes": "x" * 1_000_000}, "meren": {}})


def test_changed_call_plan_exceeds_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "CALLS", [*check.CALLS, check.CALLS[0]])
    with pytest.raises(ValueError, match="four distinct"):
        check.reserve({"yuna": {}, "meren": {}})


def test_source_hash_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"changed")
    report = tmp_path / "source-report.json"
    report.write_text(
        json.dumps({"sources": [{"type": "oracle_cards", "sha256": "wrong"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(check, "SOURCE", source)
    monkeypatch.setattr(check, "SOURCE_REPORT", report)
    with pytest.raises(ValueError, match="Source hash"):
        check.source_metadata()


def test_missing_source_and_incomplete_output_remain_failures() -> None:
    catalog = check.build_catalog([])
    report = {
        "runs": [
            {"deck_id": "yuna", "model": "luna", "status": "incomplete"},
            {"deck_id": "meren", "model": "terra", "status": "completed", "output": "{}"},
        ]
    }
    result = check.summarize(report, catalog, {"yuna": set(), "meren": set()})
    assert result["attempts"] == 2
    assert [row["error"] for row in result["runs"]] == [
        "not_completed",
        "invalid_structured_output",
    ]
    assert catalog.resolve("Missing") is None


def test_frozen_inputs_replay_but_changed_inputs_fail(tmp_path: Path) -> None:
    path = tmp_path / "inputs.json"
    check.freeze(path, {"calls": [("yuna", "luna")]})
    check.freeze(path, {"calls": [("yuna", "luna")]})
    with pytest.raises(ValueError, match="Frozen input"):
        check.freeze(path, {"calls": [("yuna", "terra")]})


class Transport:
    def __init__(self, path: Path, *, fail: bool = False) -> None:
        self.path = path
        self.fail = fail
        self.requests: list[dict[str, Any]] = []
        self.responses = self

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        report = json.loads(self.path.read_text(encoding="utf-8"))
        assert report["runs"][-1]["state"] == "attempted"
        if self.fail:
            raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
        return SimpleNamespace(
            status="completed",
            output_text='{"cards": []}',
            model=kwargs["model"],
            incomplete_details=None,
            usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 100}),
        )


@pytest.mark.parametrize("fail", [False, True])
def test_live_is_bounded_checkpointed_and_cannot_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    path = tmp_path / "results.json"
    transport = Transport(path, fail=fail)

    def client(**kwargs: Any) -> OpenAI:
        assert kwargs["max_retries"] == 0
        return cast(OpenAI, transport)

    monkeypatch.setattr(check, "OpenAI", client)
    report = check.run_live({"yuna": {}, "meren": {}}, path)

    assert len(transport.requests) == (1 if fail else 4)
    assert len(report["runs"]) == len(transport.requests)
    assert all(r["store"] is False and "tools" not in r for r in transport.requests)
    with pytest.raises(FileExistsError):
        check.run_live({"yuna": {}, "meren": {}}, path)
    assert len(transport.requests) == (1 if fail else 4)
