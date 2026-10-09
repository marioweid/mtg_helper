"""Offline regressions for feedback, unrestricted rules lookup and closed candidate coverage."""

import json

import pytest
from pydantic import ValidationError

from mtg_helper.services.recommendations import refinement
from mtg_helper.services.recommendations.discovery import Plan, card_facts, discover
from scripts.deck_recovery_check import build_catalog
from tests.test_commander_discovery_check import card, query

pytestmark = pytest.mark.no_db


def payload() -> dict:
    return {
        "commander": card_facts(card("Commander")),
        "candidates": [
            dict(key=key, **card_facts(card(name, oracle_text="Draw two cards.")))
            for key, name in [("C00", "First"), ("C01", "Second")]
        ],
        "rules": [],
    }


def review() -> dict:
    item = {
        "fit": "support",
        "reason": "Useful draw.",
        "caveat": "",
        "evidence": [{"key": "C00", "quote": "Draw two cards."}],
    }
    return {
        "recommendations": ["C00"],
        "assessments": {
            key: {**item, "evidence": [{"key": key, "quote": "Draw two cards."}]}
            for key in ["C00", "C01"]
        },
    }


def test_closed_review_requires_every_candidate_once_and_bare_rank_ids() -> None:
    context = payload()
    scored = refinement.parse_review(json.dumps(review()), context)
    assert scored["complete"] is True
    missing = review()
    del missing["assessments"]["C01"]
    with pytest.raises(ValidationError):
        refinement.parse_review(json.dumps(missing), context)
    decorated = review() | {"recommendations": ["C00 — First"]}
    with pytest.raises(ValidationError):
        refinement.parse_review(json.dumps(decorated), context)
    extra = review()
    extra["assessments"]["C99"] = extra["assessments"]["C00"]
    with pytest.raises(ValidationError):
        refinement.parse_review(json.dumps(extra), context)


def test_duplicate_json_properties_fail_instead_of_overwriting_a_candidate() -> None:
    value = json.dumps(review())
    duplicate = value.replace(
        '"recommendations": ["C00"]', '"recommendations": [], "recommendations": ["C00"]'
    )
    with pytest.raises(ValueError, match="Duplicate JSON"):
        refinement.parse_review(duplicate, payload())


def test_bad_quotes_still_fail_and_do_not_poison_other_candidates() -> None:
    value = review()
    value["assessments"]["C01"]["evidence"][0]["quote"] = "Invented source text."
    scored = refinement.parse_review(json.dumps(value), payload())
    assert scored["complete"] is False
    assert scored["evidence_valid_count"] == 1
    assert scored["assessments"][0]["evidence_errors"] == []


def test_rule_parser_preserves_native_ids_examples_and_arbitrary_glossary_terms() -> None:
    text = (
        "Contents\n\nGlossary\n\nCredits\n\n"
        "123.1. A counter is a marker on a player.\n\n"
        "Example: A player can have such a marker.\n\n"
        "999.2a UnforeseenAction adds a counter to a player.\n\n"
        "Glossary\n\nUnforeseenAction\nA future action. See rule 999.2a.\n\nCredits\n"
    )
    corpus = refinement.parse_rules(text)
    assert corpus["123.1"]["text"].endswith("such a marker.")
    assert "999.2a" in corpus
    assert "G:UnforeseenAction" in corpus
    search = refinement.RuleQuery(
        purpose="Find modifiers", text_all=["counter"], text_any=["player"], cursor=None
    )
    result = refinement.search_rules(search, corpus)
    assert result["matching_count"] == 2
    assert {r["key"] for r in result["selected"]} == {"123.1", "999.2a"}


def test_rule_lookup_rejects_empty_queries_and_conflicting_source_ids() -> None:
    query_value = refinement.RuleQuery(purpose="Empty", text_all=[], text_any=[], cursor=None)
    with pytest.raises(ValueError, match="operation"):
        refinement.search_rules(query_value, {})
    with pytest.raises(ValueError, match="Conflicting"):
        refinement.parse_rules("123.1. First rule.\n\n123.1. Different rule.")


def test_feedback_exposes_zero_results_errors_and_full_sample_facts_without_hints() -> None:
    leader = card("Commander", colors=["G"])
    found = card("Unfamiliar", oracle_text="When this creature enters, draw two cards.")
    catalog = build_catalog([leader, found])
    plan = Plan(
        intents=["Find entry value"],
        searches=[
            query(oracle_text_all=["enters the battlefield"]),
            query(oracle_text_all=["enters"]),
            query(mana_value_min=4, mana_value_max=1),
        ],
        named_cards=[],
        uncertainties=[],
    )
    discovered = discover(plan, catalog, leader, "seed")
    observation = refinement.discovery_feedback(discovered)
    assert observation["queries"][0]["matching_count"] == 0
    assert observation["queries"][1]["selected"][0]["oracle_text"] == found["oracle_text"]
    assert "error" in observation["queries"][2]
    assert "diagnostic_matches" not in json.dumps(observation)


