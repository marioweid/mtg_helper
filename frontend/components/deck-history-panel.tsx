"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CardHover } from "@/components/card-hover";
import { apiClient, ApiError } from "@/lib/api";
import type { DeckRevision, SnapshotSummary } from "@/lib/types";

interface Props {
  deckId: string;
}

function formatRelativeTime(iso: string): string {
  const minutes = Math.floor(Math.max(0, Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1_440) return `${Math.floor(minutes / 60)}h ago`;
  if (minutes < 43_200) return `${Math.floor(minutes / 1_440)}d ago`;
  return new Date(iso).toLocaleDateString();
}

function CompareLink({
  left,
  right,
  deckId,
  children,
}: {
  left: string;
  right: string;
  deckId: string;
  children: React.ReactNode;
}) {
  const rightKind = right === deckId ? "deck" : "snapshot";
  return (
    <Link
      href={`/decks/compare?left=${left}&left_kind=snapshot&right=${right}&right_kind=${rightKind}`}
      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-indigo-300 hover:bg-indigo-600/10"
    >
      {children}
    </Link>
  );
}

function RevisionItem({
  revision,
  deckId,
  onChanged,
}: {
  revision: DeckRevision;
  deckId: string;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(revision.title);
  const [note, setNote] = useState(revision.note ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await apiClient.updateDeckRevision(revision.id, {
        title: title.trim(),
        note: note.trim() || null,
      });
      setEditing(false);
      await onChanged();
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="rounded-xl border border-white/10 bg-white/5 p-4">
      <summary className="cursor-pointer list-none">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">{revision.title}</h3>
            <p className="mt-1 text-xs text-gray-400">
              {revision.changes.length} change{revision.changes.length === 1 ? "" : "s"} ·{" "}
              {formatRelativeTime(revision.created_at)}
            </p>
          </div>
          <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-indigo-200">
            revision
          </span>
        </div>
      </summary>
      <div className="mt-4 border-t border-white/10 pt-4">
        {editing ? (
          <div className="space-y-2">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              className="w-full rounded border border-white/15 bg-black/40 px-3 py-2 text-sm text-white"
            />
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={2000}
              rows={2}
              className="w-full rounded border border-white/15 bg-black/40 px-3 py-2 text-sm text-white"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={saving || !title.trim()}
                onClick={() => void save()}
                className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-40"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-xs text-gray-400"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm text-gray-300">{revision.note || "No revision note."}</p>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-xs text-gray-400 hover:text-white"
            >
              Edit title/note
            </button>
          </div>
        )}
        <ul className="mt-3 divide-y divide-white/5 rounded-lg border border-white/10 px-3">
          {revision.changes.map((change) => (
            <li
              key={change.card_id}
              className="flex items-center justify-between gap-3 py-2 text-sm"
            >
              <span
                className={change.direction === "addition" ? "text-emerald-300" : "text-red-300"}
              >
                {change.direction === "addition" ? "+" : "−"}
                {change.quantity}{" "}
                <CardHover name={change.card_name} imageUri={change.image_uri}>
                  {change.card_name}
                </CardHover>
              </span>
              <span className="text-xs text-gray-500">
                {change.collection_name ?? "no collection"}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2">
          <CompareLink
            left={revision.before_snapshot_id}
            right={revision.after_snapshot_id}
            deckId={deckId}
          >
            Before → after
          </CompareLink>
          <CompareLink left={revision.after_snapshot_id} right={deckId} deckId={deckId}>
            Compare with current
          </CompareLink>
        </div>
      </div>
    </details>
  );
}

function CheckpointList({
  deckId,
  snapshots,
  onDelete,
}: {
  deckId: string;
  snapshots: SnapshotSummary[];
  onDelete: (id: string) => Promise<void>;
}) {
  if (snapshots.length === 0)
    return <p className="py-4 text-sm text-gray-500">No checkpoints yet.</p>;
  return (
    <ul className="mt-3 space-y-2">
      {snapshots.map((snapshot) => (
        <li
          key={snapshot.id}
          className="flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3"
        >
          <div>
            <p className="text-sm text-white">{snapshot.label || "Untitled checkpoint"}</p>
            <p className="text-xs text-gray-500">
              {snapshot.source === "manual" ? "manual" : "automatic"} · {snapshot.card_count} cards
              · {formatRelativeTime(snapshot.created_at)}
            </p>
          </div>
          <div className="flex gap-2">
            <CompareLink left={snapshot.id} right={deckId} deckId={deckId}>
              Compare
            </CompareLink>
            <button
              type="button"
              onClick={() => void onDelete(snapshot.id)}
              className="text-xs text-gray-400 hover:text-red-300"
            >
              Delete
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DeckHistoryPanel({ deckId }: Props) {
  const [revisions, setRevisions] = useState<DeckRevision[] | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [unrecorded, setUnrecorded] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [revisionRows, snapshotRows] = await Promise.all([
        apiClient.listDeckRevisions(deckId),
        apiClient.listSnapshots(deckId),
      ]);
      setRevisions(revisionRows);
      setSnapshots(snapshotRows);
      if (revisionRows[0]) {
        const comparison = await apiClient.compareDecks(
          { kind: "snapshot", id: revisionRows[0].after_snapshot_id },
          { kind: "deck", id: deckId },
        );
        setUnrecorded(
          comparison.diff.added.length +
            comparison.diff.removed.length +
            comparison.diff.quantity_changed.length,
        );
      } else setUnrecorded(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load deck history");
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  const createCheckpoint = async () => {
    await apiClient.createSnapshot(deckId, label.trim() || null);
    setLabel("");
    await load();
  };

  const deleteCheckpoint = async (id: string) => {
    await apiClient.deleteSnapshot(id);
    await load();
  };

  return (
    <div className="space-y-4">
      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </p>
      )}
      {revisions?.[0] && unrecorded !== null && (
        <div
          className={`rounded-xl border p-3 text-sm ${unrecorded > 0 ? "border-amber-500/30 bg-amber-950/20 text-amber-200" : "border-emerald-500/30 bg-emerald-950/20 text-emerald-200"}`}
        >
          {unrecorded > 0
            ? `${unrecorded} unrecorded card change${unrecorded === 1 ? "" : "s"} since the latest revision.`
            : "Current deck matches the latest revision."}
        </div>
      )}
      <section>
        <h2 className="mb-2 text-sm font-semibold text-white">Deck revisions</h2>
        {revisions === null ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : revisions.length === 0 ? (
          <p className="rounded-xl border border-dashed border-white/20 py-10 text-center text-sm text-gray-500">
            No revisions yet. Apply selected planned changes to create one.
          </p>
        ) : (
          <div className="space-y-2">
            {revisions.map((revision) => (
              <RevisionItem
                key={revision.id}
                revision={revision}
                deckId={deckId}
                onChanged={load}
              />
            ))}
          </div>
        )}
      </section>
      <details className="rounded-xl border border-white/10 bg-white/5 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-white">
          Checkpoints ({snapshots.length})
        </summary>
        <p className="mt-2 text-xs text-gray-400">
          Manual saves and automatic build-stage checkpoints.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            maxLength={200}
            placeholder="Checkpoint label (optional)"
            className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            onClick={() => void createCheckpoint()}
            className="rounded-lg bg-gray-700 px-4 py-2 text-sm text-white"
          >
            Save
          </button>
        </div>
        <CheckpointList deckId={deckId} snapshots={snapshots} onDelete={deleteCheckpoint} />
      </details>
    </div>
  );
}
