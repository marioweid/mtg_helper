"use client";

import { useState } from "react";
import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { OwnedBadge } from "@/components/owned-badge";
import { ApiError, apiClient } from "@/lib/api";
import type { SwapCandidate, SwapResponse } from "@/lib/types";

interface Props {
  deckId: string;
  sourceCardId: string;
  sourceScryfallId: string;
  sourceName: string;
  onSwapped?: () => void | Promise<void>;
}

function priceLabel(cents: number | null): string {
  return cents != null ? `€${(cents / 100).toFixed(2)}` : "—";
}

function CandidateRow({
  candidate,
  onSwap,
  busy,
}: {
  candidate: SwapCandidate;
  onSwap: () => void;
  busy: boolean;
}) {
  const savings = -candidate.price_delta_cents;
  const lossColor =
    candidate.function_loss_pct > 50
      ? "text-red-300"
      : candidate.function_loss_pct > 25
        ? "text-yellow-300"
        : "text-gray-400";
  return (
    <li className="flex items-center gap-3 rounded-md border border-white/10 bg-black/20 px-2 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5 truncate text-sm text-gray-100">
          <CardHover name={candidate.name} imageUri={candidate.image_uri}>
            {candidate.name}
          </CardHover>
          {candidate.mana_cost && (
            <span className="text-xs text-gray-500">
              <ManaCost cost={candidate.mana_cost} />
            </span>
          )}
          <OwnedBadge owned={candidate.owned_in} showUnowned={false} />
        </div>
        <div className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-gray-500">
          {candidate.type_line && <span className="truncate">{candidate.type_line}</span>}
          <span className="text-emerald-400">
            {savings > 0 ? `−€${(savings / 100).toFixed(2)}` : "no savings"}
          </span>
          <span className={lossColor}>~{candidate.function_loss_pct}% loss</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onSwap}
        disabled={busy}
        className="shrink-0 rounded border border-emerald-500/40 px-2 py-0.5 text-xs text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
      >
        {busy ? "Swapping…" : "Swap"}
      </button>
    </li>
  );
}

export function SwapPanel({
  deckId,
  sourceCardId,
  sourceScryfallId,
  sourceName,
  onSwapped,
}: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SwapResponse | null>(null);
  const [swapping, setSwapping] = useState<string | null>(null);

  async function loadSwaps() {
    setOpen(true);
    if (result || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.findSwaps(deckId, sourceCardId, { limit: 5 });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to find swaps");
    } finally {
      setLoading(false);
    }
  }

  async function handleSwap(candidate: SwapCandidate) {
    setSwapping(candidate.scryfall_id);
    try {
      await apiClient.removeCard(deckId, sourceScryfallId);
      await apiClient.addCard(deckId, {
        card_scryfall_id: candidate.scryfall_id,
        added_by: "user",
      });
      if (onSwapped) await onSwapped();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Swap failed");
    } finally {
      setSwapping(null);
    }
  }

  if (!open) {
    return (
      <div>
        <button
          type="button"
          onClick={() => void loadSwaps()}
          className="rounded border border-indigo-500/40 px-2 py-1 text-xs text-indigo-300 hover:bg-indigo-500/10"
          aria-label={`Find cheaper alternatives for ${sourceName}`}
        >
          💶 Find cheaper
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">
          Cheaper alternatives
          {result?.source_price_cents != null && (
            <span className="ml-2 text-gray-500">
              source {priceLabel(result.source_price_cents)}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Close
        </button>
      </div>

      {loading && <p className="mt-2 text-xs text-gray-500">Searching…</p>}
      {error && (
        <p className="mt-2 rounded border border-red-500/40 bg-red-900/20 px-2 py-1 text-xs text-red-300">
          {error}
        </p>
      )}
      {result && !loading && result.candidates.length === 0 && (
        <p className="mt-2 text-xs text-gray-500">No cheaper alternatives found.</p>
      )}
      {result && result.candidates.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {result.candidates.map((c) => (
            <CandidateRow
              key={c.scryfall_id}
              candidate={c}
              onSwap={() => void handleSwap(c)}
              busy={swapping === c.scryfall_id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
