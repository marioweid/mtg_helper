"""cEDH-mode adapter for bounded Deck Tutor teaching."""

from mtg_helper.models.tutor import TutorAnswerDraft, TutorGuideDraft
from mtg_helper.services.tutor.teaching import (
    ConversationInput,
    TeachingInput,
    run_agent,
    run_answer_agent,
)


async def generate(guide_input: TeachingInput) -> TutorGuideDraft:
    """Generate cEDH piloting instruction without certifying tournament strength."""
    return await run_agent(
        guide_input,
        "cEDH",
        "Teach resource efficiency, tutor targets, protection windows, "
        "and race-versus-grind pivots.",
    )


async def answer(question_input: ConversationInput) -> TutorAnswerDraft:
    """Answer from current evidence with efficient race-versus-grind emphasis."""
    return await run_answer_agent(
        question_input,
        "Teach resource efficiency, tutor targets, protection windows, "
        "and race-versus-grind pivots.",
    )
