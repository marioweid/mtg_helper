"use client";

import { useEffect, useRef, useState } from "react";

import { CardHover } from "@/components/card-hover";
import { apiClient, ApiError } from "@/lib/api";
import type {
  DeckCardItem,
  OptimizationProposal,
  PlaytestStats,
  ProposedSwap,
  SearchDepth,
} from "@/lib/types";

function jobStorageKey(deckId: string): string {
  return `optimize-job:${deckId}`;
}

function readActiveJob(deckId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(jobStorageKey(deckId));
  } catch {
    return null;
  }
}

function writeActiveJob(deckId: string, jobId: string): void {
  try {
    window.sessionStorage.setItem(jobStorageKey(deckId), jobId);
  } catch {
    /* private mode — non-critical */
  }
}

function clearActiveJob(deckId: string): void {
  try {
    window.sessionStorage.removeItem(jobStorageKey(deckId));
  } catch {
    /* private mode — non-critical */
  }
}

interface Props {
  deckId: string;
  deckCards: DeckCardItem[];
  onApplied?: () => void;
}

type MetricDirection = "lower" | "higher";

interface MetricRow {
  key: string;
  label: string;
  baseline: number;
  final: number;
  formatter: (n: number) => string;
  direction: MetricDirection;
}

const SWAPS_MIN = 1;
const SWAPS_MAX = 15;
const POLL_INTERVAL_MS = 1000;

const DEPTH_OPTIONS: { value: SearchDepth; label: string }[] = [
  { value: "quick", label: "Quick" },
  { value: "thorough", label: "Thorough" },
  { value: "exhaustive", label: "Exhaustive" },
];

interface Progress {
  phase: string;
  current: number;
  total: number;
}

const PHASE_LABELS: Record<string, string> = {
  "searching lands": "Searching land swaps",
  "searching cards": "Searching card swaps",
  confirming: "Confirming results",
};

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function num(n: number): string {
  return n.toFixed(2);
}

function metricRows(baseline: PlaytestStats, final: PlaytestStats): MetricRow[] {
  return [
    {
      key: "screw",
      label: "Mana screw rate",
      baseline: baseline.pct_screw,
      final: final.pct_screw,
      formatter: pct,
      direction: "lower",
    },
    {
      key: "flood",
      label: "Mana flood rate",
      baseline: baseline.pct_flood,
      final: final.pct_flood,
      formatter: pct,
      direction: "lower",
    },
    {
      key: "color_screw",
      label: "Color screw rate",
      baseline: baseline.color_screw.pct_color_screw,
      final: final.color_screw.pct_color_screw,
      formatter: pct,
      direction: "lower",
    },
    {
      key: "mulligans",
      label: "Avg mulligans",
      baseline: baseline.avg_mulligans,
      final: final.avg_mulligans,
      formatter: num,
      direction: "lower",
    },
    {
      key: "kept_7",
      label: "Kept at 7",
      baseline: baseline.opening_hand.pct_kept_7,
      final: final.opening_hand.pct_kept_7,
      formatter: pct,
      direction: "higher",
    },
    {
      key: "commander_cast",
      label: "Commander cast rate",
      baseline: baseline.commander?.pct_ever_cast ?? 0,
      final: final.commander?.pct_ever_cast ?? 0,
      formatter: pct,
      direction: "higher",
    },
  ];
}

function deltaTone(row: MetricRow): "good" | "bad" | "flat" {
  const diff = row.final - row.baseline;
  if (Math.abs(diff) < 1e-4) return "flat";
  const isImprovement = row.direction === "lower" ? diff < 0 : diff > 0;
  return isImprovement ? "good" : "bad";
}

function priceCentsToEur(cents: number): string {
  return (cents / 100).toFixed(2);
}

function priceEurToCents(eur: string): number | null {
  const trimmed = eur.trim();
  if (trimmed === "") return null;
  const value = Number.parseFloat(trimmed);
  if (Number.isNaN(value) || value <= 0) return null;
  return Math.round(value * 100);
}

