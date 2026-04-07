"use client";

import { apiClient } from "@/lib/api";
import type { PreferenceResponse } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  pet_card: "Pet Card",
  avoid_card: "Avoid Card",
  avoid_archetype: "Avoid Archetype",
  general: "General Note",
};

const TYPE_COLORS: Record<string, string> = {
  pet_card: "text-green-400 bg-green-900/20 border-green-500/20",
  avoid_card: "text-red-400 bg-red-900/20 border-red-500/20",
  avoid_archetype: "text-yellow-400 bg-yellow-900/20 border-yellow-500/20",
  general: "text-blue-400 bg-blue-900/20 border-blue-500/20",
};

interface Props {
  accountId: string;
  preferences: PreferenceResponse[];
  onDeleted: () => void;
}

export function PreferenceList({ accountId, preferences, onDeleted }: Props) {
  const displayPreferences = preferences.filter(
    (p) => p.preference_type !== "feedback_boosting",
  );

  if (displayPreferences.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4 text-center">
        No preferences set yet.
      </p>
    );
  }

  async function handleDelete(id: string) {
    try {
      await apiClient.deletePreference(accountId, id);
      onDeleted();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete preference");
    }
  }

  return (
    <ul className="flex flex-col gap-2">
      {displayPreferences.map((pref) => (
        <li
          key={pref.id}
          className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3"
        >
          <span
            className={`rounded border px-2 py-0.5 text-xs font-medium ${
              TYPE_COLORS[pref.preference_type] ?? "text-gray-400 bg-white/5 border-white/10"
            }`}
          >
            {TYPE_LABELS[pref.preference_type] ?? pref.preference_type}
          </span>
          <span className="flex-1 text-sm text-white">
            {pref.card_name ?? pref.description}
          </span>
          <button
            onClick={() => void handleDelete(pref.id)}
            className="text-gray-600 hover:text-red-400 transition-colors text-lg leading-none"
            aria-label="Delete preference"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
