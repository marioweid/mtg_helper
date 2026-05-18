"use client";

import { useState } from "react";
import { CardDetailPanel } from "@/components/card-detail-panel";
import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, totalCardCount, type DeckCardItem } from "@/lib/types";

interface Props {
  category: string;
  cards: DeckCardItem[];
  onRemove?: (scryfallId: string) => void;
  onSetCategories?: (scryfallId: string, categories: string[]) => void | Promise<void>;
  petCardNames?: Set<string>;
  comboCardIds?: Set<string>;
}

export function DeckCategoryGroup({
  category,
  cards,
  onRemove,
  onSetCategories,
  petCardNames,
  comboCardIds,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const [openCard, setOpenCard] = useState<string | null>(null);

  return (
    <div className="rounded-xl border border-white/10 bg-white/5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors"
      >
        <h3 className="font-medium text-white capitalize">{category}</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{totalCardCount(cards)}</span>
          <span className="text-gray-500 text-xs">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <ul className="divide-y divide-white/5 border-t border-white/10">
          {cards.map((card) => {
            const isOpen = openCard === card.deck_card_id;
            const tags = bucketsFor(card).filter((t) => t !== "untagged");
            return (
              <li
                key={card.deck_card_id}
                className="relative hover:bg-white/5 transition-colors"
              >
                <button
                  onClick={() => setOpenCard(isOpen ? null : card.deck_card_id)}
                  className="flex w-full items-center gap-3 px-4 py-2 text-left"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate flex items-center gap-1.5">
                      <CardHover name={card.name} imageUri={card.image_uri}>
                        {card.name}
                      </CardHover>
                      {petCardNames?.has(card.name) && (
                        <span className="text-red-400 flex-shrink-0" title="Pet card">♥</span>
                      )}
                      {comboCardIds?.has(card.scryfall_id) && (
                        <span
                          className="flex-shrink-0 text-yellow-300"
                          title="Part of an active or near-complete combo in this deck"
                        >
                          ⚡
                        </span>
                      )}
                    </p>
                    {tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {tags.map((t) => (
                          <span
                            key={t}
                            className="rounded bg-indigo-900/40 px-1.5 py-0.5 text-[10px] text-indigo-300 capitalize"
                          >
                            {STAGE_LABELS[t] ?? t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {card.mana_cost && (
                    <span className="flex-shrink-0 text-xs text-gray-500">
                      <ManaCost cost={card.mana_cost} />
                    </span>
                  )}
                  <span className="w-16 text-right text-xs text-gray-300 flex-shrink-0 tabular-nums">
                    {card.price_eur_cents != null
                      ? `€${(card.price_eur_cents / 100).toFixed(2)}`
                      : "—"}
                  </span>
                  <span className="text-gray-600 text-xs flex-shrink-0">{isOpen ? "▴" : "▾"}</span>
                </button>

                {isOpen && (
                  <div className="border-t border-white/5 bg-black/20 px-4 py-3">
                    <CardDetailPanel
                      card={card}
                      onRemove={onRemove}
                      onSetCategories={onSetCategories}
                    />
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
