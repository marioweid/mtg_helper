"""AI agent that diagnoses a goldfish sim run and proposes card swaps.

Drives a Gemini tool-calling loop with a single ``card_search`` tool so the
model's swap recommendations stay grounded in our card DB and within the
deck's color identity. Hard caps on tool calls and wall clock keep the loop
bounded.
"""

import asyncio
import json
import logging
import time
from typing import Any

import asyncpg
from google.genai import types as genai_types

from mtg_helper.models.ai import (
    AnalysisFinding,
    CardSearchHit,
    CardSearchInput,
    SimulationAnalysisResponse,
    SwapSuggestion,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.models.playtest import PlaytestStats
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.llm_client import ChatToolResponse, LLMClient, ToolCall

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 6
_WALL_CLOCK_SECONDS = 30.0
_TEMPERATURE = 0.2
_MAX_OUTPUT_TOKENS = 2048

_SYSTEM_PROMPT = """You are a deck-coaching analyst for Magic: The Gathering Commander decks.

You receive a JSON brief describing the deck and a batch of goldfish-simulation
KPIs. Diagnose the most impactful problems and propose concrete swap suggestions.

You have one tool — `card_search` — that returns candidate cards from our card
database, already filtered to the deck's color identity. Use it to look up
specific replacement cards before recommending them. Do not invent card names.

When you have enough information, respond with a single JSON object (no prose
around it) matching this schema:

{
  "summary": "2-3 sentence flavor paragraph",
  "findings": [
    {"category": "mana_base|consistency|curve|commander|color_fix|card_quality",
     "severity": "info|warn|critical",
     "title": "short headline",
     "detail": "what's wrong and why",
     "evidence": "the specific stat backing this"}
  ],
  "swap_suggestions": [
    {"remove": ["Card to remove"],
     "add": ["Card from card_search"],
     "reason": "why this swap helps"}
  ]
}

Keep findings <= 6 and swap_suggestions <= 4. Prefer concrete stats as evidence."""


def _tool_declaration() -> genai_types.Tool:
    return genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(
                name="card_search",
                description=(
                    "Search the card pool for replacement candidates. Always "
                    "filtered to the deck's color identity. Provide structural "
                    "filters; the tool returns up to `limit` matching cards."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "text_query": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Optional free-form search over name/oracle text.",
                        ),
                        "types": genai_types.Schema(
                            type=genai_types.Type.ARRAY,
                            items=genai_types.Schema(type=genai_types.Type.STRING),
                            description="Substrings to match in type_line (e.g. 'Land').",
                        ),
                        "tags": genai_types.Schema(
                            type=genai_types.Type.ARRAY,
                            items=genai_types.Schema(type=genai_types.Type.STRING),
                            description="Tags to match (e.g. 'ramp', 'removal', 'draw').",
                        ),
                        "min_cmc": genai_types.Schema(type=genai_types.Type.INTEGER),
                        "max_cmc": genai_types.Schema(type=genai_types.Type.INTEGER),
                        "max_price_eur_cents": genai_types.Schema(type=genai_types.Type.INTEGER),
                        "limit": genai_types.Schema(
                            type=genai_types.Type.INTEGER,
                            description="Up to 20.",
                        ),
                    },
                ),
            )
        ]
    )


def _brief_payload(deck: DeckDetailResponse, stats: PlaytestStats) -> dict[str, Any]:
    """Compact JSON view of the deck + sim for the model."""
    commander = deck.commander_card
    deck_view = {
        "commander": commander.name if commander else None,
        "commander_cost": commander.mana_cost if commander else None,
        "commander_colors": list(deck.commander_color_identity or []),
        "partner": deck.partner_card.name if deck.partner_card else None,
        "bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
        "max_price_cents": deck.max_price_cents,
        "card_count": sum(c.quantity for c in deck.cards),
        "land_count": sum(c.quantity for c in deck.cards if "Land" in (c.type_line or "")),
    }
    return {
        "deck": deck_view,
        "sim": _stats_summary(stats),
    }


def _stats_summary(stats: PlaytestStats) -> dict[str, Any]:
    return {
        "trials": stats.trials,
        "turns": stats.turns,
        "consistency": {
            "avg_mulligans": round(stats.avg_mulligans, 2),
            "pct_flood": round(stats.pct_flood, 3),
            "pct_screw": round(stats.pct_screw, 3),
            "pct_color_screw": round(stats.color_screw.pct_color_screw, 3),
            "color_shortages": stats.color_screw.shortages_by_color,
            "avg_first_missed_land_turn": round(stats.avg_first_missed_land_turn, 2),
            "kept_at_7": round(stats.opening_hand.pct_kept_7, 3),
        },
        "mulligan_reasons": stats.mulligan_reasons.model_dump(),
        "commander": stats.commander.model_dump() if stats.commander else None,
        "partner": stats.partner.model_dump() if stats.partner else None,
        "cast_rate_by_cmc": stats.cast_rate_by_cmc,
        "top_stuck_cards": [s.model_dump() for s in stats.top_stuck_cards],
        "unpaid_costs": [u.model_dump() for u in stats.unpaid_cost_summary],
        "per_turn_snapshot": [_turn_snapshot(t) for t in stats.per_turn],
        "sample_trials": [s.model_dump() for s in stats.sample_trials],
    }


