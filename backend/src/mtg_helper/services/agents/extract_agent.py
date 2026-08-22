"""Keyword-extracting deck agent (conversational, structured tag output)."""

from dataclasses import dataclass
from uuid import UUID

import asyncpg
from pydantic_ai import Agent, RunContext, UsageLimits

from mtg_helper.models.ai import KeywordExtractResponse
from mtg_helper.services import card_service
from mtg_helper.services.agents._history import to_model_messages
from mtg_helper.services.agents._model import make_openai_model, openai_model_settings
from mtg_helper.services.agents._prompts import (
    BRACKET_DESCRIPTIONS,
    FORCE_FINALIZE_HINT,
    MAX_HISTORY_TURNS,
    SANDBOX_RULES,
)
from mtg_helper.services.agents._usage import log_run_usage
from mtg_helper.services.agents.describe_agent import CommanderNotFoundError
from mtg_helper.services.theme_service import load_theme_prompt_catalog, load_theme_tags

_MAX_OUTPUT_TOKENS = 2048

KEYWORD_EXAMPLES: tuple[str, ...] = (
    "landfall",
    "surveil",
    "scry",
    "dredge",
    "flashback",
    "escape",
    "descend",
    "threshold",
    "delirium",
    "morbid",
    "undergrowth",
    "proliferate",
    "investigate",
    "connive",
    "discover",
    "explore",
    "cascade",
    "storm",
    "toxic",
    "infect",
)


@dataclass
class ExtractDeps:
    """Per-run context threaded into the agent's system prompt."""

    commander_name: str
    commander_type: str | None
    commander_oracle: str | None
    commander_colors: list[str]
    partner_name: str | None
    partner_oracle: str | None
    bracket: int
    at_history_limit: bool
    hub_catalog: str


def _build_system_prompt(deps: ExtractDeps) -> str:
    color_str = ", ".join(deps.commander_colors) if deps.commander_colors else "colorless"
    bracket_desc = BRACKET_DESCRIPTIONS.get(deps.bracket, "")
    vocab_str = ", ".join(KEYWORD_EXAMPLES)

    parts = [
        "You are a Magic: The Gathering Commander deck strategist.",
        "Your job is to identify a small set of shared deck theme tags",
        "that match the player's deck vision. The downstream retrieval system",
        "uses these tags as the primary card-suggestion signal.",
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
        "Use theme tags from this local Moxfield and Archidekt catalog:",
        deps.hub_catalog,
        "",
        "MTGJSON mechanic examples, for context only, include:",
        vocab_str,
        "",
        "Prefer hub tags like graveyard, blink, reanimator, aristocrats,",
        "voltron, spellslinger, etb, pingers, or plus_one_plus_one_counters.",
        "",
        "RULES:",
        "- Ask 1-3 short, focused questions to narrow the keyword plan while done=false.",
        "- Each question must be ONE sentence; no preambles.",
        "- Reference the commander's specific abilities when picking what to ask.",
        "- The `reply` field holds the conversational text shown to the user.",
        "- Set done=true ONLY when you have enough information.",
        "- When done=true, populate archetype_tags with theme tags from the catalog,",
        "  suggested_name, and stage_targets.",
        "",
        "STAGE TARGET GUIDELINES (defaults are fixed):",
        "- ramp: 12",
        "- draw: 12",
        "- interaction: 12",
        "- lands: 38",
        "- theme has no fixed target — fills remaining slots",
        "",
        "FORBIDDEN:",
        "- Do NOT invent tags outside the local theme catalog.",
        "- Do NOT write a prose `description` field.",
        "- Do NOT mention internal matching implementation details.",
    ]
    if deps.at_history_limit:
        parts += ["", FORCE_FINALIZE_HINT]
    return "\n".join(parts)


def _build_agent() -> Agent[ExtractDeps, KeywordExtractResponse]:
    agent = Agent[ExtractDeps, KeywordExtractResponse](
        model=make_openai_model(),
        deps_type=ExtractDeps,
        output_type=KeywordExtractResponse,
        model_settings=openai_model_settings(
            max_tokens=_MAX_OUTPUT_TOKENS,
            reasoning="minimal",
        ),
        retries=1,
    )

    @agent.system_prompt
    def system_prompt(ctx: RunContext[ExtractDeps]) -> str:
        return _build_system_prompt(ctx.deps)

    return agent


_AGENT: Agent[ExtractDeps, KeywordExtractResponse] | None = None


def get_agent() -> Agent[ExtractDeps, KeywordExtractResponse]:
    """Return the lazily constructed OpenAI Responses agent."""
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def extract_turn(
    pool: asyncpg.Pool,
    commander_scryfall_id: UUID,
    partner_scryfall_id: UUID | None,
    bracket: int,
    history: list[dict[str, str]],
    *,
    message: str,
) -> KeywordExtractResponse:
    """Run one turn of the keyword-extracting deck agent.

    Args:
        pool: asyncpg connection pool.
        commander_scryfall_id: Scryfall ID of the commander card.
        partner_scryfall_id: Scryfall ID of the partner commander, if any.
        bracket: Power level bracket (1–5).
        history: Full conversation history from the client.
        message: Latest user message; empty string means the initial prompt.

    Returns:
        ``KeywordExtractResponse`` with the reply, completion flag, and the
        running Moxfield hub theme tag selection.

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
    deps = ExtractDeps(
        commander_name=commander.name,
        commander_type=commander.type_line,
        commander_oracle=commander.oracle_text,
        commander_colors=list(commander.color_identity or []),
        partner_name=partner_name,
        partner_oracle=partner_oracle,
        bracket=bracket,
        at_history_limit=len(history) >= MAX_HISTORY_TURNS,
        hub_catalog=await load_theme_prompt_catalog(pool),
    )
    user_message = message.strip() or "I want to build a deck with this commander."
    result = await get_agent().run(
        user_message,
        deps=deps,
        message_history=to_model_messages(trimmed),
        usage_limits=UsageLimits(
            request_limit=2,
            tool_calls_limit=0,
            input_tokens_limit=24_000,
            output_tokens_limit=3_000,
        ),
    )
    log_run_usage("extract", "turn", result.usage())
    output = result.output
    allowed = await load_theme_tags(pool)
    output.archetype_tags = [tag for tag in output.archetype_tags if tag in allowed]
    return output
