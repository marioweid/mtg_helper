import type { DeckCardItem } from "@/lib/types";

const MAX_CMC = 7;
const BAR_H = 80;

export function ManaCurve({ cards }: { cards: DeckCardItem[] }) {
  // Count cards per CMC bucket (0-6, then 7+)
  const counts = Array.from<number>({ length: MAX_CMC + 1 }).fill(0);
  for (const card of cards) {
    if (card.type_line?.includes("Land")) continue;
    const cmc = card.cmc ?? 0;
    const bucket = Math.min(Math.floor(cmc), MAX_CMC);
    counts[bucket] = (counts[bucket] ?? 0) + 1;
  }

  const maxCount = Math.max(...counts, 1);
  const barWidth = 28;
  const gap = 6;
  const totalW = (barWidth + gap) * (MAX_CMC + 1);

  return (
    <div>
      <h3 className="mb-3 text-sm font-medium text-gray-400">Mana Curve</h3>
      <svg
        viewBox={`0 0 ${totalW} ${BAR_H + 24}`}
        className="w-full max-w-xs"
        aria-label="Mana curve chart"
      >
        {counts.map((count, i) => {
          const barH = count === 0 ? 2 : Math.max(4, (count / maxCount) * BAR_H);
          const x = i * (barWidth + gap);
          const y = BAR_H - barH;
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barH}
                rx={3}
                className="fill-indigo-500"
                opacity={count === 0 ? 0.2 : 0.85}
              />
              {count > 0 && (
                <text
                  x={x + barWidth / 2}
                  y={y - 3}
                  textAnchor="middle"
                  className="fill-gray-300"
                  fontSize={9}
                >
                  {count}
                </text>
              )}
              <text
                x={x + barWidth / 2}
                y={BAR_H + 14}
                textAnchor="middle"
                className="fill-gray-500"
                fontSize={10}
              >
                {i === MAX_CMC ? `${MAX_CMC}+` : String(i)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
