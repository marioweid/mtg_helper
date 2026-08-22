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

from mtg_helper.models.ai import CardSuggestion, ColorStatus, ManaBaseReport
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

pytestmark = pytest.mark.no_db


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
    oracle_text: str | None = None,
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}",
        cmc=Decimal("2"),
        type_line=type_line,
        oracle_text=oracle_text,
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


def _patch_lands(
    monkeypatch: pytest.MonkeyPatch,
    candidates: list[CardSuggestion],
    report: ManaBaseReport | None = None,
) -> AsyncMock:
    """Patch the land-pool + mana-base helpers the land search depends on."""
    if report is not None:
        monkeypatch.setattr(
            deck_optimizer_service.mana_base_service,
            "analyze_mana_base",
            lambda deck, **_: report,
        )
    cl = AsyncMock(return_value=candidates)
    monkeypatch.setattr(deck_optimizer_service.mana_base_service, "candidate_lands", cl)
    return cl


async def _run(monkeypatch: pytest.MonkeyPatch, deck, **kwargs):
    """Invoke ``run_search`` with the standard mocked dependencies."""
    return await deck_optimizer_service.run_search(
        MagicMock(),
        deck,
        kwargs.pop("sim_request", PlaytestSimulateRequest()),
        max_price_cents=kwargs.pop("max_price_cents", None),
        max_swaps=kwargs.pop("max_swaps", 3),
        account_id=uuid4(),
        **kwargs,
    )


class TestNonlandSearch:
    @pytest.mark.asyncio
    async def test_no_swap_when_healthy(self, monkeypatch: pytest.MonkeyPatch):
        deck = _deck([_card("All Good")])
        monkeypatch.setattr(
            deck_optimizer_service.playtest_service, "simulate", lambda d, req: _stats()
        )
        _patch_lands(monkeypatch, [])
        find_swaps = AsyncMock()
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await _run(monkeypatch, deck)
        assert proposal.swaps == []
        find_swaps.assert_not_called()

    @pytest.mark.asyncio
    async def test_commits_swap_when_score_improves(self, monkeypatch: pytest.MonkeyPatch):
        weak = _card("Weak Card", price_eur_cents=1500)
        deck = _deck([weak])

        def fake_simulate(d, req):
            if any(c.name == "Better Card" for c in d.cards):
                return _stats(pct_screw=0.10)
            return _stats(
                pct_screw=0.30,
                top_stuck=[
                    StuckCard(name="Weak Card", cost="{2}", pct_stuck=0.4, blocker="colors")
                ],
            )

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        _patch_lands(monkeypatch, [])
        cand = _candidate("Better Card", price_eur_cents=400)
        find_swaps = AsyncMock(return_value=_swap_response(weak.card_id, [cand]))
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await _run(monkeypatch, deck, max_price_cents=500)
        assert len(proposal.swaps) == 1
        swap = proposal.swaps[0]
        assert swap.out_card_name == "Weak Card"
        assert swap.in_card_name == "Better Card"
        assert swap.price_delta_cents == 400 - 1500
        assert find_swaps.await_args is not None
        assert find_swaps.await_args.kwargs["max_price_cents"] == 500

    @pytest.mark.asyncio
    async def test_neutral_swap_rejected_by_epsilon(self, monkeypatch: pytest.MonkeyPatch):
        weak = _card("Weak Card")
        deck = _deck([weak])

        def fake_simulate(d, req):
            screw = 0.299 if any(c.name == "Sideways Card" for c in d.cards) else 0.30
            return _stats(
                pct_screw=screw,
                top_stuck=[
                    StuckCard(name="Weak Card", cost="{2}", pct_stuck=0.4, blocker="colors")
                ],
            )

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        _patch_lands(monkeypatch, [])
        find_swaps = AsyncMock(
            return_value=_swap_response(weak.card_id, [_candidate("Sideways Card")])
        )
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await _run(monkeypatch, deck)
        assert proposal.swaps == []

    @pytest.mark.asyncio
    async def test_stops_at_max_swaps(self, monkeypatch: pytest.MonkeyPatch):
        names = ["Weak A", "Weak B", "Weak C", "Weak D"]
        cards = [_card(n, price_eur_cents=2000) for n in names]
        deck = _deck(cards)

        def fake_simulate(d, req):
            present = {c.name for c in d.cards}
            repl = sum(1 for c in d.cards if c.name.startswith("Replacement"))
            stuck = [
                StuckCard(name=n, cost="{2}", pct_stuck=0.5, blocker="colors")
                for n in names
                if n in present
            ]
            return _stats(pct_screw=0.50 - 0.05 * repl, top_stuck=stuck)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        _patch_lands(monkeypatch, [])

        async def fake_find_swaps(*args, **kwargs):
            source = next(c for c in cards if c.card_id == args[2])
            return _swap_response(
                source.card_id, [_candidate(f"Replacement for {source.name}", price_eur_cents=500)]
            )

        monkeypatch.setattr(
            deck_optimizer_service.swap_service,
            "find_budget_swaps",
            AsyncMock(side_effect=fake_find_swaps),
        )

        proposal = await _run(monkeypatch, deck, max_price_cents=600, max_swaps=3)
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


