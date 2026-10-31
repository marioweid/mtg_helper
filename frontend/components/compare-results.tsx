"use client";

import { useState } from "react";

import { CardExportDialog } from "@/components/card-export-dialog";
import { CardHover } from "@/components/card-hover";
import { ComparisonPlanningActions } from "@/components/comparison-planning-actions";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import { ManaCost } from "@/components/mana-cost";
import { ManaCurve } from "@/components/mana-curve";
import { OwnedBadge } from "@/components/owned-badge";
import { comparisonExportCards, type ExportScope } from "@/lib/comparison";
import type {
  ComparisonSideMeta,
  DeckCompareResponse,
  DeckDiff,
  DeckSummary,
  DiffEntry,
} from "@/lib/types";

const SCOPE_LABELS: Record<ExportScope, string> = {
  incoming: "Export incoming cards (left → right)",
  left: "Export full left deck",
  right: "Export full right deck",
  selected: "Export selected cards",
};

export function CompareResults({
  result,
  decks,
  onPlanned,
}: {
  result: DeckCompareResponse;
  decks: DeckSummary[];
  onPlanned: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState<ExportScope | null>(null);
  const entries = [...result.diff.added, ...result.diff.removed, ...result.diff.quantity_changed];
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const incoming = comparisonExportCards(result.diff, "incoming");
  const incomingCount = incoming.reduce((sum, card) => sum + card.quantity, 0);
  return (
    <>
      <section className="grid gap-4 md:grid-cols-2">
        <SideSummary label="Left" meta={result.left} diff={result.diff} side="left" />
        <SideSummary label="Right" meta={result.right} diff={result.diff} side="right" />
      </section>
      <ComparisonActions
        incomingCount={incomingCount}
        selectedCount={selected.size}
        onExport={setScope}
        onSelectAll={() => setSelected(new Set(entries.map((entry) => entry.card.card_id)))}
        onClear={() => setSelected(new Set())}
      />
      <ComparisonPlanningActions
        result={result}
        decks={decks}
        selected={selected}
        onPlanned={() => {
          setSelected(new Set());
          onPlanned();
        }}
      />
      <section className="grid gap-6 md:grid-cols-2">
        <DiffGroup
          label="Added"
          entries={result.diff.added}
          kind="added"
          selected={selected}
          onToggle={toggle}
        />
        <DiffGroup
          label="Removed"
          entries={result.diff.removed}
          kind="removed"
          selected={selected}
          onToggle={toggle}
        />
      </section>
      <DiffGroup
        label="Quantity changed"
        entries={result.diff.quantity_changed}
        kind="qty"
        selected={selected}
        onToggle={toggle}
      />
      <details>
        <summary className="cursor-pointer text-sm text-gray-400">
          Common ({result.diff.common.length})
        </summary>
        <DiffGroup
          label="Common"
          entries={result.diff.common}
          kind="common"
          selected={selected}
          onToggle={toggle}
        />
      </details>
      {scope && (
        <CardExportDialog
          title={SCOPE_LABELS[scope]}
          cards={comparisonExportCards(result.diff, scope, selected)}
          onClose={() => setScope(null)}
        />
      )}
    </>
  );
}

function ComparisonActions({
  incomingCount,
  selectedCount,
  onExport,
  onSelectAll,
  onClear,
}: {
  incomingCount: number;
  selectedCount: number;
  onExport: (scope: ExportScope) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  return (
    <section
      aria-label="Comparison actions"
      className="rounded-xl border border-indigo-500/25 bg-indigo-950/15 p-4"
    >
      <p className="text-sm text-indigo-200">
        Left → right: {incomingCount} incoming copies · {selectedCount} cards selected
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Exports use changed quantities; full-deck exports include commanders. Nothing is applied to
        your deck.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {(Object.keys(SCOPE_LABELS) as ExportScope[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onExport(item)}
            disabled={
              (item === "incoming" && !incomingCount) || (item === "selected" && !selectedCount)
            }
            className={`rounded border border-indigo-400/30 px-3 py-2 text-xs
              text-indigo-200 hover:bg-indigo-500/15 disabled:opacity-40`}
          >
            {SCOPE_LABELS[item]}
          </button>
        ))}
        <button type="button" onClick={onSelectAll} className="px-2 text-xs text-gray-400">
          Select all changes
        </button>
        <button type="button" onClick={onClear} className="px-2 text-xs text-gray-400">
          Clear selection
        </button>
      </div>
    </section>
  );
}

function SideSummary({
  label,
  meta,
  diff,
  side,
}: {
  label: string;
  meta: ComparisonSideMeta;
  diff: DeckDiff;
  side: "left" | "right";
}) {
  const quantities = comparisonExportCards(diff, side);
  const entries = [...diff.added, ...diff.removed, ...diff.quantity_changed, ...diff.common];
  const cards = quantities.map((item) => {
    const entry = entries.find((entry) => entry.card.card_id === item.card_id)!;
    return { ...entry.card, quantity: item.quantity };
  });
  const kindLabel =
    meta.kind === "planned"
      ? "Planned deck"
      : meta.kind === "snapshot"
        ? "Snapshot"
        : "Physical deck";
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase text-gray-500">
        {label} · {kindLabel}
      </p>
      <h2 className="mt-1 text-sm font-medium text-white">{meta.deck_name}</h2>
      {meta.label && <p className="text-xs text-indigo-300">{meta.label}</p>}
      {meta.kind === "snapshot" && (
        <p className="mt-1 text-xs text-gray-500">
          Saved main deck; commanders use the deck&apos;s current configuration.
        </p>
      )}
      <p className="mt-1 text-xs text-gray-400">
        {meta.card_count} cards including commanders · stage: {meta.stage}
      </p>
      {meta.kind === "planned" && meta.card_count !== 100 && (
        <p className="mt-2 text-xs text-amber-300">
          Planned deck has {meta.card_count} cards:{" "}
          {meta.card_count > 100
            ? `${meta.card_count - 100} cuts still needed`
            : `${100 - meta.card_count} additions still needed`}{" "}
          to reach 100.
        </p>
      )}
      <div className="mt-4">
        <DeckTypeBreakdown cards={cards} />
      </div>
      <div className="mt-3">
        <ManaCurve cards={cards} curve={meta.mana_curve} />
      </div>
    </div>
  );
}

