"use client";

import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { CollectionResponse } from "@/lib/types";

interface Props {
  open: boolean;
  deckId: string;
  collections: CollectionResponse[];
  onClose: () => void;
}

export function PlannedBuyListDialog({ open, deckId, collections, onClose }: Props) {
  const toast = useToast();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelectedIds(new Set(collections.map((collection) => collection.id)));
    setError(null);
  }, [collections, open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !copying) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [copying, onClose, open]);

  if (!open) return null;

  async function copyBuyList() {
    setCopying(true);
    setError(null);
    try {
      const text = await apiClient.exportPlannedShoppingList(deckId, {
        collection_ids: [...selectedIds],
      });
      if (text.trim()) {
        await navigator.clipboard.writeText(text);
        toast.push("Shopping list copied.", "success");
      } else {
        toast.push("You already own all planned additions.", "success");
      }
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not copy the planned buy list");
    } finally {
      setCopying(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !copying) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="planned-buy-list-title"
        className="w-full max-w-md rounded-xl border border-white/15 bg-zinc-950 p-5 shadow-2xl"
      >
        <h2 id="planned-buy-list-title" className="text-base font-semibold text-white">
          Count cards from these binders
        </h2>
        <p className="mt-1 text-xs text-gray-400">
          Uncheck collections you do not want to use, such as proxy binders.
        </p>
        <BinderSelection
          collections={collections}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
        />
        {error && (
          <p className="mt-2 rounded border border-red-500/30 bg-red-950/30 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}
        <DialogActions copying={copying} onClose={onClose} onCopy={copyBuyList} />
      </section>
    </div>
  );
}

interface SelectionProps {
  collections: CollectionResponse[];
  selectedIds: Set<string>;
  onChange: (ids: Set<string>) => void;
}

function BinderSelection({ collections, selectedIds, onChange }: SelectionProps) {
  function toggle(collectionId: string) {
    const next = new Set(selectedIds);
    if (next.has(collectionId)) next.delete(collectionId);
    else next.add(collectionId);
    onChange(next);
  }

  return (
    <>
      <div className="mt-4 flex items-center justify-between border-b border-white/10 pb-2">
        <span className="text-xs text-gray-500">
          {selectedIds.size} of {collections.length} selected
        </span>
        <div className="flex gap-3 text-xs">
          <button
            type="button"
            onClick={() => onChange(new Set(collections.map((item) => item.id)))}
            className="text-indigo-300 hover:text-indigo-200"
          >
            Select all
          </button>
          <button
            type="button"
            onClick={() => onChange(new Set())}
            className="text-gray-400 hover:text-white"
          >
            Select none
          </button>
        </div>
      </div>
      <div className="max-h-64 overflow-y-auto py-2">
        {collections.length === 0 ? (
          <p className="py-4 text-sm text-gray-400">
            No binders available. The full planned quantity will be included.
          </p>
        ) : (
          collections.map((collection) => (
            <label
              key={collection.id}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/5"
            >
              <input
                type="checkbox"
                checked={selectedIds.has(collection.id)}
                onChange={() => toggle(collection.id)}
                className="h-4 w-4 accent-indigo-500"
              />
              <span className="min-w-0 flex-1 truncate text-sm text-gray-200">
                {collection.name}
              </span>
              <span className="text-xs tabular-nums text-gray-500">
                {collection.card_count} cards
              </span>
            </label>
          ))
        )}
      </div>
    </>
  );
}

interface ActionProps {
  copying: boolean;
  onClose: () => void;
  onCopy: () => Promise<void>;
}

function DialogActions({ copying, onClose, onCopy }: ActionProps) {
  return (
    <div className="mt-4 flex justify-end gap-2">
      <button
        type="button"
        disabled={copying}
        onClick={onClose}
        className="rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-300 hover:text-white disabled:opacity-40"
      >
        Cancel
      </button>
      <button
        type="button"
        disabled={copying}
        onClick={() => void onCopy()}
        className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
      >
        {copying ? "Creating…" : "Copy buy list"}
      </button>
    </div>
  );
}
