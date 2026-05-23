"use client";

import { useEffect, useId } from "react";

import { CardDetailPanel } from "@/components/card-detail-panel";
import { ManaCost } from "@/components/mana-cost";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  card: DeckCardItem | null;
  onClose: () => void;
  deckId?: string;
  onRemove?: (scryfallId: string) => void;
  onSetCategories?: (scryfallId: string, categories: string[]) => void | Promise<void>;
  onSwapped?: () => void | Promise<void>;
}

/**
 * Full-screen modal showing the full detail surface for a single deck card.
 * Closes on Esc or clicking the scrim. Used by the grid view; the list view
 * keeps its inline expansion.
 */
export function CardDetailModal({
  card,
  onClose,
  deckId,
  onRemove,
  onSetCategories,
  onSwapped,
}: Props) {
  useEffect(() => {
    if (!card) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, onClose]);

  const titleId = useId();
  if (!card) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
    >
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 text-left shadow-2xl">
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <h2 id={titleId} className="text-xl font-semibold text-white">
            {card.name}
          </h2>
          <div className="flex items-center gap-3">
            {card.mana_cost ? (
              <span className="text-sm text-gray-300">
                <ManaCost cost={card.mana_cost} />
              </span>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close card detail"
              className="rounded-full px-2 text-lg leading-none text-gray-400 hover:bg-white/10 hover:text-white"
            >
              ×
            </button>
          </div>
        </div>
        <CardDetailPanel
          card={card}
          {...(deckId ? { deckId } : {})}
          onRemove={onRemove}
          onSetCategories={onSetCategories}
          {...(onSwapped ? { onSwapped } : {})}
          showImage
        />
      </div>
    </div>
  );
}
