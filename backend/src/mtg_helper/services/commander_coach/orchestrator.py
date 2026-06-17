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
    """Route the request to a specialist mode.

    The first slice intentionally supports only doctor behavior. Unsupported
    explicit modes fall back to doctor with a user-facing note in the response.
    """
    if request.mode == "auto":
        text = request.message.lower()
        if any(word in text for word in ("mana", "land", "color screw")):
            return "doctor"
        if any(word in text for word in ("cut", "add", "swap", "doctor", "fix")):
            return "doctor"
        return "doctor"
    if request.mode == "doctor":
        return "doctor"
    return "doctor"


ProgressCb = Callable[[str, str], Awaitable[None]]


async def _noop_progress(_event: str, _message: str) -> None:
    return None


async def run_coach(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
) -> CommanderCoachResponse:
    """Run the Commander Coach against a deck using the selected specialist."""
    emit = progress or _noop_progress
    await emit("started", "Reading deck and routing request")
    mode = _resolve_mode(request)
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
            doctor = await deck_doctor.doctor_deck(pool, deck)

        await emit("validating_theme", "Validating swaps against commander and theme")
        validate_span = (
            logfire.span("Validate doctor output {deck_id}", deck_id=str(deck.id))
            if logfire is not None
            else nullcontext()
        )
        with validate_span:
            issues = validators.validate_doctor_output(deck, doctor)
            if logfire is not None:
                logfire.info("Doctor validation found {issue_count} issues", issue_count=len(issues))

        revised = False
        if issues:
            await emit("revising", "Revising recommendations after theme validation")
            revision_span = (
                logfire.span("Deck Doctor revision {deck_id}", deck_id=str(deck.id))
                if logfire is not None
                else nullcontext()
            )
            with revision_span:
                feedback = validators.feedback_for_doctor(issues)
                doctor = await deck_doctor.doctor_deck(pool, deck, feedback)
            await emit("validating_theme", "Running final validation")
            final_span = (
                logfire.span("Final doctor validation {deck_id}", deck_id=str(deck.id))
                if logfire is not None
                else nullcontext()
            )
            with final_span:
                final_issues = validators.filter_invalid_doctor_output(deck, doctor)
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
