"""Offline checks for source-backed planning, retrieval, assessment, and spending guards."""

import pytest

from mtg_helper.services.recommendations import discovery
from scripts.deck_recovery_check import build_catalog

pytestmark = pytest.mark.no_db


def card(name: str, *, colors: list[str] | None = None, **fields: object) -> dict:
    return {
        "name": name,
        "oracle_id": name,
        "games": ["paper"],
        "type_line": "Creature",
        "mana_cost": "{1}",
        "cmc": 1,
        "oracle_text": "",
        "keywords": [],
        "color_identity": colors or [],
        "legalities": {"commander": "legal"},
        "layout": "normal",
    } | fields


def query(**fields: object) -> discovery.Query:
    return discovery.Query.model_validate(
        {
            "purpose": "Look for a useful interaction",
            "oracle_text_all": [],
            "oracle_text_any": [],
            "type_line_any": [],
            "keywords_any": [],
            "mana_cost_all": [],
            "mana_value_min": None,
            "mana_value_max": None,
        }
        | fields
    )


def test_search_combines_literal_operations_without_classifying_abilities() -> None:
    search = query(oracle_text_all=["sacrifice", "creature"], mana_value_max=3)
    assert discovery.matches(search, card("Seer", oracle_text="Sacrifice a creature: Scry 1."))
    assert discovery.matches(
        search, card("Frog", oracle_text="Sacrifice this creature: Prevent all combat damage.")
    )
    assert not discovery.matches(search, card("Draw", oracle_text="Draw a card."))
    assert not discovery.matches(
        search, card("Expensive", cmc=4, oracle_text="Sacrifice a creature: Draw a card.")
    )


def test_unknown_keywords_and_other_face_text_remain_searchable() -> None:
    novel = card("Novel", keywords=["Unprecedented Mechanic"])
    assert discovery.matches(query(keywords_any=["unprecedented mechanic"]), novel)
    modal = card("Front // Back", card_faces=[{"oracle_text": "Proliferate."}])
    assert discovery.matches(query(oracle_text_all=["proliferate"]), modal)
    assert not discovery.matches(query(oracle_text_all=["%"]), novel)


def test_independent_discovery_excludes_illegal_cards_and_reports_bad_queries() -> None:
    leader = card("Commander", colors=["G"])
    useful = card("New Card", keywords=["Novel"])
    catalog = build_catalog(
        [leader, useful, card("Wrong", colors=["B"]), card("Land", type_line="Land")]
    )
    plan = discovery.Plan(
        intents=["Explore new interactions"],
        searches=[query(keywords_any=["Novel"]), query(mana_value_min=5, mana_value_max=1)],
        named_cards=["Wrong", "Land", "Missing", "New Card"],
        uncertainties=[],
    )
    result = discovery.discover(plan, catalog, leader, "fixed-seed")
    assert [c["name"] for c in result.shortlist] == ["New Card"]
    assert len(result.nomination_errors) == 3
    assert result.queries[0]["matching_count"] == 1
    assert "minimum" in result.queries[1]["error"]


def test_source_facts_do_not_expose_popularity_prices_or_labels() -> None:
    facts = discovery.card_facts(
        card("Candidate", edhrec_rank=1, tags=["ramp"], prices={"usd": "999"})
    )
    assert not {"edhrec_rank", "tags", "prices"} & facts.keys()
    assert facts["mana_value"] == 1


def test_quote_failure_does_not_discard_other_assessments() -> None:
    facts = [discovery.card_facts(card("Good", oracle_text="Draw two cards."))]
    facts += [discovery.card_facts(card("Bad", oracle_text="Proliferate."))]
    payload = {
        "commander": discovery.card_facts(card("Commander")),
        "candidates": [dict(key=f"C{i:02d}", **c) for i, c in enumerate(facts)],
        "rules": [],
    }
    review = discovery.Review.model_validate(
        {
            "recommendations": ["C00", "C01"],
            "assessments": [
                {
                    "card_key": key,
                    "fit": "support",
                    "reason": "Potential useful role.",
                    "caveat": "Context matters.",
                    "evidence": [{"key": key, "quote": quote}],
                }
                for key, quote in [("C00", "Draw two cards."), ("C01", "Invented rules text.")]
            ],
        }
    )
    scored = discovery.validate_review(review, payload)
    assert scored["assessments"][0]["evidence_errors"] == []
    assert scored["assessments"][1]["evidence_errors"]
    assert scored["recommendations"][0]["evidence_valid"] is True
    assert scored["recommendations"][1]["evidence_valid"] is False