# ─── Mana-fix stage ─────────────────────────────────────────────────────────


def _basic(name: str, color: str, *, quantity: int = 10) -> DeckCardItem:
    return _card(
        name,
        quantity=quantity,
        type_line=f"Basic Land — {name}",
        price_eur_cents=10,
        color_identity=[color],
    )


def _land_suggestion(
    name: str, colors: list[str], *, price_eur_cents: int | None = 800
) -> CardSuggestion:
    return CardSuggestion(
        scryfall_id=uuid4(),
        name=name,
        mana_cost=None,
        type_line="Land",
        image_uri=None,
        oracle_text=None,
        cmc=0.0,
        color_identity=colors,
        category="lands",
        reasoning="fixes color",
        synergies=[],
        price_eur_cents=price_eur_cents,
        qualifying_stages=["lands"],
    )


def _mana_report(source_by_color: dict[str, int]) -> ManaBaseReport:
    colors = [
        ColorStatus(
            color=color,
            pip_count=1.0,
            source_count=count,
            target=count,
            deficit=0,
        )
        for color, count in source_by_color.items()
    ]
    return ManaBaseReport(
        total_lands=sum(source_by_color.values()), total_colored_pips=1.0, colors=colors
    )


def _tapland(name: str, colors: list[str], *, price_eur_cents: int = 100) -> DeckCardItem:
    return _card(
        name,
        quantity=1,
        type_line="Land",
        price_eur_cents=price_eur_cents,
        color_identity=colors,
        oracle_text=f"{name} enters the battlefield tapped.",
    )


