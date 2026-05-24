"""Unit tests for the deck optimizer service.

The simulator and swap retrieval are mocked so each test exercises the
greedy loop in isolation. End-to-end behavior (real sim + real candidates)
is covered indirectly by the playtest/swap service tests.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import (
    ColorScrewStats,
    CommanderStats,
    MulliganReasonStats,
    OpeningHandStats,
    PlaytestSimulateRequest,
    PlaytestStats,
    StuckCard,
    TurnStat,
)
from mtg_helper.models.swaps import SwapCandidate, SwapResponse
from mtg_helper.services import deck_optimizer_service


def _stats(
    *,
    pct_screw: float = 0.05,
    pct_flood: float = 0.05,
    pct_color_screw: float = 0.05,
    avg_mulligans: float = 0.5,
    kept_at_7: float = 0.6,
    commander_pct_ever_cast: float = 0.85,
    top_stuck: list[StuckCard] | None = None,
) -> PlaytestStats:
    """Build a synthetic ``PlaytestStats`` for score/ranking tests."""
    return PlaytestStats(
        trials=1000,
        turns=4,
        on_the_play=True,
        avg_mulligans=avg_mulligans,
        mulligan_distribution=[1, 0, 0, 0],
        avg_total_spells_cast=3.0,
        total_spells_stddev=1.0,
        pct_flood=pct_flood,
        pct_screw=pct_screw,
        avg_first_missed_land_turn=5.0,
        opening_hand=OpeningHandStats(
            pct_screwed_mull=0.0,
            pct_balanced=1.0,
            pct_flood_mull=0.0,
            pct_kept_7=kept_at_7,
            pct_kept_6=0.0,
            pct_kept_5=0.0,
            pct_kept_le4=0.0,
        ),
        color_screw=ColorScrewStats(pct_color_screw=pct_color_screw),
        commander=CommanderStats(
            name="Test Commander", avg_cast_turn=3.0, pct_ever_cast=commander_pct_ever_cast
        ),
        top_stuck_cards=top_stuck or [],
        mulligan_reasons=MulliganReasonStats(
            total=0, low_lands=0, high_lands=0, no_commander_color=0, no_early_play=0
        ),
        per_turn=[
            TurnStat(
                turn=t,
                avg_lands_in_play=t,
                avg_mana_available=t,
                avg_mana_spent=t - 1,
                mana_utilization=0.8,
                avg_spells_cast_cumulative=t,
                pct_land_drop=1.0,
                pct_cast_any=0.9,
                avg_dead_cards=0.0,
                avg_color_dead_cards=0.0,
                avg_interaction_in_hand=0.0,
                avg_cards_drawn_extra=0.0,
                avg_selection_events=0.0,
                avg_tutors_cast=0.0,
                avg_cards_in_hand=7,
                lands_p25=t,
                lands_p50=t,
                lands_p75=t,
                mana_p25=t,
                mana_p50=t,
                mana_p75=t,
                avg_mana_unspent=0.0,
                avg_hand_lands=2,
                avg_hand_ramp=0,
                avg_hand_draw=0,
                avg_hand_interaction=0,
                avg_hand_tutors=0,
                avg_hand_other=4,
            )
            for t in range(1, 5)
        ],
    )


def _card(
    name: str,
    *,
    quantity: int = 1,
    type_line: str = "Creature — Human",
    price_eur_cents: int | None = 1000,
    color_identity: list[str] | None = None,
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}",
        cmc=Decimal("2"),
        type_line=type_line,
        oracle_text=None,
        color_identity=color_identity or [],
        image_uri=None,
        rarity=None,
        quantity=quantity,
        categories=[],
        added_by="ai",
        ai_reasoning=None,
        qualifying_stages=[],
        tags=[],
        power=None,
        price_eur_cents=price_eur_cents,
    )


def _deck(cards: list[DeckCardItem]) -> DeckDetailResponse:
    now = datetime(2026, 5, 18)
    return DeckDetailResponse(
        id=uuid4(),
        name="Opt Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=uuid4(),
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=CommanderCardSummary(id=uuid4(), name="Cmdr", color_identity=["G"]),
        partner_card=None,
        owner_email="user@example.com",
        created_at=now,
        updated_at=now,
        cards=cards,
    )


def _candidate(name: str, *, price_eur_cents: int | None = 500) -> SwapCandidate:
    return SwapCandidate(
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}",
        type_line="Creature — Elf",
        image_uri=None,
        oracle_text=None,
        power=None,
        toughness=None,
        rarity="common",
        cmc=2.0,
        color_identity=["G"],
        category="swap",
        reasoning="cheaper alt",
        synergies=[],
        highlight_reasons=None,
        price_eur_cents=price_eur_cents,
        owned_in=[],
        qualifying_stages=[],
        sources=[],
        price_delta_cents=-(1000 - (price_eur_cents or 0)),
        function_loss_pct=10,
        similarity_breakdown={"total": 0.8},
    )


def _swap_response(source_id: UUID, candidates: list[SwapCandidate]) -> SwapResponse:
    return SwapResponse(source_card_id=source_id, source_price_cents=1000, candidates=candidates)


# ─── Pure helpers ──────────────────────────────────────────────────────────


class TestHealthScore:
    def test_healthy_deck_scores_high(self):
        score = deck_optimizer_service._health_score(_stats())
        assert score > 4.5

    def test_screw_lowers_score(self):
        healthy = deck_optimizer_service._health_score(_stats())
        screwed = deck_optimizer_service._health_score(_stats(pct_screw=0.5))
        assert screwed < healthy

    def test_kept_at_7_raises_score(self):
        low = deck_optimizer_service._health_score(_stats(kept_at_7=0.2))
        high = deck_optimizer_service._health_score(_stats(kept_at_7=0.9))
        assert high > low


class TestRankWeakCards:
    def test_skips_basic_lands(self):
        cards = [
            _card("Forest", type_line="Basic Land — Forest"),
            _card("Bad Spell"),
        ]
        deck = _deck(cards)
        stats = _stats(
            top_stuck=[
                StuckCard(name="Forest", cost=None, pct_stuck=0.5, blocker="never_drawn"),
                StuckCard(name="Bad Spell", cost="{2}", pct_stuck=0.3, blocker="colors"),
            ]
        )
        ranked = deck_optimizer_service._rank_weak_cards(deck, stats, set())
        assert [w.card.name for w in ranked] == ["Bad Spell"]

    def test_colors_blocker_beats_never_drawn(self):
        cards = [_card("Colors Card"), _card("Never Drawn Card")]
        deck = _deck(cards)
        stats = _stats(
            top_stuck=[
                StuckCard(name="Colors Card", cost="{G}{W}", pct_stuck=0.3, blocker="colors"),
                StuckCard(
                    name="Never Drawn Card", cost="{2}", pct_stuck=0.5, blocker="never_drawn"
                ),
            ]
        )
        ranked = deck_optimizer_service._rank_weak_cards(deck, stats, set())
        # colors 0.3 * 3.0 = 0.9, never_drawn 0.5 * 0.5 = 0.25.
        assert ranked[0].card.name == "Colors Card"

    def test_excluded_names_are_dropped(self):
        cards = [_card("Already Swapped"), _card("Fresh Target")]
        deck = _deck(cards)
        stats = _stats(
            top_stuck=[
                StuckCard(name="Already Swapped", cost="{2}", pct_stuck=0.4, blocker="mana"),
                StuckCard(name="Fresh Target", cost="{2}", pct_stuck=0.3, blocker="mana"),
            ]
        )
        ranked = deck_optimizer_service._rank_weak_cards(deck, stats, {"Already Swapped"})
        assert [w.card.name for w in ranked] == ["Fresh Target"]


class TestApplySwapInMemory:
    def test_quantity_one_removes_and_appends(self):
        out_card = _card("Out", quantity=1)
        deck = _deck([out_card])
        replacement = _card("In", quantity=1)
        variant = deck_optimizer_service._apply_swap_in_memory(deck, out_card, replacement)
        names = [c.name for c in variant.cards]
        assert names == ["In"]
        # Original deck untouched.
        assert deck.cards[0].name == "Out"

    def test_quantity_above_one_decrements(self):
        out_card = _card("Out", quantity=4)
        deck = _deck([out_card])
        replacement = _card("In", quantity=1)
        variant = deck_optimizer_service._apply_swap_in_memory(deck, out_card, replacement)
        names = sorted(c.name for c in variant.cards)
        assert names == ["In", "Out"]
        out_in_variant = next(c for c in variant.cards if c.name == "Out")
        assert out_in_variant.quantity == 3


class TestPropose:
    @pytest.mark.asyncio
    async def test_no_swap_when_no_weak_cards(self, monkeypatch: pytest.MonkeyPatch):
        deck = _deck([_card("All Good")])
        baseline = _stats()

        def fake_simulate(d, req):
            return baseline

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        find_swaps = AsyncMock()
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await deck_optimizer_service.propose_optimization(
            pool=MagicMock(),
            ai_client=MagicMock(),
            qdrant_client=MagicMock(),
            deck=deck,
            sim_request=PlaytestSimulateRequest(),
            max_price_cents=None,
            max_swaps=3,
            account_id=uuid4(),
        )
        assert proposal.swaps == []
        assert proposal.baseline_stats is proposal.final_stats
        find_swaps.assert_not_called()

    @pytest.mark.asyncio
    async def test_commits_swap_when_score_improves(self, monkeypatch: pytest.MonkeyPatch):
        weak = _card("Weak Card", price_eur_cents=1500)
        deck = _deck([weak])
        baseline = _stats(
            pct_screw=0.30,
            top_stuck=[StuckCard(name="Weak Card", cost="{2}", pct_stuck=0.4, blocker="colors")],
        )
        improved = _stats(pct_screw=0.10)

        call_count = {"n": 0}

        def fake_simulate(d, req):
            call_count["n"] += 1
            return baseline if call_count["n"] == 1 else improved

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        cand = _candidate("Better Card", price_eur_cents=400)
        find_swaps = AsyncMock(return_value=_swap_response(weak.card_id, [cand]))
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await deck_optimizer_service.propose_optimization(
            pool=MagicMock(),
            ai_client=MagicMock(),
            qdrant_client=MagicMock(),
            deck=deck,
            sim_request=PlaytestSimulateRequest(),
            max_price_cents=500,
            max_swaps=3,
            account_id=uuid4(),
        )
        assert len(proposal.swaps) == 1
        swap = proposal.swaps[0]
        assert swap.out_card_name == "Weak Card"
        assert swap.in_card_name == "Better Card"
        assert swap.price_delta_cents == 400 - 1500
        assert swap.score_delta > 0
        find_swaps.assert_awaited_once()
        # Price cap is forwarded verbatim.
        kwargs = find_swaps.await_args.kwargs
        assert kwargs["max_price_cents"] == 500

    @pytest.mark.asyncio
    async def test_neutral_swap_rejected_by_epsilon(self, monkeypatch: pytest.MonkeyPatch):
        weak = _card("Weak Card")
        deck = _deck([weak])
        baseline = _stats(
            pct_screw=0.30,
            top_stuck=[StuckCard(name="Weak Card", cost="{2}", pct_stuck=0.4, blocker="colors")],
        )
        # Variant nudges screw by 0.001 → score delta well under epsilon (0.01).
        flat = _stats(
            pct_screw=0.299,
            top_stuck=[StuckCard(name="Weak Card", cost="{2}", pct_stuck=0.4, blocker="colors")],
        )

        sim_calls = {"n": 0}

        def fake_simulate(d, req):
            sim_calls["n"] += 1
            return baseline if sim_calls["n"] == 1 else flat

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        cand = _candidate("Sideways Card")
        find_swaps = AsyncMock(return_value=_swap_response(weak.card_id, [cand]))
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await deck_optimizer_service.propose_optimization(
            pool=MagicMock(),
            ai_client=MagicMock(),
            qdrant_client=MagicMock(),
            deck=deck,
            sim_request=PlaytestSimulateRequest(),
            max_price_cents=None,
            max_swaps=3,
            account_id=uuid4(),
        )
        assert proposal.swaps == []

    @pytest.mark.asyncio
    async def test_seed_pinned_across_all_sims(self, monkeypatch: pytest.MonkeyPatch):
        weak = _card("Weak")
        deck = _deck([weak])
        baseline = _stats(
            pct_screw=0.30,
            top_stuck=[StuckCard(name="Weak", cost="{2}", pct_stuck=0.4, blocker="colors")],
        )
        improved = _stats(pct_screw=0.10)

        seen_seeds: list[int | None] = []
        sim_calls = {"n": 0}

        def fake_simulate(d, req: PlaytestSimulateRequest):
            seen_seeds.append(req.seed)
            sim_calls["n"] += 1
            return baseline if sim_calls["n"] == 1 else improved

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        find_swaps = AsyncMock(return_value=_swap_response(weak.card_id, [_candidate("Better")]))
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        await deck_optimizer_service.propose_optimization(
            pool=MagicMock(),
            ai_client=MagicMock(),
            qdrant_client=MagicMock(),
            deck=deck,
            sim_request=PlaytestSimulateRequest(seed=42),
            max_price_cents=None,
            max_swaps=2,
            account_id=uuid4(),
        )
        assert len(seen_seeds) >= 2
        assert all(s == 42 for s in seen_seeds)

    @pytest.mark.asyncio
    async def test_stops_at_max_swaps(self, monkeypatch: pytest.MonkeyPatch):
        cards = [
            _card("Weak A", price_eur_cents=2000),
            _card("Weak B", price_eur_cents=2000),
            _card("Weak C", price_eur_cents=2000),
            _card("Weak D", price_eur_cents=2000),
        ]
        deck = _deck(cards)

        def fake_simulate(d, req):
            screw = 0.50 - 0.05 * len([c for c in d.cards if c.name.startswith("Replacement")])
            return _stats(
                pct_screw=screw,
                top_stuck=[
                    StuckCard(name=n, cost="{2}", pct_stuck=0.5, blocker="colors")
                    for n in ["Weak A", "Weak B", "Weak C", "Weak D"]
                    if any(orig.name == n for orig in d.cards)
                ],
            )

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)

        async def fake_find_swaps(*args, **kwargs):
            source_card_id = args[4]
            source = next(c for c in cards if c.card_id == source_card_id)
            return _swap_response(
                source.card_id,
                [_candidate(f"Replacement for {source.name}", price_eur_cents=500)],
            )

        monkeypatch.setattr(
            deck_optimizer_service.swap_service,
            "find_budget_swaps",
            AsyncMock(side_effect=fake_find_swaps),
        )

        proposal = await deck_optimizer_service.propose_optimization(
            pool=MagicMock(),
            ai_client=MagicMock(),
            qdrant_client=MagicMock(),
            deck=deck,
            sim_request=PlaytestSimulateRequest(),
            max_price_cents=600,
            max_swaps=3,
            account_id=uuid4(),
        )
        assert len(proposal.swaps) == 3


class TestCandidateToCardItem:
    def test_inherits_categories_from_source(self):
        out = _card("Out")
        out_with_cats = out.model_copy(update={"categories": ["lands", "ramp"]})
        cand = _candidate("New")
        item = deck_optimizer_service._candidate_to_card_item(cand, out_with_cats, [])
        assert item.categories == ["lands", "ramp"]
        assert item.scryfall_id == cand.scryfall_id
        assert item.cmc == Decimal("2.0")
