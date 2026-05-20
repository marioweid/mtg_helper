"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ManaCost } from "@/components/mana-cost";
import { apiClient, ApiError } from "@/lib/api";
import type {
  ComparisonKind,
  ComparisonSideMeta,
  DeckCompareResponse,
  DeckSummary,
  DiffEntry,
  SnapshotSummary,
} from "@/lib/types";

interface SideState {
  deckId: string | null;
  snapshotId: string | null;
}

function SidePicker({
  label,
  decks,
  state,
  onDeckChange,
  onSnapshotChange,
}: {
  label: string;
  decks: DeckSummary[];
  state: SideState;
  onDeckChange: (deckId: string | null) => void;
  onSnapshotChange: (snapshotId: string | null) => void;
}) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!state.deckId) {
      setSnapshots([]);
      return;
    }
    apiClient
      .listSnapshots(state.deckId)
      .then((rows) => {
        if (!cancelled) setSnapshots(rows);
      })
      .catch(() => {
        if (!cancelled) setSnapshots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [state.deckId]);

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</h3>
      <select
        value={state.deckId ?? ""}
        onChange={(e) => {
          const next = e.target.value || null;
          onDeckChange(next);
          onSnapshotChange(null);
        }}
        className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
      >
        <option value="">— Choose a deck —</option>
        {decks.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
      <select
        value={state.snapshotId ?? ""}
        onChange={(e) => onSnapshotChange(e.target.value || null)}
        disabled={!state.deckId}
        className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none disabled:opacity-50"
      >
        <option value="">Live deck (current state)</option>
        {snapshots.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label || "Untitled"} · {s.source === "manual" ? "manual" : "auto"} ·{" "}
            {new Date(s.created_at).toLocaleDateString()}
          </option>
        ))}
      </select>
    </div>
  );
}

