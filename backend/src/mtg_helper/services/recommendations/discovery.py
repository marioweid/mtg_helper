"""Pure source-backed operations for the isolated commander discovery experiment."""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import zip_longest
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mtg_helper.services.recommendations.source import Card, Catalog, eligibility_error

SHORTLIST_LIMIT = 32
POOL_LIMIT = 64
CUTOFF = "2026-02-16"
AS_OF = "2026-10-04"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Query(StrictModel):
    """Executable source filters, not classifications of Magic interactions."""

    purpose: str = Field(min_length=1, max_length=220)
    oracle_text_all: list[str] = Field(max_length=5)
    oracle_text_any: list[str] = Field(max_length=5)
    type_line_any: list[str] = Field(max_length=5)
    keywords_any: list[str] = Field(max_length=5)
    mana_cost_all: list[str] = Field(max_length=5)
    mana_value_min: float | None
    mana_value_max: float | None


class Plan(StrictModel):
    intents: list[str] = Field(min_length=1, max_length=8)
    searches: list[Query] = Field(max_length=8)
    named_cards: list[str] = Field(max_length=12)
    uncertainties: list[str] = Field(max_length=4)


class Evidence(StrictModel):
    key: str
    quote: str = Field(min_length=10, max_length=160)


class Assessment(StrictModel):
    card_key: str
    fit: Literal["core", "support", "conditional", "weak", "uncertain"]
    reason: str = Field(min_length=1, max_length=220)
    caveat: str = Field(max_length=140)
    evidence: list[Evidence] = Field(min_length=1, max_length=2)


class Review(StrictModel):
    recommendations: list[str] = Field(max_length=15)
    assessments: list[Assessment] = Field(max_length=POOL_LIMIT)


@dataclass(kw_only=True)
class Discovery:
    nominations: list[Card]
    nomination_errors: list[Card]
    queries: list[Card]
    shortlist: list[Card]
    matched_ids: set[str]


def field_text(card: Card, field: str) -> str:
    """Search all printed faces without implying simultaneous face access."""
    return "\n".join(
        [card.get(field) or "", *[face.get(field) or "" for face in card.get("card_faces", [])]]
    ).casefold()


def matches(query: Query, card: Card) -> bool:
    """Combine literal source operations; matching is not strategic classification."""
    oracle = field_text(card, "oracle_text")
    types = field_text(card, "type_line")
    mana = field_text(card, "mana_cost")
    keywords = {k.casefold() for k in card.get("keywords", [])}
    value = card.get("cmc")
    return all(
        (
            all(term.casefold() in oracle for term in query.oracle_text_all),
            not query.oracle_text_any or any(t.casefold() in oracle for t in query.oracle_text_any),
            not query.type_line_any or any(t.casefold() in types for t in query.type_line_any),
            not query.keywords_any or bool(keywords & {k.casefold() for k in query.keywords_any}),
            all(term.casefold() in mana for term in query.mana_cost_all),
            query.mana_value_min is None or value is not None and value >= query.mana_value_min,
            query.mana_value_max is None or value is not None and value <= query.mana_value_max,
        )
    )


def validate_query(query: Query) -> None:
    """Reject unsupported empty/range inputs instead of silently weakening the search."""
    payload = query.model_dump(exclude={"purpose"})
    if not any(value is not None and value != [] for value in payload.values()):
        raise ValueError("Empty search: specify at least one source operation")
    terms = [term for value in payload.values() if isinstance(value, list) for term in value]
    if any(not term.strip() or len(term) > 100 for term in terms):
        raise ValueError("Search terms must be nonblank literal strings of at most 100 characters")
    minimum, maximum = query.mana_value_min, query.mana_value_max
    if any(value is not None and not math.isfinite(value) for value in (minimum, maximum)):
        raise ValueError("Mana-value bounds must be finite numbers")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("Mana-value minimum exceeds maximum; correct the range")


