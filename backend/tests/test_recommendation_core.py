"""Offline application protocol checks, independent of provider and database."""

import importlib.util
import json
from uuid import uuid4

import pytest

from mtg_helper.services.recommendations import refinement
from tests.test_commander_discovery_check import card, query

pytestmark = pytest.mark.no_db


def test_application_has_no_research_script_or_fixture_dependencies() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).parents[1] / "src" / "mtg_helper"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("scripts"), str(path)
            if isinstance(node, ast.Import):
                assert not any(name.name.startswith("scripts") for name in node.names), str(path)
    for name in ("source", "profiles", "discovery", "refinement", "pipeline"):
        text = (root / "services" / "recommendations" / f"{name}.py").read_text()
        assert ".cache" not in text and "backend/evals" not in text


def test_application_protocol_exists_separately_from_frozen_evaluation() -> None:
    assert importlib.util.find_spec("mtg_helper.services.recommendations.pipeline") is not None


def test_application_rejects_empty_plan_without_changing_old_schema() -> None:
    from mtg_helper.services.recommendations.pipeline import usable_plan

    plan = refinement.RefinementPlan(
        intents=["Strategy"], searches=[], named_cards=[], uncertainties=[], rule_searches=[]
    )
    assert plan.intents == ["Strategy"]
    with pytest.raises(ValueError, match="executable"):
        usable_plan(plan, [])
    plan.searches = [query(oracle_text_all=["Draw"])]
    usable_plan(plan, [])


def test_partial_review_retains_good_neighbors_without_repairing_bad_rows() -> None:
    from mtg_helper.services.recommendations.pipeline import partial_review
    from tests.test_commander_discovery_refinement import payload, review

    result = review()
    result["assessments"]["C01"]["reason"] = 123
    scored = partial_review(json.dumps(result), payload())
    assert scored["evidence_valid_count"] == 1
    assert scored["complete"] is False
    assert scored["assessments"][1]["evidence_errors"] == ["invalid_assessment"]
    del result["assessments"]["C01"]
    assert partial_review(json.dumps(result), payload())["missing_keys"] == ["C01"]
    result["assessments"]["C99"] = {}
    with pytest.raises(ValueError, match="identit"):
        partial_review(json.dumps(result), payload())


def test_source_preserves_faces_and_new_keyword_without_legacy_flattening() -> None:
    from mtg_helper.services.recommendations.snapshots import normalize_cards, pack, unpack

    raw = card("Front // Back", oracle_id=str(uuid4()), keywords=["NewUnclassifiedKeyword"])
    raw["card_faces"] = [
        {"name": "Front", "type_line": "Creature", "oracle_text": "Draw two cards."},
        {"name": "Back", "type_line": "Land", "oracle_text": "{T}: Add {G}."},
    ]
    raw["oracle_text"] = None
    facts = normalize_cards([raw])
    assert facts[0]["oracle_text"] is None
    assert facts[0]["card_faces"] == raw["card_faces"]
    assert facts[0]["keywords"] == raw["keywords"]
    blob, digest = pack(facts)
    assert unpack(blob, digest) == facts
    with pytest.raises(ValueError, match="hash"):
        unpack(blob, "0" * 64)


def test_unrequested_rule_continuation_is_an_explicit_error() -> None:
    from mtg_helper.services.recommendations.pipeline import rule_observations

    entries = refinement.parse_rules("123.1. Counter marker.\n\n123.2. Counter marker.")
    query_value = refinement.RuleQuery(
        purpose="Continue", text_all=["Counter"], text_any=[], cursor="123.1"
    )
    rows = rule_observations([query_value], entries, [])
    assert rows[0]["selected"] == [] and "error" in rows[0]


def test_browsing_cursor_is_bound_to_commander_query_and_snapshot() -> None:
    from mtg_helper.models.recommendations import QueryPreview
    from mtg_helper.services.recommendations.snapshots import Sources
    from mtg_helper.services.recommendations.views import browse

    leader = card("Commander", oracle_id=str(uuid4()))
    cards = [leader, *[card(f"Card {i}", oracle_id=str(uuid4())) for i in range(3)]]
    sources = Sources.load(cards=cards, rules={}, card_hash="a" * 64, rules_hash="b" * 64)
    page = browse(sources, leader, set(), QueryPreview(limit=1))
    assert page.total == 3 and page.next_cursor
    second = browse(
        sources,
        leader,
        set(),
        QueryPreview(limit=1, cursor=page.next_cursor, rules_hash=page.rules_hash),
    )
    assert second.cards[0].oracle_id != page.cards[0].oracle_id
    assert page.rules_hash == sources.rules_hash
    from mtg_helper.services.recommendations.repository import DiscoveryError

    with pytest.raises(DiscoveryError, match="cursor"):
        browse(
            sources, leader, set(), QueryPreview(limit=1, name="Different", cursor=page.next_cursor)
        )


def test_rules_browse_continuation_rejects_changed_terms_or_snapshot() -> None:
    from mtg_helper.models.recommendations import PreviewRuleQuery, QueryPreview
    from mtg_helper.services.recommendations.repository import DiscoveryError
    from mtg_helper.services.recommendations.snapshots import Sources
    from mtg_helper.services.recommendations.views import rule_results

    entries = {f"123.{i}": {"key": f"123.{i}", "text": "Counter marker."} for i in range(20)}
    sources = Sources.load(cards=[], rules=entries, card_hash="a" * 64, rules_hash="b" * 64)
    query_value = {"purpose": "Lookup", "text_all": ["Counter"], "text_any": [], "cursor": None}
    first = rule_results(QueryPreview(rule_query=PreviewRuleQuery(**query_value)), sources)
    cursor = first["next_cursor"]
    request = QueryPreview(
        rules_hash=sources.rules_hash,
        rule_query=PreviewRuleQuery(**(query_value | {"cursor": cursor})),
    )
    second = rule_results(request, sources)
    assert second["selected"][0] != first["selected"][0]
    request.rule_query.text_all = ["marker"]
    with pytest.raises(DiscoveryError, match="cursor"):
        rule_results(request, sources)


def test_source_rejects_malformed_fields_and_bounded_decompression(monkeypatch) -> None:
    from mtg_helper.services.recommendations import snapshots

    raw = card("Broken", oracle_id=str(uuid4()), card_faces=[], type_line=None)
    with pytest.raises(ValueError, match="printed type"):
        snapshots.normalize_cards([raw])
    monkeypatch.setattr(snapshots, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="exceeds"):
        snapshots.pack({"too_large": "x" * 20})


def test_budget_rejects_unpriced_boolean_oversized_or_wrong_tier_usage() -> None:
    from mtg_helper.services.recommendations.budget import BOUNDS, reservation, usage_cost

    assert reservation() == 67_750
    response = {
        "model": "gpt-5.6-luna",
        "service_tier": "default",
        "usage": {"input_tokens": 100, "output_tokens": 100},
    }
    assert usage_cost(response, BOUNDS["plan"]) == 145
    for field, value in [
        ("input_tokens", True),
        ("input_tokens", 20_001),
        ("output_tokens", -1),
        ("output_tokens", None),
    ]:
        broken = response | {"usage": response["usage"] | {field: value}}
        with pytest.raises(ValueError, match="usage"):
            usage_cost(broken, BOUNDS["plan"])
    with pytest.raises(ValueError, match="pricing"):
        usage_cost(response | {"service_tier": "priority"}, BOUNDS["plan"])
