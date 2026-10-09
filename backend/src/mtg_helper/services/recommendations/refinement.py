"""Offline-only foundations for the separate, Luna-first refined discovery pipeline.

No client, secrets, database, paid execution or application integration is present here.
"""

import json
import re
from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from types import GenericAlias
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from mtg_helper.services.recommendations.discovery import (
    Discovery,
    Evidence,
    Plan,
    Review,
    StrictModel,
    card_facts,
    discover,
    eligible_cards,
    validate_review,
)
from mtg_helper.services.recommendations.source import Card, Catalog

RULE_ID = re.compile(r"^(\d{3,}\.\d+[a-z]*)(?:\.)?\s+")


class RuleQuery(StrictModel):
    """Literal full-source lookup, with no fixed mechanic or interaction labels."""

    purpose: str = Field(min_length=1, max_length=220)
    text_all: list[str] = Field(max_length=5)
    text_any: list[str] = Field(max_length=5)
    cursor: str | None = Field(max_length=100)


class RefinementPlan(Plan):
    """Card hypotheses plus requests against the unclassified, complete rules corpus."""

    rule_searches: list[RuleQuery] = Field(max_length=8)


class KeyedAssessment(StrictModel):
    """The enclosing candidate key is authoritative; the model cannot supply another one."""

    fit: Literal["core", "support", "conditional", "weak", "uncertain"]
    reason: str = Field(min_length=1, max_length=220)
    caveat: str = Field(max_length=140)
    evidence: list[Evidence] = Field(min_length=1, max_length=2)


def review_type(payload: Card) -> type[BaseModel]:
    """Build a closed coverage contract from this request's candidate IDs.

    Args:
        payload: Complete source context with stable, unique C-keys.

    Returns:
        A response model requiring one assessment property per supplied candidate.
    """
    keys = [candidate["key"] for candidate in payload["candidates"]]
    if not keys or len(keys) > 64 or len(set(keys)) != len(keys):
        raise ValueError("Review needs 1–64 unique supplied candidate IDs; correct the payload")
    if any(re.fullmatch(r"C\d{2}", key) is None for key in keys):
        raise ValueError("Candidate IDs must be bare Cxx values; correct the payload")
    candidate_id = StrEnum("candidate_id", {key: key for key in keys})
    fields: dict[str, Any] = {key: (KeyedAssessment, ...) for key in keys}
    coverage = create_model("CandidateCoverage", __base__=StrictModel, **fields)
    return create_model(
        "GroundedReview",
        __base__=StrictModel,
        recommendations=(GenericAlias(list, candidate_id), Field(max_length=15)),
        assessments=(coverage, ...),
    )


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject repeated JSON properties rather than allowing a silent last-value overwrite."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON property {key!r}; retain the failed response")
        value[key] = item
    return value


def parse_review(text: str, payload: Card) -> Card:
    """Validate closed coverage, then reuse unchanged literal/semantic-boundary checks.

    Args:
        text: Raw model JSON; duplicate properties are an error, not a last-value override.
        payload: Exact source context used to construct the request-specific schema.

    Returns:
        Original scorer output, without claiming semantic accuracy or repairing invalid evidence.
    """
    raw = json.loads(text, object_pairs_hook=unique_object)
    parsed = review_type(payload).model_validate(raw).model_dump(mode="json")
    legacy = Review.model_validate(
        {
            "recommendations": parsed["recommendations"],
            "assessments": [
                {"card_key": key, **item} for key, item in parsed["assessments"].items()
            ],
        }
    )
    return validate_review(legacy, payload)


def insert_rule(entries: Card, key: str, text: str) -> None:
    """Refuse conflicting source identities instead of choosing an arbitrary definition."""
    if key in entries and entries[key]["text"] != text:
        raise ValueError(f"Conflicting rule source {key!r}; inspect the versioned text")
    entries[key] = {"key": key, "text": text}


def parse_rules(text: str) -> Card:
    """Index native numbered paragraphs and glossary definitions, preserving source examples.

    Args:
        text: Full official Comprehensive Rules text, or an isolated source fragment.

    Returns:
        Complete text entries keyed by native rule ID or unrestricted glossary title.
    """
    entries: Card = {}
    glossary = None
    markers = list(re.finditer(r"^Glossary\s*$", text, re.MULTILINE))
    if markers:
        marker = markers[-1]
        glossary = text[marker.end() :].split("\nCredits", 1)[0]
        text = text[: marker.start()]
    last = None
    for block in re.split(r"\n[\t \u00a0]*\n", text.replace("\r\n", "\n")):
        block = block.strip()
        found = RULE_ID.match(block)
        if found:
            last = found[1]
            insert_rule(entries, last, block)
        elif block.startswith("Example:") and last:
            entries[last]["text"] += "\n\n" + block
    if glossary is not None:
        entries.update(parse_glossary(glossary))
    if not entries:
        raise ValueError("No native rules/glossary entries found; inspect the source shape")
    return entries


