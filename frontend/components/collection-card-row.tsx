"use client";

import { CardHover } from "@/components/card-hover";
import type { CollectionCardItem, DeckSummary } from "@/lib/types";

const EUR_FORMATTER = new Intl.NumberFormat("en-US", { style: "currency", currency: "EUR" });

export function formatCollectionPrice(value: string): string {
  const amount = Number.parseFloat(value);
  return Number.isFinite(amount) ? EUR_FORMATTER.format(amount) : value;
}

export interface CollectionCardActions {
  busy: boolean;
  onSetQuantity: (card: CollectionCardItem, quantity: number) => void | Promise<void>;
  onRemove: (card: CollectionCardItem) => void | Promise<void>;
  onPlanForDeck: (card: CollectionCardItem, deckId: string) => void | Promise<void>;
}

interface Props extends CollectionCardActions {
  card: CollectionCardItem;
  decks?: DeckSummary[];
}

export function CollectionCardRow({
  card,
  decks = [],
  busy,
  onSetQuantity,
  onRemove,
  onPlanForDeck,
}: Props) {
  return (
    <li className="flex flex-wrap items-center gap-3 border-b border-white/5 px-4 py-3 last:border-b-0 hover:bg-white/5">
      {card.image_uri ? (
        <img
          src={card.image_uri}
          alt={card.name}
          width={44}
          height={64}
          loading="lazy"
          className="h-16 w-11 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="h-16 w-11 shrink-0 rounded bg-gray-800" />
      )}
      <div className="min-w-[180px] flex-1">
        <p className="truncate text-sm font-medium text-white">
          <CardHover name={card.name} imageUri={card.image_uri}>{card.name}</CardHover>
        </p>
        <p className="truncate text-xs text-gray-500">
          {card.type_line ?? ""}
          {card.set_code ? (
            <span className="ml-2 text-gray-600">
              {card.set_code.toUpperCase()} {card.collector_number}
            </span>
          ) : null}
        </p>
        <CollectionMetadata card={card} />
      </div>
      <CollectionDeckSelect
        card={card}
        decks={decks}
        busy={busy}
        onPlanForDeck={onPlanForDeck}
      />
      <QuantityControls
        card={card}
        busy={busy}
        onSetQuantity={onSetQuantity}
        onRemove={onRemove}
      />
    </li>
  );
}

export function CollectionMetadata({ card }: { card: CollectionCardItem }) {
  return (
    <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
      {card.foil ? (
        <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-amber-200">Foil</span>
      ) : null}
      {card.condition ? (
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-gray-400">{card.condition}</span>
      ) : null}
      {card.purchase_price ? (
        <span className="rounded bg-emerald-900/30 px-1.5 py-0.5 text-emerald-300">
          {formatCollectionPrice(card.purchase_price)}
        </span>
      ) : null}
      {card.tags.map((tag) => (
        <span key={tag} className="rounded bg-indigo-900/40 px-1.5 py-0.5 text-indigo-200">
          {tag}
        </span>
      ))}
    </div>
  );
}

export function CollectionDeckSelect({
  card,
  decks,
  busy,
  onPlanForDeck,
}: Pick<Props, "card" | "decks" | "busy" | "onPlanForDeck">) {
  if (!decks || decks.length === 0) return null;
  return (
    <select
      value=""
      name={`plan-${card.card_id}`}
      disabled={busy}
      aria-label={`Plan ${card.name} for a deck`}
      onChange={(event) => void onPlanForDeck(card, event.target.value)}
      className="min-h-11 max-w-44 rounded-lg border border-indigo-500/30 bg-zinc-950 px-2 text-xs text-indigo-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
    >
      <option value="">Plan for deck…</option>
      {decks.map((deck) => (
        <option key={deck.id} value={deck.id}>{deck.name}</option>
      ))}
    </select>
  );
}

export function QuantityControls({
  card,
  busy,
  onSetQuantity,
  onRemove,
}: Pick<Props, "card" | "busy" | "onSetQuantity" | "onRemove">) {
  return (
    <div className="ml-auto flex items-center gap-1">
      <button
        type="button"
        onClick={() => void onSetQuantity(card, card.quantity - 1)}
        disabled={busy}
        className="min-h-11 min-w-11 touch-manipulation rounded-lg border border-white/10 bg-white/5 text-gray-300 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-40"
        aria-label={`Decrease ${card.name}`}
      >
        −
      </button>
      <span className="w-8 text-center text-sm tabular-nums text-white">{card.quantity}</span>
      <button
        type="button"
        onClick={() => void onSetQuantity(card, card.quantity + 1)}
        disabled={busy}
        className="min-h-11 min-w-11 touch-manipulation rounded-lg border border-white/10 bg-white/5 text-gray-300 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-40"
        aria-label={`Increase ${card.name}`}
      >
        +
      </button>
      <button
        type="button"
        onClick={() => void onRemove(card)}
        disabled={busy}
        className="min-h-11 touch-manipulation rounded-lg px-2 text-xs text-gray-500 hover:bg-red-500/10 hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-40"
        aria-label={`Remove ${card.name}`}
      >
        Remove
      </button>
    </div>
  );
}
