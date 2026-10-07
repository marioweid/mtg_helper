"""Constrained identity and verbatim-evidence contract for the New Cards experiment.

This validates references and quotations, not the truth of a rules interpretation.
"""

import json
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.new_cards_data_spike import Card, rules_text


class Evidence(BaseModel):
    """A short, verifiable quotation from a supplied card field."""

    model_config = ConfigDict(extra="forbid")
    card_key: str
    face_index: int | None = Field(ge=0)
    field: Literal[
        "rules",
        "name",
        "type_line",
        "mana_cost",
        "power",
        "toughness",
        "loyalty",
        "defense",
        "color_identity",
        "commander_legality",
    ]
    quote: str = Field(min_length=1)


class GroundedAssessment(BaseModel):
    """One judgment, mechanically bound to its required candidate slot."""

    model_config = ConfigDict(extra="forbid")
    label: Literal["strong", "worth_testing", "reject"]
    evidence: list[Evidence] = Field(min_length=1, max_length=3)
    support_keys: list[str] = Field(max_length=2)
    mechanism: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    caveat: str
    required_changes: list[str] = Field(max_length=2)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject repeated JSON keys instead of silently overwriting an assessment."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _normalized(value: object) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return " ".join(text.split())


def enrich_cases(cases: list[Card], source_cards: Iterable[Card]) -> None:
    """Restore characteristics from the frozen export without changing baseline facts."""
    targets: dict[str, list[Card]] = {}
    for case in cases:
        cards = [case["deck"]["commander"], *case["deck"]["physical_cards"], *case["candidates"]]
        for card in cards:
            targets.setdefault(card["oracle_id"], []).append(card)
    found = set()
    for raw in source_cards:
        card_id = raw.get("oracle_id")
        if card_id not in targets:
            continue
        if card_id in found:
            raise ValueError(f"Duplicate source Oracle identity: {card_id}")
        found.add(card_id)
        for target in targets[card_id]:
            _enrich_card(target, raw)
    if missing := set(targets) - found:
        raise ValueError(f"Missing {len(missing)} baseline identities in frozen export")


def _enrich_card(target: Card, raw: Card) -> None:
    facts = {
        key: raw.get(key)
        for key in (
            "name",
            "mana_cost",
            "cmc",
            "type_line",
            "color_identity",
            "layout",
        )
    } | {"rules": rules_text(raw), "commander_legality": raw["legalities"]["commander"]}
    if any(target[key] != value for key, value in facts.items()):
        raise ValueError(f"Frozen baseline facts changed for {raw['oracle_id']}")
    target.update(characteristics(raw))
    target["faces"] = [
        characteristics(face)
        | {
            "name": face["name"],
            "mana_cost": face.get("mana_cost"),
            "type_line": face.get("type_line"),
            "rules": face.get("oracle_text", ""),
        }
        for face in raw.get("card_faces", [])
    ]


def characteristics(card: Card) -> Card:
    """Keep absent characteristics null rather than guessing a creature's body."""
    return {
        field: card.get(field)
        for field in (
            "power",
            "toughness",
            "loyalty",
            "defense",
            "colors",
            "color_indicator",
            "keywords",
        )
    }


def eligibility_issues(card: Card, deck: Card) -> list[str]:
    """Compute deterministic exclusions independently of the model's label."""
    issues = []
    if card.get("commander_legality") != "legal":
        issues.append("current_legality_not_confirmed_legal")
    colors = set(deck["commander"].get("color_identity", []))
    if not set(card.get("color_identity", [])) <= colors:
        issues.append("outside_color_identity")
    physical = [deck["commander"], *deck["physical_cards"]]
    if card.get("oracle_id") in {item.get("oracle_id") for item in physical}:
        issues.append("already_in_physical_deck")
    return issues


