"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ArchetypeChipPicker } from "@/components/archetype-chip-picker";
import { CardSearch } from "@/components/card-search";
import { PageHeader } from "@/components/page-header";
import { apiClient } from "@/lib/api";
import { BRACKET_LABELS } from "@/lib/constants";
import type { CardResponse } from "@/lib/types";

export default function KeywordMenuPage() {
  const router = useRouter();

  const [commander, setCommander] = useState<CardResponse | null>(null);
  const [partner, setPartner] = useState<CardResponse | null>(null);
  const [bracket, setBracket] = useState(3);
  const [archetypeTags, setArchetypeTags] = useState<string[]>([]);
  const [deckName, setDeckName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function createDeck() {
    if (!commander) {
      setError("Pick a commander first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const deck = await apiClient.createDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        name: deckName.trim() || `${commander.name} Deck`,
        bracket,
        archetype_tags: archetypeTags,
      });
      router.push(`/decks/${deck.id}/build`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deck.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <button
        type="button"
        onClick={() => router.push("/decks/new")}
        className="mb-4 inline-block text-sm text-gray-500 transition-colors hover:text-gray-300"
      >
        ← Back
      </button>
      <PageHeader
        title="Pick keywords"
        subtitle="Pick the official MTGJSON keywords your deck cares about. Suggestions in the build wizard will favour cards that share these tags."
      />

      <div className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 font-semibold text-white">Commander</h2>
          <CardSearch
            placeholder="Search for your commander..."
            typeFilter="Legendary Creature"
            onSelect={setCommander}
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
          <span className="mb-2 block text-sm font-semibold text-white">Power Level</span>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([1, 2, 3, 4] as const).map((b) => (
              <button
                key={b}
                type="button"
                onClick={() => setBracket(b)}
                className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  bracket === b
                    ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                    : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                }`}
              >
                {BRACKET_LABELS[b]}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-3 font-semibold text-white">MTGJSON keywords</h2>
          <ArchetypeChipPicker value={archetypeTags} onChange={setArchetypeTags} />
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <label htmlFor="deck-name" className="mb-1.5 block text-sm font-semibold text-white">
            Deck name
          </label>
          <input
            id="deck-name"
            type="text"
            value={deckName}
            onChange={(e) => setDeckName(e.target.value)}
            placeholder={commander ? `${commander.name} Deck` : "My new deck"}
            className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </section>

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={() => void createDeck()}
          disabled={!commander || submitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Creating..." : "Create deck & start building"}
        </button>
      </div>
    </div>
  );
}
