"use client";

import { useState } from "react";
import { ApiError, apiClient } from "@/lib/api";
import { BracketValidationPanel } from "@/components/bracket-validation-panel";
import { BRACKET_LABELS } from "@/lib/constants";
import type { BracketValidationResponse } from "@/lib/types";

interface Props {
  deckId: string;
  bracket: number | null;
  onBracketChange: (bracket: number) => void;
}

const BRACKETS = [1, 2, 3, 4, 5] as const;

export function BracketSelector({ deckId, bracket, onBracketChange }: Props) {
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<BracketValidationResponse | null>(null);

  async function handleBracketChange(next: number) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.updateDeck(deckId, { bracket: next });
      onBracketChange(next);
      // Invalidate stale validation so the user re-checks against the new bracket.
      setValidation(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update bracket");
    } finally {
      setSaving(false);
    }
  }

  async function handleCheck() {
    setChecking(true);
    setError(null);
    try {
      const result = await apiClient.getBracketValidation(deckId);
      setValidation(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to check legality");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs uppercase tracking-wide text-gray-400">Bracket</label>
        <select
          value={bracket ?? ""}
          onChange={(e) => void handleBracketChange(Number(e.target.value))}
          disabled={saving}
          className="rounded-md border border-white/10 bg-black/40 px-2 py-1 text-sm text-white disabled:opacity-50"
        >
          {bracket == null && <option value="">—</option>}
          {BRACKETS.map((b) => (
            <option key={b} value={b}>
              {BRACKET_LABELS[b]}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void handleCheck()}
          disabled={checking || bracket == null}
          className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          title="Check whether the deck meets every rule for the selected bracket"
        >
          {checking ? "Checking…" : "Check legality"}
        </button>
        {saving && <span className="text-xs text-gray-500">Saving…</span>}
      </div>

      {error && (
        <div className="mt-2 rounded border border-red-500/40 bg-red-900/20 px-2 py-1 text-xs text-red-300">
          {error}
        </div>
      )}

      {validation && (
        <div className="mt-2">
          <BracketValidationPanel validation={validation} />
        </div>
      )}
    </div>
  );
}
