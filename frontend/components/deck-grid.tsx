"use client";

import { groupByPrimaryType, sortedPrimaryTypes } from "@/lib/card-types";
import { totalCardCount, type DeckCardItem } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onCardClick: (deckCardId: string) => void;
  comboCardIds?: Set<string>;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
}

function isBasicLand(card: DeckCardItem): boolean {
  return !!card.type_line?.includes("Basic Land");
}

/**
 * Moxfield-style visual deck view. Cards are grouped by primary type and
 * stacked vertically within each column, overlapping so only the title strip
 * of every card behind the top one is visible. Hover keeps the existing
 * floating popover; click opens a detail modal at the page level.
 */
export function DeckGrid({ cards, onCardClick, comboCardIds, onSetQuantity }: Props) {
  const groups = groupByPrimaryType(cards);
  const types = sortedPrimaryTypes(groups);

  if (cards.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
      {types.map((type) => (
        <DeckGridColumn
          key={type}
          type={type}
          cards={groups[type] ?? []}
          onCardClick={onCardClick}
          comboCardIds={comboCardIds}
          onSetQuantity={onSetQuantity}
        />
      ))}
    </div>
  );
}

interface ColumnProps {
  type: string;
  cards: DeckCardItem[];
  onCardClick: (deckCardId: string) => void;
  comboCardIds?: Set<string> | undefined;
  onSetQuantity?: ((scryfallId: string, quantity: number) => void | Promise<void>) | undefined;
}

function DeckGridColumn({ type, cards, onCardClick, comboCardIds, onSetQuantity }: ColumnProps) {
  return (
    <section className="flex flex-col">
      <header className="mb-2 flex items-baseline justify-between px-1">
        <h3 className="text-sm font-semibold text-white">{type}</h3>
        <span className="text-xs text-gray-500">{totalCardCount(cards)}</span>
      </header>
      <ul className="flex flex-col">
        {cards.map((card, idx) => (
          <li
            key={card.deck_card_id}
            style={idx === 0 ? undefined : { marginTop: "-78%" }}
            className="relative"
          >
            <button
              type="button"
              onClick={() => onCardClick(card.deck_card_id)}
              title={card.name}
              className="block w-full overflow-hidden rounded-[4.5%] focus:outline-none focus:ring-2 focus:ring-indigo-400"
              aria-label={`Open ${card.name}`}
            >
              {card.image_uri ? (
                <img
                  src={card.image_uri}
                  alt={card.name}
                  className="block w-full rounded-[4.5%] shadow-md"
                />
              ) : (
                <span className="flex aspect-[5/7] w-full items-center justify-center rounded-[4.5%] border border-white/10 bg-white/5 px-2 text-center text-xs text-gray-400">
                  {card.name}
                </span>
              )}
              {card.quantity > 1 ? (
                <span className="absolute right-1.5 top-1.5 rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium text-white backdrop-blur">
                  ×{card.quantity}
                </span>
              ) : null}
              {card.price_eur_cents != null ? (
                <span className="absolute bottom-1.5 right-1.5 rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium text-emerald-300 backdrop-blur tabular-nums">
                  €{(card.price_eur_cents / 100).toFixed(2)}
                </span>
              ) : null}
              {comboCardIds?.has(card.scryfall_id) ? (
                <span
                  className="absolute left-1.5 top-1.5 rounded-full bg-black/70 px-2 py-0.5 text-sm text-yellow-300 backdrop-blur"
                  title="Part of an active or near-complete combo"
                >
                  ⚡
                </span>
              ) : null}
            </button>
            {isBasicLand(card) && onSetQuantity ? (
              <div
                className="absolute bottom-1.5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-full bg-black/80 px-1.5 py-0.5 backdrop-blur"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => void onSetQuantity(card.scryfall_id, card.quantity - 1)}
                  aria-label="Decrease quantity"
                  className="h-5 w-5 rounded text-sm text-gray-200 hover:text-white"
                >
                  −
                </button>
                <span className="min-w-[1.5rem] text-center text-xs tabular-nums text-white">
                  {card.quantity}
                </span>
                <button
                  type="button"
                  onClick={() => void onSetQuantity(card.scryfall_id, card.quantity + 1)}
                  aria-label="Increase quantity"
                  className="h-5 w-5 rounded text-sm text-gray-200 hover:text-white"
                >
                  +
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
