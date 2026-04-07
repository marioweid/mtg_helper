"use client";

import { useState, useEffect, useCallback } from "react";
import { getOrCreateAccountId } from "@/lib/account";
import { apiClient } from "@/lib/api";
import { PreferenceForm } from "@/components/preference-form";
import { PreferenceList } from "@/components/preference-list";
import { ToggleSwitch } from "@/components/toggle-switch";
import type { PreferenceResponse } from "@/lib/types";

export default function PreferencesPage() {
  const [accountId, setAccountId] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<PreferenceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [boostingToggling, setBoostingToggling] = useState(false);
  const [profileToggling, setProfileToggling] = useState(false);

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

  const boostingPref = preferences.find(
    (p) => p.preference_type === "feedback_boosting",
  );
  const isBoosting = boostingPref !== undefined;

  const profilePref = preferences.find(
    (p) => p.preference_type === "user_profile_boosting",
  );
  const isProfileEnabled = profilePref !== undefined;

  async function handleProfileToggle() {
    if (!accountId || profileToggling) return;
    setProfileToggling(true);
    try {
      if (profilePref) {
        await apiClient.deletePreference(accountId, profilePref.id);
      } else {
        await apiClient.createPreference(accountId, {
          preference_type: "user_profile_boosting",
        });
      }
      await loadPreferences(accountId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle profile boosting");
    } finally {
      setProfileToggling(false);
    }
  }

  async function handleBoostingToggle() {
    if (!accountId || boostingToggling) return;
    setBoostingToggling(true);
    try {
      if (boostingPref) {
        await apiClient.deletePreference(accountId, boostingPref.id);
      } else {
        await apiClient.createPreference(accountId, {
          preference_type: "feedback_boosting",
        });
      }
      await loadPreferences(accountId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle boosting");
    } finally {
      setBoostingToggling(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-8 text-2xl font-bold text-white">Preferences</h1>
      <p className="mb-6 text-sm text-gray-400">
        Preferences are injected into every AI prompt to customize deck suggestions.
      </p>

      <section className="mb-8 rounded-xl border border-white/10 bg-white/5 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-white">Feedback Boosting</h2>
            <p className="mt-1 text-sm text-gray-400">
              Re-rank AI suggestions based on your thumbs up/down and pet/avoid card
              preferences.
            </p>
          </div>
          <ToggleSwitch
            enabled={isBoosting}
            onToggle={() => void handleBoostingToggle()}
            disabled={boostingToggling}
          />
        </div>
      </section>

      <section className="mb-8 rounded-xl border border-white/10 bg-white/5 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-white">Profile-Based Suggestions</h2>
            <p className="mt-1 text-sm text-gray-400">
              Subtly influence suggestions using patterns from your other decks — tags you favour
              and cards you&apos;ve rated across your collection.
            </p>
          </div>
          <ToggleSwitch
            enabled={isProfileEnabled}
            onToggle={() => void handleProfileToggle()}
            disabled={profileToggling}
          />
        </div>
      </section>

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
