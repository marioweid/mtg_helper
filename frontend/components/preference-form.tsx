"use client";

import { useState } from "react";
import { CardSearch } from "@/components/card-search";
import { apiClient } from "@/lib/api";
import type { CardResponse, PreferenceType } from "@/lib/types";

interface Props {
  accountId: string;
  onCreated: () => void;
}

const TYPES: { value: PreferenceType; label: string }[] = [
  { value: "pet_card", label: "Pet Card" },
  { value: "avoid_card", label: "Avoid Card" },
  { value: "avoid_archetype", label: "Avoid Archetype" },
  { value: "general", label: "General Note" },
];

export function PreferenceForm({ accountId, onCreated }: Props) {
  const [type, setType] = useState<PreferenceType>("pet_card");
  const [card, setCard] = useState<CardResponse | null>(null);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsCard = type === "pet_card" || type === "avoid_card";
  const needsText = type === "avoid_archetype" || type === "general";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (needsCard && !card) {
      setError("Please select a card.");
      return;
    }
    if (needsText && !description.trim()) {
      setError("Please enter a description.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.createPreference(accountId, {
        preference_type: type,
        card_scryfall_id: needsCard && card ? card.scryfall_id : null,
        description: needsText ? description.trim() : null,
      });
      setCard(null);
      setDescription("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save preference.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => {
              setType(t.value);
              setCard(null);
              setDescription("");
              setError(null);
            }}
            className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
              type === t.value
                ? "bg-indigo-600 text-white"
                : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {needsCard && (
        <CardSearch
          placeholder={`Search for card to ${type === "pet_card" ? "always include" : "avoid"}...`}
          onSelect={setCard}
          selected={card}
          onClear={() => setCard(null)}
        />
      )}

      {needsText && (
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={
            type === "avoid_archetype" ? "e.g. stax, land destruction" : "e.g. prefer synergy over power"
          }
          className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
      >
        {submitting ? "Saving..." : "Add Preference"}
      </button>
    </form>
  );
}
