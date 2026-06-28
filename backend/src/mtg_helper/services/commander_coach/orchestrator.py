"""Commander Coach orchestration layer.

The coach is the stable entrypoint for user-facing Commander help. Whole-deck
advice now runs a small specialist pipeline: identity, mana, curve, cuts,
upgrades, validation, and final response composition.
"""

from collections.abc import Awaitable, Callable
from contextlib import nullcontext

import asyncpg

try:
    import logfire
except ModuleNotFoundError:  # pragma: no cover - depends on optional runtime package
    logfire = None

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse, DeckDoctorResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.commander_coach import final_response, pipeline, signal_lanes, validators
from mtg_helper.services.commander_coach.specialists import challenger, cuts, identity, upgrades
from mtg_helper.services.commander_coach.validators import ValidationIssue

ProgressCb = Callable[[str, str], Awaitable[None]]
MemoryLearnCb = Callable[[str], Awaitable[None]]


async def _noop_progress(_event: str, _message: str) -> None:
    return None


def _resolve_mode(request: CommanderCoachRequest) -> str:
    """Resolve specialist mode after the Coach router has selected whole-deck work."""
    if request.mode in {"auto", "doctor", "mana"}:
        return "doctor"
    return "doctor"


async def run_coach(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
    memory_learn: MemoryLearnCb | None = None,
) -> CommanderCoachResponse:
    """Run the Commander Coach specialist pipeline against a deck."""
    emit = progress or _noop_progress
    mode = _resolve_mode(request)
    await emit("routing", "Reading deck and routing request")
    await emit("routed", "Routed request to Commander Coach pipeline")
    span = _span("Commander Coach pipeline {deck_id} {mode}", deck_id=str(deck.id), mode=mode)
    with span:
        doctor = await _run_pipeline(pool, deck, request, emit)
        doctor = await _validate_output(deck, doctor, request, emit, memory_learn)
        await emit("finalizing", "Finalizing Coach response")
    prefix = "Commander Coach pipeline complete."
    if request.mode not in {"auto", "doctor", "mana"}:
        prefix = f"{request.mode.title()} specialist is not implemented yet; used Coach pipeline."
    return CommanderCoachResponse(mode=mode, reply=f"{prefix} {doctor.summary}", doctor=doctor)


async def _run_pipeline(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    emit: ProgressCb,
) -> DeckDoctorResponse:
    """Run specialist steps and compose their output."""
    await emit("mana_analyzing", "Mana Base step is checking sources and land count")
    mana_report = pipeline.analyze_mana(deck)
    await emit("mana_complete", mana_report.summary)
    await emit("curve_analyzing", "Curve & Tempo step is checking early plays")
    curve_report = pipeline.analyze_curve(deck)
    await emit("curve_complete", curve_report.summary)
    await emit("roles_analyzing", "Role Budget step is checking deck composition")
    role_report = pipeline.analyze_role_budget(deck)
    synergy_report = pipeline.analyze_synergy(deck)
    await emit("roles_complete", role_report.summary)
    await emit("signals_analyzing", "Signal Lane step is mapping commander and deck lanes")
    signal_report = signal_lanes.analyze_signals(
        deck,
        memory=request.coach_memory_notes,
        roles=role_report,
        synergy=synergy_report,
    )
    await emit("signals_complete", signal_report.summary)
    await emit("identity_analyzing", "Deck Identity Agent is identifying the game plan")
    identity_report = await identity.identify_deck(
        deck,
        coach_memory_notes=request.coach_memory_notes,
        user_goal=request.message,
        signals=signal_report,
    )
    await emit("identity_complete", f"Identified deck as {identity_report.archetype}")
    await emit("cuts_analyzing", "Cut Recommendation Agent is ranking weak fits")
    cut_report = await cuts.recommend_cuts(
        deck,
        identity_report,
        mana_report,
        curve_report,
        role_report,
        synergy_report,
        signal_report,
    )
    await emit("cuts_complete", f"Ranked {len(cut_report.candidates)} cut candidate(s)")
    await emit("upgrades_searching", "Upgrade Finder Agent is searching grounded additions")
    upgrade_report = await upgrades.recommend_upgrades(
        pool,
        deck,
        identity_report,
        mana_report,
        curve_report,
        cut_report,
        role_report,
        synergy_report,
        signal_report,
    )
    await emit("upgrades_complete", f"Found {len(upgrade_report.candidates)} upgrade(s)")
    await emit("challenger_reviewing", "Challenger Agent is reviewing recommendation fit")
    review = await challenger.review_plan(
        deck,
        identity_report,
        cut_report,
        upgrade_report,
        signal_report,
        role_report,
    )
    cut_report, upgrade_report = challenger.apply_review(cut_report, upgrade_report, review)
    await emit("challenger_complete", review.summary)
    return final_response.compose_doctor_response(
        identity_report,
        mana_report,
        curve_report,
        cut_report,
        upgrade_report,
        role_report,
        synergy_report,
    )


async def _validate_output(
    deck: DeckDetailResponse,
    doctor: DeckDoctorResponse,
    request: CommanderCoachRequest,
    emit: ProgressCb,
    memory_learn: MemoryLearnCb | None,
) -> DeckDoctorResponse:
    """Run existing Theme Guardian checks and filter invalid recommendations."""
    await emit("validation_routing", "Routing pipeline output to Theme Guardian")
    await emit("validating_theme", "Theme Guardian is checking commander, theme, and memory")
    with _span("Theme Guardian validation {deck_id}", deck_id=str(deck.id)):
        issues = validators.validate_doctor_output(
            deck,
            doctor,
            coach_memory_notes=request.coach_memory_notes,
        )
    await emit("validation_complete", f"Theme Guardian found {len(issues)} issue(s)")
    if issues and memory_learn is not None:
        await _learn_validation_issues(issues, emit, memory_learn)
    if not issues:
        return doctor
    await emit("final_validation", "Removing theme-breaking recommendations")
    removed = validators.filter_invalid_doctor_output(
        deck,
        doctor,
        coach_memory_notes=request.coach_memory_notes,
    )
    await emit("final_validation_complete", f"Removed {len(removed)} recommendation(s)")
    if removed:
        doctor.summary += f" Removed {len(removed)} theme-breaking recommendation(s)."
    return doctor


async def _learn_validation_issues(
    issues: list[ValidationIssue],
    emit: ProgressCb,
    memory_learn: MemoryLearnCb,
) -> None:
    learned = "; ".join(
        f"avoid {', '.join(issue.names)}: {issue.reason}" for issue in issues[:3]
    )
    await emit("memory_learning", "Writing Theme Guardian learning to Coach memory")
    await memory_learn(f"Theme Guardian learned: {learned}")


def _span(message: str, **kwargs: str):
    if logfire is None:
        return nullcontext()
    return logfire.span(message, **kwargs)
