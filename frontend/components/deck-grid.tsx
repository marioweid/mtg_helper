"use client";

import { CardHover } from "@/components/card-hover";
import { groupByPrimaryType, sortedPrimaryTypes } from "@/lib/card-types";
import { totalCardCount, type DeckCardItem } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onCardClick: (deckCardId: string) => void;
}

/**
 * Moxfield-style visual deck view. Cards are grouped by primary type and
 * stacked vertically within each column, overlapping so only the title strip
 * of every card behind the top one is visible. Hover keeps the existing
 * floating popover; click opens a detail modal at the page level.
 */
export function DeckGrid({ cards, onCardClick }: Props) {
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
        />
      ))}
    </div>
  );
}

interface ColumnProps {
  type: string;
  cards: DeckCardItem[];
  onCardClick: (deckCardId: string) => void;
}

function DeckGridColumn({ type, cards, onCardClick }: ColumnProps) {
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
            className="relative transition-transform hover:z-10 hover:-translate-y-1"
          >
            <CardHover name={card.name} imageUri={card.image_uri}>
              <button
                type="button"
                onClick={() => onCardClick(card.deck_card_id)}
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
              </button>
            </CardHover>
          </li>
        ))}
      </ul>
    </section>
  );
}