def card_facts(card: Card) -> Card:
    """Whitelist complete gameplay text, omitting popularity and generated labels."""
    fields = (
        "oracle_id",
        "name",
        "mana_cost",
        "type_line",
        "oracle_text",
        "color_identity",
        "keywords",
        "layout",
        "power",
        "toughness",
        "loyalty",
        "defense",
    )
    face_fields = (
        "name",
        "mana_cost",
        "type_line",
        "oracle_text",
        "power",
        "toughness",
        "loyalty",
        "defense",
    )
    return {field: card.get(field) for field in fields} | {
        "mana_value": card.get("cmc"),
        "faces": [
            {key: face.get(key) for key in face_fields} for face in card.get("card_faces", [])
        ],
        "commander_legality": card["legalities"].get("commander"),
    }


def eligible_cards(catalog: Catalog, leader: Card) -> list[Card]:
    """Enumerate legal nonlands independently of community membership or classification."""
    unique = {c["oracle_id"]: c for entries in catalog.exact.values() for c in entries.values()}
    return [
        c
        for c in unique.values()
        if eligibility_error(c, set(leader["color_identity"]), leader["oracle_id"]) is None
    ]


def seeded(cards: list[Card], seed: str) -> list[Card]:
    """Order source identities reproducibly without popularity/alphabetical bias."""
    return sorted(cards, key=lambda c: hashlib.sha256(f"{seed}|{c['oracle_id']}".encode()).digest())


def interleave(lanes: list[list[Card]], limit: int) -> list[Card]:
    """Deduplicate/interleave channels so a broad query cannot consume every position."""
    if limit <= 0:
        return []
    selected: dict[str, Card] = {}
    for group in zip_longest(*lanes):
        for card in group:
            if card is not None:
                selected.setdefault(card["oracle_id"], card)
                if len(selected) >= limit:
                    return list(selected.values())
    return list(selected.values())


def query_results(query: Query, eligible: list[Card], seed: str) -> tuple[Card, set[str]]:
    """Preserve total matches and explicit truncation while bounding sampled candidates."""
    try:
        validate_query(query)
    except ValueError as exc:
        return {"query": query.model_dump(), "error": str(exc), "selected": []}, set()
    found = [c for c in eligible if matches(query, c)]
    signature = json.dumps(query.model_dump(exclude={"purpose"}), sort_keys=True)
    selected = seeded(found, f"{seed}|{signature}")[:8]
    return {
        "query": query.model_dump(),
        "matching_count": len(found),
        "truncated": len(found) > len(selected),
        "selected": selected,
    }, {c["oracle_id"] for c in found}


def discover(plan: Plan, catalog: Catalog, leader: Card, seed: str) -> Discovery:
    """Execute a model plan before any diagnostic cards are admitted."""
    eligible = eligible_cards(catalog, leader)
    nominations, errors = [], []
    seen: set[str] = set()
    for name in plan.named_cards:
        resolved = catalog.resolve(name)
        error = eligibility_error(resolved, set(leader["color_identity"]), leader["oracle_id"])
        if resolved is not None and resolved["oracle_id"] in seen:
            error = "duplicate"
        if error:
            errors.append({"name": name, "error": error})
        elif resolved is not None:
            nominations.append(resolved)
            seen.add(resolved["oracle_id"])
    reports, matched = [], set()
    for query in plan.searches:
        report, identities = query_results(query, eligible, seed)
        reports.append(report)
        matched.update(identities)
    query_cards = interleave([r["selected"] for r in reports], 20)
    shortlist = interleave([nominations, query_cards], SHORTLIST_LIMIT)
    return Discovery(
        nominations=nominations,
        nomination_errors=errors,
        queries=reports,
        shortlist=shortlist,
        matched_ids=matched,
    )


def recent_sample(eligible: list[Card], dates: Mapping[str, str | None], seed: str) -> list[Card]:
    """Sample eight designs first observed after model cutoff, not recent reprints."""
    recent = [c for c in eligible if CUTOFF < (dates.get(c["oracle_id"]) or "") <= AS_OF]
    return seeded(recent, seed)[:8]