def parse_glossary(text: str) -> Card:
    """Index unrestricted source titles; new mechanic names require no code vocabulary."""
    entries: Card = {}
    for block in re.split(r"\n[\t \u00a0]*\n", text):
        lines = block.strip().splitlines()
        if len(lines) >= 2:
            insert_rule(entries, f"G:{lines[0]}", "\n".join(lines))
    return entries


def search_rules(query: RuleQuery, entries: Mapping[str, Card]) -> Card:
    """Execute literal operations with stable resumable results; matching is not strategic fit.

    Args:
        query: All/any substrings and an optional last-returned-key cursor. Only reuse cursors
            with the same query and source snapshot; these are not semantic classifications.
        entries: Native rules/glossary entries from a pinned source snapshot.

    Returns:
        Total matches, up to eight complete source entries, and a continuation cursor.

    Raises:
        ValueError: Empty/unsupported terms or a cursor absent from these results.
    """
    terms = query.text_all + query.text_any
    if not terms or any(not term.strip() or len(term) > 100 for term in terms):
        raise ValueError("Rule search needs a nonblank literal operation of at most 100 chars")
    found = []
    for entry in entries.values():
        text = entry["text"].casefold()
        if all(term.casefold() in text for term in query.text_all) and (
            not query.text_any or any(term.casefold() in text for term in query.text_any)
        ):
            found.append(entry)
    found.sort(key=lambda entry: (len(entry["text"]), entry["key"]))
    total = len(found)
    if query.cursor is not None:
        positions = {entry["key"]: index for index, entry in enumerate(found)}
        if query.cursor not in positions:
            raise ValueError(
                "Rule cursor is not in these query results; restart from this snapshot"
            )
        found = found[positions[query.cursor] + 1 :]
    selected = found[:8]
    return {
        "query": query.model_dump(),
        "matching_count": total,
        "truncated": len(found) > 8,
        "next_cursor": selected[-1]["key"] if len(found) > 8 else None,
        "selected": selected,
    }


def discovery_feedback(found: Discovery) -> Card:
    """Expose actual errors, zero/broad totals and two complete source samples per query."""
    return {
        "nomination_errors": found.nomination_errors,
        "queries": [
            {key: value for key, value in report.items() if key != "selected"}
            | {
                "selected": [card_facts(card) for card in report["selected"][:2]],
                "sample_limit": 2,
                "truncated": report.get("matching_count", 0) > len(report["selected"][:2]),
            }
            for report in found.queries
        ],
    }


def source_prefixes(cards: list[Card]) -> list[Card]:
    """Show frequent actual Oracle line prefixes without teaching a mechanic whitelist."""
    counts: Counter[str] = Counter()
    for card in cards:
        texts = [card.get("oracle_text") or ""]
        texts += [face.get("oracle_text") or "" for face in card.get("card_faces", [])]
        for text in texts:
            for line in text.splitlines():
                if line.strip():
                    counts[line.strip()[:60]] += 1
    return [{"text": text, "count": count} for text, count in counts.most_common(12)]


def planning_observation(
    plan: RefinementPlan, catalog: Catalog, leader: Card, entries: Card, seed: str
) -> Card:
    """Execute declared searches and return feedback for a subsequent planning step.

    Args:
        plan: Model-generated operations, without reference-deck or diagnostic hints.
        catalog: Complete pinned local card catalog.
        leader: Source commander used to enforce eligibility.
        entries: Full versioned rules/glossary corpus.
        seed: Reproducible sampling identity.

    Returns:
        Actual results/errors and complete samples; no strategic fit is inferred.
    """
    found = discover(plan, catalog, leader, seed)
    rule_results = []
    for query in plan.rule_searches:
        try:
            rule_results.append(search_rules(query, entries))
        except ValueError as exc:
            rule_results.append({"query": query.model_dump(), "error": str(exc), "selected": []})
    return {
        "card_searches": discovery_feedback(found),
        "rule_searches": rule_results,
        "source_prefixes": source_prefixes(eligible_cards(catalog, leader)),
        "note": "Matches are hypotheses, not fit; broad/zero/error results need explicit revision.",
    }
