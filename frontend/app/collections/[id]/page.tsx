"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import { CardWorkspaceToolbar } from "@/components/card-workspace-toolbar";
import { CardSearch } from "@/components/card-search";
import { CollectionCardGrid } from "@/components/collection-card-grid";
import { CollectionCardRow } from "@/components/collection-card-row";
import { useToast } from "@/components/toast";
import { getWorkspaceView, setWorkspaceView, type CardWorkspaceView } from "@/lib/deck-view-prefs";
import type {
  CardResponse,
  CollectionCardItem,
  CollectionResponse,
  DeckSummary,
} from "@/lib/types";

const PAGE_SIZE = 50;
type CollectionSort = "name" | "price" | "quantity";
type SortDirection = "asc" | "desc";
type CollectionGroup = "none" | "type" | "set";

const SORT_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "name:asc", label: "Name: A–Z" },
  { value: "name:desc", label: "Name: Z–A" },
  { value: "price:asc", label: "Price: Low–High" },
  { value: "price:desc", label: "Price: High–Low" },
  { value: "quantity:asc", label: "Quantity: Low–High" },
  { value: "quantity:desc", label: "Quantity: High–Low" },
];

const GROUP_OPTIONS: readonly { value: CollectionGroup; label: string }[] = [
  { value: "none", label: "None" },
  { value: "type", label: "Type" },
  { value: "set", label: "Set" },
];

const TYPE_OPTIONS = [
  "Creature",
  "Instant",
  "Sorcery",
  "Artifact",
  "Enchantment",
  "Planeswalker",
  "Land",
] as const;

function parseEurInput(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const eur = Number.parseFloat(trimmed);
  if (!Number.isFinite(eur) || eur < 0) return "invalid";
  return eur > 0 ? Math.round(eur * 100) : null;
}

function primaryType(typeLine: string | null): string {
  const value = typeLine ?? "";
  for (const type of [...TYPE_OPTIONS, "Battle"] as const) {
    if (value.includes(type)) return type;
  }
  return "Other";
}

function groupCards(cards: CollectionCardItem[], group: CollectionGroup) {
  if (group === "none") return [{ key: "all", label: null, cards }];
  const sections = new Map<string, CollectionCardItem[]>();
  for (const card of cards) {
    const key =
      group === "type" ? primaryType(card.type_line) : card.set_code.toUpperCase() || "Unknown Set";
    const section = sections.get(key) ?? [];
    section.push(card);
    sections.set(key, section);
  }
  return [...sections].map(([key, sectionCards]) => ({ key, label: key, cards: sectionCards }));
}

function validSort(value: string | null): CollectionSort {
  return value === "price" || value === "quantity" ? value : "name";
}

function validDirection(value: string | null): SortDirection {
  return value === "desc" ? "desc" : "asc";
}

function validGroup(value: string | null): CollectionGroup {
  return value === "type" || value === "set" ? value : "none";
}

function priceFromQuery(value: string): number | null {
  const parsed = parseEurInput(value);
  return parsed === "invalid" ? null : parsed;
}

function offsetFromQuery(value: string | null): number {
  const page = Math.max(1, Number.parseInt(value ?? "1", 10) || 1);
  return (page - 1) * PAGE_SIZE;
}

