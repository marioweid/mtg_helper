"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { ApplyRevisionDialog } from "@/components/apply-revision-dialog";
import { CardHover } from "@/components/card-hover";
import { OwnedBadge } from "@/components/owned-badge";
import { CardExportDialog } from "@/components/card-export-dialog";
import { physicalToPlannedHref } from "@/lib/comparison";
import { apiClient, ApiError } from "@/lib/api";
import type {
  CollectionMembership,
  CollectionResponse,
  ExportCard,
  PlannedDeckChange,
} from "@/lib/types";

interface Props {
  deckId: string;
  plans: PlannedDeckChange[];
  physicalCount: number;
  plannedCount: number;
  onChanged: () => void | Promise<void>;
}

function collectionOptions(
  plan: PlannedDeckChange,
  collections: CollectionResponse[],
): CollectionMembership[] {
  if (plan.direction === "addition") return plan.owned_in;
  return collections.map((collection) => ({
    id: collection.id,
    name: collection.name,
    quantity: collection.card_count,
  }));
}

function usePlanCollections() {
  const [collections, setCollections] = useState<CollectionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void apiClient
      .listCollections()
      .then((items) => {
        if (!cancelled) setCollections(items);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load binders");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return { collections, error };
}

function usePlannedChanges({ plans, onChanged }: Props) {
  const { collections, error: collectionError } = usePlanCollections();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportCards, setExportCards] = useState<ExportCard[] | null>(null);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const available = new Set(plans.map((plan) => plan.id));
    setSelectedIds((current) => new Set([...current].filter((id) => available.has(id))));
  }, [plans]);

  const grouped = useMemo(
    () => ({
      addition: plans.filter((plan) => plan.direction === "addition"),
      cut: plans.filter((plan) => plan.direction === "cut"),
    }),
    [plans],
  );
  const selectedPlans = useMemo(
    () => plans.filter((plan) => selectedIds.has(plan.id)),
    [plans, selectedIds],
  );
  const exportAdditions = (items: PlannedDeckChange[]) =>
    setExportCards(
      items
        .filter((plan) => plan.direction === "addition")
        .map((plan) => ({ card_id: plan.card_id, quantity: plan.quantity })),
    );

  const toggleSelected = (planId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(planId)) next.delete(planId);
      else next.add(planId);
      return next;
    });
  };

  const toggleGroup = (groupPlans: PlannedDeckChange[]) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      const allSelected = groupPlans.every((plan) => next.has(plan.id));
      for (const plan of groupPlans) {
        if (allSelected) next.delete(plan.id);
        else next.add(plan.id);
      }
      return next;
    });
  };

  async function run(planId: string, action: () => Promise<unknown>) {
    setBusyId(planId);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update planned change");
    } finally {
      setBusyId(null);
    }
  }

  return {
    collections,
    busyId,
    error: error ?? collectionError,
    exportCards,
    setExportCards,
    revisionOpen,
    setRevisionOpen,
    selectedIds,
    setSelectedIds,
    grouped,
    selectedPlans,
    exportAdditions,
    toggleSelected,
    toggleGroup,
    run,
  };
}

type PanelState = ReturnType<typeof usePlannedChanges>;

export function PlannedChangesPanel(props: Props) {
  const state = usePlannedChanges(props);
  return (
    <details className="rounded-xl border border-indigo-500/25 bg-indigo-950/15">
      <PlannedSummary
        physicalCount={props.physicalCount}
        plannedCount={props.plannedCount}
        planCount={props.plans.length}
      />
      <PlannedContents deckId={props.deckId} plans={props.plans} state={state} />
      <PlannedDialogs props={props} state={state} />
    </details>
  );
}

