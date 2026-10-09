"""Persisted result projection and stable literal browsing, without model requests."""

import base64
import hashlib
import json

from mtg_helper.models.recommendations import CandidateView, QueryPage, QueryPreview, RunView
from mtg_helper.services.recommendations import budget, refinement
from mtg_helper.services.recommendations.discovery import (
    card_facts,
    eligible_cards,
    matches,
    validate_query,
)
from mtg_helper.services.recommendations.repository import DiscoveryError, value
from mtg_helper.services.recommendations.snapshots import Sources
from mtg_helper.services.recommendations.source import Card


def run_view(
    row: Card, excluded: set[str], *, commander_id: str, source_hash: str | None
) -> RunView:
    context, data = value(row["context"]), value(row["data"])
    review = data.get("review", {})
    judgments = {r["card_key"]: r for r in review.get("assessments", [])}
    ranked = {r["key"] for r in review.get("recommendations", []) if r["recommendation_valid"]}
    candidates = []
    for card in data.get("candidates", []):
        judgment = judgments.get(card["key"])
        errors = judgment.get("evidence_errors", []) if judgment else []
        state = "failed" if errors else "assessed" if judgment else "unassessed"
        if "review" in data and judgment is None:
            state = "failed"
            errors = ["missing_assessment"]
        candidates.append(
            CandidateView(
                oracle_id=card["oracle_id"],
                facts=card,
                state=state,
                evidence_errors=errors,
                recommended=card["key"] in ranked,
                excluded=card["oracle_id"] in excluded,
            )
        )
        if judgment and not errors:
            candidates[-1].assessment = refinement.KeyedAssessment.model_validate(
                {k: judgment[k] for k in refinement.KeyedAssessment.model_fields}
            )
    return RunView(
        id=row["id"],
        status=row["status"],
        phase=row["phase"],
        goal=context["goal"],
        created_at=row["created_at"],
        source_hash=row["source_hash"],
        rules_hash=row["rules_hash"],
        profile=row["profile"],
        error=row["error"],
        candidates=candidates,
        strategy=data.get("strategy_draft") if row["profile"] == budget.STRATEGY_VERSION else None,
        known_cost_microusd=row["known_cost_microusd"],
        held_microusd=row["held_microusd"],
        stale=(
            source_hash != row["source_hash"]
            or row["profile"] not in {budget.VERSION, budget.STRATEGY_VERSION}
            or context["commander"]["oracle_id"] != commander_id
        ),
    )


def rule_results(request: QueryPreview, sources: Sources) -> Card | None:
    if request.rule_query is None:
        return None
    if request.rule_query.cursor and request.rules_hash != sources.rules_hash:
        raise DiscoveryError("Rule continuation requires its pinned rules hash", 422)
    terms = request.rule_query.model_dump(exclude={"cursor"})
    fingerprint = hashlib.sha256(
        json.dumps(terms | {"profile": budget.VERSION}, sort_keys=True).encode()
    ).hexdigest()
    position = None
    if request.rule_query.cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(request.rule_query.cursor))
            if token["source"] != sources.rules_hash or token["query"] != fingerprint:
                raise ValueError("Different rules query/snapshot")
            position = token["after"]
        except (ValueError, KeyError, TypeError) as exc:
            raise DiscoveryError("Invalid rules cursor; restart this query/snapshot", 422) from exc
    query = refinement.RuleQuery.model_validate(terms | {"cursor": position})
    page = refinement.search_rules(query, sources.rules) | {"rules_hash": sources.rules_hash}
    if page["next_cursor"]:
        page["next_cursor"] = base64.urlsafe_b64encode(
            json.dumps(
                {"source": sources.rules_hash, "query": fingerprint, "after": page["next_cursor"]}
            ).encode()
        ).decode()
    return page


def browse(sources: Sources, leader: Card, excluded: set[str], request: QueryPreview) -> QueryPage:
    """Page literal eligible source matches with snapshot/query-bound continuation identity."""
    if request.query:
        validate_query(request.query)
    signature = request.model_dump(mode="json", exclude={"cursor", "snapshot_hash", "rules_hash"})
    signature["profile"] = budget.VERSION
    signature["rules_hash"] = sources.rules_hash
    signature["commander_id"] = leader["oracle_id"]
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    after = ""
    if request.cursor:
        try:
            cursor = json.loads(base64.urlsafe_b64decode(request.cursor))
            if cursor["source"] != sources.card_hash or cursor["query"] != fingerprint:
                raise ValueError("Different source/query")
            after = cursor["after"]
            if not isinstance(after, str):
                raise ValueError("Invalid continuation identity")
        except (ValueError, KeyError, TypeError) as exc:
            raise DiscoveryError("Invalid cursor; restart this query/snapshot", 422) from exc
    found = [
        c
        for c in eligible_cards(sources.catalog, leader)
        if request.name.casefold() in c["name"].casefold()
        and (request.query is None or matches(request.query, c))
    ]
    found.sort(key=lambda c: c["oracle_id"])
    if after and not any(c["oracle_id"] == after for c in found):
        raise DiscoveryError("Invalid cursor position; restart this query", 422)
    remaining = [c for c in found if c["oracle_id"] > after]
    page = remaining[: request.limit]
    next_cursor = None
    if len(remaining) > request.limit:
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {"source": sources.card_hash, "query": fingerprint, "after": page[-1]["oracle_id"]},
            ).encode()
        ).decode()
    return QueryPage(
        rules_hash=sources.rules_hash,
        snapshot_hash=sources.card_hash,
        total=len(found),
        next_cursor=next_cursor,
        cards=[
            CandidateView(
                oracle_id=c["oracle_id"], facts=card_facts(c), excluded=c["oracle_id"] in excluded
            )
            for c in page
        ],
        rule_results=rule_results(request, sources),
    )
