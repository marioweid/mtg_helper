"""Commander Coach orchestration layer.

The coach is the stable entrypoint for user-facing Commander help. It routes a
request to the best specialist agent, starting with the deck-doctor specialist.
"""

from collections.abc import Awaitable, Callable
from contextlib import nullcontext

import asyncpg

try:
    import logfire
except ModuleNotFoundError:  # pragma: no cover - depends on optional runtime package
    logfire = None

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.commander_coach import validators
from mtg_helper.services.commander_coach.specialists import deck_doctor


def _resolve_mode(request: CommanderCoachRequest) -> str:
    """Resolve specialist mode after the Coach router has selected specialist work."""
    if request.mode in {"auto", "doctor"}:
        return "doctor"
    return "doctor"


ProgressCb = Callable[[str, str], Awaitable[None]]
MemoryLearnCb = Callable[[str], Awaitable[None]]


async def _noop_progress(_event: str, _message: str) -> None:
    return None


async def run_coach(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
    memory_learn: MemoryLearnCb | None = None,
) -> CommanderCoachResponse:
    """Run the Commander Coach against a deck using the selected specialist."""
    emit = progress or _noop_progress
    await emit("routing", "Reading deck and routing request")
    mode = _resolve_mode(request)
    await emit("routed", f"Routed request to {mode.title()} specialist")
    span = (
        logfire.span("Commander Coach run {deck_id} {mode}", deck_id=str(deck.id), mode=mode)
        if logfire is not None
        else nullcontext()
    )
    with span:
        await emit("doctor_drafting", "Deck Doctor is drafting recommendations")
        draft_span = (
            logfire.span("Deck Doctor draft {deck_id}", deck_id=str(deck.id))
            if logfire is not None
            else nullcontext()
        )
        with draft_span:
            doctor = await deck_doctor.doctor_deck(
                pool,
                deck,
                coach_memory_notes=request.coach_memory_notes,
            )
        await emit(
            "doctor_complete",
            "Deck Doctor drafted "
            f"{len(doctor.findings)} finding(s), {len(doctor.swaps)} swap(s), "
            f"{len(doctor.adds)} add(s), and {len(doctor.cuts)} cut(s)",
        )

        await emit("validation_routing", "Routing Deck Doctor output to Theme Guardian")
        await emit("validation_routed", "Routed output to Theme Guardian validator")
        await emit("validating_theme", "Theme Guardian is checking commander, theme, and memory")
        validate_span = (
            logfire.span("Theme Guardian validation {deck_id}", deck_id=str(deck.id))
            if logfire is not None
            else nullcontext()
        )
        with validate_span:
            issues = validators.validate_doctor_output(
                deck,
                doctor,
                coach_memory_notes=request.coach_memory_notes,
            )
            await emit(
                "validation_complete",
                f"Theme Guardian found {len(issues)} issue(s)",
            )
            if logfire is not None:
                logfire.info(
                    "Doctor validation found {issue_count} issues",
                    issue_count=len(issues),
                )

        revised = False
        if issues:
            if memory_learn is not None:
                learned = "; ".join(
                    f"avoid {', '.join(issue.names)}: {issue.reason}" for issue in issues[:3]
                )
                await emit("memory_learning", "Writing Theme Guardian learning to Coach memory")
                await memory_learn(f"Theme Guardian learned: {learned}")
            await emit("revising", "Revising recommendations after theme validation")
            revision_span = (
                logfire.span("Deck Doctor revision {deck_id}", deck_id=str(deck.id))
                if logfire is not None
                else nullcontext()
            )
            with revision_span:
                feedback = validators.feedback_for_doctor(
                    issues,
                    coach_memory_notes=request.coach_memory_notes,
                )
                doctor = await deck_doctor.doctor_deck(
                    pool,
                    deck,
                    feedback,
                    coach_memory_notes=request.coach_memory_notes,
                )
            await emit(
                "revision_complete",
                "Deck Doctor revised recommendations after validation feedback",
            )
            await emit("validation_routing", "Routing revised output to Theme Guardian")
            await emit("validation_routed", "Routed revised output to Theme Guardian validator")
            await emit("validating_theme", "Theme Guardian is running final validation")
            final_span = (
                logfire.span("Final Theme Guardian validation {deck_id}", deck_id=str(deck.id))
                if logfire is not None
                else nullcontext()
            )
            with final_span:
                final_issues = validators.filter_invalid_doctor_output(
                    deck,
                    doctor,
                    coach_memory_notes=request.coach_memory_notes,
                )
                await emit(
                    "final_validation_complete",
                    f"Final validation removed {len(final_issues)} recommendation(s)",
                )
                if logfire is not None:
                    logfire.info(
                        "Final validation removed {issue_count} issues",
                        issue_count=len(final_issues),
                    )
            revised = True
        else:
            final_issues = []

        await emit("finalizing", "Finalizing Coach response")
    prefix = "Deck Doctor complete."
    if revised:
        prefix = "Deck Doctor revised after theme validation."
    if final_issues:
        prefix += f" Removed {len(final_issues)} theme-breaking recommendation(s)."
    if request.mode not in {"auto", "doctor"}:
        prefix = f"{request.mode.title()} specialist is not implemented yet; used Deck Doctor."
    return CommanderCoachResponse(mode=mode, reply=f"{prefix} {doctor.summary}", doctor=doctor)
