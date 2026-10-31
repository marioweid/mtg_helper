"""Model-facing selection contract: catalog membership and global bounds are structural."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from mtg_helper.services.recommendations import budget, pipeline, term_selection
from mtg_helper.services.recommendations.term_queries import StrategyQuery, selected_terms
from tests.test_discover_term_queries import TAG, query
from tests.test_discover_term_queries import workflow as historical_workflow

pytestmark = pytest.mark.no_db


def resolve(schema: dict, field: dict) -> dict:
    if "$ref" in field:
        return schema["$defs"][field["$ref"].split("/")[-1]]
    return field


def workflow() -> term_selection.Workflow:
    return term_selection.Workflow(context=historical_workflow().context)


def selection() -> dict:
    return {
        "oracle_tag_ids": [TAG],
        "printed_keywords": ["Flying"],
        "queries": [
            {
                "purpose": "Source search",
                "groups": [
                    {"oracle_tag_indices": [0], "printed_keyword_indices": []},
                    {"oracle_tag_indices": [], "printed_keyword_indices": [0]},
                ],
                "card_types_any": ["Creature"],
            }
        ],
    }


def test_new_profile_enumerates_global_choices_and_caps_each_kind_at_eight() -> None:
    payload = workflow().payload("plan", {})
    schema = pipeline.check_request(
        "plan", payload, profile="app-strategy-terms-v3"
    ).schema.model_json_schema()
    for field, expected in (("oracle_tag_ids", [TAG]), ("printed_keywords", ["Flying"])):
        choice = schema["properties"][field]
        assert choice["maxItems"] == 8
        assert resolve(schema, choice["items"])["enum"] == expected
    for model in [schema, *schema["$defs"].values()]:
        if model.get("type") == "object":
            assert set(model["required"]) == set(model["properties"])
            assert model["additionalProperties"] is False


def test_decoder_preserves_saved_query_shape_groups_scope_and_context() -> None:
    work = workflow()
    work.context |= {"strategy_revision": "saved-revision", "source_hash": "frozen-source"}
    accepted = work.accept("plan", json.dumps(selection()), {})
    expected = query(tags=[TAG])
    expected["groups"].append({"oracle_tag_ids": [], "printed_keywords": ["Flying"]})
    expected["card_types_any"] = ["Creature"]
    assert accepted == {
        "queries": [expected],
        "strategy_revision": "saved-revision",
        "source_hash": "frozen-source",
    }


def test_eight_global_choices_can_be_reused_across_searches_without_expanding_budget() -> None:
    work = workflow()
    tags = [str(UUID(int=i)) for i in range(1, 9)]
    work.context["oracle_tags"] = [{"id": identity} for identity in tags]
    data: dict[str, Any] = selection() | {"oracle_tag_ids": tags}
    data["queries"][0]["groups"][0]["oracle_tag_indices"] = list(range(8))
    data["queries"].append(data["queries"][0] | {"card_types_any": ["Artifact"]})
    accepted = work.accept("plan", json.dumps(data), {})
    assert len(accepted["queries"]) == 2
    assert all(row["groups"][0]["oracle_tag_ids"] == tags for row in accepted["queries"])
    assert budget.reservation(budget.BOUNDED_TERMS_VERSION) == 24_800
    assert budget.bounds(budget.BOUNDED_TERMS_VERSION) == {"plan": (80_000, 4_000)}
    assert budget.bounds(budget.BOUNDED_TERMS_VERSION) == budget.bounds(budget.TERMS_VERSION)


@pytest.mark.parametrize("field", ["oracle_tag_ids", "printed_keywords"])
def test_ninth_supplied_choice_is_rejected_even_when_every_identity_is_valid(field: str) -> None:
    work = workflow()
    values = [str(UUID(int=i)) if field == "oracle_tag_ids" else f"Keyword{i}" for i in range(9)]
    context_key = "oracle_tags" if field == "oracle_tag_ids" else field
    work.context[context_key] = (
        [{"id": value} for value in values] if field == "oracle_tag_ids" else values
    )
    model = term_selection.selection_type(work.payload("plan", {}))
    data = selection()
    data[field] = values[:8]
    assert model.model_validate(data)
    data[field] = values
    with pytest.raises(ValueError, match="at most 8"):
        model.model_validate(data)


@pytest.mark.parametrize("field", ["oracle_tag_ids", "printed_keywords"])
def test_empty_source_kind_is_structurally_closed_but_the_other_kind_is_usable(field: str) -> None:
    work = workflow()
    context_key = "oracle_tags" if field == "oracle_tag_ids" else field
    work.context[context_key] = []
    payload = work.payload("plan", {})
    model = term_selection.selection_type(payload)
    assert model.model_json_schema()["properties"][field]["maxItems"] == 0
    data = selection()
    data[field] = []
    del data["queries"][0]["groups"][0 if field == "oracle_tag_ids" else 1]
    assert work.accept("plan", json.dumps(data), {})["queries"]
    data[field] = [TAG if field == "oracle_tag_ids" else "Flying"]
    with pytest.raises(ValueError):
        model.model_validate(data)


def test_no_sources_fail_before_a_request_and_menus_do_not_leak_between_schemas() -> None:
    work = workflow()
    work.context["oracle_tags"] = []
    work.context["printed_keywords"] = []
    with pytest.raises(ValueError, match="No source terms"):
        pipeline.check_request(
            "plan", work.payload("plan", {}), profile=budget.BOUNDED_TERMS_VERSION
        )
    first = term_selection.selection_type(workflow().payload("plan", {}))
    other = workflow()
    other.context["oracle_tags"] = [{"id": str(UUID(int=2))}]
    second = term_selection.selection_type(other.payload("plan", {}))
    assert first.model_validate(selection())
    with pytest.raises(ValueError):
        second.model_validate(selection())


@pytest.mark.parametrize("index", [-1, 1, 8, True, "0", 0.0])
def test_missing_or_noninteger_references_are_rejected_not_repaired(index: object) -> None:
    data = selection()
    data["queries"][0]["groups"][0]["oracle_tag_indices"] = [index]
    with pytest.raises(ValueError):
        workflow().accept("plan", json.dumps(data), {})


@pytest.mark.parametrize("change", ["choices", "references", "searches", "empty_group", "keyword"])
def test_invalid_selections_fail_without_silently_discarding_fields(change: str) -> None:
    data = selection()
    if change == "choices":
        data["oracle_tag_ids"] *= 2
    elif change == "references":
        data["queries"][0]["groups"][0]["oracle_tag_indices"] *= 2
    elif change == "searches":
        data["queries"] *= 2
    elif change == "empty_group":
        data["queries"][0]["groups"][0]["oracle_tag_indices"] = []
    else:
        data["printed_keywords"] = ["flying"]
    original = json.dumps(data)
    with pytest.raises(ValueError):
        workflow().accept("plan", original, {})
    assert json.dumps(data) == original


def test_duplicate_json_properties_and_historical_shape_cannot_bypass_selection() -> None:
    text = json.dumps(selection())
    with pytest.raises(ValueError, match="Duplicate JSON property"):
        workflow().accept(
            "plan", text.replace('"oracle_tag_ids":', '"queries": [], "oracle_tag_ids":'), {}
        )
    with pytest.raises(ValueError):
        workflow().accept("plan", json.dumps({"queries": [query(tags=[TAG])]}), {})
    with pytest.raises(ValueError):
        workflow().accept("review", text, {})


def test_observed_meren_oversize_and_invented_identity_are_excluded_by_new_model() -> None:
    destination = Path(__file__).resolve().parents[2] / "docs/research/discover-result-aware"
    frozen = json.loads((destination / "inputs.json").read_text(encoding="utf-8"))
    ledger = json.loads((destination / "attempts.json").read_text(encoding="utf-8"))
    attempt = next(row for row in ledger["attempts"] if row["deck"] == "meren")
    work = term_selection.Workflow(context=frozen["cases"]["meren"]["context"])
    raw = json.loads(attempt["output"])
    tags, _ = selected_terms([StrategyQuery.model_validate(row) for row in raw["queries"]])
    model = term_selection.selection_type(work.payload("plan", {}))
    data = selection() | {"oracle_tag_ids": [str(tag) for tag in tags], "printed_keywords": []}
    with pytest.raises(ValueError, match="at most 8"):
        model.model_validate(data)
    data["oracle_tag_ids"] = ["524845ed-ea82-4a60-8b52-8a38ab06a503"]
    with pytest.raises(ValueError, match="Input should be"):
        model.model_validate(data)
