import type {
  ComparisonKind,
  DeckDiff,
  DiffEntry,
  ExportCard,
  PlannedDeckChangeCreate,
} from "@/lib/types";

export interface ComparisonSelection {
  deckId: string | null;
  kind: ComparisonKind;
  snapshotId: string | null;
}

export type ExportScope = "incoming" | "left" | "right" | "selected";

export type PlanningScope = "additions" | "changes";

export interface ComparisonPlannedChange extends PlannedDeckChangeCreate {
  card_id: string;
  name: string;
  quantity: number;
  categories: string[];
}

export type ComparisonSelectionPreset = "changes" | "additions" | "cuts";

/** Select changed rows by direction; common cards require an explicit group or row selection. */
export function comparisonSelectionPreset(
  diff: DeckDiff,
  preset: ComparisonSelectionPreset,
): Set<string> {
  const entries = [...diff.added, ...diff.removed, ...diff.quantity_changed];
  return new Set(
    entries
      .filter((entry) => {
        const delta = entry.right_quantity - entry.left_quantity;
        if (preset === "additions") return delta > 0;
        if (preset === "cuts") return delta < 0;
        return delta !== 0;
      })
      .map((entry) => entry.card.card_id),
  );
}

/** Fill a partial group or clear a complete one without disturbing selections elsewhere. */
export function toggleComparisonGroup(
  selected: ReadonlySet<string>,
  entries: DiffEntry[],
): Set<string> {
  const next = new Set(selected);
  const allSelected = entries.every((entry) => selected.has(entry.card.card_id));
  for (const entry of entries) {
    if (allSelected) next.delete(entry.card.card_id);
    else next.add(entry.card.card_id);
  }
  return next;
}

/** Count selected card types separately from positive and negative copy deltas. */
export function comparisonSelectionTotals(diff: DeckDiff, selected: ReadonlySet<string>) {
  const totals = { types: 0, changedTypes: 0, addedCopies: 0, removedCopies: 0 };
  for (const entry of [...diff.added, ...diff.removed, ...diff.quantity_changed, ...diff.common]) {
    if (!selected.has(entry.card.card_id)) continue;
    const delta = entry.right_quantity - entry.left_quantity;
    totals.types += 1;
    if (delta !== 0) totals.changedTypes += 1;
    totals.addedCopies += Math.max(0, delta);
    totals.removedCopies += Math.max(0, -delta);
  }
  return totals;
}

/** Convert selected non-commander deltas to minimum pending quantities on a target deck. */
export function comparisonPlanningChanges(
  diff: DeckDiff,
  scope: PlanningScope,
  selected: ReadonlySet<string>,
): ComparisonPlannedChange[] {
  const changes: ComparisonPlannedChange[] = [];
  for (const entry of [...diff.added, ...diff.removed, ...diff.quantity_changed]) {
    if (!selected.has(entry.card.card_id)) continue;
    if (entry.left_categories.includes("commander") || entry.right_categories.includes("commander"))
      continue;
    const delta = entry.right_quantity - entry.left_quantity;
    if (delta === 0 || (scope === "additions" && delta < 0)) continue;
    changes.push({
      card_id: entry.card.card_id,
      card_scryfall_id: entry.card.scryfall_id,
      name: entry.card.name,
      direction: delta > 0 ? "addition" : "cut",
      quantity: Math.abs(delta),
      categories: delta > 0 ? entry.right_categories : [],
    });
  }
  return changes;
}

/** Use positive deltas for incoming cards and absolute deltas for selected changes. */
export function comparisonExportCards(
  diff: DeckDiff,
  scope: ExportScope,
  selected: ReadonlySet<string> = new Set(),
): ExportCard[] {
  return [...diff.added, ...diff.removed, ...diff.quantity_changed, ...diff.common]
    .map((entry) => ({
      card_id: entry.card.card_id,
      quantity: exportQuantity(entry, scope, selected),
    }))
    .filter((card) => card.quantity > 0);
}

function exportQuantity(entry: DiffEntry, scope: ExportScope, selected: ReadonlySet<string>) {
  if (scope === "left") return entry.left_quantity;
  if (scope === "right") return entry.right_quantity;
  const delta = entry.right_quantity - entry.left_quantity;
  if (scope === "incoming") return Math.max(0, delta);
  if (!selected.has(entry.card.card_id)) return 0;
  return Math.abs(delta) || entry.right_quantity;
}

export function physicalToPlannedHref(deckId: string): string {
  const query = new URLSearchParams({
    left: deckId,
    left_kind: "deck",
    right: deckId,
    right_kind: "planned",
  });
  return `/decks/compare?${query.toString()}`;
}
