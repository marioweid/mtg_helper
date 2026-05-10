"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { BRACKET_LABELS } from "@/lib/constants";
import type { DeckImportResponse } from "@/lib/types";

/** Cache the import-time suggested archetype tags so the keyword step can read them. */
function stashSuggestedTags(deckId: string, tags: string[]): void {
  if (typeof window === "undefined" || tags.length === 0) return;
  try {
    sessionStorage.setItem(`import-suggested-tags:${deckId}`, JSON.stringify(tags));
  } catch {
    // sessionStorage can throw in private mode; suggestions are optional.
  }
}

type Mode = "text" | "url";

export default function ImportDeckPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("text");

  // Shared
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [bracket, setBracket] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeckImportResponse | null>(null);

  // Text mode
  const [deckList, setDeckList] = useState("");

  // URL mode
  const [url, setUrl] = useState("");

  async function submitText(e: React.FormEvent) {
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
      const imported = await apiClient.importDeck({
        deck_list: deckList,
        name: name.trim(),
        description: description.trim() || null,
        bracket,
      });
      setResult(imported);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.");
      setSubmitting(false);
    }
  }

  async function submitUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) {
      setError("Please paste a Moxfield or Archidekt URL.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const imported = await apiClient.importDeckUrl({
        url: url.trim(),
        name: name.trim() || null,
        description: description.trim() || null,
        bracket,
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
          <button
            type="button"
            onClick={() => {
              stashSuggestedTags(result.deck.id, result.suggested_archetype_tags);
              router.push(`/decks/${result.deck.id}/keywords?from=import`);
            }}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            Set keywords
          </button>
          <Link
            href={`/decks/${result.deck.id}`}
            className="rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-medium text-gray-300 transition-colors hover:bg-white/10"
          >
            Skip — view deck
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

      <div className="mb-6 inline-flex rounded-lg border border-white/10 bg-white/5 p-1">
        {(["url", "text"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              setError(null);
            }}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              mode === m
                ? "bg-indigo-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {m === "url" ? "From URL" : "Paste Text"}
          </button>
        ))}
      </div>

      <form onSubmit={mode === "url" ? submitUrl : submitText} className="flex flex-col gap-6">
        {mode === "url" ? (
          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h2 className="mb-1 font-semibold text-white">Deck URL</h2>
            <p className="mb-4 text-xs text-gray-500">
              Paste a public Moxfield or Archidekt deck URL. The deck name and
              description will be taken from the source unless you override below.
            </p>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.moxfield.com/decks/abc123"
              className="w-full rounded-lg border border-white/20 bg-black/20 px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
            />
          </section>
        ) : (
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
        )}

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 font-semibold text-white">Deck Details</h2>
          <div className="flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm text-gray-400" htmlFor="name">
                Name {mode === "url" && <span className="text-gray-600">(optional — falls back to source name)</span>}
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={mode === "url" ? "Override (optional)" : "My Hazel Deck"}
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
          {submitting ? "Importing..." : mode === "url" ? "Import from URL" : "Import Deck"}
        </button>
      </form>
    </div>
  );
}
