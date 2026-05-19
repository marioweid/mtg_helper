"use client";

import { useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type { PlaytestStats } from "@/lib/types";

interface Props {
  deckId: string;
  defaultTurns?: number;
}

const TRIAL_OPTIONS = [100, 500, 1000, 5000] as const;

export function PlaytestStatsPanel({ deckId, defaultTurns = 4 }: Props) {
  const [trials, setTrials] = useState<number>(1000);
  const [turns, setTurns] = useState<number>(defaultTurns);
  const [onThePlay, setOnThePlay] = useState<boolean>(true);
  const [stats, setStats] = useState<PlaytestStats | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
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
          Trials
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
            min={1}
            max={10}
            value={turns}
            onChange={(e) => setTurns(Number.parseInt(e.target.value, 10) || 1)}
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
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Trials" value={String(stats.trials)} />
        <Stat label="Avg mulligans" value={stats.avg_mulligans.toFixed(2)} />
        <Stat
          label="Kept at 7"
          value={pct((stats.mulligan_distribution[0] ?? 0) / stats.trials)}
        />
        <Stat
          label={`Avg spells (T1–T${stats.turns})`}
          value={stats.avg_total_spells_cast.toFixed(2)}
        />
      </div>

      <table className="w-full table-fixed text-left">
        <thead>
          <tr className="border-b border-white/10 text-gray-500">
            <th className="py-1 font-medium">Turn</th>
            <th className="py-1 font-medium">Avg lands</th>
            <th className="py-1 font-medium">Land drop</th>
            <th className="py-1 font-medium">Cast any</th>
            <th className="py-1 font-medium">Spells (cum)</th>
          </tr>
        </thead>
        <tbody>
          {stats.per_turn.map((row) => (
            <tr key={row.turn} className="border-b border-white/5">
              <td className="py-1.5 font-semibold text-white">{row.turn}</td>
              <td className="py-1.5 tabular-nums text-gray-200">
                {row.avg_lands_in_play.toFixed(2)}
              </td>
              <td className="py-1.5 tabular-nums text-gray-200">{pct(row.pct_land_drop)}</td>
              <td className="py-1.5 tabular-nums text-gray-200">{pct(row.pct_cast_any)}</td>
              <td className="py-1.5 tabular-nums text-gray-200">
                {row.avg_spells_cast_cumulative.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

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
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-3 py-2">
      <p className="text-gray-500">{label}</p>
      <p className="font-semibold text-white tabular-nums">{value}</p>
    </div>
  );
}
