"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";

import { ManaCost } from "@/components/mana-cost";
import { NewCardsController, type NewCardsState } from "@/components/new-cards-state";
import type { NewCardFace, NewCardPick, NewCardsResponse } from "@/lib/types";

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
      <PilotWarning />
      <NewCardsControls state={state} controller={controller} />
      <NewCardsErrors state={state} controller={controller} />
      <NewCardsProgress state={state} controller={controller} />
      {state.result && (
        <NewCardsResults result={state.result} busy={state.busy} controller={controller} />
      )}
    </section>
  );
}

interface StateProps {
  state: NewCardsState;
  controller: NewCardsController;
}

function NewCardsControls({ state, controller }: StateProps) {
  return (
    <div className={`${BOX} space-y-3`}>
      <NewCardsCoverage result={state.result} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={cannotAnalyze(state.result) || state.busy || state.loading}
          onClick={() => void controller.analyze()}
        >
          Analyze next eight
        </button>
        <button
          type="button"
          className={BUTTON}
          disabled={state.busy || state.loading}
          onClick={() => void controller.refresh()}
        >
          Refresh status
        </button>
      </div>
    </div>
  );
}

function NewCardsErrors({ state, controller }: StateProps) {
  return (
    <>
      {state.error && <RequestError message={state.error} />}
      {state.planRefreshError && (
        <RequestError message={state.planRefreshError}>
          <button
            type="button"
            className="mt-2 underline"
            disabled={state.busy}
            onClick={() => void controller.retryPlanRefresh()}
          >
            Retry deck refresh
          </button>
        </RequestError>
      )}
      {state.error && state.result && (
        <p className="text-sm text-amber-300">Showing the last usable result; it may be stale.</p>
      )}
    </>
  );
}

function NewCardsProgress({ state, controller }: StateProps) {
  return (
    <>
      {state.loading && <p role="status">Loading New Cards status…</p>}
      {state.busy && <p role="status">Updating New Cards…</p>}
      {state.lastDismissal && (
        <p className="text-sm text-gray-300">
          Dismissed {state.lastDismissal.name}.{" "}
          <button
            type="button"
            className="underline"
            disabled={state.busy}
            onClick={() => void controller.undo()}
          >
            Undo latest dismissal
          </button>
        </p>
      )}
    </>
  );
}

function cannotAnalyze(result: NewCardsResponse | null): boolean {
  if (!result) return true;
  return (
    result.status === "unavailable" || result.status === "running" || result.remaining_count === 0
  );
}

function PilotWarning() {
  return (
    <div className={`${BOX} space-y-2 text-sm text-gray-300`}>
      <h2 className="font-semibold text-white">New Cards · Experimental pilot</h2>
      <p className="text-amber-300">
        AI advice is unverified. Check source rules and supporting cards before planning an
        addition.
      </p>
      <p>
        Released, Commander-legal paper cards only. No previews, unknown-release products or
        promo-only originals. Scryfall discovery uses conservative normal-product and historical
        origin filters; special-product coverage is incomplete. No community sources are used.
      </p>
      <p>
        Catalog refresh is daily in production. Opening this tab or refreshing status never starts
        analysis or source sync. Planning adds one pending addition, not a physical deck edit.
        Advice uses your current physical deck; planned additions are not present support.
      </p>
    </div>
  );
}

function RequestError({ message, children }: { message: string; children?: React.ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border border-red-500/30 p-3 text-sm text-red-300">
      <p>{message}</p>
      {children}
    </div>
  );
}

function NewCardsCoverage({ result }: { result: NewCardsResponse | null }) {
  if (!result) return <p className="text-sm text-gray-400">Waiting for source status.</p>;
  return (
    <div className="space-y-1 text-sm text-gray-300" aria-live="polite">
      <p>
        Dates in UTC · Today {utcDate(new Date().toISOString())} · Scryfall catalog updated{" "}
        {utcDate(result.catalog_updated_at)} · Analyzed {utcDate(result.analyzed_at)}
      </p>
      <p>
        Coverage: {result.assessed_count} of {result.eligible_count} currently eligible cards
        assessed
        {" · "}
        {result.remaining_count} remaining · {result.dismissed_count} dismissed. Rejected cards
        count as assessed.
      </p>
      {result.stale && (
        <p className="text-amber-300">
          Source or analysis is stale. Ask an admin to sync old source data, or analyze remaining
          cards.
        </p>
      )}
      {result.remaining_count > 0 && (
        <p>Partial coverage. Unassessed cards are not evidence of no matches.</p>
      )}
      {result.status === "running" && (
        <p role="status">Analysis running; status updates automatically.</p>
      )}
      {result.status === "unavailable" && (
        <p>
          Not ready. Source catalog or deck context is unavailable; ask an admin to sync if needed.
        </p>
      )}
      {result.status === "error" && (
        <p className="text-red-300">Analysis failed. Retry explicitly with Analyze next eight.</p>
      )}
      {result.error && <RequestError message={result.error} />}
    </div>
  );
}

