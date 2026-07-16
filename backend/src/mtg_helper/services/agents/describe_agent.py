"""Deck-description agent (conversational, structured output).

The agent runs a short conversation about the user's deck vision and emits
a ``DescribeResponse`` directly — pydantic-ai validates the output shape,
so no regex parsing is needed.
"""

from dataclasses import dataclass
from uuid import UUID

import asyncpg
from pydantic_ai import Agent, RunContext

from mtg_helper.models.ai import DescribeResponse
from mtg_helper.services import card_service
from mtg_helper.services.agents._history import to_model_messages
from mtg_helper.services.agents._model import (
    fast_google_model_settings,
    make_fast_google_model,
)
from mtg_helper.services.agents._prompts import (
    BRACKET_DESCRIPTIONS,
    FORCE_FINALIZE_HINT,
    MAX_HISTORY_TURNS,
    SANDBOX_RULES,
)

_TEMPERATURE = 0.3
_MAX_OUTPUT_TOKENS = 2048

# Known strategy tags the retrieval system recognizes — injected into the
# agent prompt so synthesized descriptions align with the retrieval vocabulary.
_STRATEGY_TAGS = (
    "ramp, token, tokens, voltron, aristocrats, graveyard, blink, stax, mill, "
    "tribal, sacrifice, lifegain, counters, equipment, interaction, tutor, "
    "extra turn, group hug, fast mana, draw, reanimator"
)


class CommanderNotFoundError(LookupError):
    """The requested commander card is not in the database."""


@dataclass
class DescribeDeps:
    """Per-run context threaded into the agent's system prompt."""

    commander_name: str
    commander_type: str | None
    commander_oracle: str | None
    commander_colors: list[str]
    partner_name: str | None
    partner_oracle: str | None
    bracket: int
    at_history_limit: bool


def _build_system_prompt(deps: DescribeDeps) -> str:
    color_str = ", ".join(deps.commander_colors) if deps.commander_colors else "colorless"
    bracket_desc = BRACKET_DESCRIPTIONS.get(deps.bracket, "")
    parts = [
        "You are a Magic: The Gathering Commander deck strategist.",
        "Your job is to understand the player's vision through conversation, then synthesize",
        "a structured deck description that will improve AI card suggestions.",
        "",
        SANDBOX_RULES,
        "",
        f"Commander: {deps.commander_name}",
        f"Type: {deps.commander_type or 'unknown'}",
        f"Color identity: {color_str}",
    ]
    if deps.commander_oracle:
        parts.append(f"Rules text: {deps.commander_oracle}")
    if deps.partner_name:
        parts.append(f"Partner: {deps.partner_name}")
        if deps.partner_oracle:
            parts.append(f"Partner rules text: {deps.partner_oracle}")
    parts += [
        f"\nPower level: Bracket {deps.bracket} — {bracket_desc}",
        "",
        "YOUR TASK:",
        "Ask focused questions to understand the player's deck vision.",
        "Tailor questions specifically to this commander's abilities and color identity.",
        "After 3-5 exchanges, return the final structured output with done=true.",
        "",
        "RULES:",
        "- Ask ONE question at a time while done=false.",
        "- Keep questions short and conversational.",
        "- Reference the commander's specific abilities when relevant.",
        "- The `reply` field holds the conversational text shown to the user.",
        "- Set done=true ONLY when you have enough information to synthesize.",
        "- When done=true, populate description, suggested_name, and stage_targets.",
        "",
        "STAGE TARGET GUIDELINES (defaults are intentionally fixed at 12/12/12/38):",
        "- ramp: 12 (mana acceleration)",
        "- draw: 12 (card draw / card advantage)",
        "- interaction: 12 (removal, board wipes, counterspells, protection, graveyard hate)",
        "- lands: 38 (mana base)",
        "- theme has no fixed target — fills remaining slots",
        "",
        "DESCRIPTION FORMAT:",
        "The description MUST naturally include relevant strategy keywords so the retrieval",
        "system can find thematically matching cards. Use words from this vocabulary when",
        f"appropriate: {_STRATEGY_TAGS}",
        "Example: 'graveyard aristocrats deck that sacrifices tokens to trigger death effects",
        "and drain opponents with lifegain. Focuses on recursive threats.'",
    ]
    if deps.at_history_limit:
        parts += ["", FORCE_FINALIZE_HINT]
    return "\n".join(parts)


def _build_agent() -> Agent[DescribeDeps, DescribeResponse]:
    agent = Agent[DescribeDeps, DescribeResponse](
        model=make_fast_google_model(),
        deps_type=DescribeDeps,
        output_type=DescribeResponse,
        model_settings=fast_google_model_settings(
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=_TEMPERATURE,
            thinking="minimal",
        ),
        retries=1,
    )

    @agent.system_prompt
    def system_prompt(ctx: RunContext[DescribeDeps]) -> str:
        return _build_system_prompt(ctx.deps)

    return agent


_AGENT: Agent[DescribeDeps, DescribeResponse] | None = None


def get_agent() -> Agent[DescribeDeps, DescribeResponse]:
    """Lazy singleton — Gemini provider needs ``settings.gemini_api_key``."""
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def describe_turn(
    pool: asyncpg.Pool,
    commander_scryfall_id: UUID,
    partner_scryfall_id: UUID | None,
    bracket: int,
    history: list[dict[str, str]],
    message: str,
) -> DescribeResponse:
    """Run one turn of the deck-description agent.

    Args:
        pool: asyncpg connection pool.
        commander_scryfall_id: Scryfall ID of the commander card.
        partner_scryfall_id: Scryfall ID of the partner commander, if any.
        bracket: Power level bracket (1–5).
        history: Full conversation history from the client.
        message: Latest user message; empty string means the initial prompt.

    Returns:
        ``DescribeResponse`` with the conversational reply plus optional
        completion fields when ``done=True``.

    Raises:
        CommanderNotFoundError: If the commander card is not in the database.
    """
    commander = await card_service.get_card_by_scryfall_id(pool, commander_scryfall_id)
    if commander is None:
        raise CommanderNotFoundError(f"Commander card {commander_scryfall_id} not found")

    partner_name: str | None = None
    partner_oracle: str | None = None
    if partner_scryfall_id is not None:
        partner = await card_service.get_card_by_scryfall_id(pool, partner_scryfall_id)
        if partner is not None:
            partner_name = partner.name
            partner_oracle = partner.oracle_text

    trimmed = history[-MAX_HISTORY_TURNS:]
    deps = DescribeDeps(
        commander_name=commander.name,
        commander_type=commander.type_line,
        commander_oracle=commander.oracle_text,
        commander_colors=list(commander.color_identity or []),
        partner_name=partner_name,
        partner_oracle=partner_oracle,
        bracket=bracket,
        at_history_limit=len(history) >= MAX_HISTORY_TURNS,
    )
    user_message = message.strip() or "I want to build a deck with this commander."
    result = await get_agent().run(
        user_message,
        deps=deps,
        message_history=to_model_messages(trimmed),
    )
    return result.output
