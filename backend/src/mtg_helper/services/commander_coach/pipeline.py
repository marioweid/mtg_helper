"""Deterministic deck diagnostics shared by the assistant and evaluation tools."""

from typing import Any

from mtg_helper.models.ai import (
    CoachCurveReport,
    CoachManaReport,
    CoachRoleBudgetReport,
    CoachRoleStatus,
    CoachSynergyPackage,
    CoachSynergyReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import mana_base_service, mana_curve_service


def deck_colors(deck: DeckDetailResponse) -> list[str]:
    """Return legal commander color identity letters for search filters."""
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


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


def analyze_role_budget(deck: DeckDetailResponse) -> CoachRoleBudgetReport:
    """Count core Commander roles and decide which roles upgrades may target."""
    counts = _role_budget_counts(deck)
    targets = {
        "ramp": (8, 12),
        "draw": (8, 12),
        "interaction": (8, 12),
        "protection": (2, 5),
        "engines": (10, 18),
        "payoffs": (6, 12),
    }
    roles = [_role_status(role, counts.get(role, 0), bounds) for role, bounds in targets.items()]
    blocked = [role.role for role in roles if role.action != "add"]
    priority = [role.role for role in roles if role.action == "add"]
    summary = "; ".join(
        f"{role.role} {role.count}/{role.target_min}-{role.target_max}" for role in roles
    )
    return CoachRoleBudgetReport(
        summary=summary,
        roles=roles,
        blocked_roles=blocked,
        priority_roles=priority,
    )


def analyze_synergy(deck: DeckDetailResponse) -> CoachSynergyReport:
    """Report direct membership in the deck's selected Oracle tags."""
    reports = _selected_tag_reports(deck)
    weak = [item.package for item in reports if item.status == "low"]
    summary = "; ".join(f"{item.package}={item.count}" for item in reports)
    return CoachSynergyReport(summary=summary, packages=reports, weak_packages=weak)


def _role_budget_counts(deck: DeckDetailResponse) -> dict[str, int]:
    """Count explicitly assigned personal categories without classifying cards."""
    counts = {"ramp": 0, "draw": 0, "interaction": 0, "protection": 0, "engines": 0, "payoffs": 0}
    for card in deck.cards:
        if "Land" in (card.type_line or ""):
            continue
        qty = max(1, card.quantity)
        for role in set(card.categories):
            if role not in counts:
                continue
            counts[role] += qty
    return counts


def _role_status(role: str, count: int, bounds: tuple[int, int]) -> CoachRoleStatus:
    low, high = bounds
    if count < low:
        status, action = "low", "add"
    elif count > high:
        status, action = "high", "trim"
    else:
        status, action = "ok", "hold"
    return CoachRoleStatus(
        role=role,
        count=count,
        target_min=low,
        target_max=high,
        status=status,
        action=action,
    )


def _selected_tag_reports(deck: DeckDetailResponse) -> list[CoachSynergyPackage]:
    """Count cards directly assigned to each selected Oracle tag."""
    selected = set(deck.archetype_tags)
    if not selected:
        return []
    labels = {
        tag["id"]: tag.get("label", tag["id"])
        for card in deck.cards
        for tag in card.oracle_tags
        if "id" in tag
    }
    return [
        _selected_tag_report(deck, tag_id, labels.get(tag_id, tag_id))
        for tag_id in sorted(selected)
    ]


def _selected_tag_report(
    deck: DeckDetailResponse,
    tag_id: str,
    label: str,
) -> CoachSynergyPackage:
    """Build one direct Oracle-tag membership report."""
    examples: list[str] = []
    count = 0
    for card in deck.cards:
        if "Land" in (card.type_line or ""):
            continue
        card_tag_ids = {tag["id"] for tag in card.oracle_tags if "id" in tag}
        if tag_id in card_tag_ids:
            count += max(1, card.quantity)
            examples.append(card.name)
    status = "low" if count == 0 else "ok"
    return CoachSynergyPackage(package=label, count=count, examples=examples[:5], status=status)


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
        if "ramp" in set(card.categories or []):
            count += max(1, card.quantity)
    return count
