"""Offline regression checks for exact identity binding and source quotations."""

import json

import pytest

from scripts.new_cards_data_spike import compact
from scripts.new_cards_evidence import EvaluationContext, enrich_cases
from scripts.new_cards_quality_spike import card_facts

pytestmark = pytest.mark.no_db


def _card(card_id: str, name: str) -> dict:
    return {
        "oracle_id": card_id,
        "name": name,
        "mana_cost": "{2}",
        "cmc": 2,
        "type_line": "Artifact",
        "color_identity": [],
        "layout": "normal",
        "rules": "{T}: Add {C}.",
        "commander_legality": "legal",
        "power": None,
        "toughness": None,
        "faces": [],
    }


def _case() -> dict:
    return {
        "deck": {
            "id": "fixture",
            "commander": _card("commander-id", "Commander"),
            "physical_cards": [_card("support-id", "Support")],
            "planned_changes": [],
        },
        "candidates": [_card("candidate-id", "Candidate")],
    }


def _quote(key: str, **changes: object) -> dict:
    return {
        "card_key": key,
        "face_index": None,
        "field": "rules",
        "quote": "{T}: Add {C}.",
        **changes,
    }


def _output(**changes: object) -> dict:
    return {
        "C01": {
            "label": "strong",
            "evidence": [_quote("C01"), _quote("D01")],
            "support_keys": ["D01"],
            "mechanism": "Provides an additional mana source.",
            "reason": "Supports casting spells.",
            "caveat": "Costs a slot.",
            "required_changes": [],
            **changes,
        }
    }


def test_valid_output_is_bound_to_actual_ids_and_support_names() -> None:
    rows, errors = EvaluationContext(_case()).decode(json.dumps(_output()))
    assert errors == []
    assert rows[0]["oracle_id"] == "candidate-id"
    assert rows[0]["support_names"] == ["Support"]
    assert rows[0]["candidate_key"] == "C01"


def test_slots_and_support_schema_are_strict_and_never_expose_answers() -> None:
    case = _case()
    case["expected"] = {"candidate-id": ["reject"]}
    context = EvaluationContext(case)
    schema = context.schema()
    assert schema["required"] == ["C01"]
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    assessment = schema["$defs"]["GroundedAssessment"]["properties"]
    assert assessment["support_keys"]["items"]["enum"] == ["D00", "D01"]
    evidence = schema["$defs"]["Evidence"]["properties"]
    assert evidence["card_key"]["enum"] == ["D00", "D01", "C01"]
    payload = json.dumps(context.payload(False))
    assert "oracle_id" not in payload
    assert "expected" not in payload


def test_reversal_changes_presentation_not_identity_or_schema() -> None:
    case = _case()
    case["candidates"].append(_card("second-id", "Second"))
    context = EvaluationContext(case)
    forward = context.payload(False)["candidates"]
    reverse = context.payload(True)["candidates"]
    assert reverse == list(reversed(forward))
    assert reverse[0]["key"] == "C02"
    assert context.schema()["required"] == ["C01", "C02"]


@pytest.mark.parametrize("candidates", [[], [_card("x", "One"), _card("x", "Two")]])
def test_empty_or_duplicate_pool_is_not_sent(candidates: list[dict]) -> None:
    case = _case()
    case["candidates"] = candidates
    with pytest.raises(ValueError, match="unique Oracle IDs"):
        EvaluationContext(case)


@pytest.mark.parametrize("output", [{}, {"foreign": {}}, {"C01": {}, "C02": {}}, []])
def test_missing_or_foreign_slots_fail_closed(output: object) -> None:
    with pytest.raises(ValueError, match="candidate slots"):
        EvaluationContext(_case()).decode(json.dumps(output))


def test_repeated_json_properties_are_not_silently_overwritten() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        EvaluationContext(_case()).decode('{"C01": {}, "C01": {}}')


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence": [_quote("C01", quote="invented ability"), _quote("D01")]},
        {"evidence": [_quote("C01", quote="   "), _quote("D01")]},
        {"evidence": [_quote("C01", field="power", quote="2"), _quote("D01")]},
        {"evidence": [_quote("C01", face_index=0), _quote("D01")]},
        {"evidence": [_quote("C01"), _quote("D99")]},
        {"evidence": [_quote("D01")]},
        {"support_keys": ["C01"]},
        {"support_keys": ["D99"]},
        {"support_keys": ["D01", "D01"]},
        {"support_keys": []},
        {"required_changes": ["Add support"]},
    ],
)
def test_unverified_or_overconfident_results_have_explicit_errors(changes: dict) -> None:
    _, errors = EvaluationContext(_case()).decode(json.dumps(_output(**changes)))
    assert errors


