"""Bounded guide teacher shared by explicit Commander and cEDH adapters."""

from collections import Counter
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


def _prompt(guide_input: TeachingInput, perspective: str, focus: str) -> str:
    commanders = "\n".join(
        f"{fact.quantity} {fact.name}: {fact.oracle_text or 'rules text unavailable'}"
        for fact in guide_input.evidence.commanders
    )
    cards = "\n".join(
        f"{fact.quantity} {fact.name}: {fact.oracle_text or 'rules text unavailable'}"
        for fact in guide_input.evidence.cards
    )
    rules = "\n".join(f"{rule.identifier}: {rule.text}" for rule in guide_input.evidence.rules)
    combos = "\n".join(
        f"{combo.identifier}: {' + '.join(combo.pieces)} → "
        f"{', '.join(combo.produces) or 'no outlet'}; source description: "
        f"{combo.description or 'unverified'}"
        for combo in guide_input.evidence.combos
    )
    return "\n".join(
        [
            f"You are a {perspective} Magic: The Gathering deck teacher.",
            f"Teaching focus: {focus}",
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
            "Return exactly one structured opening_hands example for each decision. Each example",
            "contains exactly seven Mainboard cards, within listed quantities. Command-zone cards",
            "can never be opening-hand cards. Do not duplicate those card lists in the prose; the",
            "workspace renders the verified examples.",
            f"Saved description: {guide_input.description or 'none'}; "
            f"bracket: {guide_input.bracket!s}.",
            "Warnings: " + "; ".join(guide_input.evidence.warnings or ["none"]),
            "Source status: "
            + "; ".join(
                f"{kind}={status}" for kind, status in guide_input.evidence.sources.items()
            ),
            "Pinned rules: " + (rules or "unavailable"),
            "Captured combo lines: " + (combos or "none verified"),
            "Command zone (not in the library):",
            commanders or "unavailable",
            "Mainboard (the only opening-hand cards):",
            cards,
        ]
    )


def _agent(focus: str) -> Agent[TeachingInput, TutorGuideDraft]:
    agent = Agent[TeachingInput, TutorGuideDraft](
        model=make_openai_model(),
        deps_type=TeachingInput,
        output_type=TutorGuideDraft,
        model_settings=openai_model_settings(max_tokens=6000, reasoning="low", verbosity="medium"),
        retries=1,
    )

    @agent.system_prompt
    def system_prompt(ctx: RunContext[TeachingInput]) -> str:
        return _prompt(ctx.deps, ctx.deps.mode, focus)

    return agent


def validate_opening_hands(guide: TutorGuideDraft, evidence: TutorEvidence) -> None:
    """Reject teacher examples that cannot be drawn from the frozen mainboard."""
    expected_decisions = {"keep", "mulligan", "context-dependent"}
    decisions = {hand.decision for hand in guide.opening_hands}
    if len(guide.opening_hands) != 3 or decisions != expected_decisions:
        raise ValueError("Guide must provide keep, mulligan, and context-dependent opening hands")
    available = Counter({fact.name.casefold(): fact.quantity for fact in evidence.cards})
    for hand in guide.opening_hands:
        requested = Counter(card.casefold() for card in hand.cards)
        if any(requested[name] > available[name] for name in requested):
            raise ValueError("Guide opening hand contains cards outside the frozen mainboard")


async def run_agent(guide_input: TeachingInput, perspective: str, focus: str) -> TutorGuideDraft:
    """Run one bounded model request for a guide; malformed output raises for durable failure."""
    result = await _agent(focus).run(
        f"Generate the {perspective} guide now.",
        deps=guide_input,
        usage_limits=UsageLimits(request_limit=1, tool_calls_limit=0, output_tokens_limit=6000),
    )
    return result.output
