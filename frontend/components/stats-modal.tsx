"use client";

import { useEffect } from "react";

import { DeckStats } from "@/components/deck-stats";
import { ManaCurve } from "@/components/mana-curve";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  cards: DeckCardItem[];
  minPriceCents: number | null;
  maxPriceCents: number | null;
}

/**
 * Modal version of the deck stats sidebar. Renders the same ``ManaCurve`` +
 * ``DeckStats`` components plus the price-range card so users on mobile (where
 * the sidebar drops below the fold) can access stats without scrolling.
 */
export function StatsModal({ open, onClose, cards, minPriceCents, maxPriceCents }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const hasPriceRange = minPriceCents != null || maxPriceCents != null;

  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close stats"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-md cursor-default overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 text-left shadow-2xl"
      >
        <h2 className="mb-4 text-xl font-semibold text-white">Deck Stats</h2>
        <div className="flex flex-col gap-6">
          {hasPriceRange ? (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <h3 className="mb-2 text-sm font-semibold text-white">Price range</h3>
              <p className="text-sm text-gray-300">
                €{minPriceCents != null ? (minPriceCents / 100).toFixed(2) : "0.00"}
                {" – "}
                {maxPriceCents != null
                  ? `€${(maxPriceCents / 100).toFixed(2)}`
                  : "∞"}{" "}
                per card
              </p>
            </div>
          ) : null}
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <ManaCurve cards={cards} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <DeckStats cards={cards} />
          </div>
        </div>
      </div>
    </button>
  );
}
