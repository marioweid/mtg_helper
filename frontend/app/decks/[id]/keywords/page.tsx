"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { ArchetypeChipPicker } from "@/components/archetype-chip-picker";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/skeleton";
import { apiClient } from "@/lib/api";
import type { DeckDetailResponse } from "@/lib/types";

/** Read + clear the import-time suggested tags stashed by the import flow. */
function takeSuggestedTags(deckId: string): string[] {
  if (typeof window === "undefined") return [];
  const key = `import-suggested-tags:${deckId}`;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    sessionStorage.removeItem(key);
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((t): t is string => typeof t === "string");
    }
    return [];
  } catch {
    return [];
  }
}

export default function DeckKeywordsPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const fromImport = searchParams.get("from") === "import";

  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [archetypeTags, setArchetypeTags] = useState<string[]>([]);
  const [suggested, setSuggested] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getDeck(params.id)
      .then((d) => {
        if (cancelled) return;
        setDeck(d);
        setArchetypeTags(d.archetype_tags ?? []);
        if (fromImport) {
          const stashed = takeSuggestedTags(params.id);
          setSuggested(stashed);
          // Pre-select the suggestions on first arrival from import.
          if ((d.archetype_tags ?? []).length === 0 && stashed.length > 0) {
            setArchetypeTags(stashed);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load deck.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id, fromImport]);

  async function save() {
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.updateDeck(params.id, { archetype_tags: archetypeTags });
      router.push(`/decks/${params.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save keywords.");
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-6 w-full max-w-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }
  if (!deck) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error ?? "Deck not found."}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link
        href={`/decks/${deck.id}`}
        className="mb-4 inline-block text-sm text-gray-500 transition-colors hover:text-gray-300"
      >
        ← {deck.name}
      </Link>
      <PageHeader
        title={fromImport ? "Set keywords for your imported deck" : "Edit deck keywords"}
        subtitle={
          fromImport
            ? "We pre-selected the most common EDHREC themes from your imported cards. Adjust the chips so future suggestions stay on-theme."
            : "Adjust the EDHREC themes that drive AI card suggestions for this deck."
        }
      />

      {fromImport && (
        <div className="mb-6 rounded-lg border border-indigo-500/30 bg-indigo-900/10 p-4 text-sm text-indigo-200">
          Prefer the conversational route?{" "}
          <Link
            href={`/decks/new/agent?deck_id=${deck.id}`}
            className="underline hover:text-indigo-100"
          >
            Chat with the agent instead
          </Link>{" "}
          — it will pick chips for you.
        </div>
      )}

      <section className="rounded-xl border border-white/10 bg-white/5 p-6">
        <ArchetypeChipPicker
          value={archetypeTags}
          onChange={setArchetypeTags}
          suggested={suggested}
        />
      </section>

      {error && (
        <p className="mt-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </p>
      )}

      <div className="mt-6 flex gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Saving..." : "Save keywords"}
        </button>
        <Link
          href={`/decks/${deck.id}`}
          className="rounded-lg border border-white/20 bg-white/5 px-6 py-3 font-medium text-gray-300 transition-colors hover:bg-white/10"
        >
          Skip
        </Link>
      </div>
    </div>
  );
}
