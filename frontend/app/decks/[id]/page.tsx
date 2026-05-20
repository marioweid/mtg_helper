"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { apiClient } from "@/lib/api";
import { CardDetailModal } from "@/components/card-detail-modal";
import { DeckDetailSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { BracketSelector } from "@/components/bracket-selector";
import { ComboTab } from "@/components/combo-tab";
import { DeckHistoryPanel } from "@/components/deck-history-panel";
import type { ComboListResponse } from "@/lib/types";
import { CommandBar } from "@/components/command-bar";
import { CommanderSection } from "@/components/commander-section";
import { DeckCategoryGroup } from "@/components/deck-category-group";
import { DeckCompactColumns } from "@/components/deck-compact-columns";
import {
  applyDeckFilter,
  DeckFilterBar,
  type DeckFilter,
} from "@/components/deck-filter-bar";
import { DeckGrid } from "@/components/deck-grid";
import { DeckHero } from "@/components/deck-hero";
import { DeckScorecard } from "@/components/deck-scorecard";
import { DeckStats } from "@/components/deck-stats";
import { ManaCurve } from "@/components/mana-curve";
import { ManaFixPanel } from "@/components/mana-fix-panel";
import { StatsModal } from "@/components/stats-modal";
import { BRACKET_LABELS, CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, totalCardCount, type DeckCardItem, type DeckDetailResponse } from "@/lib/types";

type ViewMode = "tags" | "types" | "grid";
type DeckTab = "cards" | "combos" | "history";

const VIEW_MODES: readonly ViewMode[] = ["tags", "types", "grid"];

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
  const toast = useToast();
  const deckId = params["id"] as string;
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [petCardNames, setPetCardNames] = useState<Set<string>>(new Set());
  const [editingDescription, setEditingDescription] = useState(false);
  const [draftDescription, setDraftDescription] = useState("");
  const [savingDescription, setSavingDescription] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("tags");
  const [tab, setTab] = useState<DeckTab>("cards");
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [statsOpen, setStatsOpen] = useState(false);
  const [filter, setFilter] = useState<DeckFilter>({
    query: "",
    colors: [],
    sort: "price",
  });
  const [combos, setCombos] = useState<ComboListResponse | null>(null);

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
    let cancelled = false;
    apiClient
      .getDeckCombos(deckId)
      .then((data) => {
        if (!cancelled) setCombos(data);
      })
      .catch(() => {
        /* non-critical */
      });
    return () => {
      cancelled = true;
    };
  }, [deckId]);

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
      toast.push(err instanceof Error ? err.message : "Failed to update description", "error");
    } finally {
      setSavingDescription(false);
    }
  }

  async function handleDeleteDeck() {
    if (!deck) return;
    if (!confirm(`Delete "${deck.name}"? All cards and feedback will be permanently removed.`)) return;
    setDeleting(true);
    try {
      await apiClient.deleteDeck(deck.id);
      router.push("/decks");
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to delete deck", "error");
      setDeleting(false);
    }
  }

  async function handleRemoveCard(scryfallId: string) {
    if (!deck) return;
    try {
      await apiClient.removeCard(deck.id, scryfallId);
      await load();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to remove card", "error");
    }
  }

  async function handleAddCard(scryfallId: string) {
    if (!deck) return;
    try {
      await apiClient.addCard(deck.id, { card_scryfall_id: scryfallId, added_by: "ai" });
      await load();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to add card", "error");
    }
  }

  async function handleSetCategories(scryfallId: string, categories: string[]) {
    if (!deck) return;
    try {
      await apiClient.updateCardCategories(deck.id, scryfallId, categories);
      await load();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to update categories", "error");
    }
  }

  async function handleSetQuantity(scryfallId: string, quantity: number) {
    if (!deck) return;
    if (quantity < 1) {
      await handleRemoveCard(scryfallId);
      return;
    }
    try {
      await apiClient.updateCardQuantity(deck.id, scryfallId, quantity);
      await load();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to update quantity", "error");
    }
  }

  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const scryfallId = String(active.id);
    const target = String(over.id);
    if (target === "bangers") return;
    const next = target === "untagged" ? [] : [target];
    void handleSetCategories(scryfallId, next);
  }

  if (error) {
    return (
      <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
        {error}
      </p>
    );
  }

  if (!deck) {
    return <DeckDetailSkeleton />;
  }

  const isGrid = viewMode === "grid";
  const visibleCards = applyDeckFilter(deck.cards, filter);
  const groups = viewMode === "tags" ? groupByCategory(visibleCards) : {};
  const categories = viewMode === "tags" ? sortedCategories(groups) : [];
  const colors = colorIdentityFromCards(deck.cards);
  const selectedCard = selectedCardId
    ? deck.cards.find((c) => c.deck_card_id === selectedCardId) ?? null
    : null;
  const comboCardIds = new Set<string>();
  if (combos) {
    for (const c of [...combos.active, ...combos.almost_there]) {
      for (const p of c.pieces) {
        if (p.in_deck && p.card.scryfall_id) comboCardIds.add(p.card.scryfall_id);
      }
    }
  }
  const stage = STAGE_LABELS[deck.stage] ?? deck.stage;
  const bracket = deck.bracket != null ? BRACKET_LABELS[deck.bracket] ?? null : null;

  const buildLabel = deck.stage === "complete" ? "View Build" : "Continue Building";

  return (
    <div className="pb-28">
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
        deleting={deleting}
        onDraftChange={setDraftDescription}
        onStartEditDescription={() => {
          setDraftDescription(deck.description ?? "");
          setEditingDescription(true);
        }}
        onSaveDescription={() => void handleSaveDescription()}
        onCancelEditDescription={() => setEditingDescription(false)}
        onDelete={() => void handleDeleteDeck()}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Card list / combos */}
        <div className="flex flex-col gap-3">
          <div
            role="tablist"
            aria-label="Deck view"
            className="inline-flex w-fit overflow-hidden rounded-lg border border-white/10 text-sm"
          >
            {(["cards", "combos", "history"] as const).map((t) => {
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
                  aria-label="Deck view mode"
                  className="inline-flex w-fit overflow-hidden rounded-lg border border-white/10 text-xs"
                >
                  {VIEW_MODES.map((mode) => {
                    const active = viewMode === mode;
                    return (
                      <button
                        key={mode}
                        onClick={() => setViewMode(mode)}
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
              <BracketSelector
                deckId={deck.id}
                bracket={deck.bracket}
                onBracketChange={(b) => setDeck({ ...deck, bracket: b })}
              />
              {deck.cards.length > 0 && (
                <DeckFilterBar
                  value={filter}
                  onChange={setFilter}
                  resultCount={totalCardCount(visibleCards)}
                  totalCount={totalCardCount(deck.cards)}
                  availableColors={deck.commander_color_identity}
                />
              )}
              <CommanderSection
                commander={deck.commander_card}
                partner={deck.partner_card}
              />
              {isGrid ? (
                <DeckGrid
                  cards={visibleCards}
                  onCardClick={setSelectedCardId}
                  comboCardIds={comboCardIds}
                  onSetQuantity={handleSetQuantity}
                />
              ) : viewMode === "tags" ? (
                <DndContext sensors={dndSensors} onDragEnd={handleDragEnd}>
                  {categories.map((cat) => (
                    <DeckCategoryGroup
                      key={cat}
                      category={cat}
                      cards={groups[cat] ?? []}
                      deckId={deck.id}
                      draggable
                      onRemove={handleRemoveCard}
                      onSetCategories={handleSetCategories}
                      onSetQuantity={handleSetQuantity}
                      onSwapped={load}
                      petCardNames={petCardNames}
                      comboCardIds={comboCardIds}
                    />
                  ))}
                </DndContext>
              ) : (
                <DeckCompactColumns
                  cards={visibleCards}
                  groupBy="type"
                  onCardClick={(c) => setSelectedCardId(c.deck_card_id)}
                  onRemove={handleRemoveCard}
                  petCardNames={petCardNames}
                  comboCardIds={comboCardIds}
                />
              )}
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

          {tab === "history" && <DeckHistoryPanel deckId={deck.id} />}
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
          <ManaFixPanel deckId={deck.id} onAddCard={handleAddCard} />
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <DeckStats cards={deck.cards} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <DeckScorecard cards={deck.cards} stageTargets={deck.stage_targets} />
          </div>
        </div>
      </div>

      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCardId(null)}
        deckId={deck.id}
        onRemove={async (id) => {
          await handleRemoveCard(id);
          setSelectedCardId(null);
        }}
        onSetCategories={handleSetCategories}
        onSwapped={async () => {
          await load();
          setSelectedCardId(null);
        }}
      />

      <StatsModal
        open={statsOpen}
        onClose={() => setStatsOpen(false)}
        cards={deck.cards}
        minPriceCents={deck.min_price_cents}
        maxPriceCents={deck.max_price_cents}
      />

      <CommandBar
        deckId={deck.id}
        buildLabel={buildLabel}
        onOpenStats={() => setStatsOpen(true)}
      />
    </div>
  );
}
