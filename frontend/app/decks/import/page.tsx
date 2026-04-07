"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import { getOrCreateAccountId } from "@/lib/account";
import { BRACKET_LABELS } from "@/lib/constants";
import type { DeckImportResponse } from "@/lib/types";

export default function ImportDeckPage() {
  const router = useRouter();
  const [deckList, setDeckList] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [bracket, setBracket] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeckImportResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!deckList.trim()) {
      setError("Please paste a deck list.");
      return;
    }
    if (!name.trim()) {
      setError("Please enter a deck name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const ownerId = await getOrCreateAccountId();
      const imported = await apiClient.importDeck({
        deck_list: deckList,
        name: name.trim(),
        description: description.trim() || null,
        bracket,
        owner_id: ownerId || null,
      });
      setResult(imported);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.");
      setSubmitting(false);
    }
  }

  if (result) {
    const hasWarnings = result.unresolved.length > 0 || result.color_violations.length > 0;
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-2xl font-bold text-white">Import Complete</h1>

        <div className="rounded-xl border border-green-500/30 bg-green-900/10 p-6 mb-4">
          <p className="text-green-400 font-medium text-lg mb-1">
            {result.imported_count} card{result.imported_count !== 1 ? "s" : ""} imported
          </p>
          <p className="text-gray-400 text-sm">
            Deck: <span className="text-white">{result.deck.name}</span>
          </p>
        </div>

        {hasWarnings && (
          <div className="rounded-xl border border-yellow-500/30 bg-yellow-900/10 p-5 mb-4 flex flex-col gap-3">
            {result.unresolved.length > 0 && (
              <div>
                <p className="text-yellow-400 text-sm font-medium mb-1">
                  {result.unresolved.length} card{result.unresolved.length !== 1 ? "s" : ""} not found in database
                </p>
                <ul className="text-xs text-gray-400 list-disc list-inside space-y-0.5">
                  {result.unresolved.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
                <p className="text-xs text-gray-500 mt-1">
                  These cards may not be in your local DB yet. Try syncing cards from the admin panel.
                </p>
              </div>
            )}
            {result.color_violations.length > 0 && (
              <div>
                <p className="text-red-400 text-sm font-medium mb-1">
                  {result.color_violations.length} card{result.color_violations.length !== 1 ? "s" : ""} skipped
                  (color identity violation)
                </p>
                <ul className="text-xs text-gray-400 list-disc list-inside space-y-0.5">
                  {result.color_violations.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <Link
            href={`/decks/${result.deck.id}`}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            View Deck
          </Link>
          <Link
            href={`/decks/${result.deck.id}/chat`}
            className="rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
          >
            Chat About This Deck
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-8 flex items-center gap-3">
        <Link href="/decks" className="text-gray-500 hover:text-gray-300 text-sm transition-colors">
          ← Decks
        </Link>
        <h1 className="text-2xl font-bold text-white">Import Deck</h1>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Deck List</h2>
          <p className="mb-4 text-xs text-gray-500">
            Paste your deck list from Moxfield, MTGO, TappedOut, or any similar format.
            Mark your commander with <code className="text-indigo-400">*CMDR*</code> at the end of the line.
          </p>
          <textarea
            value={deckList}
            onChange={(e) => setDeckList(e.target.value)}
            placeholder={`1 Hazel of the Rootbloom *CMDR*\n\n// Ramp\n1 Sol Ring\n1 Arcane Signet\n\n// Lands\n37 Forest`}
            rows={20}
            spellCheck={false}
            className="w-full rounded-lg border border-white/20 bg-black/20 px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y font-mono"
          />
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 font-semibold text-white">Deck Details</h2>
          <div className="flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm text-gray-400" htmlFor="name">
                Name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Hazel Deck"
                className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm text-gray-400" htmlFor="description">
                Strategy (optional)
              </label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe your strategy or theme..."
                rows={2}
                className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
              />
            </div>
            <div>
              <span className="mb-2 block text-sm text-gray-400">Power Level</span>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {([1, 2, 3, 4] as const).map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => setBracket(b)}
                    className={`rounded-lg border px-3 py-2 text-xs text-left transition-colors ${
                      bracket === b
                        ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                        : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                    }`}
                  >
                    {BRACKET_LABELS[b]}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Importing..." : "Import Deck"}
        </button>
      </form>
    </div>
  );
}