type DiffKind = "added" | "removed" | "qty" | "common";

function DiffGroup({
  label,
  entries,
  kind,
  selected,
  onToggle,
}: {
  label: string;
  entries: DiffEntry[];
  kind: DiffKind;
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  const color =
    kind === "added" ? "text-emerald-300" : kind === "removed" ? "text-red-300" : "text-amber-300";
  return (
    <section>
      <h2 className={`mb-2 text-sm font-semibold ${color}`}>
        {label} ({entries.length})
      </h2>
      {!entries.length && <p className="text-xs text-gray-500">No {label.toLowerCase()} cards.</p>}
      <ul className="flex flex-col gap-1">
        {entries.map((entry) => (
          <DiffRow
            key={entry.card.card_id}
            entry={entry}
            kind={kind}
            selected={selected.has(entry.card.card_id)}
            onToggle={() => onToggle(entry.card.card_id)}
          />
        ))}
      </ul>
    </section>
  );
}

function DiffRow({
  entry,
  kind,
  selected,
  onToggle,
}: {
  entry: DiffEntry;
  kind: DiffKind;
  selected: boolean;
  onToggle: () => void;
}) {
  const quantity =
    kind === "qty"
      ? `${entry.left_quantity} → ${entry.right_quantity}`
      : kind === "added"
        ? `+${entry.right_quantity}`
        : kind === "removed"
          ? `−${entry.left_quantity}`
          : `×${entry.left_quantity}`;
  return (
    <li className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        aria-label={`Select ${entry.card.name} for export or planning`}
        className="accent-indigo-500"
      />
      {entry.card.image_uri && (
        <img src={entry.card.image_uri} alt="" className="h-12 w-9 shrink-0 rounded object-cover" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <CardHover name={entry.card.name} imageUri={entry.card.image_uri}>
            <span className="text-sm text-white">{entry.card.name}</span>
          </CardHover>
          {entry.card.mana_cost && (
            <span className="text-xs">
              <ManaCost cost={entry.card.mana_cost} />
            </span>
          )}
        </div>
        <p className="truncate text-xs text-gray-500">{entry.card.type_line}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-gray-400">
          <span>
            {entry.card.price_eur_cents == null
              ? "No EUR price"
              : `€${(entry.card.price_eur_cents / 100).toFixed(2)}`}
          </span>
          <OwnedBadge owned={entry.card.owned_in} />
        </div>
      </div>
      <span className="shrink-0 text-xs text-gray-300">{quantity}</span>
    </li>
  );
}
