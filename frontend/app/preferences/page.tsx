"use client";

import { useState, useEffect, useCallback } from "react";
import { getOrCreateAccountId } from "@/lib/account";
import { apiClient } from "@/lib/api";
import { PreferenceForm } from "@/components/preference-form";
import { PreferenceList } from "@/components/preference-list";
import { ToggleSwitch } from "@/components/toggle-switch";
import type { PreferenceResponse, RankingWeightsResponse } from "@/lib/types";

const DEFAULT_WEIGHTS = { semantic: 0.25, synergy: 0.22, popularity: 0.20, personal: 0.15 };

const WEIGHT_LABELS: Record<keyof typeof DEFAULT_WEIGHTS, string> = {
  semantic: "Semantic Match",
  synergy: "Tag Synergy",
  popularity: "EDHREC Popularity",
  personal: "Personal Feedback",
};

const WEIGHT_DESCRIPTIONS: Record<keyof typeof DEFAULT_WEIGHTS, string> = {
  semantic: "How closely a card matches the deck strategy description",
  synergy: "How many relevant tags a card shares with the deck",
  popularity: "How often the card appears in similar decks on EDHREC",
  personal: "Your accept/reject history for this deck",
};

export default function PreferencesPage() {
  const [accountId, setAccountId] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<PreferenceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [boostingToggling, setBoostingToggling] = useState(false);
  const [profileToggling, setProfileToggling] = useState(false);
  const [rankingWeights, setRankingWeights] = useState<RankingWeightsResponse | null>(null);
  const [draftWeights, setDraftWeights] = useState(DEFAULT_WEIGHTS);
  const [weightsSaving, setWeightsSaving] = useState(false);
  const [weightsDirty, setWeightsDirty] = useState(false);

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
        const w = await apiClient.getRankingWeights(id);
        setRankingWeights(w);
        setDraftWeights({ semantic: w.semantic, synergy: w.synergy, popularity: w.popularity, personal: w.personal });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to initialize account");
      } finally {
        setLoading(false);
      }
    }
    void init();
  }, [loadPreferences]);

  function handleWeightChange(key: keyof typeof DEFAULT_WEIGHTS, pct: number) {
    setDraftWeights((prev) => ({ ...prev, [key]: pct / 100 }));
    setWeightsDirty(true);
  }

  async function handleWeightsSave() {
    if (!accountId || weightsSaving) return;
    setWeightsSaving(true);
    try {
      const updated = await apiClient.updateRankingWeights(accountId, draftWeights);
      setRankingWeights(updated);
      setDraftWeights({ semantic: updated.semantic, synergy: updated.synergy, popularity: updated.popularity, personal: updated.personal });
      setWeightsDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save ranking weights");
    } finally {
      setWeightsSaving(false);
    }
  }

  function handleWeightsReset() {
    setDraftWeights(DEFAULT_WEIGHTS);
    setWeightsDirty(true);
  }

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
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-white">Ranking Weights</h2>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleWeightsReset}
              className="rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:text-white transition-colors"
            >
              Reset defaults
            </button>
            <button
              type="button"
              onClick={() => void handleWeightsSave()}
              disabled={!weightsDirty || weightsSaving}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white transition-colors disabled:opacity-40 hover:bg-indigo-500"
            >
              {weightsSaving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
        <p className="mb-5 text-sm text-gray-400">
          Control how much each signal influences card suggestions. Values are auto-normalized.
        </p>
        <div className="flex flex-col gap-5">
          {(Object.keys(DEFAULT_WEIGHTS) as Array<keyof typeof DEFAULT_WEIGHTS>).map((key) => {
            const pct = Math.round((rankingWeights ? draftWeights[key] : DEFAULT_WEIGHTS[key]) * 100);
            return (
              <div key={key}>
                <div className="mb-1.5 flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-white">{WEIGHT_LABELS[key]}</span>
                    <p className="text-xs text-gray-500">{WEIGHT_DESCRIPTIONS[key]}</p>
                  </div>
                  <span className="ml-4 w-10 text-right text-sm tabular-nums text-indigo-300">
                    {pct}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={pct}
                  onChange={(e) => handleWeightChange(key, Number(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>
            );
          })}
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
