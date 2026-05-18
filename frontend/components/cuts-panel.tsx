"use client";

import { useState } from "react";
import { ApiError, apiClient } from "@/lib/api";
import type { CutSuggestion } from "@/lib/types";

interface Props {
  deckId: string;
  onRemoveCard?: (scryfallId: string) => Promise<void> | void;
}

export function CutsPanel({ deckId, onRemoveCard }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cuts, setCuts] = useState<CutSuggestion[] | null>(null);
  const [protectedCount, setProtectedCount] = useState<number>(0);
  const [removing, setRemoving] = useState<string | null>(null);

  async function handleSuggest() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.suggestCuts(deckId, { count: 10 });
      setCuts(res.cuts);
      setProtectedCount(res.protected_count);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to suggest cuts");
    } finally {
      setLoading(false);
    }
  }

  async function handleCut(scryfallId: string) {
    if (!onRemoveCard) return;
    setRemoving(scryfallId);
    try {
      await onRemoveCard(scryfallId);
      setCuts((prev) => (prev ? prev.filter((c) => c.scryfall_id !== scryfallId) : prev));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-medium text-gray-200">Suggest cuts</div>
          <div className="text-xs text-gray-500">
            Combo pieces, commander, and basic lands are never suggested.
          </div>
        </div>
        <button
          type="button"
          onClick={() => void handleSuggest()}
          disabled={loading}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Thinking…" : cuts ? "Refresh" : "Suggest 10 cuts"}
        </button>
      </div>

      {error && (
        <div className="mt-2 rounded border border-red-500/40 bg-red-900/20 px-2 py-1 text-xs text-red-300">
          {error}
        </div>
      )}

      {cuts && cuts.length === 0 && !error && (
        <div className="mt-2 text-xs text-gray-400">No cuts suggested.</div>
      )}

      {cuts && cuts.length > 0 && (
        <>
          <div className="mt-2 text-xs text-gray-500">
            Protected {protectedCount} cards. {cuts.length} suggested cuts:
          </div>
          <ul className="mt-2 space-y-2">
            {cuts.map((c) => (
              <li
                key={c.scryfall_id}
                className="flex items-start justify-between gap-3 rounded-md border border-white/10 bg-black/20 px-2 py-1.5"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-gray-100">{c.name}</div>
                  <div className="text-xs text-gray-400">{c.reasoning}</div>
                </div>
                {onRemoveCard && (
                  <button
                    type="button"
                    onClick={() => void handleCut(c.scryfall_id)}
                    disabled={removing === c.scryfall_id}
                    className="shrink-0 rounded border border-red-500/40 px-2 py-0.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    {removing === c.scryfall_id ? "Cutting…" : "Cut"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