def shared_pool(
    discoveries: dict[str, Discovery], controls: list[Card], recent: list[Card], seed: str
) -> Card:
    """Construct a common review pool while preserving independent-discovery attribution."""
    discovered = interleave([d.shortlist for d in discoveries.values()], POOL_LIMIT)
    # Diagnostic/scout slots are explicit additions, never credited to a planner.
    pool = interleave([[*controls, *recent, *discovered]], POOL_LIMIT)
    provenance: Card = {}
    for card in pool:
        identity = card["oracle_id"]
        channels = []
        if any(c["oracle_id"] == identity for c in controls):
            channels.append("diagnostic")
        if any(c["oracle_id"] == identity for c in recent):
            channels.append("recent_exploration")
        selected_by = []
        for model, found in discoveries.items():
            if any(c["oracle_id"] == identity for c in found.shortlist):
                selected_by.append(model)
                channels.append(f"{model}:independent_shortlist")
        provenance[identity] = {"channels": channels, "shortlisted_by": selected_by}
    return {"cards": seeded(pool, seed), "provenance": provenance}


def source_strings(value: object) -> list[str]:
    """Collect original field strings for literal quotation checks only."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in source_strings(child)]
    if isinstance(value, list):
        return [text for child in value for text in source_strings(child)]
    return []


def evidence_errors(item: Assessment, refs: dict[str, str], counts: Counter, keys: set) -> list:
    """Validate identity/quotation grounding without claiming semantic correctness."""
    errors = []
    if item.card_key not in keys:
        errors.append("unknown_candidate")
    if counts[item.card_key] > 1:
        errors.append("duplicate_assessment")
    if not any(e.key == item.card_key for e in item.evidence):
        errors.append("missing_candidate_evidence")
    for evidence in item.evidence:
        if evidence.key not in refs or evidence.quote not in refs[evidence.key]:
            errors.append(f"invalid_quote:{evidence.key}")
    if item.fit == "conditional" and not item.caveat.strip():
        errors.append("conditional_without_prerequisite")
    return errors


def validate_review(review: Review, payload: Card) -> Card:
    """Retain independently grounded items and report missing/duplicate/invalid results."""
    candidates = {c["key"]: c for c in payload["candidates"]}
    refs = {key: "\n".join(source_strings(card)) for key, card in candidates.items()}
    refs["D0"] = "\n".join(source_strings(payload["commander"]))
    refs.update({rule["key"]: rule["text"] for rule in payload["rules"]})
    counts = Counter(item.card_key for item in review.assessments)
    rows = [
        item.model_dump()
        | {
            "name": candidates.get(item.card_key, {}).get("name"),
            "evidence_errors": evidence_errors(item, refs, counts, set(candidates)),
        }
        for item in review.assessments
    ]
    valid = {r["card_key"] for r in rows if not r["evidence_errors"]}
    recommendation_counts = Counter(review.recommendations)
    by_key = {row["card_key"]: row for row in rows}
    recommendations = [
        {
            "rank": rank,
            "key": key,
            "name": candidates.get(key, {}).get("name"),
            "evidence_valid": key in valid and recommendation_counts[key] == 1,
            "recommendation_valid": key in valid
            and recommendation_counts[key] == 1
            and by_key[key]["fit"] not in {"weak", "uncertain"},
        }
        for rank, key in enumerate(review.recommendations, 1)
    ]
    missing = sorted(set(candidates) - counts.keys())
    return {
        "complete": not missing
        and len(rows) == len(candidates)
        and len(valid) == len(candidates)
        and all(r["recommendation_valid"] for r in recommendations),
        "missing_keys": missing,
        "assessments": rows,
        "recommendations": recommendations,
        "evidence_valid_count": len(valid),
        "candidate_count": len(candidates),
    }