def test_common_pool_does_not_relabel_forced_controls_as_discovered() -> None:
    leader = card("Commander", colors=["G"])
    catalog = build_catalog([leader, card("Found"), card("Forced"), card("Recent")])
    plan = discovery.Plan(
        intents=["A strategy"], searches=[], named_cards=["Found"], uncertainties=[]
    )
    found = discovery.discover(plan, catalog, leader, "seed")
    forced, recent = catalog.resolve("Forced"), catalog.resolve("Recent")
    assert forced is not None and recent is not None
    pool = discovery.shared_pool({"luna": found, "terra": found}, [forced], [recent], "seed")
    assert set(pool["provenance"]["Forced"]["channels"]) == {"diagnostic"}
    assert pool["provenance"]["Forced"]["shortlisted_by"] == []
    assert set(pool["provenance"]["Found"]["shortlisted_by"]) == {"luna", "terra"}
    assert len(pool["cards"]) == 3


def test_duplicate_and_missing_assessments_are_not_a_pass() -> None:
    payload = {
        "commander": discovery.card_facts(card("Commander")),
        "candidates": [dict(key="C00", **discovery.card_facts(card("Candidate")))],
        "rules": [],
    }
    review = discovery.Review(recommendations=[], assessments=[])
    scored = discovery.validate_review(review, payload)
    assert scored["missing_keys"] == ["C00"]
    assert scored["complete"] is False


def test_empty_and_whitespace_searches_are_rejected() -> None:
    for search in [query(), query(oracle_text_any=["  "])]:
        with pytest.raises(ValueError):
            discovery.validate_query(search)


def test_unknown_extra_assessment_and_weak_recommendation_cannot_pass() -> None:
    payload = {
        "commander": discovery.card_facts(card("Commander")),
        "candidates": [
            dict(
                key="C00", **discovery.card_facts(card("Candidate", oracle_text="Draw two cards."))
            )
        ],
        "rules": [],
    }
    item = discovery.Assessment(
        card_key="C00",
        fit="support",
        reason="Useful draw.",
        caveat="",
        evidence=[discovery.Evidence(key="C00", quote="Draw two cards.")],
    )
    extra = item.model_copy(update={"card_key": "C99"})
    scored = discovery.validate_review(
        discovery.Review(recommendations=["C00"], assessments=[item, extra]), payload
    )
    assert scored["complete"] is False
    assert "unknown_candidate" in scored["assessments"][1]["evidence_errors"]
    weak = item.model_copy(update={"fit": "weak"})
    scored = discovery.validate_review(
        discovery.Review(recommendations=["C00"], assessments=[weak]), payload
    )
    assert scored["recommendations"][0]["recommendation_valid"] is False
    assert scored["complete"] is False
    duplicate = discovery.validate_review(
        discovery.Review(recommendations=["C00", "C00"], assessments=[item, item]), payload
    )
    assert duplicate["complete"] is False
    assert "duplicate_assessment" in duplicate["assessments"][0]["evidence_errors"]


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_mana_bounds_fail_explicitly(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        discovery.validate_query(query(mana_value_min=value))


def test_unknown_mana_value_is_not_zero_and_long_search_terms_fail() -> None:
    assert not discovery.matches(query(mana_value_max=3), card("Unknown", cmc=None))
    assert discovery.matches(query(type_line_any=["creature"]), card("Unknown", cmc=None))
    with pytest.raises(ValueError, match="100 characters"):
        discovery.validate_query(query(oracle_text_all=["x" * 101]))


def test_recent_sampling_uses_first_paper_date_not_reprint_date() -> None:
    eligible = [card("Old", released_at="2026-09-01"), card("New")]
    dates = {"Old": "2000-01-01", "New": "2026-09-01"}
    recent = discovery.recent_sample(eligible, dates, "seed")
    assert [c["name"] for c in recent] == ["New"]


def test_empty_interleaving_and_duplicate_identity_are_safe() -> None:
    assert discovery.interleave([[card("A")]], 0) == []
    assert discovery.interleave([[], []], 4) == []
    assert [c["name"] for c in discovery.interleave([[card("A")], [card("A"), card("B")]], 3)] == [
        "A",
        "B",
    ]
