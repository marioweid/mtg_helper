"use client";

import { useState } from "react";

import { ComparisonPlanDialog } from "@/components/comparison-plan-dialog";
import { ComparisonPlanningSummary } from "@/components/comparison-planning-summary";
import { comparisonPlanningChanges, type PlanningScope } from "@/lib/comparison";
import type { DeckCompareResponse, DeckSummary } from "@/lib/types";

interface Props {
  result: DeckCompareResponse;
  decks: DeckSummary[];
  selected: ReadonlySet<string>;
  onPlanned: () => void;
}

export function ComparisonPlanningActions({ result, decks, selected, onPlanned }: Props) {
  const [mode, setMode] = useState<PlanningScope | null>(null);
  const additions = comparisonPlanningChanges(result.diff, "additions", selected);
  const changes = comparisonPlanningChanges(result.diff, "changes", selected);
  return (
    <section
      aria-label="Plan selected comparison cards"
      className="rounded-xl border border-emerald-500/20 bg-emerald-950/10 p-4"
    >
      <h2 className="text-sm font-medium text-emerald-200">Plan additions or swaps</h2>
      <p className="mt-1 text-xs text-gray-400">
        Queue left → right deltas on a chosen deck after confirmation. Common cards and commander
        changes are excluded. Swap sides to reverse the direction. Physical cards stay unchanged.
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Plan selected changes reviews additions and cuts together; each card is checked separately.
      </p>
      <ComparisonPlanningSummary changes={changes} />
      {selected.size > changes.length && (
        <p className="mt-1 text-xs text-gray-400">
          {selected.size - changes.length} selected{" "}
          {selected.size - changes.length === 1 ? "card is" : "cards are"} export-only
          (common/commander).
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!additions.length}
          onClick={() => setMode("additions")}
          className={`rounded border border-emerald-400/30 px-3 py-2 text-xs
          text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-40`}
        >
          Plan selected additions
        </button>
        <button
          type="button"
          disabled={!changes.length}
          onClick={() => setMode("changes")}
          className={`rounded border border-emerald-400/30 px-3 py-2 text-xs
          text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-40`}
        >
          Plan selected changes
        </button>
      </div>
      {mode && (
        <ComparisonPlanDialog
          title={mode === "additions" ? "Plan selected additions" : "Plan selected changes"}
          changes={mode === "additions" ? additions : changes}
          decks={decks}
          defaultDeck={result.left}
          onClose={(attempted) => {
            setMode(null);
            if (attempted) onPlanned();
          }}
        />
      )}
    </section>
  );
}
