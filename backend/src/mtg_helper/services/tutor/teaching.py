"""Bounded guide teacher shared by explicit Commander and cEDH adapters."""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext, UsageLimits

from mtg_helper.models.tutor import TutorEvidence, TutorGuideDraft
from mtg_helper.services.agents._model import make_openai_model, openai_model_settings


@dataclass(frozen=True)
class TeachingInput:
    """Frozen facts supplied to a single guide generation."""

    mode: str
    description: str | None
    bracket: int | None
    evidence: TutorEvidence


def _prompt(guide_input: TeachingInput, perspective: str) -> str:
    cards = "\n".join(
        f"{fact.quantity} {fact.name}: {fact.oracle_text or 'rules text unavailable'}"
        for fact in guide_input.evidence.commanders + guide_input.evidence.cards
    )
    return "\n".join(
        [
            f"You are a {perspective} Magic: The Gathering deck teacher.",
            "Write an English, practical saved deck guide only from the frozen list below.",
            "Label strategic interpretation as interpretation. Never call absent cards present or",
            "infer a win from missing evidence. Explain uncertainty rather than absence as proof.",
            "Do not certify",
            "strength.",
            "Cover commander role, packages, primary and backup lines with prerequisites or",
            "outlets/gaps, early/mid/late priorities, interaction, strengths, weaknesses, lessons,",
            "mistakes,",
            "terminology,",
            "and three actual-list seven-card keep/mulligan/context-dependent examples.",
            f"Saved description: {guide_input.description or 'none'}; "
            f"bracket: {guide_input.bracket!s}.",
            "Warnings: " + "; ".join(guide_input.evidence.warnings or ["none"]),
            "Frozen card facts:",
            cards,
        ]
    )


def _agent() -> Agent[TeachingInput, TutorGuideDraft]:
    agent = Agent[TeachingInput, TutorGuideDraft](
        model=make_openai_model(),
        deps_type=TeachingInput,
        output_type=TutorGuideDraft,
        model_settings=openai_model_settings(max_tokens=6000, reasoning="low", verbosity="medium"),
        retries=1,
    )

    @agent.system_prompt
    def system_prompt(ctx: RunContext[TeachingInput]) -> str:
        return _prompt(ctx.deps, ctx.deps.mode)

    return agent


async def run_agent(guide_input: TeachingInput, perspective: str) -> TutorGuideDraft:
    """Run one bounded model request for a guide; malformed output raises for durable failure."""
    result = await _agent().run(
        f"Generate the {perspective} guide now.",
        deps=guide_input,
        usage_limits=UsageLimits(request_limit=1, tool_calls_limit=0, output_tokens_limit=6000),
    )
    return result.output
