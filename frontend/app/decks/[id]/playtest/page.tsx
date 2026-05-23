"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { CardDetailModal } from "@/components/card-detail-modal";
import { ExpandableDeckBar } from "@/components/expandable-deck-bar";
import { PlaytestStatsPanel } from "@/components/playtest/stats-panel";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { DeckCardItem, DeckDetailResponse } from "@/lib/types";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function SimulatePage({ params }: PageProps) {
  const { id: deckId } = use(params);
  const toast = useToast();
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);

  const loadDeck = async () => {
    try {
      const loaded = await apiClient.getDeck(deckId);
      setDeck(loaded);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load deck");
    }
  };

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

  async function handleRemoveCard(scryfallId: string) {
    try {
      await apiClient.removeCard(deckId, scryfallId);
      await loadDeck();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to remove card", "error");
    }
  }

  async function handleSetQuantity(scryfallId: string, quantity: number) {
    try {
      if (quantity < 1) {
        await apiClient.removeCard(deckId, scryfallId);
      } else {
        await apiClient.updateCardQuantity(deckId, scryfallId, quantity);
      }
      await loadDeck();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to update quantity", "error");
    }
  }

  async function handleUndoCut(card: DeckCardItem) {
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        quantity: card.quantity,
        categories: card.categories,
        added_by: card.added_by === "ai" ? "ai" : "user",
      });
      await loadDeck();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to undo cut", "error");
    }
  }

  async function handleSetCategories(scryfallId: string, categories: string[]) {
    try {
      await apiClient.updateCardCategories(deckId, scryfallId, categories);
      await loadDeck();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to update categories", "error");
    }
  }

  const selectedCard = deck?.cards.find((c) => c.deck_card_id === selectedCardId) ?? null;

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

      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCardId(null)}
        deckId={deckId}
        onRemove={async (id) => {
          await handleRemoveCard(id);
          setSelectedCardId(null);
        }}
        onSetCategories={handleSetCategories}
        onSwapped={async () => {
          await loadDeck();
          setSelectedCardId(null);
        }}
      />

      {deck && (
        <ExpandableDeckBar
          cards={deck.cards}
          onRemove={handleRemoveCard}
          onUndoCut={handleUndoCut}
          onCardClick={(c) => setSelectedCardId(c.deck_card_id)}
          onSetQuantity={handleSetQuantity}
          commander={deck.commander_card}
          deckId={deckId}
          onCardAdded={() => void loadDeck()}
        />
      )}
    </div>
  );
}
