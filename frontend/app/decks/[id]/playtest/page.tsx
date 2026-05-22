"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { CommandBar } from "@/components/command-bar";
import { PlaytestStatsPanel } from "@/components/playtest/stats-panel";
import { StatsModal } from "@/components/stats-modal";
import { apiClient, ApiError } from "@/lib/api";
import type { DeckDetailResponse } from "@/lib/types";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function SimulatePage({ params }: PageProps) {
  const { id: deckId } = use(params);
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statsOpen, setStatsOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await apiClient.getDeck(deckId);
        if (!cancelled) setDeck(loaded);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load deck");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deckId]);

  const buildLabel = deck?.stage === "complete" ? "Edit deck" : "Continue building";

  return (
    <div className="flex flex-col gap-4 pb-28">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <Link
            href={`/decks/${deckId}`}
            className="text-xs text-indigo-400 hover:underline"
          >
            ← {deck?.name || "Deck"}
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-white">Simulate</h1>
          <p className="mt-1 text-xs text-gray-500">
            Batch goldfish simulation across many trials. For interactive playtesting,
            use Moxfield.
          </p>
        </div>
      </header>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </p>
      )}

      <PlaytestStatsPanel deckId={deckId} />

      {deck && (
        <StatsModal
          open={statsOpen}
          onClose={() => setStatsOpen(false)}
          cards={deck.cards}
          minPriceCents={deck.min_price_cents}
          maxPriceCents={deck.max_price_cents}
        />
      )}

      <CommandBar
        deckId={deckId}
        buildLabel={buildLabel}
        onOpenStats={() => setStatsOpen(true)}
      />
    </div>
  );
}
