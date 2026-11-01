"""cEDH-mode adapter for bounded Deck Tutor teaching."""

from mtg_helper.models.tutor import TutorGuideDraft
from mtg_helper.services.tutor.teaching import TeachingInput, run_agent


async def generate(guide_input: TeachingInput) -> TutorGuideDraft:
    """Generate cEDH piloting instruction without certifying tournament strength."""
    return await run_agent(
        guide_input,
        "cEDH",
        "Teach resource efficiency, tutor targets, protection windows, "
        "and race-versus-grind pivots.",
    )
