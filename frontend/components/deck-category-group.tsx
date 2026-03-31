"use client";

import { useState } from "react";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  category: string;
  cards: DeckCardItem[];
  onRemove?: (scryfallId: string) => void;
}

export function DeckCategoryGroup({ category, cards, onRemove }: Props) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors"
      >
        <h3 className="font-medium text-white capitalize">{category}</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{cards.length}</span>
          <span className="text-gray-500 text-xs">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <ul className="divide-y divide-white/5 border-t border-white/10">
          {cards.map((card) => (
            <li
              key={card.deck_card_id}
              className="flex items-center gap-3 px-4 py-2 hover:bg-white/5 transition-colors"
            >
              {card.image_uri && (
                <img
                  src={card.image_uri}
                  alt={card.name}
                  className="h-10 w-7 rounded object-cover flex-shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{card.name}</p>
                <p className="text-xs text-gray-500 truncate">{card.type_line}</p>
              </div>
              {card.mana_cost && (
                <span className="text-xs text-gray-500 flex-shrink-0">{card.mana_cost}</span>
              )}
              {onRemove && (
                <button
                  onClick={() => onRemove(card.scryfall_id)}
                  className="ml-2 text-gray-600 hover:text-red-400 transition-colors text-lg leading-none flex-shrink-0"
                  aria-label={`Remove ${card.name}`}
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