@pytest.mark.parametrize("term", ["   ", "x" * 101])
def test_bad_rule_terms_are_explicit_errors(term: str) -> None:
    search = refinement.RuleQuery(purpose="Unsupported", text_all=[term], text_any=[], cursor=None)
    with pytest.raises(ValueError, match="operation"):
        refinement.search_rules(search, {})


def test_rule_results_are_resumable_and_bad_cursors_fail_explicitly() -> None:
    entries = {
        f"999.{i}": {"key": f"999.{i}", "text": "A future counter modifier."} for i in range(10)
    }
    search = refinement.RuleQuery(
        purpose="Look broadly", text_all=["counter"], text_any=[], cursor=None
    )
    first = refinement.search_rules(search, entries)
    second = refinement.search_rules(
        search.model_copy(update={"cursor": first["next_cursor"]}), entries
    )
    assert first["matching_count"] == second["matching_count"] == 10
    assert first["truncated"] is True
    assert second["next_cursor"] is None
    assert len({r["key"] for r in first["selected"] + second["selected"]}) == 10
    with pytest.raises(ValueError, match="cursor"):
        refinement.search_rules(search.model_copy(update={"cursor": "missing"}), entries)


def test_invalid_candidate_context_and_empty_rule_sources_are_rejected() -> None:
    for candidates in [[], [{"key": "C00"}, {"key": "C00"}], [{"key": "invented"}]]:
        with pytest.raises(ValueError, match="candidate|Candidate"):
            refinement.review_type(payload() | {"candidates": candidates})
    with pytest.raises(ValueError, match="No native"):
        refinement.parse_rules("Unrecognised future source structure.")


def test_feedback_truncation_reflects_two_samples_not_old_eight_card_limit() -> None:
    leader = card("Commander")
    cards = [card(f"Candidate {i}", oracle_text="Draw two cards.") for i in range(6)]
    plan = Plan(
        intents=["Draw"],
        searches=[query(oracle_text_all=["Draw"])],
        named_cards=[],
        uncertainties=[],
    )
    found = discover(plan, build_catalog([leader, *cards]), leader, "seed")
    assert found.queries[0]["truncated"] is False
    result = refinement.discovery_feedback(found)["queries"][0]
    assert result["matching_count"] == 6
    assert len(result["selected"]) == result["sample_limit"] == 2
    assert result["truncated"] is True


def test_planning_observations_report_failed_rule_operations_individually() -> None:
    leader = card("Commander")
    catalog = build_catalog([leader, card("Candidate")])
    plan = refinement.RefinementPlan(
        intents=["Find resource modifiers"],
        searches=[],
        named_cards=[],
        uncertainties=[],
        rule_searches=[
            refinement.RuleQuery(purpose="Invalid", text_all=[], text_any=[], cursor=None),
            refinement.RuleQuery(purpose="Valid", text_all=["marker"], text_any=[], cursor=None),
        ],
    )
    entries = refinement.parse_rules("123.1. A marker modifies an object or player.")
    observed = refinement.planning_observation(plan, catalog, leader, entries, "seed")
    assert "error" in observed["rule_searches"][0]
    assert observed["rule_searches"][1]["matching_count"] == 1
    assert "reference_deck" not in observed


def test_native_rule_ids_with_multiple_suffix_letters_are_searchable() -> None:
    corpus = refinement.parse_rules("704.5aa A counter-related future state action.")
    assert "704.5aa" in corpus
    search = refinement.RuleQuery(
        purpose="Inspect native ID", text_all=["704.5aa"], text_any=[], cursor=None
    )
    assert refinement.search_rules(search, corpus)["matching_count"] == 1


def test_planning_revision_can_request_the_next_rules_page() -> None:
    entries = {f"999.{i}": {"key": f"999.{i}", "text": "A counter modifier."} for i in range(10)}
    leader = card("Commander")
    plan = refinement.RefinementPlan(
        intents=["Resources"],
        searches=[],
        named_cards=[],
        uncertainties=[],
        rule_searches=[
            refinement.RuleQuery(
                purpose="Inspect modifiers", text_all=["counter"], text_any=[], cursor=None
            )
        ],
    )
    catalog = build_catalog([leader])
    first = refinement.planning_observation(plan, catalog, leader, entries, "seed")
    plan.rule_searches[0].cursor = first["rule_searches"][0]["next_cursor"]
    second = refinement.planning_observation(plan, catalog, leader, entries, "seed")
    assert len(second["rule_searches"][0]["selected"]) == 2


def test_source_prefixes_come_from_the_data_not_a_mechanic_dictionary() -> None:
    cards = [card("Future", oracle_text="Whenever you quantum-fold, draw a card.")]
    assert refinement.source_prefixes(cards) == [
        {"text": "Whenever you quantum-fold, draw a card.", "count": 1}
    ]
