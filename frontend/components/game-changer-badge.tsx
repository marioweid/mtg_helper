"use client";

import {
  findGameChangers,
  gameChangerLimit,
} from "@/lib/game-changers";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  cards: readonly DeckCardItem[];
  bracket: number | null | undefined;
  commanderName?: string | null;
  /** Compact = no leading label. Useful inside dense headers. */
  compact?: boolean;
}

/**
 * Pill showing ``N / limit`` Game Changers for the deck's bracket. Hovering
 * reveals the matching card names. Brackets 1/2 cap at 0, bracket 3 at 3,
 * bracket 4 is unlimited (shown as ``∞``).
 */
export function GameChangerBadge({ cards, bracket, commanderName, compact }: Props) {
  const matches = findGameChangers(cards, commanderName);
  const count = matches.length;
  const limit = gameChangerLimit(bracket);
  const overLimit = limit != null && count > limit;
  const display = limit == null ? `${count}/∞` : `${count}/${limit}`;

  const tone = overLimit
    ? "border-red-500/50 bg-red-900/30 text-red-200"
    : count > 0
      ? "border-amber-500/40 bg-amber-900/20 text-amber-200"
      : "border-white/15 bg-white/5 text-gray-300";

  return (
    <span className="group relative inline-flex">
      <span
        className={`inline-flex cursor-help items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium tabular-nums ${tone}`}
        aria-label={`${count} Game Changers${limit != null ? ` of ${limit} allowed` : ""}`}
      >
        {!compact && <span className="text-gray-400">GC</span>}
        <span>{display}</span>
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1 hidden w-56 -translate-x-1/2 rounded-md border border-white/10 bg-gray-900 px-3 py-2 text-xs text-gray-100 shadow-xl group-hover:block"
      >
        <span className="mb-1 block font-semibold text-white">
          Game Changers ({count}
          {limit != null ? ` / ${limit}` : ""})
        </span>
        {matches.length === 0 ? (
          <span className="text-gray-400">None in deck.</span>
        ) : (
          <ul className="space-y-0.5">
            {matches.map((name) => (
              <li key={name} className="truncate">
                {name}
              </li>
            ))}
          </ul>
        )}
      </span>
    </span>
  );
}
