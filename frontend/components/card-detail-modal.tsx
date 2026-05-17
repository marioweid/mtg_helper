"use client";

import { useEffect } from "react";

import { CardDetailPanel } from "@/components/card-detail-panel";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  card: DeckCardItem | null;
  onClose: () => void;
  onRemove?: (scryfallId: string) => void;
  onSetCategories?: (scryfallId: string, categories: string[]) => void | Promise<void>;
}

/**
 * Full-screen modal showing the full detail surface for a single deck card.
 * Closes on Esc or clicking the scrim. Used by the grid view; the list view
 * keeps its inline expansion.
 */
export function CardDetailModal({ card, onClose, onRemove, onSetCategories }: Props) {
  useEffect(() => {
    if (!card) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, onClose]);

  if (!card) return null;

  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close card detail"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-3xl cursor-default overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 text-left shadow-2xl"
      >
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold text-white">{card.name}</h2>
          {card.mana_cost ? (
            <span className="text-sm tracking-wider text-gray-400">{card.mana_cost}</span>
          ) : null}
        </div>
        <CardDetailPanel
          card={card}
          onRemove={onRemove}
          onSetCategories={onSetCategories}
          showImage
        />
      </div>
    </button>
  );
}