def _turn_snapshot(turn: Any) -> dict[str, float | int]:
    return {
        "turn": turn.turn,
        "lands": round(turn.avg_lands_in_play, 2),
        "mana": round(turn.avg_mana_available, 2),
        "spent": round(turn.avg_mana_spent, 2),
        "unspent": round(turn.avg_mana_unspent, 2),
        "dead": round(turn.avg_dead_cards, 2),
        "color_dead": round(turn.avg_color_dead_cards, 2),
        "hand": round(turn.avg_cards_in_hand, 2),
    }


async def _run_tool(pool: asyncpg.Pool, deck_colors: list[str], call: ToolCall) -> dict[str, Any]:
    """Execute a tool call; return a JSON-serializable response payload."""
    if call.name != "card_search":
        return {"error": f"unknown tool: {call.name}"}
    try:
        inp = CardSearchInput.model_validate(call.args)
    except Exception as exc:  # noqa: BLE001 — surface validation errors to the agent
        return {"error": f"invalid args: {exc}"}
    hits = await search_cards(pool, deck_color_identity=deck_colors, inp=inp)
    return {"hits": [h.model_dump() for h in hits]}


def _user_brief_part(deck: DeckDetailResponse, stats: PlaytestStats) -> genai_types.Content:
    payload = _brief_payload(deck, stats)
    text = "Analyze this deck and simulation. Respond with the JSON schema described.\n\n"
    text += json.dumps(payload, indent=2, default=str)
    return genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=text)])


def _function_response_content(name: str, response: dict[str, Any]) -> genai_types.Content:
    return genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_function_response(name=name, response=response)],
    )


def _function_call_content(call: ToolCall) -> genai_types.Content:
    return genai_types.Content(
        role="model",
        parts=[
            genai_types.Part(function_call=genai_types.FunctionCall(name=call.name, args=call.args))
        ],
    )


def _normalize_add_entry(entry: Any) -> CardSearchHit:
    if isinstance(entry, str):
        return CardSearchHit(name=entry)
    return CardSearchHit.model_validate(entry)


def _parse_final_response(text: str, tool_call_count: int) -> SimulationAnalysisResponse:
    """Parse the model's final JSON response. Strips ```json fences if
    present; returns a minimal response with the raw text on parse failure
    so the user still sees the model's output.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json\n"):
            cleaned = cleaned[5:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return SimulationAnalysisResponse(
            summary=text.strip()[:500] or "Analysis returned no parseable output.",
            tool_call_count=tool_call_count,
        )
    findings = [AnalysisFinding.model_validate(f) for f in data.get("findings", [])]
    swaps_raw = data.get("swap_suggestions", [])
    swaps: list[SwapSuggestion] = []
    for s in swaps_raw:
        add_raw = s.get("add", [])
        # Add list may be names (strings) or full hits; normalize to hits.
        add_hits = [_normalize_add_entry(entry) for entry in add_raw]
        swaps.append(
            SwapSuggestion(
                remove=list(s.get("remove", [])),
                add=add_hits,
                reason=str(s.get("reason", "")),
            )
        )
    return SimulationAnalysisResponse(
        summary=str(data.get("summary", "")),
        findings=findings,
        swap_suggestions=swaps,
        tool_call_count=tool_call_count,
    )


async def analyze_simulation(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    deck: DeckDetailResponse,
    stats: PlaytestStats,
) -> SimulationAnalysisResponse:
    """Drive the agent loop. Returns a structured response — may include a
    partial result if the loop hit the tool-call cap or wall-clock timeout.
    """
    deck_colors = _deck_colors(deck)
    history: list[genai_types.Content] = [_user_brief_part(deck, stats)]
    tools = [_tool_declaration()]
    deadline = time.monotonic() + _WALL_CLOCK_SECONDS
    tool_calls = 0
    last_text: str = ""
    for _ in range(_MAX_TOOL_CALLS + 1):
        if time.monotonic() > deadline:
            _log.warning("analysis wall-clock timeout after %d tool calls", tool_calls)
            break
        resp = await _invoke_llm(ai_client, history, tools, deadline)
        if resp is None:
            break
        if resp.text is not None:
            last_text = resp.text
            break
        if resp.tool_calls is None:
            break
        tool_calls = await _dispatch_tool_calls(
            pool, deck_colors, resp.tool_calls, history, tool_calls
        )
        if tool_calls >= _MAX_TOOL_CALLS:
            break
    if not last_text:
        return SimulationAnalysisResponse(
            summary="Agent did not produce a final response within limits.",
            tool_call_count=tool_calls,
        )
    return _parse_final_response(last_text, tool_calls)


def _deck_colors(deck: DeckDetailResponse) -> list[str]:
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


async def _invoke_llm(
    ai_client: LLMClient,
    history: list[genai_types.Content],
    tools: list[genai_types.Tool],
    deadline: float,
) -> ChatToolResponse | None:
    try:
        return await asyncio.wait_for(
            ai_client.chat_with_tools(
                system=_SYSTEM_PROMPT,
                history=history,
                tools=tools,
                temperature=_TEMPERATURE,
                max_output_tokens=_MAX_OUTPUT_TOKENS,
            ),
            timeout=max(1.0, deadline - time.monotonic()),
        )
    except TimeoutError:
        return None


async def _dispatch_tool_calls(
    pool: asyncpg.Pool,
    deck_colors: list[str],
    calls: list[ToolCall],
    history: list[genai_types.Content],
    tool_calls: int,
) -> int:
    for call in calls:
        history.append(_function_call_content(call))
        tool_calls += 1
        result = await _run_tool(pool, deck_colors, call)
        history.append(_function_response_content(call.name, result))
        if tool_calls >= _MAX_TOOL_CALLS:
            break
    return tool_calls
