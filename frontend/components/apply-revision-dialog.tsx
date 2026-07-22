"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient, ApiError } from "@/lib/api";
import type { CollectionResponse, PlannedDeckChange } from "@/lib/types";

interface Props {
  deckId: string;
  plans: PlannedDeckChange[];
  physicalCount: number;
  collections: CollectionResponse[];
  open: boolean;
  onClose: () => void;
  onApplied: () => void | Promise<void>;
}

function defaultTitle(plans: PlannedDeckChange[]): string {
  if (plans.length === 1) {
    return `${plans[0]?.direction === "addition" ? "Added" : "Cut"} ${plans[0]?.name ?? "card"}`;
  }
  const additions = plans.filter((plan) => plan.direction === "addition").length;
  const cuts = plans.length - additions;
  if (cuts === 0) return `Applied ${additions} additions`;
  if (additions === 0) return `Applied ${cuts} cuts`;
  return `Applied ${additions} additions and ${cuts} cuts`;
}

export function ApplyRevisionDialog({
  deckId,
  plans,
  physicalCount,
  collections,
  open,
  onClose,
  onApplied,
}: Props) {
  const generatedTitle = useMemo(() => defaultTitle(plans), [plans]);
  const [title, setTitle] = useState(generatedTitle);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTitle(generatedTitle);
      setNote("");
      setError(null);
    }
  }, [generatedTitle, open]);

  if (!open) return null;
  const delta = plans.reduce(
    (sum, plan) => sum + (plan.direction === "addition" ? plan.quantity : -plan.quantity),
    0,
  );

  const apply = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.applyDeckRevision(deckId, {
        title: title.trim(),
        note: note.trim() || null,
        plan_ids: plans.map((plan) => plan.id),
      });
      await onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to apply deck revision");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="revision-title" className="w-full max-w-lg rounded-xl border border-white/15 bg-gray-950 p-5 shadow-2xl">
        <h2 id="revision-title" className="text-lg font-semibold text-white">Apply deck revision</h2>
        <p className="mt-1 text-xs text-gray-400">
          {plans.length} selected change{plans.length === 1 ? "" : "s"} · {physicalCount} → {physicalCount + delta} physical cards
        </p>
        <ul className="mt-4 max-h-44 space-y-1 overflow-y-auto rounded-lg border border-white/10 p-3 text-sm">
          {plans.map((plan) => (
            <li key={plan.id} className="flex justify-between gap-3 text-gray-300">
              <span>{plan.direction === "addition" ? "+" : "−"}{plan.quantity} {plan.name}</span>
              <span className="text-xs text-gray-500">{plan.collection_id ? plan.owned_in.find((item) => item.id === plan.collection_id)?.name ?? collections.find((item) => item.id === plan.collection_id)?.name ?? "collection" : "no collection"}</span>
            </li>
          ))}
        </ul>
        <label className="mt-4 block text-xs font-medium text-gray-300">
          Revision title
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className="mt-1 w-full rounded-lg border border-white/15 bg-black/40 px-3 py-2 text-sm text-white" />
        </label>
        <label className="mt-3 block text-xs font-medium text-gray-300">
          Note (optional)
          <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={3} className="mt-1 w-full resize-none rounded-lg border border-white/15 bg-black/40 px-3 py-2 text-sm text-white" />
        </label>
        {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-300">Cancel</button>
          <button type="button" onClick={() => void apply()} disabled={saving || !title.trim()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
            {saving ? "Applying…" : "Apply revision"}
          </button>
        </div>
      </div>
    </div>
  );
}
