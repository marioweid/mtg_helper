"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import { ComboTab } from "@/components/combo-tab";
import { DeckCategoryGroup } from "@/components/deck-category-group";
import { DeckHero } from "@/components/deck-hero";
import { DeckStats } from "@/components/deck-stats";
import { ManaCurve } from "@/components/mana-curve";
import { ExportButton } from "@/components/export-button";
import { BRACKET_LABELS, CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, totalCardCount, type DeckCardItem, type DeckDetailResponse } from "@/lib/types";
import { groupByPrimaryType, sortedPrimaryTypes } from "@/lib/card-types";

type GroupingMode = "tags" | "types";
type DeckTab = "cards" | "combos";

function groupByCategory(cards: DeckCardItem[]): Record<string, DeckCardItem[]> {
  const groups: Record<string, DeckCardItem[]> = {};
  for (const card of cards) {
    for (const cat of bucketsFor(card)) {
      (groups[cat] ??= []).push(card);
    }
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
  const router = useRouter();
  const deckId = params["id"] as string;
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [petCardNames, setPetCardNames] = useState<Set<string>>(new Set());
  const [editingDescription, setEditingDescription] = useState(false);
  const [draftDescription, setDraftDescription] = useState("");
  const [savingDescription, setSavingDescription] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [groupingMode, setGroupingMode] = useState<GroupingMode>("tags");
  const [tab, setTab] = useState<DeckTab>("cards");

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
    apiClient.listPreferences().then((prefs) => {
      const names = new Set(
        prefs
          .filter((p) => p.preference_type === "pet_card" && p.card_name)
          .map((p) => p.card_name as string),
      );
      setPetCardNames(names);
    }).catch(() => {/* non-critical */});
  }, []);

  async function handleSaveDescription() {
    if (!deck) return;
    setSavingDescription(true);
    try {
      await apiClient.updateDeck(deck.id, { description: draftDescription || null });
      setDeck({ ...deck, description: draftDescription || null });
      setEditingDescription(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update description");
    } finally {
      setSavingDescription(false);
    }
  }

  async function handleDeleteDeck() {
    if (!deck) return;
    if (!confirm(`Delete "${deck.name}"? All cards, feedback, and chat history will be permanently removed.`)) return;
    setDeleting(true);
    try {
      await apiClient.deleteDeck(deck.id);
      router.push("/decks");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete deck");
      setDeleting(false);
    }
  }

  async function handleRemoveCard(scryfallId: string) {
    if (!deck) return;
    try {
      await apiClient.removeCard(deck.id, scryfallId);
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
    }
  }

  async function handleSetCategories(scryfallId: string, categories: string[]) {
    if (!deck) return;
    try {
      await apiClient.updateCardCategories(deck.id, scryfallId, categories);
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update categories");
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

  const groups =
    groupingMode === "types" ? groupByPrimaryType(deck.cards) : groupByCategory(deck.cards);
  const categories =
    groupingMode === "types" ? sortedPrimaryTypes(groups) : sortedCategories(groups);
  const colors = colorIdentityFromCards(deck.cards);
  const stage = STAGE_LABELS[deck.stage] ?? deck.stage;
  const bracket = deck.bracket != null ? BRACKET_LABELS[deck.bracket] ?? null : null;

  const actions = (
    <>
      <Link
        href={`/decks/${deck.id}/build`}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
      >
        {deck.stage === "complete" ? "View Build" : "Continue Building"}
      </Link>
      <Link
        href={`/decks/${deck.id}/keywords`}
        className="rounded-lg border border-white/30 bg-black/30 px-4 py-2 text-sm text-gray-100 backdrop-blur transition-colors hover:bg-white/10 hover:text-white"
      >
        Keywords
      </Link>
      <ExportButton deckId={deck.id} />
      <button
        onClick={() => void handleDeleteDeck()}
        disabled={deleting}
        className="rounded-lg border border-red-500/50 bg-black/30 px-4 py-2 text-sm text-red-300 backdrop-blur transition-colors hover:border-red-400 hover:text-red-200 disabled:opacity-50"
      >
        {deleting ? "Deleting…" : "Delete"}
      </button>
    </>
  );

  return (
    <div>
      <DeckHero
        name={deck.name}
        deckId={deck.id}
        description={deck.description}
        commander={deck.commander_card}
        partner={deck.partner_card}
        colors={colors}
        cardCount={totalCardCount(deck.cards)}
        stage={stage}
        bracket={bracket}
        archetypeTags={deck.archetype_tags ?? []}
        editingDescription={editingDescription}
        draftDescription={draftDescription}
        savingDescription={savingDescription}
        onDraftChange={setDraftDescription}
        onStartEditDescription={() => {
          setDraftDescription(deck.description ?? "");
          setEditingDescription(true);
        }}
        onSaveDescription={() => void handleSaveDescription()}
        onCancelEditDescription={() => setEditingDescription(false)}
        actions={actions}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Card list / combos */}
        <div className="flex flex-col gap-3">
          <div
            role="tablist"
            aria-label="Deck view"
            className="inline-flex w-fit overflow-hidden rounded-lg border border-white/10 text-sm"
          >
            {(["cards", "combos"] as const).map((t) => {
              const active = tab === t;
              return (
                <button
                  key={t}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(t)}
                  className={`px-4 py-1.5 capitalize transition-colors ${
                    active
                      ? "bg-indigo-600 text-white"
                      : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                  }`}
                >
                  {t}
                </button>
              );
            })}
          </div>

          {tab === "cards" && (
            <>
              {deck.cards.length > 0 && (
                <div
                  role="group"
                  aria-label="Group cards by"
                  className="inline-flex w-fit overflow-hidden rounded-lg border border-white/10 text-xs"
                >
                  {(["tags", "types"] as const).map((mode) => {
                    const active = groupingMode === mode;
                    return (
                      <button
                        key={mode}
                        onClick={() => setGroupingMode(mode)}
                        aria-pressed={active}
                        className={`px-3 py-1.5 capitalize transition-colors ${
                          active
                            ? "bg-indigo-600 text-white"
                            : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                        }`}
                      >
                        {mode}
                      </button>
                    );
                  })}
                </div>
              )}
              {categories.map((cat) => (
                <DeckCategoryGroup
                  key={cat}
                  category={cat}
                  cards={groups[cat] ?? []}
                  onRemove={handleRemoveCard}
                  onSetCategories={handleSetCategories}
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
            </>
          )}

          {tab === "combos" && <ComboTab deckId={deck.id} />}
        </div>

        {/* Sidebar */}
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Price range</h3>
              <Link
                href={`/decks/${deck.id}/build`}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Edit in Build
              </Link>
            </div>
            {deck.max_price_cents != null || deck.min_price_cents != null ? (
              <p className="text-sm text-gray-300">
                €{deck.min_price_cents != null ? (deck.min_price_cents / 100).toFixed(2) : "0.00"}
                {" – "}
                {deck.max_price_cents != null
                  ? `€${(deck.max_price_cents / 100).toFixed(2)}`
                  : "∞"}{" "}
                per card
              </p>
            ) : (
              <p className="text-sm text-gray-600 italic">No range — suggestions include any price</p>
            )}
          </div>
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
