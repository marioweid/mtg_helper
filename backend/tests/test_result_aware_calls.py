"""One-shot budget and observation guards; only external PostgreSQL/provider IO is substituted."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from mtg_helper.services.recommendations import budget, provider
from scripts import result_aware_calls as calls
from scripts.deck_recovery_check import DECKS

pytestmark = pytest.mark.no_db


def protocol() -> dict[str, Any]:
    cases = {}
    for index, (key, (name, brief)) in enumerate(DECKS.items(), 1):
        leader = {
            "oracle_id": str(UUID(int=index)),
            "name": name,
            "color_identity": [],
            "legalities": {"commander": "legal"},
            "keywords": [],
            "card_faces": [],
        }
        context = {
            "prose": brief,
            "commanders": [leader],
            "source_hash": "source",
            "strategy_revision": None,
            "oracle_tags": [],
            "printed_keywords": ["Flying"],
        }
        payload = calls.term_queries.Workflow(context=context).payload("plan", {})
        cases[key] = {
            "leader": leader,
            "context": context,
            "request": calls.make_request(payload, "baseline"),
        }
    data = {
        "version": "result-aware-four-call-v1",
        "model": budget.MODEL,
        "call_order": calls.CALLS,
        "input_bounds": calls.INPUT_BOUNDS,
        "output_bound": calls.OUTPUT_BOUND,
        "reserved_microusd": calls.reservation(),
        "cap_microusd": calls.CAP_MICROUSD,
        "code_hashes": calls.code_hashes(),
        "fixture_hashes": calls.fixture_hashes(),
        "refinement_instructions": calls.REFINEMENT,
        "source": {
            "source_sha256": "source",
            "tag_sha256": "tags",
            "published_at": "time",
            "ranking_fingerprint": "ranks",
        },
        "cases": cases,
    }
    return json.loads(json.dumps(data))


def test_reservation_is_below_approved_ceiling_and_protocol_changes_are_rejected() -> None:
    data = protocol()
    assert calls.reservation() == 119_200 < 150_000
    calls.validate_protocol(data)
    data["call_order"].reverse()
    with pytest.raises(ValueError, match="protocol changed"):
        calls.validate_protocol(data)


def test_oversized_requests_fail_without_silently_truncating_facts() -> None:
    data = protocol()
    payload = calls.term_queries.Workflow(context=data["cases"]["yuna"]["context"]).payload(
        "plan", {}
    )
    payload["strategy"] = "x" * 120_000
    with pytest.raises(ValueError):
        calls.make_request(payload, "refined")
    assert len(payload["strategy"]) == 120_000


def test_production_output_changes_cannot_exceed_the_experiment_reservation(monkeypatch) -> None:
    data = protocol()
    payload = calls.term_queries.Workflow(context=data["cases"]["yuna"]["context"]).payload(
        "plan", {}
    )
    monkeypatch.setattr(budget, "TERMS_BOUNDS", {"plan": (80_000, 4_001)})
    with pytest.raises(ValueError, match="output bound changed"):
        calls.make_request(payload, "baseline")


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Connection:
    changed = False

    def transaction(self, **kwargs):
        assert kwargs["readonly"] is True
        return Transaction()

    async def fetchrow(self, sql):
        return {"source_sha256": "source", "tag_sha256": "tags", "published_at": "time"}

    async def fetchval(self, sql):
        return "changed" if self.changed else "ranks"

    async def fetch(self, sql, *args):
        facts = {
            "oracle_id": str(UUID(int=9)),
            "name": "Public source sample",
            "keywords": ["Flying"],
            "oracle_text": "Flying. Whenever a creature dies, draw a card.",
            "card_faces": [],
            "type_line": "Creature",
            "legalities": {"commander": "legal"},
        }
        return [
            {
                "oracle_id": UUID(int=9),
                "source_facts": json.dumps(facts),
                "global_popularity_rank": 1,
            }
        ]

    async def close(self):
        pass


class Sender(provider.Provider):
    def __init__(self, *, missing_usage: bool = False, invalid_output: bool = False) -> None:
        super().__init__("test")
        self.count = 0
        self.missing_usage = missing_usage
        self.invalid_output = invalid_output

    async def request(self, frozen: dict[str, Any]) -> dict[str, Any]:
        self.count += 1
        ledger = json.loads((calls.DESTINATION / "attempts.json").read_text())
        assert ledger["attempts"][-1]["state"] == "attempted"
        assert ledger["attempts"][-1]["request_sha256"] == calls.digest(frozen)
        payload = json.loads(frozen["input"])
        if "observations" in payload:
            assert payload["previous_queries"][0]["purpose"] == payload["strategy"]
            assert payload["observations"]["combined_total"] == 1
            assert "reference" not in json.dumps(payload).lower()
            assert "rating" not in json.dumps(payload).lower()
        queries = [
            {
                "purpose": payload["strategy"],
                "groups": [{"oracle_tag_ids": [], "printed_keywords": ["Flying"]}],
                "card_types_any": ["Creature"],
            }
        ]
        return {
            "status": "completed",
            "model": budget.MODEL,
            "service_tier": "default",
            "usage": None if self.missing_usage else {"input_tokens": 100, "output_tokens": 50},
            "output": "{}" if self.invalid_output else json.dumps({"queries": queries}),
        }


@pytest.fixture
def isolated_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Connection:
    conn = Connection()

    async def connect(dsn):
        return conn

    monkeypatch.setattr(calls, "DESTINATION", tmp_path)
    monkeypatch.setattr(calls.asyncpg, "connect", connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres/mtg_helper")
    return conn


@pytest.mark.asyncio
async def test_four_calls_are_checkpointed_refine_own_results_and_cannot_resume(
    isolated_io,
) -> None:
    sender = Sender()
    data = protocol()
    report = await calls.run_live(data, sender)
    assert sender.count == 4
    assert "stopped" not in report
    assert all("local_results" in attempt for attempt in report["attempts"])
    assert (calls.DESTINATION / "requests/meren-refined.json").exists()
    with pytest.raises(FileExistsError):
        await calls.run_live(data, sender)
    assert sender.count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["usage", "output", "data"])
async def test_failures_stop_without_retry_or_dependent_requests(isolated_io, failure: str) -> None:
    sender = Sender(missing_usage=failure == "usage", invalid_output=failure == "output")
    isolated_io.changed = failure == "data"
    report = await calls.run_live(protocol(), sender)
    assert "stopped" in report
    assert sender.count == (0 if failure == "data" else 1)
    if failure == "usage":
        assert "estimated_cost_microusd" not in report["attempts"][0]


def test_observed_frozen_meren_failure_is_rejected_without_trimming() -> None:
    destination = calls.ROOT / "docs/research/discover-result-aware"
    frozen = json.loads((destination / "inputs.json").read_text(encoding="utf-8"))
    ledger = json.loads((destination / "attempts.json").read_text(encoding="utf-8"))
    attempt = next(row for row in ledger["attempts"] if row["deck"] == "meren")
    raw = json.loads(attempt["output"])
    queries = [calls.term_queries.StrategyQuery.model_validate(query) for query in raw["queries"]]
    tags, _ = calls.term_queries.selected_terms(queries)
    assert len(tags) == 13
    allowed = {tag["id"] for tag in frozen["cases"]["meren"]["context"]["oracle_tags"]}
    assert len({str(tag) for tag in tags} - allowed) == 1
    with pytest.raises(ValueError, match="at most 8 distinct"):
        calls.term_queries.Workflow(context=frozen["cases"]["meren"]["context"]).accept(
            "plan", attempt["output"], {}
        )
    schema = frozen["cases"]["meren"]["request"]["text"]["format"]["schema"]
    field = schema["$defs"]["TermGroup"]["properties"]["oracle_tag_ids"]
    assert field["maxItems"] == 40 and "enum" not in field["items"]