export default function CollectionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialMinPrice = searchParams.get("min_price") ?? "";
  const initialMaxPrice = searchParams.get("max_price") ?? "";
  const initialSearch = searchParams.get("search") ?? "";
  const [collection, setCollection] = useState<CollectionResponse | null>(null);
  const [cards, setCards] = useState<CollectionCardItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(() => offsetFromQuery(searchParams.get("page")));
  const [typeFilter, setTypeFilter] = useState<string | null>(() => searchParams.get("type"));
  const [minPriceCents, setMinPriceCents] = useState<number | null>(() =>
    priceFromQuery(initialMinPrice),
  );
  const [maxPriceCents, setMaxPriceCents] = useState<number | null>(() =>
    priceFromQuery(initialMaxPrice),
  );
  const [minPriceDraft, setMinPriceDraft] = useState(initialMinPrice);
  const [maxPriceDraft, setMaxPriceDraft] = useState(initialMaxPrice);
  const [searchDraft, setSearchDraft] = useState(initialSearch);
  const [searchQuery, setSearchQuery] = useState(initialSearch);
  const [sort, setSort] = useState<CollectionSort>(() => validSort(searchParams.get("sort")));
  const [direction, setDirection] = useState<SortDirection>(() =>
    validDirection(searchParams.get("direction")),
  );
  const [group, setGroup] = useState<CollectionGroup>(() => validGroup(searchParams.get("group")));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [view, setView] = useState<CardWorkspaceView>("grid");
  const [busyCardId, setBusyCardId] = useState<string | null>(null);
  const cardsRequestRef = useRef(0);

  const replaceQuery = useCallback(
    (updates: Record<string, string | null>, resetPage = true) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      if (resetPage) next.delete("page");
      const query = next.toString();
      router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const loadCollection = useCallback(async () => {
    try {
      const c = await apiClient.getCollection(id);
      setCollection(c);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collection");
    }
  }, [id]);

  const loadCards = useCallback(async () => {
    const requestId = ++cardsRequestRef.current;
    try {
      const result = await apiClient.listCollectionCards(id, {
        limit: PAGE_SIZE,
        offset,
        type: typeFilter,
        min_price_cents: minPriceCents,
        max_price_cents: maxPriceCents,
        search: searchQuery,
        sort,
        direction,
        group,
      });
      if (requestId !== cardsRequestRef.current) return;
      setCards(result.data);
      setTotal(result.meta.total);
    } catch (err) {
      if (requestId !== cardsRequestRef.current) return;
      setError(err instanceof ApiError ? err.message : "Failed to load cards");
    }
  }, [id, offset, typeFilter, minPriceCents, maxPriceCents, searchQuery, sort, direction, group]);

  useEffect(() => {
    const nextSearch = searchParams.get("search") ?? "";
    const minPrice = searchParams.get("min_price") ?? "";
    const maxPrice = searchParams.get("max_price") ?? "";
    setSearchDraft(nextSearch);
    setSearchQuery(nextSearch);
    setTypeFilter(searchParams.get("type"));
    setMinPriceDraft(minPrice);
    setMaxPriceDraft(maxPrice);
    setMinPriceCents(priceFromQuery(minPrice));
    setMaxPriceCents(priceFromQuery(maxPrice));
    setSort(validSort(searchParams.get("sort")));
    setDirection(validDirection(searchParams.get("direction")));
    setGroup(validGroup(searchParams.get("group")));
    setOffset(offsetFromQuery(searchParams.get("page")));
  }, [searchParams]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const next = searchDraft.trim();
      if (next === searchQuery) return;
      setSearchQuery(next);
      setOffset(0);
      replaceQuery({ search: next || null });
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [replaceQuery, searchDraft, searchQuery]);

  useEffect(() => {
    void loadCollection();
  }, [loadCollection]);

  useEffect(() => {
    void loadCards();
  }, [loadCards]);

  useEffect(() => {
    void apiClient
      .listDecks({ limit: 100 })
      .then(setDecks)
      .catch(() => setDecks([]));
  }, []);

  useEffect(() => {
    setView(getWorkspaceView(`collection:${id}`) ?? "grid");
  }, [id]);

  function handleViewChange(next: CardWorkspaceView) {
    setView(next);
    setWorkspaceView(`collection:${id}`, next);
  }

  async function handleAdd(card: CardResponse) {
    setError(null);
    try {
      await apiClient.addCollectionCard(id, { scryfall_id: card.scryfall_id, quantity: 1 });
      setOffset(0);
      replaceQuery({ page: null }, false);
      await Promise.all([loadCollection(), loadCards()]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add card");
    }
  }

  function selectType(next: string | null) {
    setOffset(0);
    setTypeFilter(next);
    replaceQuery({ type: next });
  }

  function applyPriceFilter() {
    const nextMin = parseEurInput(minPriceDraft);
    const nextMax = parseEurInput(maxPriceDraft);
    if (nextMin === "invalid" || nextMax === "invalid") {
      setError("Enter positive numbers or leave blank to clear.");
      return;
    }
    if (nextMin != null && nextMax != null && nextMin > nextMax) {
      setError("Minimum price must not exceed the maximum.");
      return;
    }
    setError(null);
    setOffset(0);
    setMinPriceCents(nextMin);
    setMaxPriceCents(nextMax);
    replaceQuery({
      min_price: nextMin == null ? null : minPriceDraft.trim(),
      max_price: nextMax == null ? null : maxPriceDraft.trim(),
    });
  }

  function clearFilters() {
    setOffset(0);
    setTypeFilter(null);
    setMinPriceCents(null);
    setMaxPriceCents(null);
    setMinPriceDraft("");
    setMaxPriceDraft("");
    replaceQuery({ type: null, min_price: null, max_price: null });
  }

  function handleSortChange(value: string) {
    const [nextSort, nextDirection] = value.split(":");
    const resolvedSort = validSort(nextSort ?? null);
    const resolvedDirection = validDirection(nextDirection ?? null);
    setSort(resolvedSort);
    setDirection(resolvedDirection);
    setOffset(0);
    replaceQuery({
      sort: resolvedSort === "name" ? null : resolvedSort,
      direction: resolvedDirection === "asc" ? null : resolvedDirection,
    });
  }

  function handleGroupChange(next: CollectionGroup) {
    setGroup(next);
    setOffset(0);
    replaceQuery({ group: next === "none" ? null : next });
  }

  function goToPage(page: number) {
    const nextPage = Math.max(1, page);
    setOffset((nextPage - 1) * PAGE_SIZE);
    replaceQuery({ page: nextPage === 1 ? null : String(nextPage) }, false);
  }

  const filtersActive = typeFilter !== null || minPriceCents != null || maxPriceCents != null;

  async function handleRename() {
    if (!renameValue.trim() || renameValue.trim() === collection?.name) {
      setRenaming(false);
      return;
    }
    try {
      const updated = await apiClient.renameCollection(id, { name: renameValue.trim() });
      setCollection(updated);
      setRenaming(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_COLLECTION") {
        setError("You already have a collection with that name.");
      } else {
        setError(err instanceof Error ? err.message : "Rename failed");
      }
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const csv = await apiClient.exportCollectionCsv(id);
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${collection?.name ?? "collection"}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function refresh() {
    await Promise.all([loadCollection(), loadCards()]);
  }

  async function handleSetQuantity(card: CollectionCardItem, quantity: number) {
    if (quantity < 1) {
      await handleRemove(card);
      return;
    }
    setBusyCardId(card.card_id);
    try {
      await apiClient.updateCollectionCard(id, card.card_id, { quantity });
      await refresh();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Update failed", "error");
    } finally {
      setBusyCardId(null);
    }
  }

  async function handleRemove(card: CollectionCardItem) {
    if (!window.confirm(`Remove ${card.name} from this collection?`)) return;
    setBusyCardId(card.card_id);
    try {
      await apiClient.removeCollectionCard(id, card.card_id);
      await refresh();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Remove failed", "error");
    } finally {
      setBusyCardId(null);
    }
  }

  async function handlePlanForDeck(card: CollectionCardItem, deckId: string) {
    if (!deckId) return;
    setBusyCardId(card.card_id);
    try {
      await apiClient.planCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        direction: "addition",
        quantity: 1,
      });
      toast.push(`Planned ${card.name}`, "success");
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Planning failed", "error");
    } finally {
      setBusyCardId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const cardGroups = groupCards(cards, group);
  const workspaceFiltered = filtersActive || searchQuery.length > 0;

  return (
    <div>
      <Link
        href="/collections"
        className="mb-4 inline-block text-sm text-gray-500 transition-colors hover:text-gray-300"
      >
        ← Collections
      </Link>

      <header className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 flex-1">
          {renaming ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                value={renameValue}
                name="collection-name"
                autoComplete="off"
                aria-label="Collection name"
                onChange={(e) => setRenameValue(e.target.value)}
                autoFocus
                className="rounded-lg border border-white/20 bg-white/5 px-3 py-1.5 text-2xl font-bold text-white focus-visible:border-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50 sm:text-3xl"
              />
              <button
                onClick={() => void handleRename()}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500"
              >
                Save
              </button>
              <button
                onClick={() => setRenaming(false)}
                className="text-sm text-gray-400 hover:text-white"
              >
                Cancel
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="truncate text-2xl font-bold leading-tight text-white sm:text-3xl">
                {collection?.name ?? "…"}
              </h1>
              {collection && (
                <button
                  onClick={() => {
                    setRenameValue(collection.name);
                    setRenaming(true);
                  }}
                  className="text-sm text-gray-500 transition-colors hover:text-white"
                  aria-label="Rename collection"
                >
                  ✎
                </button>
              )}
            </div>
          )}
          <p className="mt-1 text-sm text-gray-400">
            {total} card{total !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/collections/${id}/import`}
            className="rounded-lg border border-indigo-500/60 px-4 py-2 text-sm font-medium text-indigo-400 transition-colors hover:bg-indigo-600/10"
          >
            Import CSV
          </Link>
          <button
            onClick={() => void handleExport()}
            disabled={exporting || total === 0}
            className="rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-white/10 disabled:opacity-50"
          >
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </header>

      {error && (
        <p className="mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </p>
      )}

      <section className="mb-6 rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-300">Add card</h2>
        <CardSearch placeholder="Search by name…" onSelect={(c) => void handleAdd(c)} />
      </section>

      <details
        open={filtersOpen}
        onToggle={(e) => setFiltersOpen((e.target as HTMLDetailsElement).open)}
        className="mb-6 rounded-xl border border-white/10 bg-white/5"
      >
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white hover:bg-white/5 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <span>Filters</span>
            {filtersActive && (
              <span className="rounded-full bg-indigo-600/40 px-2 py-0.5 text-xs text-indigo-200">
                active
              </span>
            )}
          </span>
          <span className="text-xs text-gray-400">{filtersOpen ? "▲" : "▼"}</span>
        </summary>
        <div className="border-t border-white/10 px-4 py-3">
          <div className="mb-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">Type</p>
            <div className="flex flex-wrap gap-1.5">
              {TYPE_OPTIONS.map((t) => {
                const active = typeFilter === t;
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => selectType(active ? null : t)}
                    className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                      active
                        ? "border-indigo-500 bg-indigo-600/40 text-indigo-100"
                        : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    {t}
                  </button>
                );
              })}
              {typeFilter && (
                <button
                  type="button"
                  onClick={() => selectType(null)}
                  className="rounded-full px-2.5 py-0.5 text-xs text-gray-500 hover:text-white"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
              Price (EUR)
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1 text-xs text-gray-400">
                Min €
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={minPriceDraft}
                  name="minimum-price"
                  autoComplete="off"
                  onChange={(e) => setMinPriceDraft(e.target.value)}
                  placeholder="0.00"
                  className="w-24 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus-visible:border-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-gray-400">
                Max €
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={maxPriceDraft}
                  name="maximum-price"
                  autoComplete="off"
                  onChange={(e) => setMaxPriceDraft(e.target.value)}
                  placeholder="blank = no cap"
                  className="w-32 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus-visible:border-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50"
                />
              </label>
              <button
                type="button"
                onClick={applyPriceFilter}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
              >
                Apply
              </button>
              {filtersActive && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="text-xs text-gray-400 hover:text-white transition-colors"
                >
                  Clear all
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Filters by Scryfall EUR price. Cards without an EUR price are excluded when a price
              bound is set.
            </p>
          </div>
        </div>
      </details>

      <div className="mb-5">
        <CardWorkspaceToolbar
          view={view}
          onViewChange={handleViewChange}
          resultCount={cards.length}
          totalCount={total}
        >
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="search"
              name="collection-card-search"
              autoComplete="off"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              aria-label="Search cards in this collection"
              placeholder="Search collection…"
              className="min-h-11 min-w-[180px] flex-1 rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-white placeholder-gray-500 focus-visible:border-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50"
            />
            <select
              value={`${sort}:${direction}`}
              name="collection-card-sort"
              aria-label="Sort collection cards"
              onChange={(event) => handleSortChange(event.target.value)}
              className="min-h-11 rounded-lg border border-white/10 bg-zinc-950 px-3 text-sm text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div
            role="group"
            aria-label="Group collection cards by"
            className="flex flex-wrap items-center gap-1"
          >
            {GROUP_OPTIONS.map((option) => {
              const active = group === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => handleGroupChange(option.value)}
                  className={`min-h-11 touch-manipulation rounded-lg px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                    active
                      ? "bg-indigo-500/20 text-indigo-200"
                      : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                  }`}
                >
                  Group: {option.label}
                </button>
              );
            })}
          </div>
        </CardWorkspaceToolbar>
      </div>

      {cards.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/20 py-16 text-center text-gray-500">
          {total === 0 && !workspaceFiltered
            ? "No cards yet. Add via search or import a CSV."
            : workspaceFiltered
              ? "No cards match the current filters."
              : "Loading…"}
        </div>
      ) : (
        <div className="space-y-6">
          {cardGroups.map((section) => (
            <section key={section.key} aria-label={section.label ?? "Collection cards"}>
              {section.label ? (
                <h2 className="mb-2 text-sm font-semibold text-gray-300">
                  {section.label}
                  <span className="ml-2 tabular-nums text-xs font-normal text-gray-500">
                    {section.cards.length}
                  </span>
                </h2>
              ) : null}
              {view === "grid" ? (
                <CollectionCardGrid
                  cards={section.cards}
                  decks={decks}
                  busy={busyCardId !== null}
                  onSetQuantity={handleSetQuantity}
                  onRemove={handleRemove}
                  onPlanForDeck={handlePlanForDeck}
                />
              ) : (
                <ul className="rounded-xl border border-white/10 bg-white/5">
                  {section.cards.map((card) => (
                    <CollectionCardRow
                      key={`${card.card_id}-${card.set_code}-${card.collector_number}-${card.foil}`}
                      card={card}
                      decks={decks}
                      busy={busyCardId === card.card_id}
                      onSetQuantity={handleSetQuantity}
                      onRemove={handleRemove}
                      onPlanForDeck={handlePlanForDeck}
                    />
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={offset === 0}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
