"use client";

import { useState } from "react";
import { CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  category: string;
  cards: DeckCardItem[];
  onRemove?: (scryfallId: string) => void;
  onSetCategories?: (scryfallId: string, categories: string[]) => void | Promise<void>;
  petCardNames?: Set<string>;
}

// Bangers is a retrieval-only stage; users shouldn't tag cards into it manually.
const CATEGORY_OPTIONS = CATEGORY_ORDER.filter((c) => c !== "bangers");

export function DeckCategoryGroup({
  category,
  cards,
  onRemove,
  onSetCategories,
  petCardNames,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const [openCard, setOpenCard] = useState<string | null>(null);

  function toggleCategory(card: DeckCardItem, cat: string) {
    if (!onSetCategories) return;
    const has = card.categories.includes(cat);
    const next = has ? card.categories.filter((c) => c !== cat) : [...card.categories, cat];
    void onSetCategories(card.scryfall_id, next);
  }

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

                    {onSetCategories && (
                      <div>
                        <p className="mb-1.5 text-xs uppercase tracking-wide text-gray-500">
                          Categories
                          <span className="ml-2 normal-case tracking-normal text-gray-600">
                            (dotted = auto from card text)
                          </span>
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {CATEGORY_OPTIONS.map((opt) => {
                            const active = card.categories.includes(opt);
                            const auto = !active && card.qualifying_stages.includes(opt);
                            const cls = active
                              ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                              : auto
                                ? "border-dashed border-gray-600 bg-white/5 text-gray-400 hover:border-gray-400"
                                : "border-white/10 bg-white/5 text-gray-500 hover:border-white/20 hover:text-gray-300";
                            return (
                              <button
                                key={opt}
                                onClick={() => toggleCategory(card, opt)}
                                className={`rounded border px-2 py-0.5 text-xs transition-colors ${cls}`}
                                title={auto ? "Auto-tagged from card text — click to make explicit" : undefined}
                              >
                                {STAGE_LABELS[opt] ?? opt}
                                {auto && <span className="ml-1 text-[10px] text-gray-500">auto</span>}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {onRemove && (
                      <div className="flex">
                        <button
                          onClick={() => onRemove(card.scryfall_id)}
                          className="ml-auto rounded border border-red-500/40 px-2 py-1 text-xs text-red-400 hover:border-red-500/70 hover:text-red-300 transition-colors"
                          aria-label={`Remove ${card.name}`}
                        >
                          Remove
                        </button>
                      </div>
                    )}
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
