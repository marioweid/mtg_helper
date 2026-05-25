"""Unit tests for the optimizer job registry (pure, no DB)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from mtg_helper.models.optimizer import OptimizationProposal
from mtg_helper.models.playtest import (
    ColorScrewStats,
    MulliganReasonStats,
    OpeningHandStats,
    PlaytestStats,
)
from mtg_helper.services import optimizer_jobs


def _stats() -> PlaytestStats:
    return PlaytestStats(
        trials=1,
        turns=4,
        on_the_play=True,
        avg_mulligans=0.0,
        mulligan_distribution=[1],
        avg_total_spells_cast=0.0,
        total_spells_stddev=0.0,
        pct_flood=0.0,
        pct_screw=0.0,
        avg_first_missed_land_turn=5.0,
        opening_hand=OpeningHandStats(
            pct_screwed_mull=0.0,
            pct_balanced=1.0,
            pct_flood_mull=0.0,
            pct_kept_7=1.0,
            pct_kept_6=0.0,
            pct_kept_5=0.0,
            pct_kept_le4=0.0,
        ),
        color_screw=ColorScrewStats(pct_color_screw=0.0),
        mulligan_reasons=MulliganReasonStats(
            total=0, low_lands=0, high_lands=0, no_commander_color=0, no_early_play=0
        ),
        per_turn=[],
    )


def _proposal() -> OptimizationProposal:
    s = _stats()
    return OptimizationProposal(baseline_stats=s, final_stats=s)


def test_create_registers_running_job():
    registry: dict = {}
    account_id, deck_id = uuid4(), uuid4()
    job = optimizer_jobs.create(registry, account_id, deck_id)
    assert registry[job.job_id] is job
    assert job.status == "running"
    assert job.account_id == account_id
    assert job.deck_id == deck_id


def test_progress_cb_updates_fields():
    job = optimizer_jobs.create({}, uuid4(), uuid4())
    optimizer_jobs.progress_cb(job)("searching lands", 3, 10)
    assert (job.phase, job.current, job.total) == ("searching lands", 3, 10)


def test_finish_ok_completes_bar_and_attaches_result():
    job = optimizer_jobs.create({}, uuid4(), uuid4())
    optimizer_jobs.progress_cb(job)("confirming", 8, 10)
    proposal = _proposal()
    optimizer_jobs.finish_ok(job, proposal)
    assert job.status == "ok"
    assert job.result is proposal
    assert job.current == job.total == 10
    assert job.finished_at is not None


def test_finish_error_records_message():
    job = optimizer_jobs.create({}, uuid4(), uuid4())
    optimizer_jobs.finish_error(job, "boom")
    assert job.status == "error"
    assert job.error == "boom"
    assert job.finished_at is not None


def test_prune_drops_old_finished_jobs():
    registry: dict = {}
    fresh = optimizer_jobs.create(registry, uuid4(), uuid4())
    stale = optimizer_jobs.create(registry, uuid4(), uuid4())
    optimizer_jobs.finish_ok(stale, _proposal())
    stale.finished_at = datetime.now(tz=UTC) - timedelta(hours=1)
    optimizer_jobs.prune(registry, max_age=timedelta(minutes=15))
    assert stale.job_id not in registry
    assert fresh.job_id in registry