def test_another_candidate_is_not_physical_support() -> None:
    case = _case()
    case["candidates"].append(_card("second-id", "Second"))
    output = _output(evidence=[_quote("C01"), _quote("C02")], support_keys=["C02"])
    output["C02"] = _output(label="reject", evidence=[_quote("C02")], support_keys=[])["C01"]
    _, errors = EvaluationContext(case).decode(json.dumps(output))
    assert any("unplanned candidate" in error for error in errors)


@pytest.mark.parametrize(
    "changes",
    [
        {"required_changes": ["a", "b", "c"]},
        {"label": "great"},
        {"evidence": []},
        {"unexpected": True},
        {"evidence": [_quote("C01", face_index=-1)]},
    ],
)
def test_malformed_assessments_are_not_accepted(changes: dict) -> None:
    with pytest.raises(ValueError):
        EvaluationContext(_case()).decode(json.dumps(_output(**changes)))


def test_face_specific_characteristics_require_matching_face_evidence() -> None:
    case = _case()
    case["candidates"][0]["faces"] = [{"power": "4"}, {"power": "7"}]
    output = _output(
        evidence=[_quote("C01", field="power", face_index=1, quote="7"), _quote("D01")]
    )
    assert EvaluationContext(case).decode(json.dumps(output))[1] == []
    output["C01"]["evidence"][0]["face_index"] = 0
    assert EvaluationContext(case).decode(json.dumps(output))[1]


def test_verbatim_matching_normalizes_only_whitespace() -> None:
    output = _output(evidence=[_quote("C01", quote="{T}:  Add\n{C}."), _quote("D01")])
    assert EvaluationContext(_case()).decode(json.dumps(output))[1] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"commander_legality": "banned"},
        {"commander_legality": "not_legal"},
        {"color_identity": ["R"]},
        {"oracle_id": "support-id"},
    ],
)
def test_hard_ineligibility_cannot_receive_a_positive_label(changes: dict) -> None:
    case = _case()
    case["candidates"][0].update(changes)
    context = EvaluationContext(case)
    assert context.payload(False)["candidates"][0]["eligibility_issues"]
    assert context.decode(json.dumps(_output()))[1]
    assert context.decode(json.dumps(_output(label="reject")))[1] == []


def _enrichment_case() -> tuple[dict, dict]:
    raw = {
        "oracle_id": "candidate-id",
        "name": "Front // Back",
        "mana_cost": None,
        "cmc": 2,
        "type_line": "Creature // Creature",
        "color_identity": [],
        "layout": "transform",
        "legalities": {"commander": "legal"},
        "card_faces": [
            {
                "name": "Front",
                "power": "2",
                "toughness": "3",
                "type_line": "Creature",
                "oracle_text": "Vigilance",
            },
            {
                "name": "Back",
                "power": "4",
                "toughness": "5",
                "type_line": "Creature",
                "oracle_text": "Flying",
            },
        ],
    }
    facts = card_facts(compact(raw, None))
    case = {"deck": {"commander": dict(facts), "physical_cards": []}, "candidates": [dict(facts)]}
    return case, raw


def test_enrichment_preserves_baseline_facts_and_restores_every_face() -> None:
    case, raw = _enrichment_case()
    previous = dict(case["candidates"][0])
    enrich_cases([case], [raw])
    enriched = case["candidates"][0]
    assert all(enriched[key] == value for key, value in previous.items())
    assert enriched["power"] is None
    assert enriched["faces"][0]["power"] == "2"
    assert enriched["faces"][1]["toughness"] == "5"
    assert enriched == case["deck"]["commander"]


@pytest.mark.parametrize("problem", ["missing", "duplicate", "changed"])
def test_missing_duplicate_or_changed_frozen_facts_fail_before_live_use(problem: str) -> None:
    case, raw = _enrichment_case()
    sources = [raw]
    if problem == "missing":
        sources = []
    elif problem == "duplicate":
        sources.append(raw)
    else:
        raw["name"] = "Changed card"
    with pytest.raises(ValueError):
        enrich_cases([case], sources)
