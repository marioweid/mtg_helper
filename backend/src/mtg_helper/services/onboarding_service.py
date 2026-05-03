"""Onboarding quickstart: create a deck and auto-fill it via the build pipeline.

A first-run user picks a commander, optional partner, and a price band, and
this service runs the entire staged build pipeline server-side, accepting the
top suggestions for each stage. The user lands on the deck's build wizard with
a complete draft already populated.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import asyncpg
from qdrant_client import AsyncQdrantClient

from mtg_helper.models.decks import DeckCardAdd, DeckCreate, DeckResponse, DeckUpdate
from mtg_helper.services import ai_service, card_service, deck_service
from mtg_helper.services.deck_service import (
    CardNotFoundError,
    ColorIdentityError,
    DeckNotFoundError,
)
from mtg_helper.services.llm_client import LLMClient

_log = logging.getLogger(__name__)

# Stage order: theme first so the synergy backbone is in place before
# category stages retrieve against it. "complete" is intentionally absent.
QUICKSTART_STAGE_ORDER: tuple[str, ...] = (
    "theme",
    "ramp",
    "interaction",
    "draw",
    "utility",
    "lands",
)

# Per-stage acceptance targets. Sums to ~90 cards (commander + 89).
QUICKSTART_TARGETS: dict[str, int] = {
    "theme": 22,
    "ramp": 10,
    "interaction": 8,
    "draw": 8,
    "utility": 5,
    "lands": 37,
}

# Land the user at stage 1 of the wizard so they can review/swap from the
# top of the funnel rather than at "complete".
_INITIAL_WIZARD_STAGE = QUICKSTART_STAGE_ORDER[0]

# How aggressively to over-fetch from build_stage to leave headroom for
# color/category rejections.
_OVERFETCH_MULTIPLIER = 2

# Default basic-land mapping. The lands stage of quickstart fills the mana
# base entirely with basics distributed across the commander's color identity
# — duals are intentionally left for the user to swap in. A colorless commander
# falls back to Wastes.
_COLOR_TO_BASIC: dict[str, str] = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}
_COLORLESS_BASIC = "Wastes"


@dataclass
class QuickstartStageResult:
    """Per-stage outcome reported back to the caller."""

    stage: str
    target: int
    accepted: int


ProgressCb = Callable[[QuickstartStageResult], Awaitable[None]]


async def quickstart(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    *,
    email: str,
    account_id: UUID,
    commander_scryfall_id: UUID,
    partner_scryfall_id: UUID | None = None,
    max_price_cents: int | None = None,
    min_price_cents: int | None = None,
    bracket: int = 2,
    name: str | None = None,
    on_progress: ProgressCb | None = None,
) -> tuple[DeckResponse, list[QuickstartStageResult]]:
    """Run the full staged build pipeline against a fresh deck.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter (used by build_stage for embeddings).
        qdrant_client: Qdrant async client (used by build_stage retrieval).
        email: Authenticated account email; deck owner.
        account_id: Authenticated account UUID; passed to build_stage so
            preference and feedback weights are honored.
        commander_scryfall_id: Commander to build around.
        partner_scryfall_id: Optional partner commander.
        max_price_cents: Optional per-card price ceiling, persisted on the
            deck so subsequent manual stage rebuilds inherit it.
        min_price_cents: Optional per-card price floor; persisted.
        bracket: Deck bracket (1–4); default 2 (precon-friendly).
        name: Optional deck name; defaults to "{commander_name} sample deck".
        on_progress: Optional async callback fired after each stage.

    Returns:
        Tuple of (final DeckResponse, per-stage results). Stage column on the
        returned deck is set to ``QUICKSTART_STAGE_ORDER[0]`` so the wizard
        opens at stage 1.

    Raises:
        CardNotFoundError: If the commander or partner is not in the local DB.
    """
    commander = await card_service.get_card_by_scryfall_id(pool, commander_scryfall_id)
    if commander is None:
        raise CardNotFoundError(
            f"Commander {commander_scryfall_id} not found in the local card database"
        )

    deck_name = name or f"{commander.name} sample deck"
    deck = await deck_service.create_deck(
        pool,
        DeckCreate(
            commander_scryfall_id=commander_scryfall_id,
            partner_scryfall_id=partner_scryfall_id,
            name=deck_name,
            description=None,
            bracket=bracket,
            stage_targets=dict(QUICKSTART_TARGETS),
            max_price_cents=max_price_cents,
            min_price_cents=min_price_cents,
        ),
        email,
    )

    # Shared running counts mirror the wizard's `computeStageCounts` view
    # (cards with overlapping qualifying_stages count toward each stage). This
    # keeps "X / target" displays honest after quickstart.
    stage_counts: dict[str, int] = dict.fromkeys(QUICKSTART_STAGE_ORDER, 0)
    results: list[QuickstartStageResult] = []
    for stage in QUICKSTART_STAGE_ORDER:
        if stage == "lands":
            result = await _fill_basic_lands(
                pool,
                deck_id=deck.id,
                email=email,
                color_identity=commander.color_identity,
                target=QUICKSTART_TARGETS[stage],
            )
            stage_counts[stage] += result.accepted
        else:
            result = await _build_and_accept_stage(
                pool,
                ai_client,
                qdrant_client,
                deck_id=deck.id,
                account_id=account_id,
                email=email,
                stage=stage,
                target=QUICKSTART_TARGETS[stage],
                max_price_cents=max_price_cents,
                min_price_cents=min_price_cents,
                stage_counts=stage_counts,
            )
        results.append(result)
        if on_progress is not None:
            await on_progress(result)

    await deck_service.update_deck(pool, deck.id, DeckUpdate(stage=_INITIAL_WIZARD_STAGE), email)

    final = await deck_service._fetch_deck(pool, deck.id)
    if final is None:
        raise DeckNotFoundError(f"Deck {deck.id} vanished after quickstart")
    _log.info(
        "Quickstart finished for deck %s: %s",
        deck.id,
        ", ".join(f"{r.stage}={r.accepted}/{r.target}" for r in results),
    )
    return final, results


def _distribute_basics(color_identity: list[str], target: int) -> dict[str, int]:
    """Split ``target`` basic-land slots across the commander's colors.

    Colorless commanders get ``Wastes``. Multi-color commanders get an even
    split with the remainder spread across the leading colors. Always returns
    counts that sum to ``target``.
    """
    if not color_identity:
        return {_COLORLESS_BASIC: target}
    basics = [_COLOR_TO_BASIC[c] for c in color_identity if c in _COLOR_TO_BASIC]
    if not basics:
        return {_COLORLESS_BASIC: target}
    base, remainder = divmod(target, len(basics))
    return {name: base + (1 if i < remainder else 0) for i, name in enumerate(basics)}


async def _fill_basic_lands(
    pool: asyncpg.Pool,
    *,
    deck_id: UUID,
    email: str,
    color_identity: list[str],
    target: int,
) -> QuickstartStageResult:
    """Fill the lands stage with basics distributed across the commander's colors.

    Quickstart deliberately does not seed duals — the user can swap them in
    from the wizard. This keeps the starting mana base predictable, budget-
    neutral, and easy to reason about.
    """
    distribution = _distribute_basics(color_identity, target)
    accepted = 0
    for basic_name, qty in distribution.items():
        if qty <= 0:
            continue
        card = await card_service.resolve_card_by_name(pool, basic_name)
        if card is None:
            _log.warning("Basic land %s missing from local DB; skipping", basic_name)
            continue
        try:
            await deck_service.add_card_to_deck(
                pool,
                deck_id,
                DeckCardAdd(
                    card_scryfall_id=card.scryfall_id,
                    quantity=qty,
                    category="lands",
                    added_by="ai",
                    ai_reasoning=None,
                ),
                email,
            )
        except (CardNotFoundError, ColorIdentityError) as exc:
            _log.debug("Quickstart skipping basic %s: %s", basic_name, exc)
            continue
        accepted += qty
    return QuickstartStageResult(stage="lands", target=target, accepted=accepted)


async def _build_and_accept_stage(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    *,
    deck_id: UUID,
    account_id: UUID,
    email: str,
    stage: str,
    target: int,
    max_price_cents: int | None,
    min_price_cents: int | None,
    stage_counts: dict[str, int],
) -> QuickstartStageResult:
    """Run one stage of build_stage and accept cards until ``target`` is met.

    Acceptance respects each suggestion's ``qualifying_stages`` and the shared
    ``stage_counts`` map, so cards that fill multiple stages are not greedily
    counted against this stage's quota when those stages are already met. This
    mirrors how the build wizard's ``computeStageCounts`` view will display
    counts after quickstart returns.
    """
    response = await ai_service.build_stage(
        pool,
        ai_client,
        qdrant_client,
        deck_id,
        account_id,
        email,
        stage=stage,
        target=target * _OVERFETCH_MULTIPLIER,
        max_price_cents=max_price_cents,
        min_price_cents=min_price_cents,
    )
    accepted = 0
    for suggestion in response.suggestions:
        if stage_counts[stage] >= target:
            break
        try:
            await deck_service.add_card_to_deck(
                pool,
                deck_id,
                DeckCardAdd(
                    card_scryfall_id=suggestion.scryfall_id,
                    category=stage,
                    added_by="ai",
                    ai_reasoning=suggestion.reasoning,
                ),
                email,
            )
        except (CardNotFoundError, ColorIdentityError) as exc:
            _log.debug(
                "Quickstart skipping %s in %s: %s",
                suggestion.name,
                stage,
                exc,
            )
            continue
        accepted += 1
        # A card with no qualifying_stages falls back to its assigned category
        # in the wizard view — mirror that here so counts stay aligned.
        contributing = list(suggestion.qualifying_stages) or [stage]
        for s in contributing:
            if s in stage_counts:
                stage_counts[s] += 1
    return QuickstartStageResult(stage=stage, target=target, accepted=accepted)
