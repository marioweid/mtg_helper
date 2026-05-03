"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CardSearch } from "@/components/card-search";
import { apiClient, ApiError } from "@/lib/api";
import { BRACKET_LABELS } from "@/lib/constants";
import type { CardResponse } from "@/lib/types";

type PricePreset = "budget" | "mid" | "open";

const PRICE_PRESETS: Record<PricePreset, { label: string; cents: number | null; hint: string }> = {
  budget: { label: "Budget", cents: 5000, hint: "≤ €50 per card" },
  mid: { label: "Mid", cents: 20000, hint: "≤ €200 per card" },
  open: { label: "Open", cents: null, hint: "no price cap" },
};

const SPINNER_MESSAGES = [
  "Reading the commander's text…",
  "Picking the synergy spine…",
  "Filling out ramp…",
  "Adding interaction…",
  "Wiring up card draw…",
  "Sprinkling in utility…",
  "Tuning the mana base…",
];

export default function OnboardingPage() {
  const router = useRouter();
  const [commander, setCommander] = useState<CardResponse | null>(null);
  const [partnerOpen, setPartnerOpen] = useState(false);
  const [partner, setPartner] = useState<CardResponse | null>(null);
  const [pricePreset, setPricePreset] = useState<PricePreset>("mid");
  const [bracket, setBracket] = useState(2);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [spinnerIdx, setSpinnerIdx] = useState(0);

  useEffect(() => {
    if (!submitting) return;
    const id = setInterval(() => {
      setSpinnerIdx((i) => (i + 1) % SPINNER_MESSAGES.length);
    }, 4500);
    return () => clearInterval(id);
  }, [submitting]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!commander) {
      setError("Pick a commander first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSpinnerIdx(0);
    try {
      const res = await apiClient.quickstart({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        bracket,
        max_price_cents: PRICE_PRESETS[pricePreset].cents,
      });
      router.push(`/decks/${res.deck.id}/build`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Quickstart failed.";
      setError(message);
      setSubmitting(false);
    }
  }

  if (submitting) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center justify-center py-24 text-center">
        <div className="mb-6 h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        <h1 className="mb-2 text-2xl font-bold text-white">Building your sample deck</h1>
        <p className="mb-1 text-sm text-gray-400">{SPINNER_MESSAGES[spinnerIdx]}</p>
        <p className="text-xs text-gray-500">This usually takes 30–60 seconds.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-8 flex items-center gap-3">
        <Link href="/decks" className="text-gray-500 hover:text-gray-300 text-sm transition-colors">
          ← Decks
        </Link>
        <h1 className="text-2xl font-bold text-white">Quickstart</h1>
      </div>

      <p className="mb-6 text-sm text-gray-400">
        Pick a commander and we&apos;ll generate a complete draft deck in about a minute.
        You can then review and swap any card in the build wizard.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Commander</h2>
          <p className="mb-4 text-xs text-gray-500">
            Search any commander-legal legendary creature.
          </p>
          <CardSearch
            placeholder="Search for a commander..."
            commanderLegal
            typeFilter="Legendary Creature"
            selected={commander}
            onSelect={setCommander}
            onClear={() => setCommander(null)}
          />

          <div className="mt-4">
            {!partnerOpen ? (
              <button
                type="button"
                onClick={() => setPartnerOpen(true)}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                + Add a partner
              </button>
            ) : (
              <>
                <p className="mb-2 text-xs text-gray-500">Partner (optional)</p>
                <CardSearch
                  placeholder="Search partner..."
                  commanderLegal
                  typeFilter="Legendary Creature"
                  selected={partner}
                  onSelect={setPartner}
                  onClear={() => {
                    setPartner(null);
                    setPartnerOpen(false);
                  }}
                />
              </>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Budget</h2>
          <p className="mb-4 text-xs text-gray-500">
            Caps the price per card. Persists on the deck so manual stage rebuilds inherit it.
          </p>
          <div className="grid grid-cols-3 gap-2">
            {(Object.keys(PRICE_PRESETS) as PricePreset[]).map((key) => {
              const preset = PRICE_PRESETS[key];
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setPricePreset(key)}
                  className={`rounded-lg border px-3 py-3 text-left transition-colors ${
                    pricePreset === key
                      ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                      : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                  }`}
                >
                  <div className="text-sm font-medium">{preset.label}</div>
                  <div className="text-xs text-gray-500">{preset.hint}</div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Power Level</h2>
          <p className="mb-4 text-xs text-gray-500">
            Bracket 2 (Upgraded) gives a precon-friendly draft you can iterate on.
          </p>
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
        </section>

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={!commander}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Build my deck
        </button>
      </form>
    </div>
  );
}