export function OptimizerPanel({ deckId, deckCards, onApplied }: Props) {
  const [maxPriceEur, setMaxPriceEur] = useState<string>("5.00");
  const [maxSwaps, setMaxSwaps] = useState<number>(3);
  const [depth, setDepth] = useState<SearchDepth>("thorough");
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<OptimizationProposal | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [applyingKey, setApplyingKey] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  function stopPolling() {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  function poll(jobId: string) {
    timerRef.current = setTimeout(() => {
      void (async () => {
        if (cancelledRef.current) return;
        try {
          const status = await apiClient.getOptimizeStatus(deckId, jobId);
          if (cancelledRef.current) return;
          setProgress({ phase: status.phase, current: status.current, total: status.total });
          if (status.status === "ok") {
            setProposal(status.proposal);
            setRunning(false);
            setProgress(null);
            clearActiveJob(deckId);
          } else if (status.status === "error") {
            setError(status.error ?? "Optimization failed");
            setRunning(false);
            setProgress(null);
            clearActiveJob(deckId);
          } else {
            poll(jobId);
          }
        } catch (err) {
          if (cancelledRef.current) return;
          setError(err instanceof ApiError ? err.message : "Optimization failed");
          setRunning(false);
          setProgress(null);
          clearActiveJob(deckId);
        }
      })();
    }, POLL_INTERVAL_MS);
  }

  // Resume polling a job that's still running server-side after the user
  // navigated away and back. The unmount cleanup only cancels the local timer;
  // it leaves the sessionStorage token so the job can be picked back up.
  useEffect(() => {
    cancelledRef.current = false;
    const jobId = readActiveJob(deckId);
    if (jobId) {
      setRunning(true);
      setProgress({ phase: "", current: 0, total: 0 });
      poll(jobId);
    }
    return () => {
      cancelledRef.current = true;
      stopPolling();
    };
  }, [deckId]);

  async function handleRun() {
    cancelledRef.current = false;
    stopPolling();
    setRunning(true);
    setError(null);
    setProposal(null);
    setProgress({ phase: "", current: 0, total: 0 });
    try {
      const { job_id } = await apiClient.startOptimizeDeck(deckId, {
        max_price_cents: priceEurToCents(maxPriceEur),
        max_swaps: maxSwaps,
        search_depth: depth,
      });
      writeActiveJob(deckId, job_id);
      poll(job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Optimization failed");
      setRunning(false);
      setProgress(null);
    }
  }

  function handleCancel() {
    cancelledRef.current = true;
    stopPolling();
    clearActiveJob(deckId);
    setRunning(false);
    setProgress(null);
  }

  async function applyOneSwap(swap: ProposedSwap) {
    const original = deckCards.find((c) => c.scryfall_id === swap.out_scryfall_id);
    const categories = original?.categories ?? [];
    await apiClient.removeCard(deckId, swap.out_scryfall_id);
    await apiClient.addCard(deckId, {
      card_scryfall_id: swap.in_scryfall_id,
      quantity: 1,
      categories,
      added_by: "ai",
      ai_reasoning: `Optimizer swap: ${swap.reason}`,
    });
  }

  async function handleApply() {
    if (!proposal) return;
    setApplying(true);
    setError(null);
    try {
      for (const swap of proposal.swaps) {
        await applyOneSwap(swap);
      }
      setProposal(null);
      onApplied?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to apply swaps");
    } finally {
      setApplying(false);
    }
  }

  async function handleApplySwap(swap: ProposedSwap) {
    if (!proposal) return;
    setApplyingKey(swap.out_scryfall_id);
    setError(null);
    try {
      await applyOneSwap(swap);
      const remaining = proposal.swaps.filter((s) => s.out_scryfall_id !== swap.out_scryfall_id);
      setProposal(remaining.length === 0 ? null : { ...proposal, swaps: remaining });
      onApplied?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to apply swap");
    } finally {
      setApplyingKey(null);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-white">Optimize deck</h2>
        <p className="text-xs text-gray-500">
          Search land + card swaps under a price ceiling, then resim.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-1.5 text-gray-300">
          Max price per swap (EUR)
          <input
            type="number"
            inputMode="decimal"
            min={0.1}
            step={0.1}
            value={maxPriceEur}
            disabled={running || applying}
            onChange={(e) => setMaxPriceEur(e.target.value)}
            className="w-20 rounded border border-white/15 bg-zinc-900 px-2 py-1 text-gray-100"
          />
        </label>
        <label className="flex items-center gap-1.5 text-gray-300">
          Max swaps
          <input
            type="number"
            inputMode="numeric"
            min={SWAPS_MIN}
            max={SWAPS_MAX}
            value={maxSwaps}
            disabled={running || applying}
            onChange={(e) => {
              const parsed = Number.parseInt(e.target.value, 10);
              if (Number.isNaN(parsed)) return;
              setMaxSwaps(Math.min(SWAPS_MAX, Math.max(SWAPS_MIN, parsed)));
            }}
            className="w-14 rounded border border-white/15 bg-zinc-900 px-2 py-1 text-gray-100"
          />
        </label>
        <label className="flex items-center gap-1.5 text-gray-300">
          Depth
          <select
            value={depth}
            disabled={running || applying}
            onChange={(e) => setDepth(e.target.value as SearchDepth)}
            className="rounded border border-white/15 bg-zinc-900 px-2 py-1 text-gray-100"
          >
            {DEPTH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {running ? (
          <button
            type="button"
            onClick={handleCancel}
            className="ml-auto rounded-lg border border-white/15 px-4 py-1.5 text-xs font-medium text-gray-200 hover:border-white/30"
          >
            Cancel
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={applying}
            className="ml-auto rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Optimize deck
          </button>
        )}
      </div>

      {error && (
        <p className="mb-3 rounded border border-red-500/30 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {running && progress && <ProgressBar progress={progress} />}

      {proposal && (
        <ProposalView
          proposal={proposal}
          applyingKey={applyingKey}
          busy={applying}
          onApplySwap={(swap) => void handleApplySwap(swap)}
        />
      )}

      {proposal && proposal.swaps.length > 0 && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void handleApply()}
            disabled={applying || applyingKey !== null}
            className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {applying ? "Planning…" : `Plan all ${proposal.swaps.length}`}
          </button>
          <button
            type="button"
            onClick={() => setProposal(null)}
            disabled={applying || applyingKey !== null}
            className="rounded-lg border border-white/15 px-4 py-1.5 text-xs font-medium text-gray-200 hover:border-white/30 disabled:opacity-50"
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
}

function ProgressBar({ progress }: { progress: Progress }) {
  const { phase, current, total } = progress;
  const fraction = total > 0 ? Math.min(1, current / total) : 0;
  const label = PHASE_LABELS[phase] ?? (phase || "Starting…");
  return (
    <div className="flex flex-col gap-1 text-xs text-gray-400">
      <div className="flex items-baseline justify-between">
        <span>{label}</span>
        <span>{total > 0 ? `${current}/${total} sims` : "preparing…"}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-white/10">
        <div
          className="h-full bg-indigo-500 transition-[width] duration-300"
          style={{ width: `${Math.round(fraction * 100)}%` }}
        />
      </div>
      <p className="text-[11px] text-gray-500">
        Running many simulations — this can take a while on deeper settings. You can keep using the
        rest of the app.
      </p>
    </div>
  );
}

function ProposalView({
  proposal,
  applyingKey,
  busy,
  onApplySwap,
}: {
  proposal: OptimizationProposal;
  applyingKey: string | null;
  busy: boolean;
  onApplySwap: (swap: ProposedSwap) => void;
}) {
  const rows = metricRows(proposal.baseline_stats, proposal.final_stats);
  if (proposal.swaps.length === 0) {
    return (
      <p className="rounded border border-white/10 bg-zinc-900/40 px-3 py-2 text-xs text-gray-300">
        No improvements found within the current price ceiling. The deck looks healthy or no
        candidate beat the noise floor.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="overflow-x-auto rounded border border-white/10">
        <table className="min-w-full text-left">
          <thead className="bg-white/5 text-gray-400">
            <tr>
              <th className="px-3 py-1.5 font-medium">Metric</th>
              <th className="px-3 py-1.5 font-medium">Baseline</th>
              <th className="px-3 py-1.5 font-medium">After</th>
              <th className="px-3 py-1.5 font-medium">Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const tone = deltaTone(row);
              const diff = row.final - row.baseline;
              const sign = diff > 0 ? "+" : "";
              const toneClass =
                tone === "good"
                  ? "text-emerald-300"
                  : tone === "bad"
                    ? "text-red-300"
                    : "text-gray-400";
              return (
                <tr key={row.key} className="border-t border-white/5">
                  <td className="px-3 py-1.5 text-gray-300">{row.label}</td>
                  <td className="px-3 py-1.5 text-gray-200">{row.formatter(row.baseline)}</td>
                  <td className="px-3 py-1.5 text-gray-200">{row.formatter(row.final)}</td>
                  <td className={`px-3 py-1.5 font-medium ${toneClass}`}>
                    {sign}
                    {row.formatter(diff)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="rounded border border-white/10">
        <div className="bg-white/5 px-3 py-1.5 text-gray-400">
          Proposed swaps ({proposal.swaps.length})
          {proposal.total_price_delta_cents !== null && (
            <span className="ml-2">
              total Δ price{" "}
              <span
                className={
                  proposal.total_price_delta_cents < 0 ? "text-emerald-300" : "text-red-300"
                }
              >
                {proposal.total_price_delta_cents < 0 ? "-" : "+"}€
                {priceCentsToEur(Math.abs(proposal.total_price_delta_cents))}
              </span>
            </span>
          )}
        </div>
        <ul className="divide-y divide-white/5">
          {proposal.swaps.map((swap) => (
            <li key={swap.out_scryfall_id} className="px-3 py-2">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-gray-200">
                  <CardHover name={swap.out_card_name}>
                    <span className="text-red-300 line-through">{swap.out_card_name}</span>
                  </CardHover>
                  <span className="mx-1.5 text-gray-500">→</span>
                  <CardHover name={swap.in_card_name}>
                    <span className="text-emerald-300">{swap.in_card_name}</span>
                  </CardHover>
                </span>
                {swap.price_delta_cents !== null && (
                  <span
                    className={swap.price_delta_cents < 0 ? "text-emerald-400" : "text-red-300"}
                  >
                    {swap.price_delta_cents < 0 ? "-" : "+"}€
                    {priceCentsToEur(Math.abs(swap.price_delta_cents))}
                  </span>
                )}
                <span className="text-gray-500">+{swap.score_delta.toFixed(3)} score</span>
                <button
                  type="button"
                  onClick={() => onApplySwap(swap)}
                  disabled={busy || applyingKey !== null}
                  className="ml-auto rounded border border-emerald-400/40 px-2 py-0.5 text-[11px] font-medium text-emerald-300 hover:border-emerald-400 hover:text-emerald-200 disabled:opacity-50"
                >
                  {applyingKey === swap.out_scryfall_id ? "Planning…" : "Plan swap"}
                </button>
              </div>
              <p className="mt-1 text-gray-400">{swap.reason}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
