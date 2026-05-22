"use client";

import { useCallback, useEffect, useState } from "react";

import { DeckBrowserPanel } from "@/components/deck-browser-panel";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onRemove: (scryfallId: string) => void | Promise<void>;
  onUndoCut?: (card: DeckCardItem) => void | Promise<void>;
  onCardClick?: (card: DeckCardItem) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  /** Target card count for the breakdown bar. Defaults to 100 (Commander). */
  target?: number;
}

/**
 * Sticky bottom bar with a deck-type breakdown that expands into the full
 * deck browser. Open/close is mirrored through ``window.history`` so the
 * system back button collapses the panel instead of leaving the page.
 *
 * Shared by the build page and the playtest/simulation page so editing a
 * deck is always one tap away.
 */
export function ExpandableDeckBar({
  cards,
  onRemove,
  onUndoCut,
  onCardClick,
  onSetQuantity,
  petCardNames,
  target = 100,
}: Props) {
  const [open, setOpenState] = useState(false);

  const setOpen = useCallback((next: boolean | ((prev: boolean) => boolean)) => {
    setOpenState((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      if (typeof window !== "undefined") {
        if (resolved && !prev) {
          window.history.pushState({ deckBar: true }, "");
        } else if (!resolved && prev && window.history.state?.deckBar) {
          window.history.back();
        }
      }
      return resolved;
    });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => setOpenState(false);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-zinc-950/90 backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {open && (
        <div className="mx-auto max-w-5xl border-b border-white/10 px-4 pt-3">
          <div className="h-[70vh] max-h-[640px]">
            <DeckBrowserPanel
              cards={cards}
              onRemove={onRemove}
              {...(onUndoCut && { onUndoCut })}
              {...(onCardClick && { onCardClick })}
              {...(onSetQuantity && { onSetQuantity })}
              {...(petCardNames && { petCardNames })}
            />
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Collapse deck browser" : "Expand deck browser"}
        className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors"
      >
        <DeckTypeBreakdown cards={cards} target={target} />
        <span
          className="shrink-0 text-gray-400 transition-transform"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
          aria-hidden
        >
          ▲
        </span>
      </button>
    </div>
  );
}
