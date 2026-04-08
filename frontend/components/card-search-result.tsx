"use client";

import type { CardResponse } from "@/lib/types";

interface Props {
  card: CardResponse;
  onAdd: () => void;
  added: boolean;
}

export function CardSearchResult({ card, onAdd, added }: Props) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 p-2">
      {card.image_uri && (
        <img
          src={card.image_uri}
          alt={card.name}
          className="h-12 w-9 flex-shrink-0 rounded object-cover object-top"
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <p className="truncate text-sm font-medium text-white">{card.name}</p>
        {card.mana_cost && <p className="text-xs text-gray-500">{card.mana_cost}</p>}
        {card.type_line && <p className="truncate text-xs text-gray-400">{card.type_line}</p>}
      </div>
      <button
        onClick={onAdd}
        disabled={added}
        className={`flex-shrink-0 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
          added
            ? "cursor-default bg-green-900/30 text-green-400"
            : "bg-indigo-600 text-white hover:bg-indigo-500"
        }`}
      >
        {added ? "Added" : "Add"}
      </button>
    </div>
  );
}
