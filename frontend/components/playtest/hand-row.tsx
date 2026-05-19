import type { PlaytestCard } from "@/lib/playtest";

interface Props {
  hand: PlaytestCard[];
  castable: Set<string>;
  canPlayLand: boolean;
  onPlayLand: (uid: string) => void;
  onCast: (uid: string) => void;
  onDiscard?: (uid: string) => void;
}

export function HandRow({ hand, castable, canPlayLand, onPlayLand, onCast, onDiscard }: Props) {
  if (hand.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/15 px-4 py-6 text-center text-sm text-gray-500">
        Hand is empty.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {hand.map((card) => {
        const playable = card.isLand ? canPlayLand : castable.has(card.uid);
        return (
          <div
            key={card.uid}
            className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2"
          >
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <span className="truncate text-sm text-white">{card.name}</span>
              {card.mana_cost && (
                <span className="font-mono text-xs text-gray-400">{card.mana_cost}</span>
              )}
              <span className="text-xs text-gray-500">{card.type_line ?? ""}</span>
            </div>
            <div className="flex items-center gap-2">
              {card.isLand ? (
                <button
                  type="button"
                  onClick={() => onPlayLand(card.uid)}
                  disabled={!canPlayLand}
                  className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Play land
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onCast(card.uid)}
                  disabled={!playable}
                  className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Cast
                </button>
              )}
              {onDiscard && (
                <button
                  type="button"
                  onClick={() => onDiscard(card.uid)}
                  className="rounded-md border border-white/15 px-2 py-1 text-xs text-gray-300 hover:border-white/30 hover:text-white"
                  aria-label="Bottom this card"
                >
                  ↓
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
