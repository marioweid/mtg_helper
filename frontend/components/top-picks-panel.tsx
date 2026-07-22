"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { OwnedBadge } from "@/components/owned-badge";
import { apiClient, ApiError } from "@/lib/api";
import type { TopPickCard, TopPicksResponse, TopPickSource } from "@/lib/types";

interface Props {
  deckId: string;
  onPlanChanged: () => void | Promise<void>;
}

const SOURCES: readonly TopPickSource[] = ["combined", "moxfield", "archidekt"];

function formatPrice(cents: number | null): string {
  return cents === null ? "—" : `€${(cents / 100).toFixed(2)}`;
}

function formatCacheTime(value: string | null): string {
  if (!value) return "not cached";
  return new Date(value).toLocaleDateString();
}

export function TopPicksPanel({ deckId, onPlanChanged }: Props) {
  const [source, setSource] = useState<TopPickSource>("combined");
  const [result, setResult] = useState<TopPicksResponse | null>(null);
  const [query, setQuery] = useState("");
  const [hideInDeck, setHideInDeck] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await apiClient.getTopPicks(deckId, source));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load commander top picks");
    } finally {
      setLoading(false);
    }
  }, [deckId, source]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return (result?.picks ?? []).filter(
      (pick) =>
        (!hideInDeck || pick.physical_quantity === 0) &&
        (!needle || pick.name.toLocaleLowerCase().includes(needle)),
    );
  }, [hideInDeck, query, result]);

  const planAddition = async (pick: TopPickCard) => {
    setBusyId(pick.card_id);
    setError(null);
    try {
      await apiClient.planCard(deckId, {
        card_scryfall_id: pick.scryfall_id,
        direction: "addition",
        quantity: 1,
        categories: ["theme"],
        added_by: "user",
      });
      await onPlanChanged();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to plan card addition");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <TopPicksHeader result={result} />
      <TopPicksControls
        source={source}
        query={query}
        hideInDeck={hideInDeck}
        onSourceChange={setSource}
        onQueryChange={setQuery}
        onHideInDeckChange={setHideInDeck}
      />
      <TopPicksResults
        error={error}
        loading={loading}
        visible={visible}
        hasPicks={Boolean(result?.picks.length)}
        busyId={busyId}
        onRetry={() => void load()}
        onPlan={(pick) => void planAddition(pick)}
      />
    </div>
  );
}

function TopPicksHeader({ result }: { result: TopPicksResponse | null }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h2 className="text-base font-semibold text-white">
        Top picks for {result?.commander_name ?? "this commander"}
      </h2>
      <p className="mt-1 text-xs text-gray-400">
        Common cards from highly visible public commander decks. Evidence is cached for 28 days.
      </p>
      {result && <SourceSummaries result={result} />}
    </div>
  );
}

interface TopPicksControlsProps {
  source: TopPickSource;
  query: string;
  hideInDeck: boolean;
  onSourceChange: (source: TopPickSource) => void;
  onQueryChange: (query: string) => void;
  onHideInDeckChange: (hide: boolean) => void;
}

function TopPicksControls(props: TopPicksControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-black/20 p-3">
      <div
        role="group"
        aria-label="Top pick source"
        className="flex overflow-hidden rounded-lg border border-white/10"
      >
        {SOURCES.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => props.onSourceChange(item)}
            className={`px-3 py-2 text-xs capitalize ${
              props.source === item
                ? "bg-indigo-600 text-white"
                : "text-gray-400 hover:bg-white/5"
            }`}
          >
            {item}
          </button>
        ))}
      </div>
      <input
        type="search"
        value={props.query}
        onChange={(event) => props.onQueryChange(event.target.value)}
        placeholder="Find a card"
        className="min-w-48 flex-1 rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-gray-500"
      />
      <label className="flex items-center gap-2 text-xs text-gray-300">
        <input
          type="checkbox"
          checked={props.hideInDeck}
          onChange={(event) => props.onHideInDeckChange(event.target.checked)}
          className="accent-indigo-500"
        />
        Hide cards already in deck
      </label>
    </div>
  );
}

interface TopPicksResultsProps {
  error: string | null;
  loading: boolean;
  visible: TopPickCard[];
  hasPicks: boolean;
  busyId: string | null;
  onRetry: () => void;
  onPlan: (pick: TopPickCard) => void;
}

