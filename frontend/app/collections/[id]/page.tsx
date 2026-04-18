"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import { CardSearch } from "@/components/card-search";
import { CollectionCardRow } from "@/components/collection-card-row";
import type { CardResponse, CollectionCardItem, CollectionResponse } from "@/lib/types";

const PAGE_SIZE = 50;

export default function CollectionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [collection, setCollection] = useState<CollectionResponse | null>(null);
  const [cards, setCards] = useState<CollectionCardItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

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
      const result = await apiClient.listCollectionCards(id, { limit: PAGE_SIZE, offset });
      setCards(result.data);
      setTotal(result.meta.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load cards");
    }
  }, [id, offset]);

  useEffect(() => {
    void loadCollection();
  }, [loadCollection]);

  useEffect(() => {
    void loadCards();
  }, [loadCards]);

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
      <div className="mb-6 flex items-center gap-3">
        <Link
          href="/collections"
          className="text-gray-500 hover:text-gray-300 text-sm transition-colors"
        >
          ← Collections
        </Link>
      </div>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {renaming ? (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                autoFocus
                className="rounded-lg border border-white/20 bg-white/5 px-3 py-1.5 text-xl font-bold text-white focus:border-indigo-500 focus:outline-none"
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
              <h1 className="text-2xl font-bold text-white truncate">
                {collection?.name ?? "..."}
              </h1>
              {collection && (
                <button
                  onClick={() => {
                    setRenameValue(collection.name);
                    setRenaming(true);
                  }}
                  className="text-gray-500 hover:text-white text-sm"
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
        <div className="flex flex-shrink-0 gap-2">
          <Link
            href={`/collections/${id}/import`}
            className="rounded-lg border border-indigo-500/60 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-600/10 transition-colors"
          >
            Import CSV
          </Link>
          <button
            onClick={() => void handleExport()}
            disabled={exporting || total === 0}
            className="rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            {exporting ? "Exporting..." : "Export CSV"}
          </button>
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </p>
      )}

      <section className="mb-6 rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-300">Add card</h2>
        <CardSearch placeholder="Search by name..." onSelect={(c) => void handleAdd(c)} />
      </section>

      {cards.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/20 py-16 text-center text-gray-500">
          {total === 0 ? "No cards yet. Add via search or import a CSV." : "Loading..."}
        </div>
      ) : (
        <ul className="rounded-xl border border-white/10 bg-white/5">
          {cards.map((card) => (
            <CollectionCardRow
              key={`${card.card_id}-${card.set_code}-${card.collector_number}-${card.foil}`}
              collectionId={id}
              card={card}
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
