"""Shared helpers for the Commander Coach specialist pipeline."""

from typing import Any

from mtg_helper.models.ai import AnalysisFinding, CoachCurveReport, CoachManaReport
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import mana_base_service, mana_curve_service
from mtg_helper.services.agents.deck_doctor_agent import _weak_card_rows


def deck_colors(deck: DeckDetailResponse) -> list[str]:
    """Return legal commander color identity letters for search filters."""
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


def compact_card_rows(deck: DeckDetailResponse) -> list[dict[str, Any]]:
    """Return compact, deterministic card rows for specialist prompts."""
    cards = sorted(deck.cards, key=lambda c: (float(c.cmc or 0), c.name))
    return [_card_row(card) for card in cards]


def deck_profile(deck: DeckDetailResponse, memory: str | None, message: str) -> dict[str, Any]:
    """Build the shared prompt payload used by Coach specialists."""
    commander = deck.commander_card
    partner = deck.partner_card
    return {
        "deck_name": deck.name,
        "commander": commander.model_dump() if commander else None,
        "partner": partner.model_dump() if partner else None,
        "bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
        "stage_targets": dict(deck.stage_targets or {}),
        "coach_memory_notes": memory or "",
        "user_goal": message,
        "card_count": sum(max(1, card.quantity) for card in deck.cards),
        "cards": compact_card_rows(deck),
    }


def analyze_mana(deck: DeckDetailResponse) -> CoachManaReport:
    """Convert deterministic mana-base analysis into a Coach report."""
    report = mana_base_service.analyze_mana_base(deck)
    color_issues = [_color_issue(color) for color in report.colors if color.deficit > 0]
    risky = [card.name for color in report.colors for card in color.risky_cards]
    if report.land_delta > 0:
        land_text = f"{report.land_delta} fewer land(s) than recommended"
    elif report.land_delta < 0:
        land_text = f"{-report.land_delta} more land(s) than recommended"
    else:
        land_text = "land count matches the recommendation"
    summary = f"{report.total_lands} lands; {land_text}."
    if color_issues:
        summary += " Color source pressure: " + "; ".join(color_issues[:3]) + "."
    return CoachManaReport(
        summary=summary,
        total_lands=report.total_lands,
        recommended_lands=report.recommended_lands,
        land_delta=report.land_delta,
        color_issues=color_issues,
        risky_cards=risky[:8],
        ramp_count=report.ramp_count,
    )


def analyze_curve(deck: DeckDetailResponse) -> CoachCurveReport:
    """Build a lightweight curve and tempo diagnosis for the Coach."""
    curve = mana_curve_service.current_curve(deck.cards)
    overloaded = _overloaded_buckets(curve)
    underfilled = _underfilled_buckets(curve)
    issues = _tempo_issues(deck, curve)
    parts = [f"Curve: {_curve_text(curve)}."]
    if overloaded:
        parts.append("Pressure at " + ", ".join(overloaded) + ".")
    if issues:
        parts.append(" ".join(issues[:2]))
    return CoachCurveReport(
        summary=" ".join(parts),
        curve=curve,
        overloaded_buckets=overloaded,
        underfilled_buckets=underfilled,
        tempo_issues=issues,
    )


def mana_findings(report: CoachManaReport) -> list[AnalysisFinding]:
    """Map mana report issues into existing Deck Doctor finding shape."""
    findings: list[AnalysisFinding] = []
    if report.land_delta != 0 or report.color_issues:
        findings.append(
            AnalysisFinding(
                category="mana_base",
                severity="warn",
                title="Mana base pressure",
                detail=report.summary,
                evidence=_evidence(report.color_issues + report.risky_cards),
            )
        )
    return findings


def curve_findings(report: CoachCurveReport) -> list[AnalysisFinding]:
    """Map curve report issues into existing Deck Doctor finding shape."""
    if not report.overloaded_buckets and not report.tempo_issues:
        return []
    return [
        AnalysisFinding(
            category="curve",
            severity="warn",
            title="Curve and tempo pressure",
            detail=report.summary,
            evidence=_evidence(report.overloaded_buckets + report.tempo_issues),
        )
    ]


def weak_cards(deck: DeckDetailResponse, limit: int = 16) -> list[dict[str, Any]]:
    """Return heuristic cut rows from the existing Deck Doctor helper."""
    return _weak_card_rows(deck, limit)


def _card_row(card: DeckCardItem) -> dict[str, Any]:
    return {
        "name": card.name,
        "mana_cost": card.mana_cost,
        "cmc": float(card.cmc) if card.cmc is not None else None,
        "type_line": card.type_line,
        "oracle_text": _snippet(card.oracle_text),
        "quantity": card.quantity,
        "categories": list(card.categories or []),
        "tags": list(card.tags or [])[:10],
        "price_eur_cents": card.price_eur_cents,
    }


def _color_issue(color: Any) -> str:
    return f"{color.color}: {color.source_count}/{color.target} sources"


def _curve_text(curve: dict[str, int]) -> str:
    return ", ".join(f"{key}={curve.get(key, 0)}" for key in mana_curve_service.BUCKETS)


def _overloaded_buckets(curve: dict[str, int]) -> list[str]:
    thresholds = {"1": 10, "2": 18, "3": 18, "4": 14, "5": 9, "6": 6, "7+": 4}
    return [bucket for bucket, limit in thresholds.items() if curve.get(bucket, 0) > limit]


def _underfilled_buckets(curve: dict[str, int]) -> list[str]:
    floors = {"1": 3, "2": 8}
    return [bucket for bucket, floor in floors.items() if curve.get(bucket, 0) < floor]


def _tempo_issues(deck: DeckDetailResponse, curve: dict[str, int]) -> list[str]:
    issues: list[str] = []
    early = curve.get("1", 0) + curve.get("2", 0)
    if early < 10:
        issues.append("The deck may not affect the board often enough before turn three.")
    if curve.get("3", 0) >= curve.get("2", 0) + 6:
        issues.append("The deck has 3-drop congestion; trade medium 3s for 1-2 mana engines.")
    if _early_ramp_count(deck) < 6:
        issues.append("Early ramp density looks low for reliably casting the commander on time.")
    return issues


def _early_ramp_count(deck: DeckDetailResponse) -> int:
    count = 0
    for card in deck.cards:
        if "Land" in (card.type_line or "") or float(card.cmc or 0) > 2:
            continue
        tags = set(card.tags or []) | set(card.categories or []) | set(card.qualifying_stages or [])
        text = (card.oracle_text or "").lower()
        finds_land = "search your library for a basic land" in text
        if "ramp" in tags or "add one mana" in text or finds_land:
            count += max(1, card.quantity)
    return count


def _snippet(text: str | None, limit: int = 320) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _evidence(items: list[str]) -> str:
    return "; ".join(items[:6]) if items else "No detailed evidence available."
