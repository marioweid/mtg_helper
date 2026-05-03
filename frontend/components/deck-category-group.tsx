"use client";

import { useState } from "react";
import { CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  category: string;
  cards: DeckCardItem[];
  onRemove?: (scryfallId: string) => void;
  onMove?: (scryfallId: string, category: string) => void | Promise<void>;
  petCardNames?: Set<string>;
}

const CATEGORY_OPTIONS = CATEGORY_ORDER;

export function DeckCategoryGroup({ category, cards, onRemove, onMove, petCardNames }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [openCard, setOpenCard] = useState<string | null>(null);

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
          {cards.map((card) => {
            const isOpen = openCard === card.deck_card_id;
            return (
              <li key={card.deck_card_id} className="hover:bg-white/5 transition-colors">
                <button
                  onClick={() => setOpenCard(isOpen ? null : card.deck_card_id)}
                  className="flex w-full items-center gap-3 px-4 py-2 text-left"
                >
                  {card.image_uri && (
                    <img
                      src={card.image_uri}
                      alt={card.name}
                      className="h-10 w-7 rounded object-cover flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate flex items-center gap-1.5">
                      {card.name}
                      {petCardNames?.has(card.name) && (
                        <span className="text-red-400 flex-shrink-0" title="Pet card">♥</span>
                      )}
                    </p>
                    <p className="text-xs text-gray-500 truncate">{card.type_line}</p>
                  </div>
                  {card.mana_cost && (
                    <span className="text-xs text-gray-500 flex-shrink-0">{card.mana_cost}</span>
                  )}
                  <span className="text-gray-600 text-xs flex-shrink-0">{isOpen ? "▴" : "▾"}</span>
                </button>

                {isOpen && (
                  <div className="flex flex-col gap-3 border-t border-white/5 bg-black/20 px-4 py-3">
                    {card.oracle_text && (
                      <p className="text-xs text-gray-300 whitespace-pre-line leading-relaxed">
                        {card.oracle_text}
                      </p>
                    )}
                    {!card.oracle_text && (
                      <p className="text-xs text-gray-600 italic">No oracle text.</p>
                    )}

                    <div className="flex flex-wrap items-center gap-2">
                      {onMove && (
                        <label className="flex items-center gap-2 text-xs text-gray-400">
                          <span>Move to:</span>
                          <select
                            value={card.category ?? ""}
                            onChange={(e) => void onMove(card.scryfall_id, e.target.value)}
                            className="rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-white focus:border-indigo-500 focus:outline-none"
                          >
                            {CATEGORY_OPTIONS.map((opt) => (
                              <option key={opt} value={opt} className="bg-gray-900">
                                {STAGE_LABELS[opt] ?? opt}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      {onRemove && (
                        <button
                          onClick={() => onRemove(card.scryfall_id)}
                          className="ml-auto rounded border border-red-500/40 px-2 py-1 text-xs text-red-400 hover:border-red-500/70 hover:text-red-300 transition-colors"
                          aria-label={`Remove ${card.name}`}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
