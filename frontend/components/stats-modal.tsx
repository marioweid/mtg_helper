"use client";

import { useEffect } from "react";

import { DeckStats } from "@/components/deck-stats";
import { ManaCurve } from "@/components/mana-curve";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  cards: DeckCardItem[];
}

/**
 * Modal version of the deck stats sidebar. Renders the same ``ManaCurve`` +
 * ``DeckStats`` components so users on mobile (where the sidebar drops below
 * the fold) can access stats without scrolling.
 */
export function StatsModal({ open, onClose, cards }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

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
