"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import { getStoredAccountId } from "@/lib/account";
import { DeckCategoryGroup } from "@/components/deck-category-group";
import { DeckStats } from "@/components/deck-stats";
import { ManaCurve } from "@/components/mana-curve";
import { ManaSymbols } from "@/components/mana-symbols";
import { ExportButton } from "@/components/export-button";
import { BRACKET_LABELS, CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import type { DeckCardItem, DeckDetailResponse } from "@/lib/types";

function groupByCategory(cards: DeckCardItem[]): Record<string, DeckCardItem[]> {
  const groups: Record<string, DeckCardItem[]> = {};
  for (const card of cards) {
    const cat = card.category ?? "other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(card);
  }
  return groups;
}

function sortedCategories(groups: Record<string, DeckCardItem[]>): string[] {
  const ordered = CATEGORY_ORDER.filter((c) => groups[c]?.length);
  const extra = Object.keys(groups).filter((c) => !CATEGORY_ORDER.includes(c));
  return [...ordered, ...extra];
}

function colorIdentityFromCards(cards: DeckCardItem[]): string[] {
  const colors: string[] = [];
  for (const card of cards) {
    for (const c of card.color_identity) {
      if (!colors.includes(c)) colors.push(c);
    }
  }
  return colors.sort();
}

export default function DeckDetailPage() {
  const params = useParams();
  const deckId = params["id"] as string;
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [petCardNames, setPetCardNames] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const d = await apiClient.getDeck(deckId);
      setDeck(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deck");
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const accountId = getStoredAccountId();
    if (!accountId) return;
    apiClient.listPreferences(accountId).then((prefs) => {
      const names = new Set(
        prefs
          .filter((p) => p.preference_type === "pet_card" && p.card_name)
          .map((p) => p.card_name as string),
      );
      setPetCardNames(names);
    }).catch(() => {/* non-critical */});
  }, []);

  async function handleRemoveCard(scryfallId: string) {
    if (!deck) return;
    try {
      await apiClient.removeCard(deck.id, scryfallId);
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
    }
  }

  if (error) {
    return (
      <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
        {error}
      </p>
    );
  }

  if (!deck) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">Loading...</div>
    );
  }

  const groups = groupByCategory(deck.cards);
  const categories = sortedCategories(groups);
  const colors = colorIdentityFromCards(deck.cards);
  const stage = STAGE_LABELS[deck.stage] ?? deck.stage;
  const bracket = deck.bracket != null ? BRACKET_LABELS[deck.bracket] : null;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{deck.name}</h1>
          {deck.description && (
            <p className="mt-1 text-sm text-gray-400">{deck.description}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            <span className="rounded bg-white/10 px-2 py-0.5 text-gray-300">{stage}</span>
            {bracket && (
              <span className="rounded bg-indigo-900/40 px-2 py-0.5 text-indigo-300">
                {bracket}
              </span>
            )}
            <span className="text-gray-500">{deck.cards.length} cards</span>
            <ManaSymbols colors={colors} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/decks/${deck.id}/build`}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            {deck.stage === "complete" ? "View Build" : "Continue Building"}
          </Link>
          <Link
            href={`/decks/${deck.id}/chat`}
            className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-300 hover:border-white/40 hover:text-white transition-colors"
          >
            Chat
          </Link>
          <ExportButton deckId={deck.id} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Card list */}
        <div className="flex flex-col gap-3">
          {categories.map((cat) => (
            <DeckCategoryGroup
              key={cat}
              category={cat}
              cards={groups[cat] ?? []}
              onRemove={handleRemoveCard}
              petCardNames={petCardNames}
            />
          ))}
          {deck.cards.length === 0 && (
            <div className="rounded-xl border border-dashed border-white/20 py-12 text-center text-gray-500">
              No cards yet.{" "}
              <Link href={`/decks/${deck.id}/build`} className="text-indigo-400 hover:underline">
                Start building
              </Link>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <ManaCurve cards={deck.cards} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <DeckStats cards={deck.cards} />
          </div>
        </div>
      </div>
    </div>
  );
}
