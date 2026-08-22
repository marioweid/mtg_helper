"use client";

import type { BracketValidationResponse, BracketViolation } from "@/lib/types";

const RULE_LABELS: Record<BracketViolation["rule"], string> = {
  game_changer: "Game Changers",
  mass_land_destruction: "Mass land destruction",
  fast_mana: "Fast mana",
  infinite_combo: "Two-card infinite combos",
  extra_turn_chain: "Extra-turn chains",
};

interface Props {
  validation: BracketValidationResponse | null;
}

export function BracketValidationPanel({ validation }: Props) {
  if (!validation) return null;

  if (validation.violations.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-900/15 px-3 py-2 text-sm text-emerald-200">
        Deck legal for bracket {validation.declared_bracket}.
      </div>
    );
  }

  const headerTone = validation.legal
    ? "border-amber-500/40 bg-amber-900/15 text-amber-200"
    : "border-red-500/40 bg-red-900/20 text-red-200";

  return (
    <div className={`rounded-lg border ${headerTone} px-3 py-2 text-sm`}>
      <div className="mb-1 font-medium">
        Bracket {validation.declared_bracket}:{" "}
        {validation.legal ? "warnings only" : "violations found"}
      </div>
      <ul className="space-y-2">
        {validation.violations.map((v, idx) => (
          <li key={`${v.rule}-${idx}`}>
            <div className="text-xs uppercase tracking-wide text-gray-400">
              {RULE_LABELS[v.rule]} ·{" "}
              <span className={v.severity === "block" ? "text-red-300" : "text-amber-300"}>
                {v.severity}
              </span>
            </div>
            <div>{v.message}</div>
            {v.cards.length > 0 && (
              <div className="mt-0.5 text-xs text-gray-400">{v.cards.join(", ")}</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
