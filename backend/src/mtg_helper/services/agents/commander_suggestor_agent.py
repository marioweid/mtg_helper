"""Pre-commander intent extraction agent for Commander suggestions."""

from dataclasses import dataclass

import asyncpg
from pydantic_ai import Agent, RunContext

from mtg_helper.models.ai import CommanderSuggestIntent, CommanderSuggestResponse
from mtg_helper.services.agents._history import to_model_messages
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.agents._prompts import (
    FORCE_FINALIZE_HINT,
    MAX_HISTORY_TURNS,
    SANDBOX_RULES,
)
from mtg_helper.services.agents.extract_agent import KEYWORD_EXAMPLES
from mtg_helper.services.commander_suggestor_service import (
    build_response,
    parse_intent_fallback,
)
from mtg_helper.services.keyword_catalog_service import load_keyword_prompt_catalog

_TEMPERATURE = 0.25
_MAX_OUTPUT_TOKENS = 1536


@dataclass
class CommanderSuggestDeps:
    """Per-run context for pre-commander intent extraction."""

    previous_intent: CommanderSuggestIntent | None
    at_history_limit: bool
    keyword_catalog: str


class CommanderSuggestAgentOutput(CommanderSuggestIntent):
    """LLM output: structured intent plus the next one-sentence reply."""

    reply: str
    done: bool = False


def _build_system_prompt(deps: CommanderSuggestDeps) -> str:
    previous = deps.previous_intent.model_dump_json() if deps.previous_intent else "{}"
    parts = [
        "You are a Magic: The Gathering Commander deck strategist.",
        "The player has not selected a commander yet. Infer the deck intent so a",
        "separate deterministic local ranker can recommend legal commanders.",
        "",
        SANDBOX_RULES,
        "",
        "Return structured intent only. Do NOT return commander names.",
        "Ask exactly one short follow-up question in `reply` unless done=true.",
        "The live commander board updates separately after every answer.",
        "",
        f"Previous intent JSON: {previous}",
        "",
        "Emit official MTGJSON keyword tags only in `mechanic_tags`.",
        "Use snake_case tag names such as:",
        ", ".join(KEYWORD_EXAMPLES),
        "Every `mechanic_tags` item must appear in the local catalog below.",
        "",
        "Available local MTGJSON keyword catalog:",
        deps.keyword_catalog,
        "",
        "Do not emit custom archetype tags like graveyard, blink, reanimator,",
        "aristocrats, voltron, spellslinger, or tribal tags.",
        "Do not invent compound tags such as etb_ping, graveyard_value, or token_draw.",
        "",
        "When a player asks for a concept that is not an MTGJSON keyword, express it as",
        "`traits`, `oracle_terms`, and `required_phrases` instead of fake keywords.",
        "Example: ETB ping should use traits=['etb'], oracle_terms=['enters', 'damage'],",
        "and required_phrases=['enters', 'damage'].",
        "",
        "Traits you may emit: etb, activated, evasion.",
        "Token types may be common token nouns such as treasure, food, clue, zombie, squirrel.",
        "Color identity means colors the commander must include, or null if the player has no",
        "preference. Set exact_color_identity=true only when the player asks for exactly those",
        "colors and no others.",
        "",
        "Prioritize asking about the biggest fork in the deck's plan:",
        "- graveyard: ETB value, sacrifice loops, self-mill, or big reanimation targets",
        "- ETB: blink, clones/copies, or toolbox value",
        "- open-ended: desired colors or power bracket",
    ]
    if deps.at_history_limit:
        parts += ["", FORCE_FINALIZE_HINT]
    return "\n".join(parts)


def _build_agent() -> Agent[CommanderSuggestDeps, CommanderSuggestAgentOutput]:
    agent = Agent[CommanderSuggestDeps, CommanderSuggestAgentOutput](
        model=make_google_model(),
        deps_type=CommanderSuggestDeps,
        output_type=CommanderSuggestAgentOutput,
        model_settings={"temperature": _TEMPERATURE, "max_tokens": _MAX_OUTPUT_TOKENS},
        retries=1,
    )

    @agent.system_prompt
    def system_prompt(ctx: RunContext[CommanderSuggestDeps]) -> str:
        return _build_system_prompt(ctx.deps)

    return agent


_AGENT: Agent[CommanderSuggestDeps, CommanderSuggestAgentOutput] | None = None


def get_agent() -> Agent[CommanderSuggestDeps, CommanderSuggestAgentOutput]:
    """Return the lazy singleton suggestor agent."""
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def suggest_turn(
    pool: asyncpg.Pool,
    history: list[dict[str, str]],
    message: str,
    previous_intent: CommanderSuggestIntent | None,
    *,
    limit: int,
) -> CommanderSuggestResponse:
    """Run one pre-commander suggestion turn and attach ranked commanders."""
    trimmed = history[-MAX_HISTORY_TURNS:]
    user_message = message.strip() or "I want to brew a Commander deck."
    deps = CommanderSuggestDeps(
        previous_intent=previous_intent,
        at_history_limit=len(history) >= MAX_HISTORY_TURNS,
        keyword_catalog=await load_keyword_prompt_catalog(pool),
    )
    try:
        result = await get_agent().run(
            user_message,
            deps=deps,
            message_history=to_model_messages(trimmed),
        )
        output = result.output
        intent = CommanderSuggestIntent(**output.model_dump(exclude={"reply", "done"}))
        reply = output.reply
        done = output.done
    except Exception:
        intent = parse_intent_fallback(user_message, previous_intent)
        reply = _fallback_reply(intent)
        done = False
    return await build_response(pool, reply=reply, done=done, intent=intent, limit=limit)


def _fallback_reply(intent: CommanderSuggestIntent) -> str:
    """Ask a useful deterministic follow-up when the model path is unavailable."""
    tags = set(intent.mechanic_tags)
    if tags & {"dredge", "flashback", "escape", "descend", "threshold", "delirium"}:
        return "Do you want self-mill value, sacrifice loops, or cards you can reuse from graveyard?"
    if "exile" in tags or "etb" in intent.traits:
        return "Do you want ETB value, toolbox creatures, or token-copy effects?"
    if intent.color_identity is None:
        return "Do you have a color identity in mind, or any colors you want to avoid?"
    return "Do you want this to be casual value, upgraded synergy, or optimized?"
