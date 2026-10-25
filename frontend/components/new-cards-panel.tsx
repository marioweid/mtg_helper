"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";

import { ManaCost } from "@/components/mana-cost";
import { NewCardsController, type NewCardsState } from "@/components/new-cards-state";
import type { NewCardFace, NewCardMatch, NewCardsResponse, TagMatch } from "@/lib/types";

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
    <div className="grid gap-3 xl:grid-cols-2">
      {result.matches.map((match) => (
        <NewCardTile key={match.oracle_id} match={match} busy={busy} controller={controller} />
      ))}
    </div>
  );
}

function SourceRules({ face }: { face: NewCardFace }) {
  return (
    <div className="space-y-1">
      <h5 className="font-medium">{face.name}</h5>
      {face.mana_cost && <ManaCost cost={face.mana_cost} />}
      <p>{face.type_line}</p>
      <p className="whitespace-pre-wrap">{face.oracle_text}</p>
      {(face.power !== null || face.toughness !== null) && (
        <p>
          Power / toughness: {face.power ?? "—"} / {face.toughness ?? "—"}
        </p>
      )}
    </div>
  );
}

function TagExplanation({ match }: { match: TagMatch }) {
  const relation = match.relation === "direct" ? "direct" : "descendant";
  return (
    <li>
      Commander tag “{match.commander_tag_label}” matches {relation} candidate tag “
      {match.candidate_tag_label}”.
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
    <article className={`${BOX} space-y-3`}>
      <h3 className="font-semibold text-white">{match.name}</h3>
      {(match.faces.length ? match.faces : [match]).map((face, index) => (
        <SourceRules key={index} face={face} />
      ))}
      <p>{match.matching_tag_count} matching Commander tag(s).</p>
      <ul className="list-inside list-disc">
        {match.tag_matches.map((item) => (
          <TagExplanation key={`${item.commander_tag_id}-${item.candidate_tag_id}`} match={item} />
        ))}
      </ul>
      {link ? (
        <a href={link} target="_blank" rel="noopener noreferrer" className="underline">
          View on Scryfall
        </a>
      ) : (
        <p>Source link unavailable or unsafe.</p>
      )}
      <div className="flex gap-2">
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
  );
}
