"""Pure setup-contract checks; catalog matching is exercised through the real API suite."""

import json
from uuid import UUID

import pytest

from mtg_helper.models.recommendations import DiscoverStrategySave
from mtg_helper.services.recommendations import budget, pipeline
from mtg_helper.services.recommendations.term_queries import TermsDraft, Workflow

pytestmark = pytest.mark.no_db
TAG = str(UUID(int=1))


def query(*, tags: list[str] | None = None, words: list[str] | None = None) -> dict:
    return {
        "purpose": "Source search",
        "groups": [{"oracle_tag_ids": tags or [], "printed_keywords": words or []}],
        "card_types_any": [],
    }


def workflow() -> Workflow:
    return Workflow(
        context={
            "prose": "A strategy",
            "commanders": [{"name": "Leader"}],
            "oracle_tags": [{"id": TAG, "label": "Source label", "description": "Source facts"}],
            "printed_keywords": ["Flying"],
            "source_hash": "source",
            "strategy_revision": None,
        }
    )


def test_payload_includes_commander_facts_and_source_descriptions() -> None:
    payload = workflow().payload("plan", {})
    assert payload["commanders"] == [{"name": "Leader"}]
    assert payload["oracle_tags"][0]["description"] == "Source facts"
    assert "cards" not in payload


def test_source_validation_canonicalizes_keywords_without_flattening_groups() -> None:
    data = query(tags=[TAG])
    data["groups"].append({"oracle_tag_ids": [], "printed_keywords": ["flying"]})
    data["card_types_any"] = ["Creature"]
    accepted = workflow().accept("plan", json.dumps({"queries": [data]}), {})
    assert accepted["queries"][0]["groups"][1]["printed_keywords"] == ["Flying"]
    assert accepted["queries"][0]["card_types_any"] == ["Creature"]
    assert accepted["strategy_revision"] is None


@pytest.mark.parametrize(
    "queries",
    [
        [],
        [query()],
        [query(tags=[str(UUID(int=9))])],
        [query(words=["Invented"])],
        [query(words=[" "])],
        [query(words=["Flying", "flying"])],
    ],
)
def test_invalid_or_unavailable_suggestions_fail_instead_of_broadening(queries: list[dict]) -> None:
    with pytest.raises(ValueError):
        workflow().accept("plan", json.dumps({"queries": queries}), {})


def test_ai_budget_is_eight_distinct_terms_but_manual_choices_allow_forty() -> None:
    data = {"queries": [query(tags=[str(UUID(int=index)) for index in range(1, 10)])]}
    with pytest.raises(ValueError, match="8 distinct"):
        TermsDraft.model_validate(data)
    assert len(DiscoverStrategySave.model_validate({"prose": "Manual", **data}).queries) == 1


def test_duplicate_searches_cannot_gain_weight_by_reordering_source_choices() -> None:
    first = query(tags=[TAG], words=["Flying"])
    second = first | {"purpose": "Same constraints, different prose"}
    with pytest.raises(ValueError, match="Repeated searches"):
        DiscoverStrategySave.model_validate({"prose": "Manual", "queries": [first, second]})


def test_new_profile_keeps_old_pricing_and_schema_is_strict() -> None:
    assert budget.bounds(budget.LEGACY_TERMS_VERSION) == {"plan": (20_000, 4_000)}
    assert budget.reservation(budget.TERMS_VERSION) == 24_800
    schema = pipeline.check_request(
        "plan", workflow().payload("plan", {}), profile=budget.TERMS_VERSION
    ).schema.model_json_schema()
    for model in [schema, *schema["$defs"].values()]:
        if model.get("type") == "object":
            assert set(model["required"]) == set(model["properties"])
            assert model["additionalProperties"] is False
