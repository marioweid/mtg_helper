"""Commander-mode adapter for bounded Deck Tutor teaching."""

from mtg_helper.models.tutor import TutorGuideDraft
from mtg_helper.services.tutor.teaching import TeachingInput, run_agent


async def generate(guide_input: TeachingInput) -> TutorGuideDraft:
    """Generate general Commander piloting instruction for the frozen saved list."""
    return await run_agent(
        guide_input,
        "Commander",
        "Teach multiplayer sequencing, board development, resilience, and the deck's own identity.",
    )
