"use client";

import { useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import type { CollectionCardItem } from "@/lib/types";

interface Props {
  collectionId: string;
  card: CollectionCardItem;
  onChanged: () => void;
}

export function CollectionCardRow({ collectionId, card, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setQuantity(next: number) {
    if (next < 1) {
      await remove();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.updateCollectionCard(collectionId, card.card_id, { quantity: next });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.removeCollectionCard(collectionId, card.card_id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Remove failed");
      setBusy(false);
    }
  }

  return (
    <li className="flex items-center gap-3 px-4 py-2 border-b border-white/5 last:border-b-0 hover:bg-white/5">
      {card.image_uri ? (
        <img
          src={card.image_uri}
          alt={card.name}
          className="h-14 w-10 rounded object-cover flex-shrink-0"
        />
      ) : (
        <div className="h-14 w-10 rounded bg-gray-800 flex-shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white truncate">{card.name}</p>
        <p className="text-xs text-gray-500 truncate">
          {card.type_line ?? ""}
          {card.set_code && (
            <span className="ml-2 text-gray-600">
              {card.set_code.toUpperCase()} {card.collector_number}
            </span>
          )}
        </p>
        {card.tags.length > 0 && (
          <p className="text-xs text-indigo-400/80 truncate">{card.tags.join(", ")}</p>
        )}
      </div>
      {card.foil && (
        <span className="rounded bg-yellow-900/40 px-2 py-0.5 text-xs text-yellow-300">Foil</span>
      )}
      {card.condition && <span className="text-xs text-gray-500">{card.condition}</span>}
      <div className="flex items-center gap-1">
        <button
          onClick={() => void setQuantity(card.quantity - 1)}
          disabled={busy}
          className="rounded border border-white/10 bg-white/5 px-2 py-1 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-40"
          aria-label="Decrease quantity"
        >
          −
        </button>
        <span className="w-8 text-center text-sm text-white tabular-nums">{card.quantity}</span>
        <button
          onClick={() => void setQuantity(card.quantity + 1)}
          disabled={busy}
          className="rounded border border-white/10 bg-white/5 px-2 py-1 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-40"
          aria-label="Increase quantity"
        >
          +
        </button>
      </div>
      <button
        onClick={() => void remove()}
        disabled={busy}
        className="text-gray-500 hover:text-red-400 transition-colors text-lg leading-none px-2 disabled:opacity-40"
        aria-label="Remove card"
      >
        ×
      </button>
      {error && <span className="ml-2 text-xs text-red-400">{error}</span>}
    </li>
  );
}
