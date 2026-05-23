"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DeckBrowserPanel } from "@/components/deck-browser-panel";
import { DeckCardSearch } from "@/components/deck-card-search";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onRemove: (scryfallId: string) => void | Promise<void>;
  onUndoCut?: (card: DeckCardItem) => void | Promise<void>;
  onCardClick?: (card: DeckCardItem) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  /** Commander card. Counts as +1 toward the deck total in the breakdown. */
  commander?: { type_line: string | null } | null;
  /** Target card count for the breakdown bar. Defaults to 100 (Commander). */
  target?: number;
  /** When provided, shows an "Add card" search inside the open panel. */
  deckId?: string;
  /** Called after a card is added via the embedded search. */
  onCardAdded?: () => void;
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
  commander,
  target = 100,
  deckId,
  onCardAdded,
}: Props) {
  const [open, setOpenState] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, setOpen]);

  return (
    <div
      ref={rootRef}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-zinc-950/90 backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {open && (
        <div className="mx-auto max-w-5xl border-b border-white/10 px-4 pt-3">
          {deckId && (
            <div className="mb-3">
              <DeckCardSearch
                deckId={deckId}
                {...(onCardAdded && { onAdded: onCardAdded })}
              />
            </div>
          )}
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
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
        aria-expanded={open}
        aria-label={open ? "Collapse deck browser" : "Expand deck browser"}
        className="w-full cursor-pointer hover:bg-white/5 transition-colors"
      >
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3 text-left">
          <DeckTypeBreakdown cards={cards} target={target} commander={commander ?? null} />
          <span
            className="shrink-0 text-gray-400 transition-transform"
            style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
            aria-hidden
          >
            ▲
          </span>
        </div>
      </div>
    </div>
  );
}
