"""Pre-commander intent extraction agent for Commander suggestions."""

import logging
from dataclasses import dataclass

import asyncpg
from pydantic_ai import Agent, RunContext, UsageLimits

from mtg_helper.models.ai import CommanderSuggestIntent, CommanderSuggestResponse
from mtg_helper.services.agents._history import to_model_messages
from mtg_helper.services.agents._model import make_openai_model, openai_model_settings
from mtg_helper.services.agents._prompts import (
    FORCE_FINALIZE_HINT,
    MAX_HISTORY_TURNS,
    SANDBOX_RULES,
)
from mtg_helper.services.agents._usage import log_run_usage
from mtg_helper.services.commander_suggestor_service import (
    build_response,
    parse_intent_fallback,
)
from mtg_helper.services.keyword_catalog_service import (
    load_keyword_prompt_catalog,
    load_oracle_tag_prompt_catalog,
)

_MAX_OUTPUT_TOKENS = 1536
_log = logging.getLogger(__name__)


@dataclass
class CommanderSuggestDeps:
    """Per-run context for pre-commander intent extraction."""

    previous_intent: CommanderSuggestIntent | None
    at_history_limit: bool
    oracle_tag_catalog: str
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
        "Emit Scryfall Oracle-tag UUIDs in `archetype_tags`.",
        "Every `archetype_tags` item must appear in the source catalog below.",
        "",
        "Available Scryfall Oracle-tag catalog:",
        deps.oracle_tag_catalog,
        "",
        "Emit exact printed Scryfall keywords only in `mechanic_tags`.",
        "Every `mechanic_tags` item must appear in the local catalog below.",
        "",
        "Available printed-keyword catalog:",
        deps.keyword_catalog,
        "",
        "Do not invent Oracle tags or printed keywords.",
        "",
        "When a player asks for a concept that is not a printed keyword, express it with",
        "`oracle_terms` and `required_phrases` rather than inventing a label.",
        "Example: ETB ping uses oracle_terms=['enters', 'damage'] and",
        "required_phrases=['enters', 'damage'].",
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
        model=make_openai_model(),
        deps_type=CommanderSuggestDeps,
        output_type=CommanderSuggestAgentOutput,
        model_settings=openai_model_settings(
            max_tokens=_MAX_OUTPUT_TOKENS,
            reasoning="low",
        ),
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
        oracle_tag_catalog=await load_oracle_tag_prompt_catalog(pool),
        keyword_catalog=await load_keyword_prompt_catalog(pool),
    )
    try:
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
        log_run_usage("commander_suggestor", "suggest", result.usage())
        output = result.output
        intent = CommanderSuggestIntent(**output.model_dump(exclude={"reply", "done"}))
        reply = output.reply
        done = output.done
    except Exception as exc:
        _log.error(
            "AI run failed: workflow=commander_suggestor operation=suggest "
            "exception_type=%s; using deterministic fallback",
            type(exc).__name__,
        )
        intent = parse_intent_fallback(user_message, previous_intent)
        reply = _fallback_reply(intent)
        done = False
    return await build_response(pool, reply=reply, done=done, intent=intent, limit=limit)


def _fallback_reply(intent: CommanderSuggestIntent) -> str:
    """Ask a useful deterministic follow-up when the model path is unavailable."""
    tags = set(intent.mechanic_tags) | set(intent.archetype_tags)
    if tags & {"dredge", "flashback", "escape", "descend", "threshold", "delirium"}:
        return (
            "Do you want self-mill value, sacrifice loops, or cards you can reuse from graveyard?"
        )
    if "exile" in tags:
        return "Do you want ETB value, toolbox creatures, or token-copy effects?"
    if intent.color_identity is None:
        return "Do you have a color identity in mind, or any colors you want to avoid?"
    return "Do you want this to be casual value, upgraded synergy, or optimized?"
