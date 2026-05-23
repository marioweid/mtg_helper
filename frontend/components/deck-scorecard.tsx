import type { DeckCardItem } from "@/lib/types";
import { STAGE_DEFAULTS, STAGE_LABELS } from "@/lib/constants";

const SCORECARD_STAGES = ["ramp", "draw", "interaction", "lands"] as const;
type ScorecardStage = (typeof SCORECARD_STAGES)[number];

type Status = "low" | "ok" | "high";

interface Row {
  stage: ScorecardStage;
  label: string;
  actual: number;
  target: number;
  status: Status;
}

function qty(card: DeckCardItem): number {
  return card.quantity ?? 1;
}

function isLand(card: DeckCardItem): boolean {
  return !!card.type_line?.includes("Land");
}

function countStage(cards: DeckCardItem[], stage: ScorecardStage): number {
  if (stage === "lands") {
    return cards.reduce((sum, c) => (isLand(c) ? sum + qty(c) : sum), 0);
  }
  return cards.reduce(
    (sum, c) => (c.qualifying_stages.includes(stage) && !isLand(c) ? sum + qty(c) : sum),
    0,
  );
}

function statusFor(actual: number, target: number): Status {
  if (target <= 0) return "ok";
  const ratio = actual / target;
  if (ratio < 0.85) return "low";
  if (ratio > 1.15) return "high";
  return "ok";
}

const STATUS_PIP: Record<Status, { glyph: string; text: string; tone: string }> = {
  low: { glyph: "🔴", text: "low", tone: "text-red-300" },
  ok: { glyph: "🟢", text: "ok", tone: "text-emerald-300" },
  high: { glyph: "🟡", text: "high", tone: "text-yellow-300" },
};

interface Props {
  cards: DeckCardItem[];
  stageTargets: Record<string, number>;
}

export function DeckScorecard({ cards, stageTargets }: Props) {
  const rows: Row[] = SCORECARD_STAGES.map((stage) => {
    const actual = countStage(cards, stage);
    const target = stageTargets[stage] ?? STAGE_DEFAULTS[stage] ?? 0;
    return {
      stage,
      label: STAGE_LABELS[stage] ?? stage,
      actual,
      target,
      status: statusFor(actual, target),
    };
  });

  const okCount = rows.filter((r) => r.status === "ok").length;
  const overallGlyph =
    okCount === rows.length ? "🟢" : okCount >= rows.length - 1 ? "🟡" : "🔴";

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-400">Health</h3>
        <span className="text-xs text-gray-300">
          {overallGlyph} {okCount}/{rows.length} on target
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {rows.map((row) => {
          const pip = STATUS_PIP[row.status];
          return (
            <div key={row.stage} className="flex items-center justify-between text-xs">
              <span className="text-gray-300">{row.label}</span>
              <span className="flex items-center gap-2 tabular-nums">
                <span className="text-gray-200">
                  {row.actual}
                  <span className="text-gray-600"> / {row.target}</span>
                </span>
                <span className={`${pip.tone} w-10 text-right`}>{pip.glyph}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
