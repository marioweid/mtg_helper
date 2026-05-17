"use client";

import { useState } from "react";

import { CardHover } from "@/components/card-hover";
import type { CommanderCardSummary } from "@/lib/types";

interface Props {
  commander: CommanderCardSummary | null;
  partner: CommanderCardSummary | null;
}

/**
 * Collapsible "Commander" group rendered above the regular deck category
 * groups. Mirrors ``DeckCategoryGroup``'s chrome so it reads as part of the
 * same list. Each row expands to show the full card image + oracle text.
 */
export function CommanderSection({ commander, partner }: Props) {
  const [expanded, setExpanded] = useState(true);
  const cards = [commander, partner].filter(
    (c): c is CommanderCardSummary => c !== null,
  );
  if (cards.length === 0) return null;

  return (
    <div className="rounded-xl border border-white/10 bg-white/5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-white/5"
      >
        <h3 className="font-medium capitalize text-white">Commander</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{cards.length}</span>
          <span className="text-xs text-gray-500">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <ul className="divide-y divide-white/5 border-t border-white/10">
          {cards.map((card) => (
            <CommanderRow key={card.id} card={card} />
          ))}
        </ul>
      )}
    </div>
  );
}

function CommanderRow({ card }: { card: CommanderCardSummary }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="relative transition-colors hover:bg-white/5">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-2 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">
            <CardHover name={card.name} imageUri={card.image_uri}>
              {card.name}
            </CardHover>
          </p>
          {card.type_line ? (
            <p className="truncate text-xs text-gray-500">{card.type_line}</p>
          ) : null}
        </div>
        {card.mana_cost ? (
          <span className="flex-shrink-0 text-xs text-gray-500">{card.mana_cost}</span>
        ) : null}
        <span className="flex-shrink-0 text-xs text-gray-600">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-3 border-t border-white/5 bg-black/20 px-4 py-3 sm:flex-row">
          {card.image_uri ? (
            <img
              src={card.image_uri}
              alt={card.name}
              className="h-auto w-full max-w-[220px] flex-shrink-0 rounded-[4.5%] shadow-lg"
            />
          ) : null}
          <div className="flex flex-col gap-2">
            {card.oracle_text ? (
              <p className="whitespace-pre-line text-xs leading-relaxed text-gray-200">
                {card.oracle_text}
              </p>
            ) : (
              <p className="text-xs italic text-gray-500">No oracle text.</p>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
