"use client";

import { useEffect, useId, useMemo, useState, useSyncExternalStore } from "react";

import { NewCardsController, type NewCardsState } from "@/components/new-cards-state";
import { VisualCardGrid, VisualCardTile } from "@/components/visual-card-grid";
import type { NewCardMatch, NewCardsResponse, TagMatch } from "@/lib/types";

interface Props {
  deckId: string;
  onPlanChanged: () => void | Promise<void>;
}

const BUTTON =
  "rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white " +
  "hover:bg-indigo-500 disabled:opacity-40";
const BOX = "rounded-xl border border-white/10 bg-white/5 p-4";

function utcDate(value: string | null): string {
  if (!value) return "not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "unknown date" : date.toISOString().slice(0, 10);
}

function sourceLink(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "scryfall.com") return null;
    if (url.username || url.password || url.port) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function NewCardsPanel({ deckId, onPlanChanged }: Props) {
  const controller = useMemo(
    () => new NewCardsController(deckId, onPlanChanged),
    [deckId, onPlanChanged],
  );
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  useEffect(() => {
    controller.start();
    return () => controller.stop();
  }, [controller]);
  return (
    <section aria-label="New Cards" className="space-y-4">
      <SourceSummary state={state} />
      {state.error && <p role="alert">{state.error}</p>}
      {state.lastDismissal && (
        <p>
          Dismissed {state.lastDismissal.name}.{" "}
          <button type="button" className="underline" onClick={() => void controller.undo()}>
            Undo latest dismissal
          </button>
        </p>
      )}
      {state.result && <Results result={state.result} busy={state.busy} controller={controller} />}
    </section>
  );
}

function SourceSummary({ state }: { state: NewCardsState }) {
  const result = state.result;
  if (state.loading) return <p role="status">Loading Scryfall tag matches…</p>;
  if (!result) return <p>Waiting for Scryfall source status.</p>;
  return (
    <div className={`${BOX} space-y-1 text-sm text-gray-300`}>
      <h2 className="font-semibold text-white">New Cards from Scryfall tags</h2>
      <p>
        Card source updated {utcDate(result.catalog_updated_at)} UTC · Tag source updated{" "}
        {utcDate(result.tag_updated_at)} UTC.
      </p>
      <p>
        Released, Commander-legal paper cards only. Matches use Commander-Konstellation source tags,
        not deck strategy or rules-interaction claims.
      </p>
      {result.status !== "ready" && <p className="text-amber-300">{result.error}</p>}
    </div>
  );
}

function Results({
  result,
  busy,
  controller,
}: {
  result: NewCardsResponse;
  busy: boolean;
  controller: NewCardsController;
}) {
  if (result.status !== "ready") return null;
  if (!result.matches.length) return <p>No current Scryfall tag matches for this deck.</p>;
  return (
    <VisualCardGrid>
      {result.matches.map((match) => (
        <NewCardTile key={match.oracle_id} match={match} busy={busy} controller={controller} />
      ))}
    </VisualCardGrid>
  );
}

function TagExplanation({ match }: { match: TagMatch }) {
  const descriptionId = useId();
  const [open, setOpen] = useState(false);
  const relation = match.relation === "direct" ? "direct" : "descendant";
  return (
    <li
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        aria-describedby={descriptionId}
        onClick={() => setOpen(true)}
        className={
          "cursor-help rounded-full bg-violet-500/15 px-2 py-1 text-[11px] font-medium " +
          "text-violet-200 hover:bg-violet-500/25 focus-visible:outline-none " +
          "focus-visible:ring-2 focus-visible:ring-violet-400"
        }
      >
        {match.candidate_tag_label}
      </button>
      <span
        id={descriptionId}
        role="tooltip"
        hidden={!open}
        className={
          "absolute inset-x-0 bottom-full z-10 rounded-lg border border-white/15 " +
          "bg-zinc-950 p-3 text-xs text-gray-200 shadow-xl"
        }
      >
        Commander tag “{match.commander_tag_label}” matches {relation} candidate tag “
        {match.candidate_tag_label}”.
      </span>
    </li>
  );
}

function NewCardTile({
  match,
  busy,
  controller,
}: {
  match: NewCardMatch;
  busy: boolean;
  controller: NewCardsController;
}) {
  const link = sourceLink(match.scryfall_uri);
  return (
    <VisualCardTile
      name={match.name}
      imageUri={match.image_uri}
      footer={
        <article className="space-y-2">
          <h3 className="text-sm font-semibold text-white">{match.name}</h3>
          <p className="text-xs text-gray-400">
            {match.matching_tag_count} matching Commander tag(s).
          </p>
          <ul aria-label="Matching source tags" className="relative flex flex-wrap gap-1">
            {match.tag_matches.map((item) => (
              <TagExplanation
                key={`${item.commander_tag_id}-${item.candidate_tag_id}`}
                match={item}
              />
            ))}
          </ul>
          {link ? (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-400 underline hover:text-white"
            >
              View on Scryfall
            </a>
          ) : (
            <p className="text-xs text-gray-400">Source link unavailable or unsafe.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              onClick={() => void controller.plan(match)}
            >
              Plan addition
            </button>
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              onClick={() => void controller.dismiss(match)}
            >
              Dismiss
            </button>
          </div>
        </article>
      }
    />
  );
}
