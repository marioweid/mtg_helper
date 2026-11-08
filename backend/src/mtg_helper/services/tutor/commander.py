"""Commander-mode adapter for bounded Deck Tutor teaching."""

from mtg_helper.models.tutor import TutorAnswerDraft, TutorGuideDraft
from mtg_helper.services.tutor.teaching import (
    ConversationInput,
    TeachingInput,
    run_agent,
    run_answer_agent,
)


async def generate(guide_input: TeachingInput) -> TutorGuideDraft:
    """Generate general Commander piloting instruction for the frozen saved list."""
    return await run_agent(
        guide_input,
        "Commander",
        "Teach multiplayer sequencing, board development, resilience, and the deck's own identity.",
    )


async def answer(question_input: ConversationInput) -> TutorAnswerDraft:
    """Answer from the current list with general Commander piloting emphasis."""
    return await run_answer_agent(
        question_input,
        "Teach multiplayer sequencing, board development, resilience, and the deck's own identity.",
    )