class EvaluationContext:
    """Own candidate binding, source evidence, request schema and output validation."""

    def __init__(self, case: Card) -> None:
        self.deck = case["deck"]
        self.candidates = {f"C{i:02}": card for i, card in enumerate(case["candidates"], 1)}
        self.support = {"D00": self.deck["commander"]} | {
            f"D{i:02}": card for i, card in enumerate(self.deck["physical_cards"], 1)
        }
        ids = [card["oracle_id"] for card in self.candidates.values()]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Candidate pool must be nonempty with unique Oracle IDs")
        self.sources = self.support | self.candidates
        self.eligibility = {
            key: eligibility_issues(card, self.deck) for key, card in self.candidates.items()
        }

    def payload(self, reverse: bool) -> Card:
        """Expose stable local keys, never ask the model to copy global identities."""
        candidates = [
            self._public(key) | {"eligibility_issues": self.eligibility[key]}
            for key in self.candidates
        ]
        return {
            "deck": {
                "id": self.deck.get("id", "fixture"),
                "goal": self.deck.get("goal", ""),
                "commander": self._public("D00"),
                "physical_cards": [self._public(key) for key in self.support if key != "D00"],
                "planned_changes": self.deck.get("planned_changes", []),
            },
            "candidates": list(reversed(candidates)) if reverse else candidates,
        }

    def _public(self, key: str) -> Card:
        return {
            field: value for field, value in self.sources[key].items() if field != "oracle_id"
        } | {"key": key}

    def schema(self) -> Card:
        """Require exactly one property per candidate and constrain every reference enum."""
        assessment = GroundedAssessment.model_json_schema()
        definitions = assessment.pop("$defs")
        definitions["Evidence"]["properties"]["card_key"]["enum"] = list(self.sources)
        assessment["properties"]["support_keys"]["items"]["enum"] = list(self.support)
        definitions["GroundedAssessment"] = assessment
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {key: {"$ref": "#/$defs/GroundedAssessment"} for key in self.candidates},
            "required": list(self.candidates),
            "$defs": definitions,
        }

    def decode(self, text: str) -> tuple[list[Card], list[str]]:
        """Validate coverage and evidence, then bind output to server-owned Oracle IDs."""
        data = json.loads(text, object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != set(self.candidates):
            raise ValueError("Missing or foreign candidate slots")
        assessments = []
        errors = []
        for key, card in self.candidates.items():
            item = GroundedAssessment.model_validate(data[key])
            errors.extend(f"{key}: {error}" for error in self._check(key, item))
            assessments.append(
                {
                    "oracle_id": card["oracle_id"],
                    "label": item.label,
                    "reason": item.reason,
                    "caveat": item.caveat,
                    "required_changes": item.required_changes,
                    "support_names": [
                        self.support[ref]["name"]
                        for ref in item.support_keys
                        if ref in self.support
                    ],
                    "candidate_key": key,
                    "mechanism": item.mechanism,
                    "evidence": [evidence.model_dump() for evidence in item.evidence],
                    "support_keys": item.support_keys,
                }
            )
        return assessments, errors

    def _check(self, key: str, item: GroundedAssessment) -> list[str]:
        errors = self._evidence_errors(key, item)
        if self.eligibility[key] and item.label != "reject":
            errors.append("non-reject label violates deterministic eligibility")
        if item.label == "strong" and (item.required_changes or not item.support_keys):
            errors.append("strong label needs present support and no required additions")
        if len(set(item.support_keys)) != len(item.support_keys):
            errors.append("duplicate support references")
        return errors

    def _source_text(self, evidence: Evidence) -> str:
        source = self.sources[evidence.card_key]
        if evidence.face_index is not None:
            faces = source.get("faces", [])
            if evidence.face_index >= len(faces):
                return ""
            source = faces[evidence.face_index]
        return _normalized(source.get(evidence.field))

    def _evidence_errors(self, key: str, item: GroundedAssessment) -> list[str]:
        errors = []
        valid_sources = set()
        allowed = {key, *self.support}
        for evidence in item.evidence:
            if evidence.card_key not in allowed:
                errors.append("unknown or unplanned candidate evidence")
                continue
            source = self._source_text(evidence)
            quote = _normalized(evidence.quote)
            if not quote or quote not in source:
                errors.append("quotation is not present in the supplied field")
                continue
            valid_sources.add(evidence.card_key)
        if key not in valid_sources:
            errors.append("missing valid candidate evidence")
        if not set(item.support_keys) <= (valid_sources & set(self.support)):
            errors.append("support references need corresponding verified evidence")
        return errors
