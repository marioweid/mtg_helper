"""Final response composition for the Commander Coach pipeline."""

from mtg_helper.models.ai import (
    AnalysisFinding,
    CoachCurveReport,
    CoachCutReport,
    CoachManaReport,
    CoachUpgradeReport,
    DeckDoctorResponse,
    DeckIdentityReport,
    DoctorAdd,
    DoctorCut,
    DoctorSwap,
)
from mtg_helper.services.commander_coach import pipeline


def compose_doctor_response(
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
) -> DeckDoctorResponse:
    """Compose specialist outputs into the existing DeckDoctorResponse contract."""
    findings = _findings(identity, mana, curve)
    doctor_cuts = [
        DoctorCut(card_name=cut.card_name, reason=cut.reason, confidence=_confidence(cut.cut_score))
        for cut in cuts.candidates[:10]
    ]
    adds = [
        DoctorAdd(card=upgrade.card, reason=upgrade.reason, confidence="medium")
        for upgrade in upgrades.candidates[:10]
    ]
    swaps = _swaps(cuts, upgrades)
    return DeckDoctorResponse(
        summary=_summary(identity, mana, curve, cuts, upgrades),
        game_plan=_game_plan(identity),
        findings=findings,
        cuts=doctor_cuts,
        adds=adds,
        swaps=swaps,
        tool_call_count=upgrades.tool_call_count,
    )


def _summary(
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
    upgrades: CoachUpgradeReport,
) -> str:
    parts = [
        f"This reads as {identity.archetype}: {identity.main_plan}",
        f"Mana: {mana.summary}",
        f"Tempo: {curve.summary}",
    ]
    if cuts.candidates:
        parts.append(f"Top cuts are {', '.join(c.card_name for c in cuts.candidates[:4])}.")
    if upgrades.candidates:
        parts.append(f"Best adds are {', '.join(u.card.name for u in upgrades.candidates[:4])}.")
    return " ".join(parts)


def _game_plan(identity: DeckIdentityReport) -> str:
    text = identity.main_plan
    if identity.secondary_plan:
        text += f" Secondary plan: {identity.secondary_plan}"
    if identity.deck_tension:
        text += " Current tension: " + "; ".join(identity.deck_tension[:4]) + "."
    return text


def _findings(
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
) -> list[AnalysisFinding]:
    findings = _identity_findings(identity)
    findings.extend(pipeline.mana_findings(mana))
    findings.extend(pipeline.curve_findings(curve))
    return findings


def _identity_findings(identity: DeckIdentityReport) -> list[AnalysisFinding]:
    if not identity.deck_tension:
        return []
    return [
        AnalysisFinding(
            category="consistency",
            severity="info",
            title="Deck identity tensions",
            detail="; ".join(identity.deck_tension[:4]),
            evidence=(
                f"Identity: {identity.archetype}; "
                f"preserve {identity.must_preserve_themes[:5]}"
            ),
        )
    ]


def _swaps(cuts: CoachCutReport, upgrades: CoachUpgradeReport) -> list[DoctorSwap]:
    swaps: list[DoctorSwap] = []
    cut_names = [cut.card_name for cut in cuts.candidates]
    for index, upgrade in enumerate(upgrades.candidates[:8]):
        remove = [name for name in upgrade.replaces if name in cut_names]
        if not remove and index < len(cut_names):
            remove = [cut_names[index]]
        if not remove:
            continue
        swaps.append(DoctorSwap(remove=remove[:2], add=[upgrade.card], reason=upgrade.reason))
    return swaps


def _confidence(score: float) -> str:
    if score >= 7.5:
        return "high"
    if score >= 5.0:
        return "medium"
    return "low"
