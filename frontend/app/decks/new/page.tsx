"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CardSearch } from "@/components/card-search";
import { apiClient } from "@/lib/api";
import { getOrCreateAccountId } from "@/lib/account";
import { BRACKET_LABELS } from "@/lib/constants";
import type { CardResponse } from "@/lib/types";

export default function NewDeckPage() {
  const router = useRouter();
  const [commander, setCommander] = useState<CardResponse | null>(null);
  const [partner, setPartner] = useState<CardResponse | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [bracket, setBracket] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!commander) {
      setError("Please select a commander.");
      return;
    }
    if (!name.trim()) {
      setError("Please enter a deck name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const ownerId = await getOrCreateAccountId();
      const deck = await apiClient.createDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        name: name.trim(),
        description: description.trim() || null,
        bracket,
        owner_id: ownerId || null,
      });
      router.push(`/decks/${deck.id}/build`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deck.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-8 text-2xl font-bold text-white">New Deck</h1>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 font-semibold text-white">Commander</h2>
          <CardSearch
            placeholder="Search for your commander..."
            typeFilter="Legendary Creature"
            onSelect={(card) => {
              setCommander(card);
              if (!name) setName(`${card.name} Deck`);
            }}
            selected={commander}
            onClear={() => setCommander(null)}
          />
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Partner Commander</h2>
          <p className="mb-4 text-xs text-gray-500">Optional — only for commanders with Partner</p>
          <CardSearch
            placeholder="Search for partner commander..."
            typeFilter="Legendary Creature"
            onSelect={setPartner}
            selected={partner}
            onClear={() => setPartner(null)}
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
                placeholder="My Awesome Deck"
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
                rows={3}
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
          {submitting ? "Creating..." : "Create Deck & Start Building"}
        </button>
      </form>
    </div>
  );
}
