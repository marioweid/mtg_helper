"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DeckBrowserPanel } from "@/components/deck-browser-panel";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import { GameChangerBadge } from "@/components/game-changer-badge";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { CardResponse, DeckCardItem } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onRemove: (scryfallId: string) => void | Promise<void>;
  onUndoCut?: (card: DeckCardItem) => void | Promise<void>;
  onCardClick?: (card: DeckCardItem) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  /** Commander card. Counts as +1 toward the deck total in the breakdown. */
  commander?: {
    type_line: string | null;
    name?: string | null;
    game_changer?: boolean;
  } | null;
  /** Target card count for the breakdown bar. Defaults to 100 (Commander). */
  target?: number;
  /** Declared deck bracket (1-4). Drives the Game Changer cap badge. */
  bracket?: number | null;
  /** When provided, the merged filter+search input can add cards to this deck. */
  deckId?: string;
  /** Called after a card is added via the merged search. */
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
  bracket,
  deckId,
  onCardAdded,
}: Props) {
  const [open, setOpenState] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const toast = useToast();

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

  const handleAddCard = useCallback(
    async (card: CardResponse) => {
      if (!deckId) return;
      try {
        await apiClient.addCard(deckId, {
          card_scryfall_id: card.scryfall_id,
          quantity: 1,
          added_by: "user",
        });
        toast.push(`Added ${card.name}`, "success");
        onCardAdded?.();
      } catch (err) {
        toast.push(err instanceof ApiError ? err.message : "Failed to add card", "error");
      }
    },
    [deckId, onCardAdded, toast],
  );

  return (
    <div
      ref={rootRef}
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
              {...(deckId ? { onAddCard: handleAddCard, commanderLegal: true } : {})}
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
          <GameChangerBadge
            cards={cards}
            bracket={bracket ?? null}
            commander={
              commander?.name
                ? { name: commander.name, game_changer: commander.game_changer ?? false }
                : null
            }
          />
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