function DiffRow({ entry, side }: { entry: DiffEntry; side: "added" | "removed" | "qty" | "common" }) {
  const accent =
    side === "added"
      ? "border-l-emerald-500/60"
      : side === "removed"
        ? "border-l-red-500/60"
        : side === "qty"
          ? "border-l-amber-500/60"
          : "border-l-white/20";
  return (
    <li
      className={`flex items-center gap-3 border-l-2 ${accent} rounded-r-lg bg-white/5 px-3 py-2`}
    >
      {entry.card.image_uri ? (
        <img
          src={entry.card.image_uri}
          alt=""
          className="h-12 w-9 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="h-12 w-9 shrink-0 rounded bg-zinc-800" />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm text-white">{entry.card.name}</span>
          {entry.card.mana_cost && (
            <span className="text-xs">
              <ManaCost cost={entry.card.mana_cost} />
            </span>
          )}
        </div>
        {entry.card.type_line && (
          <span className="truncate text-xs text-gray-500">{entry.card.type_line}</span>
        )}
      </div>
      <div className="shrink-0 text-xs text-gray-300">
        {side === "qty"
          ? `${entry.left_quantity} → ${entry.right_quantity}`
          : side === "added"
            ? `+${entry.right_quantity}`
            : side === "removed"
              ? `−${entry.left_quantity}`
              : `×${entry.left_quantity}`}
      </div>
    </li>
  );
}

function SideHeader({ side, meta }: { side: "Left" | "Right"; meta: ComparisonSideMeta }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{side}</div>
      <div className="mt-1 text-sm font-medium text-white">{meta.deck_name}</div>
      {meta.label && <div className="text-xs text-indigo-300">snapshot: {meta.label}</div>}
      <div className="mt-1 text-xs text-gray-400">
        stage: {meta.stage} · {meta.card_count} cards
      </div>
    </div>
  );
}

export default function ComparePage() {
  const searchParams = useSearchParams();
  const initialLeft = searchParams.get("left");
  const initialLeftKind = (searchParams.get("left_kind") as ComparisonKind | null) ?? "deck";
  const initialRight = searchParams.get("right");
  const initialRightKind = (searchParams.get("right_kind") as ComparisonKind | null) ?? "deck";

  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [left, setLeft] = useState<SideState>({ deckId: null, snapshotId: null });
  const [right, setRight] = useState<SideState>({ deckId: null, snapshotId: null });
  const [result, setResult] = useState<DeckCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCommon, setShowCommon] = useState(false);
  const [initialResolved, setInitialResolved] = useState(false);

  // Load deck list once.
  useEffect(() => {
    apiClient
      .listDecks({ limit: 100 })
      .then(setDecks)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load decks"));
  }, []);

  // Resolve initial URL params (a snapshot needs its parent deck id).
  useEffect(() => {
    if (initialResolved) return;
    const resolveSide = async (
      id: string | null,
      kind: ComparisonKind,
    ): Promise<SideState> => {
      if (!id) return { deckId: null, snapshotId: null };
      if (kind === "deck") return { deckId: id, snapshotId: null };
      try {
        const snap = await apiClient.getSnapshot(id);
        return { deckId: snap.deck_id, snapshotId: snap.id };
      } catch {
        return { deckId: null, snapshotId: null };
      }
    };
    void Promise.all([
      resolveSide(initialLeft, initialLeftKind),
      resolveSide(initialRight, initialRightKind),
    ]).then(([l, r]) => {
      setLeft(l);
      setRight(r);
      setInitialResolved(true);
    });
  }, [initialLeft, initialLeftKind, initialRight, initialRightKind, initialResolved]);

  const fetchDiff = useCallback(async () => {
    setError(null);
    if (!left.deckId || !right.deckId) {
      setResult(null);
      return;
    }
    const leftSide = left.snapshotId
      ? ({ kind: "snapshot" as const, id: left.snapshotId })
      : ({ kind: "deck" as const, id: left.deckId });
    const rightSide = right.snapshotId
      ? ({ kind: "snapshot" as const, id: right.snapshotId })
      : ({ kind: "deck" as const, id: right.deckId });
    setLoading(true);
    try {
      const r = await apiClient.compareDecks(leftSide, rightSide);
      setResult(r);
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Failed to compare");
    } finally {
      setLoading(false);
    }
  }, [left, right]);

  useEffect(() => {
    void fetchDiff();
  }, [fetchDiff]);

  const diffCounts = useMemo(() => {
    if (!result) return null;
    return {
      added: result.diff.added.length,
      removed: result.diff.removed.length,
      qty: result.diff.quantity_changed.length,
      common: result.diff.common.length,
    };
  }, [result]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Compare decks</h1>
        <p className="mt-1 text-sm text-gray-400">
          Pick two sides. Each can be a deck&apos;s current state or one of its snapshots.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        <SidePicker
          label="Left"
          decks={decks}
          state={left}
          onDeckChange={(deckId) => setLeft({ deckId, snapshotId: null })}
          onSnapshotChange={(snapshotId) => setLeft((s) => ({ ...s, snapshotId }))}
        />
        <SidePicker
          label="Right"
          decks={decks}
          state={right}
          onDeckChange={(deckId) => setRight({ deckId, snapshotId: null })}
          onSnapshotChange={(snapshotId) => setRight((s) => ({ ...s, snapshotId }))}
        />
      </section>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && <div className="text-sm text-gray-500">Comparing…</div>}

      {result && diffCounts && (
        <>
          <section className="grid gap-4 md:grid-cols-2">
            <SideHeader side="Left" meta={result.left} />
            <SideHeader side="Right" meta={result.right} />
          </section>

          <section className="grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-emerald-300">
                Added <span className="text-xs text-gray-500">({diffCounts.added})</span>
              </h2>
              {result.diff.added.length === 0 ? (
                <p className="text-xs text-gray-500">No additions.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {result.diff.added.map((e) => (
                    <DiffRow key={e.card.card_id} entry={e} side="added" />
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-red-300">
                Removed <span className="text-xs text-gray-500">({diffCounts.removed})</span>
              </h2>
              {result.diff.removed.length === 0 ? (
                <p className="text-xs text-gray-500">No removals.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {result.diff.removed.map((e) => (
                    <DiffRow key={e.card.card_id} entry={e} side="removed" />
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-300">
              Quantity changed <span className="text-xs text-gray-500">({diffCounts.qty})</span>
            </h2>
            {result.diff.quantity_changed.length === 0 ? (
              <p className="text-xs text-gray-500">No quantity changes.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {result.diff.quantity_changed.map((e) => (
                  <DiffRow key={e.card.card_id} entry={e} side="qty" />
                ))}
              </ul>
            )}
          </section>

          <section>
            <button
              onClick={() => setShowCommon((v) => !v)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white"
            >
              <span>{showCommon ? "▼" : "▶"}</span>
              Common <span className="text-xs text-gray-500">({diffCounts.common})</span>
            </button>
            {showCommon && (
              <ul className="mt-2 flex flex-col gap-1">
                {result.diff.common.map((e) => (
                  <DiffRow key={e.card.card_id} entry={e} side="common" />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
