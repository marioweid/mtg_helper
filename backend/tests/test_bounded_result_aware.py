"""Fresh-ledger safety and distinct engine/function grading without external calls."""

import json
from pathlib import Path
from typing import Any

import pytest

from mtg_helper.services.recommendations import budget, provider
from scripts import bounded_result_aware_calls as calls
from tests import test_result_aware_calls as previous

pytestmark = pytest.mark.no_db


def protocol() -> dict[str, Any]:
    data = previous.protocol()
    for case in data["cases"].values():
        payload = calls.term_selection.Workflow(context=case["context"]).payload("plan", {})
        case["request"] = calls.make_request(payload, "baseline")
    data |= {
        "version": calls.VERSION,
        "profile": budget.BOUNDED_TERMS_VERSION,
        "code_hashes": calls.code_hashes(),
        "refinement_instructions": calls.REFINEMENT,
        "contributions": calls.CONTRIBUTIONS,
    }
    return json.loads(json.dumps(data))


class Sender(provider.Provider):
    def __init__(self, *, failure: str = "") -> None:
        super().__init__("test")
        self.count = 0
        self.failure = failure

    async def request(self, frozen: dict[str, Any]) -> dict[str, Any]:
        self.count += 1
        ledger = json.loads((calls.DESTINATION / "attempts.json").read_text())
        assert ledger["attempts"][-1]["request_sha256"] == calls.digest(frozen)
        assert ledger["attempts"][-1]["state"] == "attempted"
        payload = json.loads(frozen["input"])
        if "observations" in payload:
            assert payload["previous_queries"][0]["purpose"] == payload["strategy"]
            assert payload["observations"]["combined_total"] == 1
            assert "reference_hit" not in json.dumps(payload)
            assert "contribution" not in json.dumps(payload)
        if self.failure == "timeout":
            raise TimeoutError("External provider timed out")
        raw = {
            "oracle_tag_ids": [],
            "printed_keywords": ["Flying"],
            "queries": [
                {
                    "purpose": payload["strategy"],
                    "groups": [{"oracle_tag_indices": [], "printed_keyword_indices": [0]}],
                    "card_types_any": ["Creature"],
                }
            ],
        }
        return {
            "status": "completed",
            "model": budget.MODEL,
            "service_tier": "default",
            "usage": None
            if self.failure == "usage"
            else {"input_tokens": 100, "output_tokens": 50},
            "output": "{}" if self.failure == "output" else json.dumps(raw),
        }


@pytest.fixture
def isolated_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> previous.Connection:
    conn = previous.Connection()

    async def connect(dsn):
        return conn

    monkeypatch.setattr(calls, "DESTINATION", tmp_path)
    # The protocol document is a frozen input, not a request payload or reference fixture.
    (tmp_path / "README.md").write_text("Frozen protocol for external-IO-only fixture.")
    monkeypatch.setattr(calls.asyncpg, "connect", connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres/mtg_helper")
    return conn


@pytest.mark.asyncio
async def test_new_four_call_ledger_uses_v3_and_never_resumes(isolated_io) -> None:
    data = protocol()
    assert calls.reservation() == 119_200
    sender = Sender()
    ledger = await calls.run_live(data, sender)
    assert sender.count == 4 and "stopped" not in ledger
    assert all("local_results" in row for row in ledger["attempts"])
    assert all(
        "oracle_tag_indices" not in json.dumps(row["accepted"]) for row in ledger["attempts"]
    )
    calls.save_packet(data, ledger)
    packet = json.loads((calls.DESTINATION / "review-packet.json").read_text())
    assert len(packet["cases"]["yuna"]["cards"]) == 1
    assert "reference_hit" not in json.dumps(packet) and "baseline" not in json.dumps(packet)
    with pytest.raises(FileExistsError):
        await calls.run_live(data, sender)
    assert sender.count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["usage", "output", "timeout", "data"])
async def test_fresh_attempts_fail_closed_without_retry_or_dependent_calls(
    isolated_io, failure
) -> None:
    sender = Sender(failure=failure)
    isolated_io.changed = failure == "data"
    ledger = await calls.run_live(protocol(), sender)
    assert "stopped" in ledger
    assert sender.count == (0 if failure == "data" else 1)
    if failure in {"usage", "timeout"}:
        assert "estimated_cost_microusd" not in ledger["attempts"][0]


def test_changed_rubric_and_oversized_requests_are_rejected(isolated_io) -> None:
    data = protocol()
    data["contributions"]["engine"][1] = 2
    with pytest.raises(ValueError, match="Frozen protocol changed"):
        calls.validate_protocol(data)
    payload = calls.term_selection.Workflow(context=data["cases"]["yuna"]["context"]).payload(
        "plan", {}
    )
    with pytest.raises(ValueError, match="byte bound"):
        calls.make_request(payload | {"observations": "x" * 120_000}, "refined")


def test_new_grades_distinguish_engine_from_requested_function_on_both_decks() -> None:
    report = {"runs": []}
    ratings = {"cases": {}}
    for key in ("yuna", "meren"):
        ratings["cases"][key] = [
            {"oracle_id": "a", "rating": "direct", "contribution": "requested"},
            {"oracle_id": "b", "rating": "direct", "contribution": "engine"},
        ]
        report["runs"].extend(
            [
                {
                    "deck": key,
                    "arm": "baseline",
                    "cards": [{"oracle_id": "a"}],
                    "reference_ids_in_pool": ["x"],
                },
                {
                    "deck": key,
                    "arm": "refined",
                    "cards": [{"oracle_id": "b"}],
                    "reference_ids_in_pool": ["x"],
                },
            ]
        )
    graded = calls.grade_arms(report, ratings)
    assert [row["fit_score"] for row in graded["arms"]] == [2, 3, 2, 3]
    assert graded["recommend_adoption"] is True
