import type { DeckCardItem } from "@/lib/types";
import { CATEGORY_TARGETS, COLOR_SYMBOLS, STAGE_LABELS } from "@/lib/constants";

const CATEGORY_ORDER = ["theme", "ramp", "draw", "removal", "utility", "lands"];

function avgCmc(cards: DeckCardItem[]): string {
  const nonLands = cards.filter((c) => !c.type_line?.includes("Land") && c.cmc != null);
  if (nonLands.length === 0) return "—";
  const total = nonLands.reduce((sum, c) => sum + (c.cmc ?? 0), 0);
  return (total / nonLands.length).toFixed(1);
}

function colorCounts(cards: DeckCardItem[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const card of cards) {
    if (card.type_line?.includes("Land")) continue;
    for (const color of card.color_identity) {
      counts[color] = (counts[color] ?? 0) + 1;
    }
    if (card.color_identity.length === 0) {
      counts["C"] = (counts["C"] ?? 0) + 1;
    }
  }
  return counts;
}

export function DeckStats({ cards }: { cards: DeckCardItem[] }) {
  const categoryCounts: Record<string, number> = {};
  let creatureCount = 0;

  for (const card of cards) {
    const cat = card.category ?? "other";
    categoryCounts[cat] = (categoryCounts[cat] ?? 0) + 1;
    if (card.type_line?.includes("Creature")) creatureCount++;
  }

  const colors = colorCounts(cards);
  const maxColorCount = Math.max(...Object.values(colors), 1);
  const nonLandCount = cards.filter((c) => !c.type_line?.includes("Land")).length;

  const categories = [
    ...CATEGORY_ORDER.filter((c) => (categoryCounts[c] ?? 0) > 0 || CATEGORY_TARGETS[c] != null),
    ...Object.keys(categoryCounts).filter(
      (c) => !CATEGORY_ORDER.includes(c) && (categoryCounts[c] ?? 0) > 0,
    ),
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* Quick stats */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-400">Stats</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg bg-white/5 px-3 py-2">
            <p className="text-gray-500">Total</p>
            <p className="font-semibold text-white">{cards.length}</p>
          </div>
          <div className="rounded-lg bg-white/5 px-3 py-2">
            <p className="text-gray-500">Avg CMC</p>
            <p className="font-semibold text-white">{avgCmc(cards)}</p>
          </div>
          <div className="rounded-lg bg-white/5 px-3 py-2">
            <p className="text-gray-500">Creatures</p>
            <p className="font-semibold text-white">{creatureCount}</p>
          </div>
          <div className="rounded-lg bg-white/5 px-3 py-2">
            <p className="text-gray-500">Non-land</p>
            <p className="font-semibold text-white">{nonLandCount}</p>
          </div>
        </div>
      </div>

      {/* Color distribution */}
      {Object.keys(colors).length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-400">Color Distribution</h3>
          <div className="flex flex-col gap-1.5">
            {(["W", "U", "B", "R", "G", "C"] as const)
              .filter((c) => colors[c] != null)
              .map((c) => {
                const sym = COLOR_SYMBOLS[c];
                const count = colors[c] ?? 0;
                const pct = Math.round((count / maxColorCount) * 100);
                if (!sym) return null;
                return (
                  <div key={c} className="flex items-center gap-2 text-xs">
                    <span
                      className={`w-5 rounded px-1 text-center font-bold ${sym.bg} ${sym.text}`}
                    >
                      {sym.label}
                    </span>
                    <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-5 text-right text-gray-500">{count}</span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {categories.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-400">Categories</h3>
          <div className="flex flex-col gap-1">
            {categories.map((cat) => {
              const count = categoryCounts[cat] ?? 0;
              const target = CATEGORY_TARGETS[cat];
              const label = STAGE_LABELS[cat] ?? cat;
              let indicator = "text-gray-500";
              if (target) {
                if (count >= target[0] && count <= target[1]) indicator = "text-green-400";
                else if (count > 0 && count < target[0]) indicator = "text-yellow-400";
              }
              return (
                <div key={cat} className="flex items-center justify-between text-xs">
                  <span className="capitalize text-gray-400">{label}</span>
                  <span className={`font-medium ${indicator}`}>
                    {count}
                    {target && (
                      <span className="text-gray-600 font-normal">
                        /{target[0]}–{target[1]}
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
