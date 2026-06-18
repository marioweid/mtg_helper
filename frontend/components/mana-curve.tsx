import type { DeckManaCurve } from "@/lib/types";

const MAX_CMC = 7;
const BAR_H = 80;
const TOP_PAD = 14;
const BUCKETS = ["0", "1", "2", "3", "4", "5", "6", "7+"] as const;

export interface ManaCurveCard {
  type_line: string | null;
  cmc: number | null;
  quantity?: number | null;
}

interface Props {
  cards?: ManaCurveCard[];
  curve?: DeckManaCurve | null;
  compact?: boolean;
  minimal?: boolean;
}

function countsFromCards(cards: ManaCurveCard[]): Record<string, number> {
  const counts = Object.fromEntries(BUCKETS.map((b) => [b, 0])) as Record<string, number>;
  for (const card of cards) {
    if (card.type_line?.includes("Land")) continue;
    const cmc = card.cmc ?? 0;
    const bucket = Math.min(Math.floor(cmc), MAX_CMC);
    const key = bucket === MAX_CMC ? "7+" : String(bucket);
    counts[key] = (counts[key] ?? 0) + (card.quantity ?? 1);
  }
  return counts;
}

function sourceLabel(curve: DeckManaCurve): string {
  if (curve.recommended.source === "moxfield") {
    return `Based on ${curve.recommended.deck_count} Moxfield decks`;
  }
  return "Generic Commander fallback";
}

function deltaParts(delta: Record<string, number>): string[] {
  const needs = BUCKETS.filter((b) => (delta[b] ?? 0) > 0)
    .slice(0, 3)
    .map((b) => `+${delta[b]} at MV ${b}`);
  const high = BUCKETS.filter((b) => (delta[b] ?? 0) < -1)
    .slice(0, 2)
    .map((b) => `high at MV ${b}`);
  const parts = [...needs, ...high];
  return parts.length > 0 ? parts : ["Curve is close to target"];
}

export function ManaCurve({ cards = [], curve = null, compact = false, minimal = false }: Props) {
  const current = curve?.current ?? countsFromCards(cards);
  const recommended = curve?.recommended.buckets ?? null;
  const maxCount = Math.max(
    ...BUCKETS.map((b) => current[b] ?? 0),
    ...(recommended ? BUCKETS.map((b) => recommended[b] ?? 0) : []),
    1,
  );
  const barWidth = compact ? 22 : 28;
  const gap = 6;
  const totalW = (barWidth + gap) * BUCKETS.length;

  return (
    <div>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3
            className="text-sm font-medium text-gray-400"
            title={curve ? sourceLabel(curve) : undefined}
          >
            Mana Curve
          </h3>
          {curve && !minimal && (
            <span className="mt-1 inline-flex rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-gray-400">
              {sourceLabel(curve)}
            </span>
          )}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${totalW} ${TOP_PAD + BAR_H + 24}`}
        className="w-full max-w-xs"
        aria-label="Mana curve chart"
      >
        {BUCKETS.map((bucket, i) => {
          const count = current[bucket] ?? 0;
          const target = recommended?.[bucket] ?? 0;
          const barH = count === 0 ? 2 : Math.max(4, (count / maxCount) * BAR_H);
          const targetY = TOP_PAD + BAR_H - (target / maxCount) * BAR_H;
          const x = i * (barWidth + gap);
          const y = TOP_PAD + BAR_H - barH;
          const labelInside = barH > BAR_H - 12;
          return (
            <g key={bucket}>
              {recommended && (
                <line
                  x1={x - 1}
                  x2={x + barWidth + 1}
                  y1={targetY}
                  y2={targetY}
                  className="stroke-amber-300"
                  strokeWidth={2}
                  strokeLinecap="round"
                />
              )}
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
                  y={labelInside ? y + 11 : y - 3}
                  textAnchor="middle"
                  className={labelInside ? "fill-white" : "fill-gray-300"}
                  fontSize={9}
                >
                  {count}
                </text>
              )}
              <text
                x={x + barWidth / 2}
                y={TOP_PAD + BAR_H + 14}
                textAnchor="middle"
                className="fill-gray-500"
                fontSize={10}
              >
                {bucket}
              </text>
            </g>
          );
        })}
      </svg>
      {curve && !minimal && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {deltaParts(curve.progress_delta).map((part) => (
            <span
              key={part}
              className="rounded-full border border-amber-300/20 bg-amber-300/10 px-2 py-0.5 text-[11px] font-medium text-amber-100"
            >
              {part}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
