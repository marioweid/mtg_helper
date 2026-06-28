"""Challenger review specialist for Commander Coach recommendations."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

from mtg_helper.models.ai import (
    CoachCutReport,
    CoachReviewIssue,
    CoachReviewReport,
    CoachRoleBudgetReport,
    CoachSignalReport,
    CoachUpgradeReport,
    DeckIdentityReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.commander_coach import signal_lanes

_log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 25.0
_SYSTEM_PROMPT = """You are the Challenger Agent for a Commander deck coach.
Review proposed cuts and upgrades before the user sees them.

Block recommendations when:
- A cut removes a protected signal-lane card without a card-specific reason.
- A cut weakens a core commander lane, memory preference, or bridge card.
- An upgrade is already in the deck, illegal-looking for color identity, or is a land.
- An upgrade fills a role that is already blocked/overfilled, especially ramp.
- An upgrade has no visible connection to identity, signal lanes, role gaps, or cut roles.

Return concise issues only. Do not propose a new decklist. Prefer warnings for
close calls and blocks for clear theme, legality, duplicate, or role-budget failures.
"""


@dataclass(frozen=True)
class ChallengerDeps:
    """Dependencies for the recommendation review pass."""

    deck: DeckDetailResponse


def _build_agent() -> Agent[ChallengerDeps, CoachReviewReport]:
    return Agent[ChallengerDeps, CoachReviewReport](
        model=make_google_model(),
        deps_type=ChallengerDeps,
        output_type=CoachReviewReport,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={"temperature": 0.1, "max_tokens": 2048},
        retries=1,
    )


_AGENT: Agent[ChallengerDeps, CoachReviewReport] | None = None


def _get_agent() -> Agent[ChallengerDeps, CoachReviewReport]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def review_plan(
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
    signals: CoachSignalReport,
    roles: CoachRoleBudgetReport | None = None,
) -> CoachReviewReport:
    """Run Challenger review and merge deterministic guardrail issues."""
    deterministic = _deterministic_issues(deck, cuts, upgrades, signals, roles)
    try:
        result = await asyncio.wait_for(
            _get_agent().run(
                json.dumps(_payload(deck, identity, cuts, upgrades, signals, roles), default=str),
                deps=ChallengerDeps(deck),
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        issues = _merge_issues(deterministic, result.output.issues)
    except Exception:  # noqa: BLE001 - deterministic review still protects the pipeline
        _log.exception("Challenger Agent failed")
        issues = deterministic
    return CoachReviewReport(
        summary=_summary(issues),
        issues=issues,
        approved=not any(issue.severity == "block" for issue in issues),
    )


def apply_review(
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
    review: CoachReviewReport,
) -> tuple[CoachCutReport, CoachUpgradeReport]:
    """Remove blocked cut and upgrade recommendations from specialist reports."""
    blocked_cuts = _blocked_names(review, "cut")
    blocked_upgrades = _blocked_names(review, "upgrade")
    return (
        cuts.model_copy(
            update={
                "candidates": [
                    cut for cut in cuts.candidates if cut.card_name not in blocked_cuts
                ]
            }
        ),
        upgrades.model_copy(
            update={
                "candidates": [
                    item for item in upgrades.candidates if item.card.name not in blocked_upgrades
                ]
            }
        ),
    )


def _payload(
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
    signals: CoachSignalReport,
    roles: CoachRoleBudgetReport | None,
) -> dict[str, Any]:
    return {
        "deck": {
            "name": deck.name,
            "commander": deck.commander_card.model_dump() if deck.commander_card else None,
            "archetype_tags": list(deck.archetype_tags or []),
            "card_names": [card.name for card in deck.cards],
        },
        "identity": identity.model_dump(),
        "signals": signals.model_dump(),
        "role_budget": roles.model_dump() if roles else None,
        "cuts": cuts.model_dump(),
        "upgrades": upgrades.model_dump(),
    }


def _deterministic_issues(
    deck: DeckDetailResponse,
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
    signals: CoachSignalReport,
    roles: CoachRoleBudgetReport | None,
) -> list[CoachReviewIssue]:
    issues = _cut_issues(deck, cuts, signals)
    issues.extend(_upgrade_issues(deck, upgrades, signals, roles))
    return issues


def _cut_issues(
    deck: DeckDetailResponse,
    cuts: CoachCutReport,
    signals: CoachSignalReport,
) -> list[CoachReviewIssue]:
    cards = {card.name: card for card in deck.cards}
    protected = set(signals.protected_cards)
    issues: list[CoachReviewIssue] = []
    for cut in cuts.candidates:
        card = cards.get(cut.card_name)
        if card is None:
            issues.append(_issue("block", "cut", [cut.card_name], "Cut card is not in the deck."))
            continue
        if cut.card_name in protected and cut.cut_score < 8.5:
            issues.append(
                _issue(
                    "block",
                    "cut",
                    [cut.card_name],
                    "Cuts a protected signal-lane card without overwhelming confidence.",
                )
            )
        elif signal_lanes.card_overlaps_protected_lane(card, signals) and cut.cut_score < 7.5:
            issues.append(
                _issue(
                    "warn",
                    "cut",
                    [cut.card_name],
                    "Touches a core signal lane; cut reason must explain why it is off-plan.",
                )
            )
    return issues


def _upgrade_issues(
    deck: DeckDetailResponse,
    upgrades: CoachUpgradeReport,
    signals: CoachSignalReport,
    roles: CoachRoleBudgetReport | None,
) -> list[CoachReviewIssue]:
    deck_names = {card.name for card in deck.cards}
    blocked_roles = set(roles.blocked_roles if roles else [])
    issues: list[CoachReviewIssue] = []
    for candidate in upgrades.candidates:
        card = candidate.card
        if card.name in deck_names:
            issues.append(
                _issue("block", "upgrade", [card.name], "Upgrade is already in the deck.")
            )
        if "land" in (card.type_line or "").lower():
            issues.append(_issue("block", "upgrade", [card.name], "Upgrade is a land."))
        if candidate.role in blocked_roles or (_is_ramp(card) and "ramp" in blocked_roles):
            issues.append(_issue("block", "upgrade", [card.name], "Upgrade fills a blocked role."))
        if not _overlaps_signal(card, signals) and candidate.role not in set(signals.weak_lanes):
            issues.append(
                _issue(
                    "warn",
                    "upgrade",
                    [card.name],
                    "Upgrade has weak visible overlap with the detected signal lanes.",
                )
            )
    return issues


def _overlaps_signal(card: object, signals: CoachSignalReport) -> bool:
    text = _card_text(card)
    return any(term.lower() in text for lane in signals.lanes for term in lane.terms)


def _is_ramp(card: object) -> bool:
    text = _card_text(card)
    return "add one mana" in text or "search your library for a land" in text or "ramp" in text


def _card_text(card: object) -> str:
    parts = [
        getattr(card, "type_line", "") or "",
        getattr(card, "oracle_text", "") or "",
        " ".join(getattr(card, "tags", []) or []),
    ]
    return " ".join(parts).lower()


def _issue(
    severity: str,
    item_type: str,
    names: list[str],
    reason: str,
) -> CoachReviewIssue:
    return CoachReviewIssue(
        severity=severity,  # type: ignore[arg-type]
        item_type=item_type,  # type: ignore[arg-type]
        names=names,
        reason=reason,
    )


def _merge_issues(
    first: list[CoachReviewIssue],
    second: list[CoachReviewIssue],
) -> list[CoachReviewIssue]:
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    out: list[CoachReviewIssue] = []
    for issue in [*first, *second]:
        key = (issue.severity, issue.item_type, tuple(issue.names), issue.reason)
        if key in seen:
            continue
        seen.add(key)
        out.append(issue)
    return out[:16]


def _blocked_names(review: CoachReviewReport, item_type: str) -> set[str]:
    return {
        name
        for issue in review.issues
        if issue.severity == "block" and issue.item_type == item_type
        for name in issue.names
    }


def _summary(issues: list[CoachReviewIssue]) -> str:
    blocks = sum(issue.severity == "block" for issue in issues)
    warnings = sum(issue.severity == "warn" for issue in issues)
    if not issues:
        return "Challenger review found no blocking issues."
    return f"Challenger review found {blocks} block(s) and {warnings} warning(s)."