class TestLandSearch:
    @pytest.mark.asyncio
    async def test_swaps_basic_for_dual_on_color_screw(self, monkeypatch: pytest.MonkeyPatch):
        forest = _basic("Forest", "G", quantity=10)
        deck = _deck([forest, _card("GW Creature", color_identity=["G", "W"])])

        def fake_simulate(d, req):
            if any(c.name == "Temple Garden" for c in d.cards):
                return _stats(pct_color_screw=0.05)
            return _stats(pct_color_screw=0.30)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        dual = _land_suggestion("Temple Garden", ["G", "W"], price_eur_cents=800)
        _patch_lands(monkeypatch, [dual], _mana_report({"G": 10, "W": 0}))

        proposal = await _run(monkeypatch, deck, max_price_cents=1000)
        assert len(proposal.swaps) == 1
        swap = proposal.swaps[0]
        assert swap.out_card_name == "Forest"
        assert swap.in_card_name == "Temple Garden"
        assert "color screw" in swap.reason

    @pytest.mark.asyncio
    async def test_land_search_respects_price_cap(self, monkeypatch: pytest.MonkeyPatch):
        forest = _basic("Forest", "G", quantity=10)
        deck = _deck([forest, _card("GW Creature", color_identity=["G", "W"])])

        def fake_simulate(d, req):
            if any(c.name == "Command Tower" for c in d.cards):
                return _stats(pct_color_screw=0.05)
            return _stats(pct_color_screw=0.30)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        cheap = _land_suggestion("Command Tower", ["G", "W"], price_eur_cents=200)
        pricey = _land_suggestion("Savannah", ["G", "W"], price_eur_cents=1500)
        cl = _patch_lands(monkeypatch, [pricey, cheap], _mana_report({"G": 10, "W": 0}))

        proposal = await _run(monkeypatch, deck, max_price_cents=500)
        assert len(proposal.swaps) == 1
        assert proposal.swaps[0].in_card_name == "Command Tower"
        assert cl.await_args is not None
        assert cl.await_args.kwargs["max_price_cents"] == 500

    @pytest.mark.asyncio
    async def test_upgrades_weak_tapland(self, monkeypatch: pytest.MonkeyPatch):
        tap = _tapland("Slow Land", ["G", "W"])
        deck = _deck([tap, _card("GW Creature", color_identity=["G", "W"])])

        def fake_simulate(d, req):
            if any(c.name == "Temple Garden" for c in d.cards):
                return _stats(pct_screw=0.05)
            return _stats(pct_screw=0.30)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        dual = _land_suggestion("Temple Garden", ["G", "W"], price_eur_cents=800)
        _patch_lands(monkeypatch, [dual], _mana_report({"G": 5, "W": 5}))

        proposal = await _run(monkeypatch, deck, max_price_cents=1000)
        assert len(proposal.swaps) == 1
        swap = proposal.swaps[0]
        assert swap.out_card_name == "Slow Land"
        assert swap.in_card_name == "Temple Garden"
        assert "upgrading" in swap.reason

    @pytest.mark.asyncio
    async def test_lands_then_nonland(self, monkeypatch: pytest.MonkeyPatch):
        forest = _basic("Forest", "G", quantity=10)
        stuck = _card("Stuck Guy", color_identity=["G"])
        deck = _deck([forest, stuck])
        stuck_card = StuckCard(name="Stuck Guy", cost="{2}", pct_stuck=0.5, blocker="mana")

        def fake_simulate(d, req):
            names = {c.name for c in d.cards}
            has_dual = "Temple Garden" in names
            has_better = "Better Guy" in names
            screw = 0.01 if has_better else 0.30
            color = 0.05 if has_dual else 0.30
            stuck_list = [] if has_better else [stuck_card]
            return _stats(pct_screw=screw, pct_color_screw=color, top_stuck=stuck_list)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        dual = _land_suggestion("Temple Garden", ["G", "W"], price_eur_cents=400)
        _patch_lands(monkeypatch, [dual], _mana_report({"G": 10, "W": 0}))
        find_swaps = AsyncMock(
            return_value=_swap_response(
                stuck.card_id, [_candidate("Better Guy", price_eur_cents=300)]
            )
        )
        monkeypatch.setattr(deck_optimizer_service.swap_service, "find_budget_swaps", find_swaps)

        proposal = await _run(monkeypatch, deck, max_price_cents=1000)
        names = [(s.out_card_name, s.in_card_name) for s in proposal.swaps]
        assert ("Forest", "Temple Garden") in names
        assert ("Stuck Guy", "Better Guy") in names

    @pytest.mark.asyncio
    async def test_no_swaps_when_no_candidates(self, monkeypatch: pytest.MonkeyPatch):
        deck = _deck([_basic("Forest", "G", quantity=10)])
        monkeypatch.setattr(
            deck_optimizer_service.playtest_service, "simulate", lambda d, req: _stats()
        )
        _patch_lands(monkeypatch, [])

        proposal = await _run(monkeypatch, deck)
        assert proposal.swaps == []


class TestProgressAndConfirm:
    @pytest.mark.asyncio
    async def test_progress_reported_and_confirm_uses_full_trials(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        forest = _basic("Forest", "G", quantity=10)
        deck = _deck([forest, _card("GW Creature", color_identity=["G", "W"])])
        seen_trials: list[int] = []

        def fake_simulate(d, req):
            seen_trials.append(req.trials)
            if any(c.name == "Temple Garden" for c in d.cards):
                return _stats(pct_color_screw=0.05)
            return _stats(pct_color_screw=0.30)

        monkeypatch.setattr(deck_optimizer_service.playtest_service, "simulate", fake_simulate)
        dual = _land_suggestion("Temple Garden", ["G", "W"], price_eur_cents=400)
        _patch_lands(monkeypatch, [dual], _mana_report({"G": 10, "W": 0}))

        ticks: list[tuple[str, int, int]] = []

        proposal = await _run(
            monkeypatch,
            deck,
            sim_request=PlaytestSimulateRequest(trials=1000),
            search_depth="quick",
            progress_cb=lambda phase, cur, total: ticks.append((phase, cur, total)),
        )
        assert len(proposal.swaps) == 1
        # Progress advanced through searching and confirming phases.
        phases = {t[0] for t in ticks}
        assert "searching lands" in phases
        assert "confirming" in phases
        assert ticks[-1][1] <= ticks[-1][2]
        # Search ran at reduced trials (quick → 400); confirm re-ran at full 1000.
        assert 400 in seen_trials
        assert 1000 in seen_trials
        assert seen_trials[-1] == 1000
