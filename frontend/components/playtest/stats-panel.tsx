"use client";

import { useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type {
  AnalysisFinding,
  AnalysisSwapSuggestion,
  PlaytestCommanderStats,
  PlaytestStats,
  SimulationAnalysisResponse,
} from "@/lib/types";

interface Props {
  deckId: string;
  defaultTurns?: number;
}

const TRIAL_OPTIONS = [100, 500, 1000, 5000] as const;

const TURNS_MIN = 1;
const TURNS_MAX = 10;

const COLOR_ORDER: readonly string[] = ["W", "U", "B", "R", "G", "C"];
const COLOR_LABEL: Record<string, string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
  C: "Colorless",
};

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
  color_screw_pct:
    "% of trials where, at any turn ≥3, the hand held a spell whose total mana value was affordable but whose colored pips couldn't be paid from available sources.",
  color_shortage:
    "How often this color was the missing pip across the sim. Higher = you're frequently short on this color's sources.",
  commander_avg_cast:
    "Average turn the commander first resolves. Sentinel = turns + 1 means it never resolved within the sim window.",
  commander_pct_ever:
    "% of trials in which the commander was successfully cast within the sim window.",
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
  col_color_dead:
    "Avg cards in hand that COULD be paid with the total mana available but can't be cast because of missing colored pips. Subset of Dead.",
  col_interact:
    "Avg removal / board-wipe / counterspell cards held in hand. These are NOT counted as dead — they're held for defense.",
  col_extra_cards:
    "Avg extra cards drawn this turn (draw spells + tutors-as-draw-1 proxy). Excludes the natural turn draw.",
  col_hand: "Avg cards in hand at end of turn (after draw, land drop, and casting phase).",
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
  const [analysis, setAnalysis] = useState<SimulationAnalysisResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

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

  async function handleAnalyze() {
    const turns = clampTurns(turnsText, defaultTurns);
    setTurnsText(String(turns));
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await apiClient.playtestAnalyze(deckId, {
        trials,
        turns,
        on_the_play: onThePlay,
      });
      setAnalysis(result);
    } catch (err) {
      setAnalysisError(err instanceof ApiError ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
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
        <button
          type="button"
          onClick={() => void handleAnalyze()}
          disabled={analyzing}
          className="rounded-lg border border-emerald-400/40 px-4 py-1.5 text-xs font-medium text-emerald-300 hover:border-emerald-400 hover:text-emerald-200 disabled:opacity-50"
          title="Run a sim and ask the AI agent for diagnosis + concrete swap suggestions."
        >
          {analyzing ? "Analyzing…" : "Analyze with AI"}
        </button>
      </div>

      {error && (
        <p className="mb-3 rounded border border-red-500/30 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {analysisError && (
        <p className="mb-3 rounded border border-red-500/30 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {analysisError}
        </p>
      )}

      {analysis && <AnalysisPanel analysis={analysis} />}

      {stats && <StatsTable stats={stats} />}
    </div>
  );
}

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function StatsTable({ stats }: { stats: PlaytestStats }) {
  const oh = stats.opening_hand;
  const cs = stats.color_screw;
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
          label="Color screw rate"
          tip={TIPS.color_screw_pct}
          value={pct(cs.pct_color_screw)}
        />
        <Stat
          label="Avg first missed land drop"
          tip={TIPS.first_missed}
          value={`T${stats.avg_first_missed_land_turn.toFixed(2)}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
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
        <Stat
          label="Kept ≤ 5"
          tip={TIPS.kept_le5}
          value={pct(oh.pct_kept_5 + oh.pct_kept_le4)}
        />
      </div>

      <ColorShortagePanel stats={cs} />

      {(stats.commander !== null || stats.partner !== null) && (
        <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
            Commander
          </p>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {stats.commander !== null && <CommanderRow stats={stats.commander} />}
            {stats.partner !== null && <CommanderRow stats={stats.partner} />}
          </div>
        </div>
      )}

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
              <Th tip={TIPS.col_color_dead}>Color dead</Th>
              <Th tip={TIPS.col_interact}>Interact</Th>
              <Th tip={TIPS.col_extra_cards}>+Cards</Th>
              <Th tip={TIPS.col_hand}>Hand</Th>
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
                <td className="py-1.5 tabular-nums text-amber-300">
                  {row.avg_color_dead_cards.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_interaction_in_hand.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_cards_drawn_extra.toFixed(2)}
                </td>
                <td className="py-1.5 tabular-nums text-gray-200">
                  {row.avg_cards_in_hand.toFixed(2)}
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

function ColorShortagePanel({ stats }: { stats: PlaytestStats["color_screw"] }) {
  const entries = COLOR_ORDER.filter((c) => (stats.shortages_by_color[c] ?? 0) > 0).map(
    (c) => ({ color: c, rate: stats.shortages_by_color[c] ?? 0 }),
  );
  if (entries.length === 0) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
        Color shortages — which pips are missing?
      </p>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {entries.map(({ color, rate }) => (
          <div
            key={color}
            title={TIPS.color_shortage}
            className="cursor-help rounded-md bg-white/[0.04] px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-semibold text-white">{COLOR_LABEL[color] ?? color}</p>
              <p className="tabular-nums text-amber-300">{pct(rate)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CommanderRow({ stats }: { stats: PlaytestCommanderStats }) {
  return (
    <div className="rounded-md bg-white/[0.04] px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate font-semibold text-white">{stats.name}</p>
        <p
          title={TIPS.commander_pct_ever}
          className="cursor-help tabular-nums text-emerald-300"
        >
          {pct(stats.pct_ever_cast)}
        </p>
      </div>
      <p className="mt-0.5 text-[10px] text-gray-400">
        avg first cast:{" "}
        <span
          title={TIPS.commander_avg_cast}
          className="cursor-help tabular-nums text-gray-200"
        >
          T{stats.avg_cast_turn.toFixed(2)}
        </span>
      </p>
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

const SEVERITY_STYLES: Record<AnalysisFinding["severity"], string> = {
  info: "border-sky-400/40 text-sky-300",
  warn: "border-amber-400/40 text-amber-300",
  critical: "border-red-500/40 text-red-300",
};

function AnalysisPanel({ analysis }: { analysis: SimulationAnalysisResponse }) {
  return (
    <div className="mb-3 flex flex-col gap-3 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.04] p-3 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
          AI analysis
        </p>
        <p className="text-[10px] text-gray-500">
          {analysis.tool_call_count} tool call{analysis.tool_call_count === 1 ? "" : "s"}
        </p>
      </div>
      {analysis.summary && (
        <p className="leading-snug text-gray-100">{analysis.summary}</p>
      )}
      {analysis.findings.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
            Findings
          </p>
          {analysis.findings.map((finding, i) => (
            <FindingRow key={i} finding={finding} />
          ))}
        </div>
      )}
      {analysis.swap_suggestions.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
            Swap suggestions
          </p>
          {analysis.swap_suggestions.map((swap, i) => (
            <SwapRow key={i} swap={swap} />
          ))}
        </div>
      )}
    </div>
  );
}

function FindingRow({ finding }: { finding: AnalysisFinding }) {
  return (
    <div
      className={`rounded-md border-l-2 bg-white/[0.04] px-3 py-2 ${SEVERITY_STYLES[finding.severity]}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-semibold text-white">{finding.title}</p>
        <p className="text-[10px] uppercase tracking-wide">{finding.category}</p>
      </div>
      <p className="mt-1 text-gray-200">{finding.detail}</p>
      <p className="mt-1 text-[10px] text-gray-500">Evidence: {finding.evidence}</p>
    </div>
  );
}

function SwapRow({ swap }: { swap: AnalysisSwapSuggestion }) {
  return (
    <div className="rounded-md bg-white/[0.04] px-3 py-2">
      <p className="text-gray-200">{swap.reason}</p>
      <div className="mt-1.5 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-red-300">Remove</p>
          <ul className="mt-0.5 flex flex-col gap-0.5">
            {swap.remove.map((name) => (
              <li key={name} className="text-gray-300">
                {name}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-emerald-300">Add</p>
          <ul className="mt-0.5 flex flex-col gap-0.5">
            {swap.add.map((card) => (
              <li key={card.name} className="text-gray-200">
                {card.name}
                {card.mana_cost ? (
                  <span className="ml-1 text-[10px] text-gray-500">{card.mana_cost}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
