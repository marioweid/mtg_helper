"use client";

import { useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type { PlaytestStats } from "@/lib/types";

interface Props {
  deckId: string;
  defaultTurns?: number;
}

const TRIAL_OPTIONS = [100, 500, 1000, 5000] as const;

const TURNS_MIN = 1;
const TURNS_MAX = 10;

const TIPS = {
  trials:
    "Number of independent goldfish games run for this simulation. Higher = more stable averages, slower to compute.",
  avg_mulligans:
    "Average number of London mulligans taken per trial. Lower is better; high values mean the mana base is shaky.",
  kept_7:
    "% of trials where the player kept the opening 7-card hand (no mulligan). Strong baseline indicator of consistency.",
  kept_6: "% of trials where the player mulliganed once and kept at 6.",
  kept_le5:
    "% of trials where the player mulled to 5 or fewer cards. High here means the deck is unreliable out of the gate.",
  avg_total_spells:
    "Average total non-land spells cast across all turns of the trial, ± standard deviation across trials.",
  flood_rate:
    "% of trials classified as 'flooded': hit a turn ≥4 with 2+ more lands than the turn number AND mana utilization < 50%.",
  screw_rate:
    "% of trials classified as 'mana screwed': hit a turn ≥3 where lands in play fell at least 2 behind the curve.",
  opening_flood_mull:
    "% of opening 7-card hands (before mulligan decision) that held 6+ lands.",
  opening_screw_mull:
    "% of opening 7-card hands (before mulligan decision) that held 0–1 lands.",
  first_missed:
    "Average turn the deck first failed to drop a land. Sentinel: turns + 1 means it never missed within the sim window.",
  threshold_mana:
    "Mana-engine threshold: trial crossed when ≥12 mana available AND ≥3 cards in hand. Tracks ramp / big-mana decks.",
  threshold_board:
    "Board-state threshold: trial crossed when total creature power ≥30 OR creatures on board ≥10. Tracks go-wide / aggro.",
  threshold_velocity:
    "Velocity threshold: trial crossed when ≥5 spells cast in one turn AND ≥4 cards in hand. Tracks spellslinger / storm.",
  threshold_any:
    "Trial crossed any of the three engine thresholds at least once during the sim window.",
  threshold_ever:
    "% of trials that ever crossed this threshold within the simulated turns.",
  threshold_first:
    "Average turn at which this threshold was first crossed. Sentinel = turns + 1 means it never crossed.",
  // Per-turn columns
  col_turn: "Turn number in the goldfish game.",
  col_lands: "Average number of lands in play at end of this turn.",
  col_mana:
    "Average mana available at start of casting (lands + ramp sources that came online by this turn).",
  col_spent: "Average total mana value cast this turn (sum of CMC of resolved spells).",
  col_util:
    "Mana utilization rate: average of (mana spent / mana available) per turn. Higher = the deck uses its mana well.",
  col_land_drop: "% of trials that played a land on this turn.",
  col_cast_any: "% of trials that cast at least one non-land spell this turn.",
  col_cum_spells: "Average cumulative non-land spells cast from T1 through this turn.",
  col_dead:
    "Avg uncastable non-land non-interaction cards stuck in hand at end of turn (wrong colors or not enough mana).",
  col_interact:
    "Avg removal / board-wipe / counterspell cards held in hand. These are NOT counted as dead — they're held for defense.",
  col_extra_cards:
    "Avg extra cards drawn this turn (draw spells + tutors-as-draw-1 proxy). Excludes the natural turn draw.",
  col_creatures:
    "Avg cumulative creatures on the battlefield by end of this turn. Once cast they stay — no removal in goldfish.",
  col_power:
    "Avg cumulative total printed power of creatures on the battlefield. Used for the board-state threshold.",
  col_hand: "Avg cards in hand at end of turn (after draw, land drop, and casting phase).",
  col_engine_cum:
    "Cumulative % of trials that have crossed any engine threshold by end of this turn.",
  // Percentiles
  col_lands_p25: "25th percentile of lands in play (1/4 of trials had this many or fewer).",
  col_lands_p50: "Median lands in play.",
  col_lands_p75: "75th percentile of lands in play (3/4 of trials had this many or fewer).",
  col_mana_p25: "25th percentile of mana available.",
  col_mana_p50: "Median mana available.",
  col_mana_p75: "75th percentile of mana available.",
} as const;

function clampTurns(raw: string, fallback: number): number {
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(TURNS_MAX, Math.max(TURNS_MIN, n));
}

export function PlaytestStatsPanel({ deckId, defaultTurns = 4 }: Props) {
  const [trials, setTrials] = useState<number>(1000);
  const [turnsText, setTurnsText] = useState<string>(String(defaultTurns));
  const [onThePlay, setOnThePlay] = useState<boolean>(true);
  const [stats, setStats] = useState<PlaytestStats | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    const turns = clampTurns(turnsText, defaultTurns);
    setTurnsText(String(turns));
    setRunning(true);
    setError(null);
    try {
      const result = await apiClient.playtestSimulate(deckId, {
        trials,
        turns,
        on_the_play: onThePlay,
      });
      setStats(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-white">Batch simulation</h2>
        <p className="text-xs text-gray-500">
          Aggregate stats across many goldfish runs
        </p>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-1.5 text-gray-300">
          <Tip text={TIPS.trials}>Trials</Tip>
          <select
            value={trials}
            onChange={(e) => setTrials(Number.parseInt(e.target.value, 10))}
            disabled={running}
            className="rounded border border-white/15 bg-zinc-900 px-2 py-1 text-gray-100"
          >
            {TRIAL_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-gray-300">
          Turns
          <input
            type="number"
            inputMode="numeric"
            min={TURNS_MIN}
            max={TURNS_MAX}
            value={turnsText}
            onChange={(e) => setTurnsText(e.target.value)}
            onBlur={() => setTurnsText(String(clampTurns(turnsText, defaultTurns)))}
            disabled={running}
            className="w-16 rounded border border-white/15 bg-zinc-900 px-2 py-1 text-gray-100"
          />
        </label>
        <label className="flex items-center gap-1.5 text-gray-300">
          <input
            type="checkbox"
            checked={onThePlay}
            disabled={running}
            onChange={(e) => setOnThePlay(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          On the play
        </label>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running}
          className="ml-auto rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {running ? "Running…" : "Run sims"}
        </button>
      </div>

      {error && (
        <p className="mb-3 rounded border border-red-500/30 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {stats && <StatsTable stats={stats} />}
    </div>
  );
}

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function StatsTable({ stats }: { stats: PlaytestStats }) {
  const oh = stats.opening_hand;
  const et = stats.engine_thresholds;
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Trials" tip={TIPS.trials} value={String(stats.trials)} />
        <Stat
          label="Avg mulligans"
          tip={TIPS.avg_mulligans}
          value={stats.avg_mulligans.toFixed(2)}
        />
        <Stat label="Kept at 7" tip={TIPS.kept_7} value={pct(oh.pct_kept_7)} />
        <Stat
          label={`Avg spells (T1–T${stats.turns})`}
          tip={TIPS.avg_total_spells}
          value={`${stats.avg_total_spells_cast.toFixed(2)} ± ${stats.total_spells_stddev.toFixed(2)}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Flood rate" tip={TIPS.flood_rate} value={pct(stats.pct_flood)} />
        <Stat label="Screw rate" tip={TIPS.screw_rate} value={pct(stats.pct_screw)} />
        <Stat
          label="Opening flood mull"
          tip={TIPS.opening_flood_mull}
          value={pct(oh.pct_flood_mull)}
        />
        <Stat
          label="Opening screw mull"
          tip={TIPS.opening_screw_mull}
          value={pct(oh.pct_screwed_mull)}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat
          label="Avg first missed land drop"
          tip={TIPS.first_missed}
          value={`T${stats.avg_first_missed_land_turn.toFixed(2)}`}
        />
        <Stat label="Kept at 6" tip={TIPS.kept_6} value={pct(oh.pct_kept_6)} />
        <Stat
          label="Kept ≤ 5"
          tip={TIPS.kept_le5}
          value={pct(oh.pct_kept_5 + oh.pct_kept_le4)}
        />
      </div>

      <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
          Engine thresholds — does the deck do its thing?
        </p>
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-4">
          <ThresholdRow
            label="Mana engine"
            hint="≥12 mana + ≥3 cards in hand"
            tip={TIPS.threshold_mana}
            everPct={et.pct_ever_mana_engine}
            avgFirst={et.avg_first_mana_engine_turn}
          />
          <ThresholdRow
            label="Board state"
            hint="≥30 power OR ≥10 creatures"
            tip={TIPS.threshold_board}
            everPct={et.pct_ever_board_state}
            avgFirst={et.avg_first_board_state_turn}
          />
          <ThresholdRow
            label="Velocity"
            hint="≥5 spells/turn + ≥4 in hand"
            tip={TIPS.threshold_velocity}
            everPct={et.pct_ever_velocity}
            avgFirst={et.avg_first_velocity_turn}
          />
          <ThresholdRow
            label="Any threshold"
            hint="at least one of the above"
            tip={TIPS.threshold_any}
            everPct={et.pct_ever_any}
            avgFirst={et.avg_first_any_threshold_turn}
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left">
          <thead>
            <tr className="border-b border-white/10 text-gray-500">
              <Th tip={TIPS.col_turn}>Turn</Th>
              <Th tip={TIPS.col_lands}>Lands</Th>
              <Th tip={TIPS.col_mana}>Mana</Th>
              <Th tip={TIPS.col_spent}>Spent</Th>
              <Th tip={TIPS.col_util}>Util</Th>
              <Th tip={TIPS.col_land_drop}>Land drop</Th>
              <Th tip={TIPS.col_cast_any}>Cast any</Th>
              <Th tip={TIPS.col_cum_spells}>Cum spells</Th>
              <Th tip={TIPS.col_dead}>Dead</Th>
              <Th tip={TIPS.col_interact}>Interact</Th>
              <Th tip={TIPS.col_extra_cards}>+Cards</Th>
              <Th tip={TIPS.col_creatures}>Crts</Th>
              <Th tip={TIPS.col_power}>Power</Th>
              <Th tip={TIPS.col_hand}>Hand</Th>
              <Th tip={TIPS.col_engine_cum}>Engine</Th>
            </tr>
          </thead>
          <tbody>
            {stats.per_turn.map((row) => (
              <tr key={row.turn} className="border-b border-white/5">
                <td className="py-1.5 font-semibold text-white">{row.turn}</td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_lands_in_play.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_mana_available.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_mana_spent.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">{pct(row.mana_utilization)}</td>
                <td className="py-1.5 tabular-nums text-gray-200">{pct(row.pct_land_drop)}</td>
                <td className="py-1.5 tabular-nums text-gray-200">{pct(row.pct_cast_any)}</td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_spells_cast_cumulative.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_dead_cards.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_interaction_in_hand.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_cards_drawn_extra.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_creatures_on_board.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_total_power.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_cards_in_hand.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-emerald-300">
                  {pct(row.pct_any_threshold_hit_cum)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] leading-snug text-gray-500">
        Hover any column header or stat label for a definition.
      </p>

      <details className="text-gray-500">
        <summary className="cursor-pointer hover:text-gray-300">
          Mulligan distribution
        </summary>
        <ul className="mt-1 flex flex-col gap-0.5">
          {stats.mulligan_distribution.map((count, i) => (
            <li key={i}>
              {i} mulligan{i === 1 ? "" : "s"}:{" "}
              <span className="text-gray-200">
                {count} ({pct(count / stats.trials)})
              </span>
            </li>
          ))}
        </ul>
      </details>

      <details className="text-gray-500">
        <summary className="cursor-pointer hover:text-gray-300">
          Distribution percentiles (lands / mana)
        </summary>
        <table className="mt-1 w-full table-fixed text-left">
          <thead>
            <tr className="text-gray-500">
              <Th tip={TIPS.col_turn}>Turn</Th>
              <Th tip={TIPS.col_lands_p25}>L p25</Th>
              <Th tip={TIPS.col_lands_p50}>L p50</Th>
              <Th tip={TIPS.col_lands_p75}>L p75</Th>
              <Th tip={TIPS.col_mana_p25}>M p25</Th>
              <Th tip={TIPS.col_mana_p50}>M p50</Th>
              <Th tip={TIPS.col_mana_p75}>M p75</Th>
            </tr>
          </thead>
          <tbody>
            {stats.per_turn.map((row) => (
              <tr key={row.turn}>
                <td className="py-0.5 text-gray-200">{row.turn}</td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.lands_p25.toFixed(1)}
                </td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.lands_p50.toFixed(1)}
                </td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.lands_p75.toFixed(1)}
                </td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.mana_p25.toFixed(1)}
                </td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.mana_p50.toFixed(1)}
                </td>
                <td className="py-0.5 tabular-nums text-gray-200">
                  {row.mana_p75.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function Tip({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <span
      title={text}
      className="cursor-help underline decoration-dotted decoration-gray-600 underline-offset-2"
    >
      {children}
    </span>
  );
}

function Th({ tip, children }: { tip: string; children: React.ReactNode }) {
  return (
    <th className="py-1 font-medium">
      <Tip text={tip}>{children}</Tip>
    </th>
  );
}

function Stat({ label, value, tip }: { label: string; value: string; tip?: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-3 py-2">
      <p className="text-gray-500">{tip ? <Tip text={tip}>{label}</Tip> : label}</p>
      <p className="font-semibold text-white tabular-nums">{value}</p>
    </div>
  );
}

interface ThresholdRowProps {
  label: string;
  hint: string;
  tip: string;
  everPct: number;
  avgFirst: number;
}

function ThresholdRow({ label, hint, tip, everPct, avgFirst }: ThresholdRowProps) {
  return (
    <div className="rounded-md bg-white/[0.04] px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-semibold text-white">
          <Tip text={tip}>{label}</Tip>
        </p>
        <p title={TIPS.threshold_ever} className="cursor-help tabular-nums text-emerald-300">
          {pct(everPct)}
        </p>
      </div>
      <p className="text-[10px] leading-tight text-gray-500">{hint}</p>
      <p className="mt-0.5 text-[10px] text-gray-400">
        avg first hit:{" "}
        <span
          title={TIPS.threshold_first}
          className="cursor-help tabular-nums text-gray-200"
        >
          T{avgFirst.toFixed(2)}
        </span>
      </p>
    </div>
  );
}
