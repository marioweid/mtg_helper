"use client";

import { useEffect, useRef } from "react";

import { comparisonSelectionTotals, type ComparisonSelectionPreset } from "@/lib/comparison";
import type { DeckDiff, DiffEntry } from "@/lib/types";

interface Props {
  diff: DeckDiff;
  selected: ReadonlySet<string>;
  onPreset: (preset: ComparisonSelectionPreset) => void;
  onClear: () => void;
}

export function ComparisonSelectionToolbar({ diff, selected, onPreset, onClear }: Props) {
  const totals = comparisonSelectionTotals(diff, selected);
  const changed = [...diff.added, ...diff.removed, ...diff.quantity_changed];
  const hasChanges = changed.some((entry) => entry.left_quantity !== entry.right_quantity);
  const hasAdditions = changed.some((entry) => entry.right_quantity > entry.left_quantity);
  const hasCuts = changed.some((entry) => entry.right_quantity < entry.left_quantity);
  const commonTypes = totals.types - totals.changedTypes;
  const typeLabel = totals.types === 1 ? "unique card" : "unique cards";
  const selectedLabel = `${totals.types} ${typeLabel} selected`;
  const presets = [
    { value: "changes", label: "Select all", enabled: hasChanges },
    { value: "additions", label: "Additions only", enabled: hasAdditions },
    { value: "cuts", label: "Cuts only", enabled: hasCuts },
  ] as const;
  return (
    <section
      aria-label="Comparison selection"
      className="rounded-xl border border-white/15 bg-white/5 p-4"
    >
      <h2 className="text-sm font-semibold text-white">Selection</h2>
      <p role="status" aria-live="polite" className="mt-1 text-sm tabular-nums text-gray-200">
        {selectedLabel} · +{totals.addedCopies} copies in · −{totals.removedCopies} out
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Bulk presets select changed cards only. Select common cards separately for export.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {presets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            disabled={!preset.enabled}
            onClick={() => onPreset(preset.value)}
            className={`min-h-11 touch-manipulation rounded border border-indigo-400/40 px-3
          text-sm text-indigo-200 hover:bg-indigo-500/15 disabled:opacity-40
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-300`}
          >
            {preset.label}
          </button>
        ))}
        <button
          type="button"
          disabled={!selected.size}
          onClick={onClear}
          className={`min-h-11 touch-manipulation rounded border border-white/20 px-3 text-sm
          text-gray-300 hover:bg-white/10 disabled:opacity-40 focus-visible:outline-2
          focus-visible:outline-offset-2 focus-visible:outline-indigo-300`}
        >
          Clear selection
        </button>
      </div>
      {commonTypes > 0 && (
        <p className="mt-2 text-xs text-gray-400">
          {commonTypes} unchanged {commonTypes === 1 ? "card" : "cards"} selected for export only.
        </p>
      )}
    </section>
  );
}

export function ComparisonGroupToggle({
  label,
  entries,
  selected,
  onToggle,
}: {
  label: string;
  entries: DiffEntry[];
  selected: ReadonlySet<string>;
  onToggle: () => void;
}) {
  const checkbox = useRef<HTMLInputElement>(null);
  const count = entries.filter((entry) => selected.has(entry.card.card_id)).length;
  const all = entries.length > 0 && count === entries.length;
  const mixed = count > 0 && !all;
  useEffect(() => {
    if (checkbox.current) checkbox.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-2">
      <input
        ref={checkbox}
        type="checkbox"
        checked={all}
        disabled={!entries.length}
        aria-label={`Select all ${label} cards`}
        aria-checked={mixed ? "mixed" : all}
        onChange={onToggle}
        className={`h-4 w-4 accent-indigo-500 focus-visible:outline-2
        focus-visible:outline-offset-2 focus-visible:outline-indigo-300`}
      />
      <span>
        {label} ({entries.length}){label === "Common" ? " · export only" : ""}
      </span>
      <span className="ml-auto text-xs font-normal text-gray-400">
        {count}/{entries.length} selected · {all ? "Clear all" : "Select all"}
      </span>
    </label>
  );
}