function PlannedContents({
  deckId,
  plans,
  state,
}: {
  deckId: string;
  plans: PlannedDeckChange[];
  state: PanelState;
}) {
  const {
    error,
    grouped,
    collections,
    busyId,
    run,
    exportAdditions,
    selectedIds,
    toggleSelected,
    toggleGroup,
  } = state;
  return (
    <div className="border-t border-white/10 px-3 py-3">
      <Link
        href={physicalToPlannedHref(deckId)}
        className="mb-3 inline-block text-xs text-indigo-300 hover:text-indigo-200"
      >
        Compare physical → planned
      </Link>
      {error && (
        <p
          className={`mb-3 rounded border border-red-500/30 bg-red-950/30
            px-3 py-2 text-xs text-red-300`}
        >
          {error}
        </p>
      )}
      {plans.length === 0 ? (
        <p className="px-1 py-2 text-xs text-gray-500">No pending additions or cuts.</p>
      ) : (
        <div className="space-y-4">
          <PlannedSelectionActions state={state} />
          {(["addition", "cut"] as const).map((tone) => (
            <PlanGroup
              key={tone}
              title={tone === "addition" ? "Planned additions" : "Planned cuts"}
              tone={tone}
              plans={grouped[tone]}
              collections={collections}
              busyId={busyId}
              onRun={run}
              deckId={deckId}
              onExport={tone === "addition" ? () => exportAdditions(grouped.addition) : undefined}
              selectedIds={selectedIds}
              onToggle={toggleSelected}
              onToggleAll={() => toggleGroup(grouped[tone])}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PlannedSelectionActions({ state }: { state: PanelState }) {
  const { selectedPlans, exportAdditions, setRevisionOpen } = state;
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 rounded-lg
      border border-indigo-500/20 bg-indigo-950/20 px-3 py-2`}
    >
      <span className="text-xs text-indigo-200">{selectedPlans.length} selected</span>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!selectedPlans.some((plan) => plan.direction === "addition")}
          onClick={() => exportAdditions(selectedPlans)}
          className={`rounded-md border border-indigo-400/30 px-3 py-1.5
            text-xs text-indigo-200 disabled:opacity-40`}
        >
          Export selected additions
        </button>
        <button
          type="button"
          disabled={selectedPlans.length === 0}
          onClick={() => setRevisionOpen(true)}
          className={`rounded-md bg-indigo-600 px-3 py-1.5 text-xs
            font-medium text-white disabled:opacity-40`}
        >
          Apply selected
        </button>
      </div>
    </div>
  );
}

function PlannedDialogs({ props, state }: { props: Props; state: PanelState }) {
  const {
    exportCards,
    setExportCards,
    revisionOpen,
    selectedPlans,
    collections,
    setRevisionOpen,
    setSelectedIds,
  } = state;
  const { deckId, physicalCount, onChanged } = props;
  return (
    <>
      {exportCards && (
        <CardExportDialog
          title="Export planned additions"
          cards={exportCards}
          onClose={() => setExportCards(null)}
        />
      )}
      <ApplyRevisionDialog
        open={revisionOpen}
        deckId={deckId}
        plans={selectedPlans}
        physicalCount={physicalCount}
        collections={collections}
        onClose={() => setRevisionOpen(false)}
        onApplied={async () => {
          setRevisionOpen(false);
          setSelectedIds(new Set());
          await onChanged();
        }}
      />
    </>
  );
}

function PlannedSummary({
  physicalCount,
  plannedCount,
  planCount,
}: {
  physicalCount: number;
  plannedCount: number;
  planCount: number;
}) {
  return (
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
      <span>
        <span className="text-sm font-semibold text-white">Planned changes</span>
        <span className="ml-2 text-xs text-gray-400">
          {physicalCount} physical → {plannedCount} planned
        </span>
      </span>
      <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-xs text-indigo-200">
        {planCount}
      </span>
    </summary>
  );
}

interface GroupProps {
  title: string;
  tone: "addition" | "cut";
  plans: PlannedDeckChange[];
  collections: CollectionResponse[];
  busyId: string | null;
  deckId: string;
  onRun: (planId: string, action: () => Promise<unknown>) => Promise<void>;
  onExport: (() => void) | undefined;
  selectedIds: Set<string>;
  onToggle: (planId: string) => void;
  onToggleAll: () => void;
}

function PlanGroup({
  title,
  tone,
  plans,
  collections,
  busyId,
  deckId,
  onRun,
  onExport,
  selectedIds,
  onToggle,
  onToggleAll,
}: GroupProps) {
  if (plans.length === 0) return null;
  const titleColor = tone === "addition" ? "text-emerald-300" : "text-red-300";
  return (
    <section>
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <h3 className={`text-[11px] font-semibold uppercase tracking-wide ${titleColor}`}>
          {title}
        </h3>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleAll}
            className="text-[11px] text-gray-400 hover:text-white"
          >
            {plans.every((plan) => selectedIds.has(plan.id)) ? "Clear" : "Select all"}
          </button>
          {onExport && (
            <button
              type="button"
              onClick={onExport}
              className={`rounded border border-emerald-500/30 px-2 py-1 text-[11px]
                font-medium text-emerald-200 hover:border-emerald-400/60 hover:text-white`}
            >
              Export additions
            </button>
          )}
        </div>
      </div>
      <ul className="divide-y divide-white/5 overflow-hidden rounded-lg border border-white/10">
        {plans.map((plan) => (
          <PlanRow
            key={plan.id}
            plan={plan}
            tone={tone}
            collections={collections}
            busy={busyId === plan.id}
            deckId={deckId}
            onRun={onRun}
            selected={selectedIds.has(plan.id)}
            onToggle={() => onToggle(plan.id)}
          />
        ))}
      </ul>
    </section>
  );
}

interface RowProps {
  plan: PlannedDeckChange;
  tone: "addition" | "cut";
  collections: CollectionResponse[];
  busy: boolean;
  deckId: string;
  onRun: GroupProps["onRun"];
  selected: boolean;
  onToggle: () => void;
}

function PlanRow({ plan, tone, collections, busy, deckId, onRun, selected, onToggle }: RowProps) {
  const options = collectionOptions(plan, collections);
  const completeOne = () =>
    onRun(plan.id, () => apiClient.completePlannedChange(deckId, plan.id, 1));
  return (
    <li
      className={`grid items-center gap-2 bg-black/10 px-3 py-2
      sm:grid-cols-[auto_minmax(180px,1fr)_auto_180px_auto]`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        aria-label={`Select ${plan.name} for revision`}
        className="h-4 w-4 accent-indigo-500"
      />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-white">
          <CardHover name={plan.name} imageUri={plan.image_uri}>
            {plan.name}
          </CardHover>
        </p>
        {plan.direction === "addition" ? (
          <div className="mt-1 flex flex-wrap gap-1">
            <OwnedBadge owned={plan.owned_in} />
          </div>
        ) : (
          <p className="text-[10px] text-gray-500">Still in the physical deck</p>
        )}
      </div>
      <PlanQuantityControls
        plan={plan}
        busy={busy}
        onChange={(quantity) =>
          onRun(plan.id, () => apiClient.updatePlannedChange(deckId, plan.id, { quantity }))
        }
      />
      <select
        value={plan.collection_id ?? ""}
        disabled={busy}
        aria-label={
          plan.direction === "addition"
            ? `Take ${plan.name} from collection`
            : `Place ${plan.name} in collection`
        }
        onChange={(event) =>
          void onRun(plan.id, () =>
            apiClient.updatePlannedChange(deckId, plan.id, {
              collection_id: event.target.value || null,
            }),
          )
        }
        className={`min-w-0 rounded-md border border-white/15 bg-gray-900
          px-2 py-1.5 text-xs text-gray-200`}
      >
        <option value="">— No collection</option>
        {options.map((collection) => (
          <option key={collection.id} value={collection.id}>
            {collection.name}
            {plan.direction === "addition" ? ` (${collection.quantity})` : ""}
          </option>
        ))}
      </select>
      <div className="flex justify-end gap-1">
        <button
          type="button"
          disabled={busy}
          title="Complete one physical copy"
          aria-label={`Complete one ${plan.direction} for ${plan.name}`}
          onClick={() => void completeOne()}
          className={`rounded px-2 py-1 text-xs font-medium text-white disabled:opacity-40 ${
            tone === "addition" ? "bg-emerald-700" : "bg-red-700"
          }`}
        >
          ✓
        </button>
        <button
          type="button"
          disabled={busy}
          title="Cancel planned change"
          aria-label={`Cancel planned change for ${plan.name}`}
          onClick={() => void onRun(plan.id, () => apiClient.cancelPlannedChange(deckId, plan.id))}
          className={`rounded px-2 py-1 text-xs text-gray-400
            hover:bg-white/5 hover:text-white disabled:opacity-40`}
        >
          ×
        </button>
      </div>
    </li>
  );
}

function PlanQuantityControls({
  plan,
  busy,
  onChange,
}: {
  plan: PlannedDeckChange;
  busy: boolean;
  onChange: (quantity: number) => Promise<void>;
}) {
  return (
    <div className="flex items-center gap-1 text-xs text-gray-300">
      <button
        type="button"
        disabled={busy || plan.quantity <= 1}
        aria-label={`Decrease planned quantity for ${plan.name}`}
        onClick={() => void onChange(plan.quantity - 1)}
        className="h-6 w-6 rounded border border-white/10 disabled:opacity-30"
      >
        −
      </button>
      <span className="w-7 text-center tabular-nums">{plan.quantity}</span>
      <button
        type="button"
        disabled={busy}
        aria-label={`Increase planned quantity for ${plan.name}`}
        onClick={() => void onChange(plan.quantity + 1)}
        className="h-6 w-6 rounded border border-white/10 disabled:opacity-30"
      >
        +
      </button>
    </div>
  );
}