function NewCardsResults({
  result,
  busy,
  controller,
}: {
  result: NewCardsResponse;
  busy: boolean;
  controller: NewCardsController;
}) {
  const groups = [
    { label: "strong", title: "Strong fits" },
    { label: "worth_testing", title: "Worth testing" },
  ] as const;
  if (!result.picks.length) return <EmptyResults result={result} />;
  return (
    <div className="space-y-4">
      {groups.map((group) => {
        const picks = result.picks.filter((pick) => pick.label === group.label);
        if (!picks.length) return null;
        return (
          <section key={group.label} aria-label={group.title} className="space-y-2">
            <h3 className="font-semibold text-white">{group.title}</h3>
            <div className="grid gap-3 xl:grid-cols-2">
              {picks.map((pick) => (
                <NewCardTile key={pick.oracle_id} pick={pick} busy={busy} controller={controller} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function EmptyResults({ result }: { result: NewCardsResponse }) {
  if (result.status === "unavailable") return null;
  if (result.status === "running") return <p>No picks yet; analysis is still running.</p>;
  if (result.status === "error")
    return <p>No usable picks; analysis failed, not a no-match result.</p>;
  if (result.stale)
    return <p>No current picks. Source or analysis is stale, not a no-match result.</p>;
  if (result.remaining_count > 0)
    return <p>No picks yet. Analyze unassessed cards to find matches.</p>;
  if (result.eligible_count === 0)
    return <p>No released cards currently meet the pilot filters.</p>;
  return (
    <p>No strong fits or cards worth testing in the assessed eligible pool. No filler picks.</p>
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

function GeneratedAdvice({ pick }: { pick: NewCardPick }) {
  return (
    <div className="space-y-2 border-t border-white/10 pt-3 text-sm text-gray-300">
      <h4 className="font-semibold text-amber-300">Generated advice · Unverified</h4>
      <p>Reason: {pick.reason}</p>
      <p>Caveat: {pick.caveat}</p>
      <h5 className="font-medium">Supporting changes (not planned automatically)</h5>
      {pick.required_changes.length > 0 ? (
        <ul className="list-inside list-disc">
          {pick.required_changes.map((change, index) => (
            <li key={index}>{change}</li>
          ))}
        </ul>
      ) : (
        <p>No supporting changes reported; this is not a guarantee of fit.</p>
      )}
      <h5 className="font-medium">Source evidence: candidate and physical support</h5>
      {pick.evidence.length > 0 ? (
        <ul className="space-y-1">
          {pick.evidence.map((item, index) => (
            <li key={index}>
              {item.name}: <q>{item.quote}</q>
            </li>
          ))}
        </ul>
      ) : (
        <p>No supporting evidence returned.</p>
      )}
      <p className="text-xs text-gray-400">
        Pending additions are not support facts. Review caveats for supporting cards with pending
        cuts. Evidence and supporting-change suggestions are model claims, not verified rules.
      </p>
    </div>
  );
}

function NewCardTile({
  pick,
  busy,
  controller,
}: {
  pick: NewCardPick;
  busy: boolean;
  controller: NewCardsController;
}) {
  const link = sourceLink(pick.scryfall_uri);
  return (
    <article className={`${BOX} space-y-3`}>
      <h4 className="font-semibold text-white">{pick.name}</h4>
      <div className="space-y-2 text-sm text-gray-300">
        <h4 className="font-semibold">Source rules · Scryfall</h4>
        {(pick.faces.length ? pick.faces : [pick]).map((face, index) => (
          <SourceRules key={index} face={face} />
        ))}
        <p>
          Released {utcDate(pick.released_at)} UTC · Eligible until {utcDate(pick.expires_at)} UTC
        </p>
        <p>
          {pick.price_eur_cents === null
            ? "Price unavailable"
            : `€${(pick.price_eur_cents / 100).toFixed(2)}`}
        </p>
        {link ? (
          <a href={link} target="_blank" rel="noopener noreferrer" className="underline">
            Verify on Scryfall
          </a>
        ) : (
          <p>Source link unavailable or unsafe.</p>
        )}
      </div>
      <GeneratedAdvice pick={pick} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={busy}
          onClick={() => void controller.plan(pick)}
        >
          Plan addition
        </button>
        <button
          type="button"
          className={BUTTON}
          disabled={busy}
          onClick={() => void controller.dismiss(pick)}
        >
          Dismiss
        </button>
      </div>
    </article>
  );
}
