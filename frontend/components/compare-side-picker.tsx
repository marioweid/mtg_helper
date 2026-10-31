"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { ComparisonSelection } from "@/lib/comparison";
import type { DeckSummary, SnapshotSummary } from "@/lib/types";

export function CompareSidePicker({
  label,
  decks,
  value,
  onChange,
}: {
  label: string;
  decks: DeckSummary[];
  value: ComparisonSelection;
  onChange: (selection: ComparisonSelection) => void;
}) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setSnapshots([]);
    setError("");
    if (!value.deckId) return;
    void apiClient
      .listSnapshots(value.deckId)
      .then((items) => {
        if (active) setSnapshots(items);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load snapshots");
      });
    return () => {
      active = false;
    };
  }, [value.deckId, attempt]);
  const stateValue = value.kind === "snapshot" ? `snapshot:${value.snapshotId}` : value.kind;
  function changeState(next: string) {
    if (next.startsWith("snapshot:")) {
      onChange({ ...value, kind: "snapshot", snapshotId: next.slice(9) });
    } else {
      onChange({ ...value, kind: next === "planned" ? "planned" : "deck", snapshotId: null });
    }
  }
  return (
    <fieldset className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
      <legend className="px-1 text-xs font-semibold uppercase text-gray-400">{label}</legend>
      <label className="text-xs text-gray-400">
        Deck
        <select
          aria-label={`${label} deck`}
          value={value.deckId ?? ""}
          onChange={(event) =>
            onChange({ deckId: event.target.value || null, kind: "deck", snapshotId: null })
          }
          className={`mt-1 w-full rounded-lg border border-white/10
            bg-zinc-900 px-3 py-2 text-sm text-white`}
        >
          <option value="">Choose a deck</option>
          {decks.map((deck) => (
            <option key={deck.id} value={deck.id}>
              {deck.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-gray-400">
        Composition
        <select
          aria-label={`${label} composition`}
          value={stateValue}
          disabled={!value.deckId}
          onChange={(event) => changeState(event.target.value)}
          className={`mt-1 w-full rounded-lg border border-white/10 bg-zinc-900
            px-3 py-2 text-sm text-white disabled:opacity-50`}
        >
          <option value="deck">Physical deck</option>
          <option value="planned">Planned deck (additions − cuts)</option>
          <optgroup label="Snapshots">
            {snapshots.map((snapshot) => (
              <option key={snapshot.id} value={`snapshot:${snapshot.id}`}>
                {snapshot.label || "Untitled"} ·{" "}
                {new Date(snapshot.created_at).toLocaleDateString()}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      {error && (
        <p role="alert" className="text-xs text-red-300">
          {error}{" "}
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="underline"
          >
            Retry
          </button>
        </p>
      )}
    </fieldset>
  );
}
