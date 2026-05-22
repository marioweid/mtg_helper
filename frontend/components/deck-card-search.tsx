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

  async function addCard(card: CardResponse) {
    setAdding(true);
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        quantity: 1,
        added_by: "user",
      });
      toast.push(`Added ${card.name}`, "success");
      onAdded?.();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to add card", "error");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h3 className="mb-2 text-sm font-semibold text-white">Add card</h3>
      <p className="mb-3 text-xs text-gray-400">
        Type to search the card pool. Selecting a card adds it to the deck.
      </p>
      <CardSearch
        placeholder={placeholder ?? "Search cards to add..."}
        onSelect={(card) => void addCard(card)}
        commanderLegal
      />
      {adding && <p className="mt-2 text-xs text-gray-500">Adding…</p>}
    </div>
  );
}
