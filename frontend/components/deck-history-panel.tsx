"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type { SnapshotSummary } from "@/lib/types";

interface Props {
  deckId: string;
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function DeckHistoryPanel({ deckId }: Props) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [labelDraft, setLabelDraft] = useState("");

  const load = useCallback(async () => {
    try {
      const rows = await apiClient.listSnapshots(deckId);
      setSnapshots(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load snapshots");
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await apiClient.createSnapshot(deckId, labelDraft.trim() || null);
      setLabelDraft("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create snapshot");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (snapshotId: string) => {
    try {
      await apiClient.deleteSnapshot(snapshotId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete snapshot");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h3 className="mb-2 text-sm font-semibold text-white">Save snapshot</h3>
        <p className="mb-3 text-xs text-gray-400">
          A snapshot records the deck&apos;s current cards and metadata. Auto-snapshots are also created
          when the build wizard advances a stage.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={labelDraft}
            onChange={(e) => setLabelDraft(e.target.value)}
            placeholder="Label (optional)"
            maxLength={200}
            className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            onClick={() => void handleCreate()}
            disabled={creating}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
          >
            {creating ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {snapshots === null ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-center text-sm text-gray-500">
          Loading…
        </div>
      ) : snapshots.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/20 py-12 text-center text-gray-500">
          No snapshots yet.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {snapshots.map((snap) => (
            <li
              key={snap.id}
              className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-white/5 p-4"
            >
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-white">
                    {snap.label || "Untitled snapshot"}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                      snap.source === "manual"
                        ? "bg-indigo-600/20 text-indigo-300"
                        : "bg-gray-600/20 text-gray-300"
                    }`}
                  >
                    {snap.source === "manual" ? "manual" : "auto"}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span>stage: {snap.stage}</span>
                  <span>·</span>
                  <span>{snap.card_count} cards</span>
                  <span>·</span>
                  <span>{formatRelativeTime(snap.created_at)}</span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Link
                  href={`/decks/compare?left=${snap.id}&left_kind=snapshot&right=${deckId}&right_kind=deck`}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-indigo-300 transition-colors hover:bg-indigo-600/10"
                >
                  Compare with current
                </Link>
                <button
                  onClick={() => void handleDelete(snap.id)}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:border-red-500/40 hover:text-red-300"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
