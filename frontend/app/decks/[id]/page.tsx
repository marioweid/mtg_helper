"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import { CardDetailModal } from "@/components/card-detail-modal";
import { DeckDetailSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { BracketSelector } from "@/components/bracket-selector";
import { ComboTab } from "@/components/combo-tab";
import { DeckHistoryPanel } from "@/components/deck-history-panel";
import type { ComboListResponse } from "@/lib/types";
import { CommandBar } from "@/components/command-bar";
import { CardWorkspaceToolbar } from "@/components/card-workspace-toolbar";
import { CommanderSection } from "@/components/commander-section";
import { DeckCardSearch } from "@/components/deck-card-search";
import { DeckCompactColumns } from "@/components/deck-compact-columns";
import {
  applyDeckFilter,
  DeckFilterBar,
  type DeckFilter,
  type SortMode,
} from "@/components/deck-filter-bar";
import {
  getDeckGroup,
  getDeckSort,
  getDeckView,
  getWorkspaceView,
  setDeckGroup,
  setDeckSort,
  setWorkspaceView,
  type CardWorkspaceView,
} from "@/lib/deck-view-prefs";
import { DeckGrid } from "@/components/deck-grid";
import { DeckHero } from "@/components/deck-hero";
import { DeckScorecard } from "@/components/deck-scorecard";
import { DeckStats } from "@/components/deck-stats";
import { GameChangerBadge } from "@/components/game-changer-badge";
import { ManaCurve } from "@/components/mana-curve";
import { ManaFixPanel } from "@/components/mana-fix-panel";
import { PlannedChangesPanel } from "@/components/planned-changes-panel";
import { StatsModal } from "@/components/stats-modal";
import { TopPicksPanel } from "@/components/top-picks-panel";
import { BRACKET_LABELS, STAGE_LABELS } from "@/lib/constants";
import { deckTotal, totalCardCount, type DeckCardItem, type DeckDetailResponse } from "@/lib/types";

type GroupMode = "tag" | "type";
type DeckTab = "cards" | "top-picks" | "combos" | "history";

const SORT_MODES: readonly SortMode[] = ["default", "name", "cmc", "price"];

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
  const [viewMode, setViewMode] = useState<CardWorkspaceView>("grid");
  const [groupMode, setGroupMode] = useState<GroupMode>("type");
  const [collapsedGroups, setCollapsedGroups] = useState<Record<GroupMode, Set<string>>>(() => ({
    type: new Set(),
    tag: new Set(),
  }));
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

  // Restore the per-deck view mode + sort the user last chose.
  useEffect(() => {
    const workspaceView = getWorkspaceView(`deck:${deckId}`);
    const legacyView = getDeckView(deckId);
    if (workspaceView) {
      setViewMode(workspaceView);
    } else if (legacyView === "grid") {
      setViewMode("grid");
    } else if (legacyView === "tags" || legacyView === "types") {
      setViewMode("list");
      setGroupMode(legacyView === "tags" ? "tag" : "type");
    }
    const storedGroup = getDeckGroup(deckId);
    if (storedGroup === "tag" || storedGroup === "type") {
      setGroupMode(storedGroup);
    }
    const storedSort = getDeckSort(deckId);
    if (storedSort && (SORT_MODES as readonly string[]).includes(storedSort)) {
      setFilter((prev) => ({ ...prev, sort: storedSort as SortMode }));
    }
  }, [deckId]);

  function handleViewModeChange(mode: CardWorkspaceView) {
    setViewMode(mode);
    setWorkspaceView(`deck:${deckId}`, mode);
  }

  function handleGroupModeChange(mode: GroupMode) {
    setGroupMode(mode);
    setDeckGroup(deckId, mode);
  }

  function handleToggleGroup(groupKey: string) {
    setCollapsedGroups((current) => {
      const nextForMode = new Set(current[groupMode]);
      if (nextForMode.has(groupKey)) nextForMode.delete(groupKey);
      else nextForMode.add(groupKey);
      return { ...current, [groupMode]: nextForMode };
    });
  }

  function handleFilterChange(next: DeckFilter) {
    setFilter(next);
    setDeckSort(deckId, next.sort);
  }

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
    apiClient
      .listPreferences()
      .then((prefs) => {
        const names = new Set(
          prefs
            .filter((p) => p.preference_type === "pet_card" && p.card_name)
            .map((p) => p.card_name as string),
        );
        setPetCardNames(names);
      })
      .catch(() => {
        /* non-critical */
      });
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
    if (!confirm(`Delete "${deck.name}"? All cards and feedback will be permanently removed.`))
      return;
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
    const card = deck.cards.find((item) => item.scryfall_id === scryfallId);
    if (!card || quantity === card.quantity) return;
    try {
      await apiClient.planCard(deck.id, {
        card_scryfall_id: scryfallId,
        direction: quantity > card.quantity ? "addition" : "cut",
        quantity: Math.abs(quantity - card.quantity),
        categories: card.categories,
        added_by: card.added_by === "ai" ? "ai" : "user",
      });
      await load();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to plan quantity", "error");
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
    return <DeckDetailSkeleton />;
  }

  const isGrid = viewMode === "grid";
  const visibleCards = applyDeckFilter(deck.cards, filter);
  const colors = colorIdentityFromCards(deck.cards);
  const selectedCard = selectedCardId
    ? (deck.cards.find((c) => c.deck_card_id === selectedCardId) ?? null)
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
  const bracket = deck.bracket != null ? (BRACKET_LABELS[deck.bracket] ?? null) : null;

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
        cardCount={deckTotal(deck)}
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

      <div className="mb-6">
        <PlannedChangesPanel
          deckId={deck.id}
          plans={deck.planned_changes}
          physicalCount={deck.physical_card_count}
          plannedCount={deck.planned_card_count}
          onChanged={load}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Card list / combos */}
        <div className="flex flex-col gap-3">
          <div
            role="tablist"
            aria-label="Deck view"
            className="inline-flex w-fit overflow-hidden rounded-lg border border-white/10 text-sm"
          >
            {(["cards", "top-picks", "combos", "history"] as const).map((t) => {
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
                  {t === "top-picks" ? "Top Picks" : t}
                </button>
              );
            })}
          </div>

          {tab === "cards" && (
            <>
              <div className="flex flex-wrap items-start gap-3">
                <div className="flex-1 min-w-[220px]">
                  <BracketSelector
                    deckId={deck.id}
                    bracket={deck.bracket}
                    onBracketChange={(b) => setDeck({ ...deck, bracket: b })}
                  />
                </div>
                <GameChangerBadge
                  cards={deck.cards}
                  bracket={deck.bracket}
                  commander={deck.commander_card}
                />
              </div>
              <DeckCardSearch deckId={deck.id} onAdded={() => void load()} />
              {deck.cards.length > 0 && (
                <CardWorkspaceToolbar
                  view={viewMode}
                  onViewChange={handleViewModeChange}
                  resultCount={totalCardCount(visibleCards)}
                  totalCount={totalCardCount(deck.cards)}
                >
                  <DeckFilterBar
                    value={filter}
                    onChange={handleFilterChange}
                    resultCount={totalCardCount(visibleCards)}
                    totalCount={totalCardCount(deck.cards)}
                    availableColors={deck.commander_color_identity}
                  />
                  <div role="group" aria-label="Group cards by" className="flex gap-1 px-1">
                    {(["type", "tag"] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => handleGroupModeChange(mode)}
                        aria-pressed={groupMode === mode}
                        className={`min-h-11 touch-manipulation rounded-lg px-3 text-xs font-medium capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                          groupMode === mode
                            ? "bg-indigo-500/20 text-indigo-200"
                            : "text-gray-400 hover:bg-white/5 hover:text-white"
                        }`}
                      >
                        Group: {mode}
                      </button>
                    ))}
                  </div>
                </CardWorkspaceToolbar>
              )}
              <CommanderSection commander={deck.commander_card} partner={deck.partner_card} />
              {isGrid ? (
                <DeckGrid
                  cards={visibleCards}
                  onCardClick={setSelectedCardId}
                  comboCardIds={comboCardIds}
                  onSetQuantity={handleSetQuantity}
                  onRemove={handleRemoveCard}
                  groupBy={groupMode}
                  collapsedGroups={collapsedGroups[groupMode]}
                  onToggleGroup={handleToggleGroup}
                />
              ) : (
                <DeckCompactColumns
                  cards={visibleCards}
                  groupBy={groupMode}
                  onCardClick={(c) => setSelectedCardId(c.deck_card_id)}
                  onRemove={handleRemoveCard}
                  onSetQuantity={handleSetQuantity}
                  petCardNames={petCardNames}
                  comboCardIds={comboCardIds}
                  collapsedGroups={collapsedGroups[groupMode]}
                  onToggleGroup={handleToggleGroup}
                />
              )}
              {deck.cards.length === 0 && (
                <div className="rounded-xl border border-dashed border-white/20 py-12 text-center text-gray-500">
                  No cards yet.{" "}
                  <Link
                    href={`/decks/${deck.id}/build`}
                    className="text-indigo-400 hover:underline"
                  >
                    Start building
                  </Link>
                </div>
              )}
            </>
          )}

          {tab === "combos" && <ComboTab deckId={deck.id} />}

          {tab === "top-picks" && <TopPicksPanel deckId={deck.id} onPlanChanged={load} />}

          {tab === "history" && <DeckHistoryPanel deckId={deck.id} />}
        </div>

        {/* Sidebar */}
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <ManaCurve cards={deck.cards} curve={deck.mana_curve} />
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
        manaCurve={deck.mana_curve}
      />

      <CommandBar deckId={deck.id} buildLabel={buildLabel} />
    </div>
  );
}
