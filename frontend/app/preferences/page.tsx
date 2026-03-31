"use client";

import { useState, useEffect, useCallback } from "react";
import { getOrCreateAccountId } from "@/lib/account";
import { apiClient } from "@/lib/api";
import { PreferenceForm } from "@/components/preference-form";
import { PreferenceList } from "@/components/preference-list";
import type { PreferenceResponse } from "@/lib/types";

export default function PreferencesPage() {
  const [accountId, setAccountId] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<PreferenceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPreferences = useCallback(async (id: string) => {
    try {
      const prefs = await apiClient.listPreferences(id);
      setPreferences(prefs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load preferences");
    }
  }, []);

  useEffect(() => {
    async function init() {
      try {
        const id = await getOrCreateAccountId();
        setAccountId(id);
        await loadPreferences(id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to initialize account");
      } finally {
        setLoading(false);
      }
    }
    void init();
  }, [loadPreferences]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">Loading...</div>
    );
  }

  if (error) {
    return (
      <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
        {error}
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-8 text-2xl font-bold text-white">Preferences</h1>
      <p className="mb-6 text-sm text-gray-400">
        Preferences are injected into every AI prompt to customize deck suggestions.
      </p>

      <section className="mb-8 rounded-xl border border-white/10 bg-white/5 p-6">
        <h2 className="mb-4 font-semibold text-white">Add Preference</h2>
        {accountId && (
          <PreferenceForm
            accountId={accountId}
            onCreated={() => accountId && void loadPreferences(accountId)}
          />
        )}
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h2 className="mb-4 font-semibold text-white">Your Preferences</h2>
        {accountId && (
          <PreferenceList
            accountId={accountId}
            preferences={preferences}
            onDeleted={() => void loadPreferences(accountId)}
          />
        )}
      </section>
    </div>
  );
}
