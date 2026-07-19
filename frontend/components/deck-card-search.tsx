"use client";

import { useState } from "react";

import { CardSearch } from "@/components/card-search";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { CardResponse } from "@/lib/types";

interface Props {
  deckId: string;
  /** Called after a card is successfully added so the parent can refetch the deck. */
  onAdded?: () => void;
  placeholder?: string;
}

/**
 * Search-and-add widget. Wraps ``CardSearch`` with a deck-aware ``addCard``
 * call so the user can drop in cards (often from the analysis agent's swap
 * suggestions) without leaving the page.
 */
export function DeckCardSearch({ deckId, onAdded, placeholder }: Props) {
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [immediate, setImmediate] = useState(false);

  async function addCard(card: CardResponse) {
    setAdding(true);
    try {
      const payload = {
        card_scryfall_id: card.scryfall_id,
        quantity: 1,
        added_by: "user" as const,
      };
      if (immediate) await apiClient.addCardNow(deckId, payload);
      else await apiClient.addCard(deckId, payload);
      toast.push(immediate ? `Added ${card.name}` : `Planned ${card.name}`, "success");
      onAdded?.();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to add card", "error");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">
          {immediate ? "Add card now" : "Plan addition"}
        </h3>
        <button
          type="button"
          onClick={() => setImmediate((current) => !current)}
          className="text-xs text-gray-500 hover:text-white"
        >
          {immediate ? "Use planning" : "Add now instead"}
        </button>
      </div>
      <p className="mb-3 text-xs text-gray-400">
        {immediate
          ? "Selecting a card changes the physical deck immediately."
          : "Selecting a card queues it without changing the physical deck."}
      </p>
      <CardSearch
        placeholder={placeholder ?? "Search cards to plan..."}
        onSelect={(card) => void addCard(card)}
        commanderLegal
      />
      {adding && <p className="mt-2 text-xs text-gray-500">Planning…</p>}
    </div>
  );
}
