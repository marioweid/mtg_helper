import { COLOR_SYMBOLS } from "@/lib/constants";
import type { Color, PlaytestCard } from "@/lib/playtest";
import { COLORS, manaPoolSummary } from "@/lib/playtest";

interface Props {
  untappedLands: PlaytestCard[];
  tappedCount: number;
}

export function ManaReadout({ untappedLands, tappedCount }: Props) {
  const pool = manaPoolSummary(untappedLands);
  const total = untappedLands.length;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
      <span className="text-gray-400">Mana</span>
      <span className="font-semibold text-white tabular-nums">{total}</span>
      <span className="flex items-center gap-1">
        {(COLORS as readonly Color[]).map((c) => {
          const count = pool[c];
          if (count === 0) return null;
          const sym = COLOR_SYMBOLS[c];
          if (!sym) return null;
          return (
            <span
              key={c}
              className={`flex h-5 min-w-5 items-center justify-center rounded px-1 text-xs font-bold ${sym.bg} ${sym.text}`}
              title={`${count} ${c}`}
            >
              {count}
              {sym.label}
            </span>
          );
        })}
      </span>
      {tappedCount > 0 && (
        <span className="text-xs text-gray-500">({tappedCount} tapped)</span>
      )}
    </div>
  );
}
