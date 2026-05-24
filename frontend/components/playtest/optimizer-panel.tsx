"use client";

import { useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type { DeckCardItem, OptimizationProposal, PlaytestStats } from "@/lib/types";

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
const SWAPS_MAX = 5;

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
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<OptimizationProposal | null>(null);

  async function handleRun() {
    setRunning(true);
    setError(null);
    setProposal(null);
    try {
      const result = await apiClient.optimizeDeck(deckId, {
        max_price_cents: priceEurToCents(maxPriceEur),
        max_swaps: maxSwaps,
      });
      setProposal(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleApply() {
    if (!proposal) return;
    setApplying(true);
    setError(null);
    try {
      for (const swap of proposal.swaps) {
        const original = deckCards.find((c) => c.scryfall_id === swap.out_scryfall_id);
        const quantity = original?.quantity ?? 1;
        const categories = original?.categories ?? [];
        await apiClient.removeCard(deckId, swap.out_scryfall_id);
        await apiClient.addCard(deckId, {
          card_scryfall_id: swap.in_scryfall_id,
          quantity: Math.max(1, quantity),
          categories,
          added_by: "ai",
          ai_reasoning: `Optimizer swap: ${swap.reason}`,
        });
      }
      setProposal(null);
      onApplied?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to apply swaps");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-white">Optimize deck</h2>
        <p className="text-xs text-gray-500">
          Iteratively swap weak cards under a price ceiling, then resim.
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
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running || applying}
          className="ml-auto rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {running ? "Optimizing…" : "Optimize deck"}
        </button>
      </div>

      {error && (
        <p className="mb-3 rounded border border-red-500/30 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {running && (
        <p className="text-xs text-gray-400">
          Running baseline + variant simulations. This usually takes a few seconds.
        </p>
      )}

      {proposal && <ProposalView proposal={proposal} />}

      {proposal && proposal.swaps.length > 0 && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void handleApply()}
            disabled={applying}
            className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {applying ? "Applying…" : `Apply ${proposal.swaps.length} swap(s)`}
          </button>
          <button
            type="button"
            onClick={() => setProposal(null)}
            disabled={applying}
            className="rounded-lg border border-white/15 px-4 py-1.5 text-xs font-medium text-gray-200 hover:border-white/30 disabled:opacity-50"
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
}

function ProposalView({ proposal }: { proposal: OptimizationProposal }) {
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
                  proposal.total_price_delta_cents < 0
                    ? "text-emerald-300"
                    : "text-red-300"
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
                  <span className="text-red-300 line-through">{swap.out_card_name}</span>
                  <span className="mx-1.5 text-gray-500">→</span>
                  <span className="text-emerald-300">{swap.in_card_name}</span>
                </span>
                {swap.price_delta_cents !== null && (
                  <span
                    className={
                      swap.price_delta_cents < 0 ? "text-emerald-400" : "text-red-300"
                    }
                  >
                    {swap.price_delta_cents < 0 ? "-" : "+"}€
                    {priceCentsToEur(Math.abs(swap.price_delta_cents))}
                  </span>
                )}
                <span className="ml-auto text-gray-500">
                  +{swap.score_delta.toFixed(3)} score
                </span>
              </div>
              <p className="mt-1 text-gray-400">{swap.reason}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
