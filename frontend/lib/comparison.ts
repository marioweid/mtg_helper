import type { ComparisonKind, DeckDiff, DiffEntry, ExportCard } from "@/lib/types";

export interface ComparisonSelection {
  deckId: string | null;
  kind: ComparisonKind;
  snapshotId: string | null;
}

export type ExportScope = "incoming" | "left" | "right" | "selected";

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
