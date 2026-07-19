"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import { CardSearch } from "@/components/card-search";
import { CollectionCardRow } from "@/components/collection-card-row";
import type {
  CardResponse,
  CollectionCardItem,
  CollectionResponse,
  DeckSummary,
} from "@/lib/types";

const PAGE_SIZE = 50;

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

export default function CollectionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [collection, setCollection] = useState<CollectionResponse | null>(null);
  const [cards, setCards] = useState<CollectionCardItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [minPriceCents, setMinPriceCents] = useState<number | null>(null);
  const [maxPriceCents, setMaxPriceCents] = useState<number | null>(null);
  const [minPriceDraft, setMinPriceDraft] = useState("");
  const [maxPriceDraft, setMaxPriceDraft] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [decks, setDecks] = useState<DeckSummary[]>([]);

  const loadCollection = useCallback(async () => {
    try {
      const c = await apiClient.getCollection(id);
      setCollection(c);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collection");
    }
  }, [id]);

  const loadCards = useCallback(async () => {
    try {
      const result = await apiClient.listCollectionCards(id, {
        limit: PAGE_SIZE,
        offset,
        type: typeFilter,
        min_price_cents: minPriceCents,
        max_price_cents: maxPriceCents,
      });
      setCards(result.data);
      setTotal(result.meta.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load cards");
    }
  }, [id, offset, typeFilter, minPriceCents, maxPriceCents]);

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

  async function handleAdd(card: CardResponse) {
    setError(null);
    try {
      await apiClient.addCollectionCard(id, { scryfall_id: card.scryfall_id, quantity: 1 });
      setOffset(0);
      await Promise.all([loadCollection(), loadCards()]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add card");
    }
  }

  function selectType(next: string | null) {
    setOffset(0);
    setTypeFilter(next);
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
  }

  function clearFilters() {
    setOffset(0);
    setTypeFilter(null);
    setMinPriceCents(null);
    setMaxPriceCents(null);
    setMinPriceDraft("");
    setMaxPriceDraft("");
  }

  const filtersActive =
    typeFilter !== null || minPriceCents != null || maxPriceCents != null;

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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

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
                onChange={(e) => setRenameValue(e.target.value)}
                autoFocus
                className="rounded-lg border border-white/20 bg-white/5 px-3 py-1.5 text-2xl font-bold text-white focus:border-indigo-500 focus:outline-none sm:text-3xl"
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
        <CardSearch placeholder="Search by name..." onSelect={(c) => void handleAdd(c)} />
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
                  min="0"
                  step="0.01"
                  value={minPriceDraft}
                  onChange={(e) => setMinPriceDraft(e.target.value)}
                  placeholder="0.00"
                  className="w-24 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-gray-400">
                Max €
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={maxPriceDraft}
                  onChange={(e) => setMaxPriceDraft(e.target.value)}
                  placeholder="blank = no cap"
                  className="w-32 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
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

      {cards.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/20 py-16 text-center text-gray-500">
          {total === 0 && !filtersActive
            ? "No cards yet. Add via search or import a CSV."
            : filtersActive
              ? "No cards match the current filters."
              : "Loading..."}
        </div>
      ) : (
        <ul className="rounded-xl border border-white/10 bg-white/5">
          {cards.map((card) => (
            <CollectionCardRow
              key={`${card.card_id}-${card.set_code}-${card.collector_number}-${card.foil}`}
              collectionId={id}
              card={card}
              decks={decks}
              onChanged={() => void refresh()}
            />
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <button
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
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
