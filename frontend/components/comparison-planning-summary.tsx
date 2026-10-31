import type { ComparisonPlannedChange } from "@/lib/comparison";

export function ComparisonPlanningSummary({ changes }: { changes: ComparisonPlannedChange[] }) {
  if (!changes.length)
    return (
      <p role="status" className="mt-2 text-xs text-gray-400">
        No changed cards selected for planning.
      </p>
    );
  const incoming = changes.reduce(
    (sum, change) => sum + (change.direction === "addition" ? change.quantity : 0),
    0,
  );
  const outgoing = changes.reduce(
    (sum, change) => sum + (change.direction === "cut" ? change.quantity : 0),
    0,
  );
  const net = incoming - outgoing;
  const label =
    incoming && outgoing
      ? net === 0
        ? "Balanced swap selection"
        : "Unbalanced swap selection"
      : incoming
        ? "Additions only"
        : "Cuts only";
  return (
    <div role="status" aria-live="polite" className="mt-2 text-xs text-gray-300">
      <p className="tabular-nums">
        Selection delta: +{incoming} copies in · −{outgoing} out · net {net > 0 ? "+" : ""}
        {net}
      </p>
      <p className="mt-1">{label}</p>
    </div>
  );
}
