"use client";

import Link from "next/link";
import { useId, useLayoutEffect, useRef, useState } from "react";

import { ComparisonPlanningSummary } from "@/components/comparison-planning-summary";
import type { ComparisonPlannedChange } from "@/lib/comparison";
import type {
  ComparisonSideMeta,
  DeckSummary,
  PlannedChangeBatchItem,
  PlannedDeckChange,
} from "@/lib/types";
import { useComparisonPlanning } from "@/lib/use-comparison-planning";

interface Props {
  title: string;
  changes: ComparisonPlannedChange[];
  decks: DeckSummary[];
  defaultDeck: ComparisonSideMeta;
  onClose: (attempted: boolean) => void;
}

export function ComparisonPlanDialog({ title, changes, decks, defaultDeck, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [deckId, setDeckId] = useState(defaultDeck.deck_id);
  const state = useComparisonPlanning(deckId, changes);
  useLayoutEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
    };
  }, []);
  const dismiss = () => {
    if (state.busy) return;
    dialog.current?.close();
    onClose(state.attempted);
  };
  const choices = decks.some((deck) => deck.id === defaultDeck.deck_id)
    ? decks
    : [{ id: defaultDeck.deck_id, name: defaultDeck.deck_name }, ...decks];
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      className={`m-auto max-h-[90dvh] w-[min(52rem,95vw)] overflow-y-auto rounded-xl
      border border-white/15 bg-zinc-950 p-5 text-gray-200 shadow-2xl backdrop:bg-black/75`}
    >
      <header className="flex items-start justify-between gap-3">
        <h2 id={titleId} className="text-lg font-semibold text-white">
          {title}
        </h2>
        <button
          type="button"
          onClick={dismiss}
          disabled={state.busy}
          className="rounded px-2 py-1 hover:bg-white/10 disabled:opacity-40"
        >
          Close
        </button>
      </header>
      <p className="mt-2 text-xs text-gray-400">
        Use selected left → right deltas as minimum pending quantities. Matching plans aren&apos;t
        duplicated; opposite-direction plans aren&apos;t overwritten. Physical cards and binders
        will not change. Common cards and commander changes are not included.
      </p>
      <PlanningTarget state={state} choices={choices} deckId={deckId} onChange={setDeckId} />
      <ComparisonPlanningSummary changes={changes} />
      <ComparisonPlanningPreview
        changes={changes}
        plans={state.target.deck?.planned_changes ?? []}
        items={state.items}
      />
      {state.error && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          {state.error}
        </p>
      )}
      <footer className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        {state.busy ? (
          <span className="opacity-40">Open target deck</span>
        ) : (
          <Link
            href={`/decks/${deckId}`}
            onClick={dismiss}
            className="text-indigo-300 hover:text-indigo-200"
          >
            Open target deck
          </Link>
        )}
        <button
          type="button"
          disabled={!state.canSubmit}
          onClick={() => void state.submit()}
          className="rounded-lg bg-indigo-600 px-3 py-2 text-white disabled:opacity-40"
        >
          {state.busy ? "Queuing changes…" : state.submitLabel}
        </button>
      </footer>
    </dialog>
  );
}

function PlanningTarget({
  state,
  choices,
  deckId,
  onChange,
}: {
  state: ReturnType<typeof useComparisonPlanning>;
  choices: { id: string; name: string }[];
  deckId: string;
  onChange: (deckId: string) => void;
}) {
  return (
    <>
      <label className="mt-4 block text-sm">
        Target deck
        <select
          value={deckId}
          onChange={(event) => onChange(event.target.value)}
          disabled={state.busy || state.attempted}
          className={`mt-1 w-full rounded border border-white/15 bg-zinc-900
          px-3 py-2 disabled:opacity-50`}
        >
          {choices.map((deck) => (
            <option key={deck.id} value={deck.id}>
              {deck.name}
            </option>
          ))}
        </select>
      </label>
      {state.target.loading && (
        <p role="status" className="mt-3 text-sm">
          Loading target deck…
        </p>
      )}
      {state.target.error && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          {state.target.error}{" "}
          <button type="button" onClick={state.target.reload} className="underline">
            Retry loading
          </button>
        </p>
      )}
      {state.target.deck && (
        <p className="mt-2 text-xs text-gray-500">
          Before queuing: {state.target.deck.physical_card_count} physical /{" "}
          {state.target.deck.planned_card_count} planned cards.
        </p>
      )}
    </>
  );
}

export function ComparisonPlanningPreview({
  changes,
  plans,
  items,
}: {
  changes: ComparisonPlannedChange[];
  plans: PlannedDeckChange[];
  items: PlannedChangeBatchItem[];
}) {
  const results = new Map(items.map((item) => [item.card_scryfall_id, item]));
  return (
    <section aria-label="Planning preview" className="mt-4">
      {items.length > 0 && (
        <p role="status" className="mb-3 text-sm text-indigo-200">
          {items.filter((item) => item.status === "planned").length} planned ·{" "}
          {items.filter((item) => item.status === "unchanged").length} already planned ·{" "}
          {items.filter((item) => item.status === "failed").length} failed
        </p>
      )}
      <ul
        className={`max-h-72 divide-y divide-white/10 overflow-y-auto
        rounded border border-white/10`}
      >
        {changes.map((change) => {
          const result = results.get(change.card_scryfall_id);
          return (
            <li key={change.card_id} className="px-3 py-2 text-sm">
              <p className="text-white">
                {change.direction === "addition" ? "+" : "−"}
                {change.quantity} {change.name}
              </p>
              <p
                className={`mt-1 text-xs ${
                  result?.status === "failed" ? "text-red-300" : "text-gray-400"
                }`}
              >
                {result?.message ?? pendingNote(change, plans)}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function pendingNote(change: ComparisonPlannedChange, plans: PlannedDeckChange[]) {
  const existing = plans.find((plan) => plan.name.toLowerCase() === change.name.toLowerCase());
  if (!existing) return `New pending ${change.direction}: ${change.quantity} copies`;
  if (existing.direction !== change.direction) {
    return `Conflict: ${existing.quantity} pending ${existing.direction} copies; not overwritten`;
  }
  if (existing.quantity >= change.quantity) {
    return `Already planned: ${existing.quantity} pending ${existing.direction} copies`;
  }
  return `Increase pending ${change.direction}: ${existing.quantity} → ${change.quantity}`;
}