function TopPicksResults(props: TopPicksResultsProps) {
  return (
    <>
      {props.error && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-300">
          <span>{props.error}</span>
          <button type="button" onClick={props.onRetry} className="underline">
            Retry
          </button>
        </div>
      )}
      {props.loading ? (
        <p className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-gray-500">
          Loading commander deck evidence…
        </p>
      ) : props.visible.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {props.visible.map((pick) => (
            <TopPickTile
              key={pick.card_id}
              pick={pick}
              busy={props.busyId === pick.card_id}
              onPlan={() => props.onPlan(pick)}
            />
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-white/20 p-10 text-center text-sm text-gray-500">
          {props.hasPicks
            ? "No top picks match these filters."
            : "No commander top picks are available yet."}
        </p>
      )}
    </>
  );
}

function SourceSummaries({ result }: { result: TopPicksResponse }) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {result.sources.map((summary) => (
        <div
          key={summary.source}
          className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium capitalize text-gray-200">{summary.source}</span>
            <span className="text-gray-500">{summary.deck_count} decks</span>
          </div>
          <p className="mt-1 text-gray-500">
            {summary.stale ? "stale · " : ""}
            {formatCacheTime(summary.fetched_at)}
          </p>
          {summary.error && <p className="mt-1 text-amber-300">{summary.error}</p>}
        </div>
      ))}
    </div>
  );
}

function TopPickTile({
  pick,
  busy,
  onPlan,
}: {
  pick: TopPickCard;
  busy: boolean;
  onPlan: () => void;
}) {
  return (
    <article className="overflow-hidden rounded-xl border border-white/10 bg-white/5">
      {pick.image_uri && (
        <img
          src={pick.image_uri}
          alt={pick.name}
          loading="lazy"
          className="w-full rounded-[4.5%]"
        />
      )}
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-white">
              <CardHover name={pick.name} imageUri={pick.image_uri}>
                {pick.name}
              </CardHover>
            </h3>
            <p className="truncate text-xs text-gray-500">{pick.type_line}</p>
          </div>
          {pick.mana_cost && <ManaCost cost={pick.mana_cost} />}
        </div>
        <div className="flex flex-wrap gap-1 text-[10px]">
          {pick.moxfield_count > 0 && (
            <span className="rounded bg-purple-900/40 px-1.5 py-0.5 text-purple-200">
              Moxfield {pick.moxfield_count}/{pick.moxfield_sample_size}
            </span>
          )}
          {pick.archidekt_count > 0 && (
            <span className="rounded bg-orange-900/40 px-1.5 py-0.5 text-orange-200">
              Archidekt {pick.archidekt_count}/{pick.archidekt_sample_size}
            </span>
          )}
          <span className="rounded bg-cyan-900/40 px-1.5 py-0.5 text-cyan-200">
            {Math.round(pick.combined_score * 100)}% combined
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1">
            <OwnedBadge owned={pick.owned_in} />
          </div>
          <span className="text-xs text-gray-300">{formatPrice(pick.price_eur_cents)}</span>
        </div>
        <TopPickAction pick={pick} busy={busy} onPlan={onPlan} />
      </div>
    </article>
  );
}

function TopPickAction({
  pick,
  busy,
  onPlan,
}: {
  pick: TopPickCard;
  busy: boolean;
  onPlan: () => void;
}) {
  if (pick.plan_direction === "cut") {
    return (
      <p className="rounded bg-red-950/40 px-2 py-1.5 text-xs text-red-300">
        Cut planned ×{pick.planned_quantity}
      </p>
    );
  }
  if (pick.plan_direction === "addition") {
    return (
      <p className="rounded bg-indigo-950/40 px-2 py-1.5 text-xs text-indigo-200">
        Already planned ×{pick.planned_quantity}
      </p>
    );
  }
  if (pick.physical_quantity > 0) {
    return (
      <p className="rounded bg-emerald-950/40 px-2 py-1.5 text-xs text-emerald-300">
        In deck ×{pick.physical_quantity}
      </p>
    );
  }
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onPlan}
      className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
    >
      {busy ? "Planning…" : "Plan addition"}
    </button>
  );
}
