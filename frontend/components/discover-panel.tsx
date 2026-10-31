"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { DiscoverController, type DiscoverState } from "@/components/discover-state";
import { ManaCost } from "@/components/mana-cost";
import { VisualCardGrid, VisualCardTile } from "@/components/visual-card-grid";
import type { CommanderStrategyChoice, StrategyMatch, StrategyTerm } from "@/lib/discovery-types";

const BOX = "min-w-0 rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-6";
const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const BUTTON = `min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;
const SECONDARY = `min-h-11 touch-manipulation rounded-lg px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white disabled:opacity-50 ${FOCUS}`;

interface Props {
  deckId: string;
  onPlanChanged: () => void | Promise<void>;
}
type ViewProps = { state: DiscoverState; controller: DiscoverController };

export function DiscoverPanel({ deckId, onPlanChanged }: Props) {
  const controller = useMemo(
    () => new DiscoverController(deckId, onPlanChanged),
    [deckId, onPlanChanged],
  );
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  useEffect(() => {
    void controller.start();
    return () => controller.stop();
  }, [controller]);
  return <DiscoverView state={state} controller={controller} />;
}

export function DiscoverView({ state, controller }: ViewProps) {
  const saved = state.status?.strategy;
  return (
    <section aria-label="Discover" className="min-w-0 space-y-5">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight text-white">Discover</h2>
        <p className="text-sm leading-6 text-gray-400">
          Choose a direction for your deck. We’ll find the cards.
        </p>
      </header>
      {saved && <ActiveStrategy state={state} controller={controller} />}
      {state.editing && <StrategyChooser state={state} controller={controller} />}
      {state.error && (
        <p
          role="alert"
          className="rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm leading-6 text-red-200"
        >
          {state.error}
        </p>
      )}
      {state.progress && (
        <p role="status" className="text-sm text-indigo-200">
          {state.progress}
        </p>
      )}
      {state.loading && !state.status && (
        <p role="status" className="text-sm text-gray-400">
          Loading your strategy…
        </p>
      )}
      {state.status?.source.warning && (
        <p role="status" className="text-sm leading-6 text-amber-200">
          {state.status.source.warning}
        </p>
      )}
      <AdvancedSearch state={state} controller={controller} />
      {state.dismissedOracleId && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-2 rounded-xl bg-white/5 px-4 py-2 text-sm text-gray-300"
        >
          Card dismissed from this deck.
          <button
            className={SECONDARY}
            disabled={!!state.dismissing}
            onClick={() => void controller.undoDismissal()}
          >
            Undo dismissal
          </button>
        </div>
      )}
      <Matches state={state} controller={controller} />
    </section>
  );
}

function ActiveStrategy({ state, controller }: ViewProps) {
  const saved = state.status?.strategy;
  if (!saved) return null;
  return (
    <article
      aria-label="Your strategy"
      className="min-w-0 rounded-2xl border border-indigo-400/30 bg-gradient-to-br from-indigo-500/10 to-transparent p-5 sm:p-6"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold text-white">Your strategy</h3>
          <span className="rounded-full bg-indigo-400/10 px-2.5 py-1 text-xs font-medium text-indigo-200">
            Active
          </span>
        </div>
        {!state.editing && (
          <button className={SECONDARY} onClick={() => void controller.changeStrategy()}>
            Change strategy
          </button>
        )}
      </div>
      <p className="whitespace-pre-wrap break-words text-base leading-8 text-gray-100">
        {saved.prose}
      </p>
      {state.editing && (
        <p className="mt-4 text-xs text-gray-400">
          This stays active until your new strategy is ready.
        </p>
      )}
    </article>
  );
}

function StrategyChooser({ state, controller }: ViewProps) {
  const choices =
    state.draft?.status === "completed" && !state.draft.stale ? (state.draft.strategies ?? []) : [];
  return (
    <form
      className={`${BOX} space-y-5`}
      onSubmit={(event) => {
        event.preventDefault();
        void controller.findCards();
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-white">Choose your direction</h3>
          <p className="mt-1 text-sm leading-6 text-gray-400">
            Pick a strategy, or describe the deck you want to play.
          </p>
        </div>
        {state.status?.strategy && (
          <button
            type="button"
            className={SECONDARY}
            disabled={state.busy}
            onClick={() => controller.cancelEditing()}
          >
            Cancel
          </button>
        )}
      </div>
      {state.drafting && (
        <p role="status" className="rounded-xl bg-indigo-400/5 p-4 text-sm text-indigo-200">
          Preparing strategy ideas for your commander…
        </p>
      )}
      {state.draftError && (
        <p role="alert" className="text-sm leading-6 text-amber-200">
          {state.draftError}
        </p>
      )}
      {!!choices.length && (
        <fieldset disabled={state.busy}>
          <legend className="sr-only">Strategy options</legend>
          <div className="grid gap-3 xl:grid-cols-3">
            {choices.map((choice, index) => (
              <StrategyOption
                key={choice.title}
                choice={choice}
                selected={state.selected === index && !state.manual}
                onSelect={() => controller.selectDraft(index)}
              />
            ))}
          </div>
        </fieldset>
      )}
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={SECONDARY}
          disabled={state.busy}
          onClick={() => controller.writeOwn()}
        >
          Write my own strategy
        </button>
        <button
          type="button"
          className={SECONDARY}
          disabled={state.drafting || state.busy}
          onClick={() => void controller.tryOtherStrategies()}
        >
          Try other strategies
        </button>
      </div>
      {state.manual && <ManualStrategy state={state} controller={controller} />}
      <div className="flex flex-wrap items-center gap-3 border-t border-white/10 pt-5">
        <button type="submit" className={BUTTON} disabled={state.busy}>
          {state.busy ? "Finding cards…" : "Find cards"}
          <span aria-hidden="true" className="ml-2">
            →
          </span>
        </button>
        <p className="text-xs leading-5 text-gray-400">
          Search terms and saving are handled for you.
        </p>
      </div>
    </form>
  );
}

function ManualStrategy({ state, controller }: ViewProps) {
  return (
    <label className="block space-y-2 text-sm font-medium text-gray-200">
      Your strategy
      <textarea
        name="discover-strategy"
        autoComplete="off"
        rows={7}
        maxLength={2000}
        value={state.prose}
        disabled={state.busy}
        placeholder="For example: Build a counter engine, then turn large creatures into pressure…"
        onChange={(event) => controller.setProse(event.target.value)}
        className={`block w-full resize-y rounded-xl border border-white/15 bg-gray-950/60 p-4 text-base font-normal leading-7 text-white ${FOCUS}`}
      />
    </label>
  );
}

function StrategyOption({
  choice,
  selected,
  onSelect,
}: {
  choice: CommanderStrategyChoice;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <label
      className={`relative flex min-w-0 cursor-pointer flex-col gap-4 rounded-xl border p-4 transition-colors focus-within:ring-2 focus-within:ring-indigo-400 ${selected ? "border-indigo-400 bg-indigo-400/10" : "border-white/10 bg-gray-950/30 hover:border-white/30"}`}
    >
      <div className="flex items-start gap-3">
        <input
          type="radio"
          name="discover-direction"
          aria-label={choice.title}
          checked={selected}
          onChange={onSelect}
          className="mt-1 h-4 w-4 shrink-0 accent-indigo-400"
        />
        <div className="min-w-0">
          <h4 className="break-words text-base font-semibold leading-6 text-white">
            {choice.title}
          </h4>
          <p className="mt-1 break-words text-xs leading-5 text-indigo-200">{choice.pace}</p>
        </div>
      </div>
      <p className="break-words text-sm leading-6 text-gray-300">{choice.explanation}</p>
      <dl className="space-y-3 text-sm leading-6">
        {[
          ["Early game", choice.early_game],
          ["Engine", choice.engine],
          ["Payoff", choice.payoff],
        ].map(([label, text]) => (
          <div key={label}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</dt>
            <dd className="break-words text-gray-200">{text}</dd>
          </div>
        ))}
      </dl>
      {!!choice.uncertainties.length && (
        <p className="mt-auto break-words border-t border-white/10 pt-3 text-xs leading-5 text-gray-400">
          Worth checking: {choice.uncertainties.join(" ")}
        </p>
      )}
    </label>
  );
}

function AdvancedSearch({ state, controller }: ViewProps) {
  const count = state.tagIds.length + state.keywords.length;
  return (
    <details
      className="min-w-0 rounded-xl border border-white/10 px-4 text-sm"
      open={state.advanced}
      onToggle={(event) => {
        if (event.currentTarget.open !== state.advanced)
          void controller.setAdvanced(event.currentTarget.open);
      }}
    >
      <summary
        className={`min-h-11 cursor-pointer py-3 text-gray-400 hover:text-gray-200 ${FOCUS}`}
      >
        Advanced search details{count ? ` · ${count} selected terms` : ""}
      </summary>
      {state.advanced && (
        <div className="space-y-5 pb-5 pt-2">
          <p className="text-xs leading-5 text-gray-400">
            Optional: adjust the Scryfall terms used to find cards. Your choices override automatic
            filters with one unscoped search using any selected term.
          </p>
          {!!state.queries.length && <SearchFilters state={state} />}
          {state.terms ? (
            <>
              <TermPicker
                title="Oracle-Tags"
                values={state.terms.oracle_tags}
                selected={state.tagIds}
                onToggle={(id) => controller.toggleTag(id)}
                disabled={state.busy}
              />
              <TermPicker
                title="Printed keywords"
                values={state.terms.printed_keywords.map((label) => ({
                  id: label,
                  slug: label,
                  label,
                }))}
                selected={state.keywords}
                onToggle={(id) => controller.toggleKeyword(id)}
                disabled={state.busy}
              />
            </>
          ) : (
            <p role="status" className="text-gray-400">
              Loading search terms…
            </p>
          )}
        </div>
      )}
    </details>
  );
}

function SearchFilters({ state }: { state: DiscoverState }) {
  const labels = new Map(state.terms?.oracle_tags.map((term) => [term.id, term.label]) ?? []);
  return (
    <section aria-label="Saved search filters" className="space-y-3 rounded-lg bg-white/5 p-3">
      <p className="text-xs text-gray-400">
        Any search below may match. All groups within a search must match.
      </p>
      {state.queries.map((query, index) => (
        <div key={index} className="space-y-1 text-xs leading-5 text-gray-300">
          <p className="font-medium">{query.purpose}</p>
          {query.groups.map((group, groupIndex) => (
            <p key={groupIndex}>
              {groupIndex ? "AND " : ""}
              {[
                ...group.oracle_tag_ids.map((id) => labels.get(id) ?? id),
                ...group.printed_keywords,
              ].join(" OR ")}
            </p>
          ))}
          {!!query.card_types_any.length && (
            <p>Front-face type: {query.card_types_any.join(" or ")}</p>
          )}
        </div>
      ))}
    </section>
  );
}

function TermPicker({
  title,
  values,
  selected,
  onToggle,
  disabled,
}: {
  title: string;
  values: StrategyTerm[];
  selected: string[];
  onToggle: (id: string) => void;
  disabled: boolean;
}) {
  const [search, setSearch] = useState("");
  const selectedIds = new Set(selected);
  const filtered = values.filter(
    (term) => !selectedIds.has(term.id) && term.label.toLowerCase().includes(search.toLowerCase()),
  );
  const labels = new Map(values.map((term) => [term.id, term.label]));
  return (
    <fieldset className="min-w-0 space-y-3" disabled={disabled}>
      <legend className="font-medium text-gray-200">{title}</legend>
      {!!selected.length && (
        <div className="flex flex-wrap gap-2" aria-label={`Selected ${title}`}>
          {selected.map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed="true"
              className={`min-h-11 max-w-full break-words rounded-lg bg-indigo-500/15 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/25 ${FOCUS}`}
              onClick={() => onToggle(id)}
            >
              {labels.get(id) ?? `Unavailable term: ${id}`} <span aria-hidden="true">×</span>
              <span className="sr-only"> — remove</span>
            </button>
          ))}
        </div>
      )}
      <input
        aria-label={`Search ${title}`}
        name={`discover-${title}-search`}
        autoComplete="off"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search terms…"
        className={`min-h-11 w-full rounded-lg border border-white/15 bg-gray-950/50 px-3 py-2 ${FOCUS}`}
      />
      <div className="flex flex-wrap gap-2">
        {filtered.slice(0, 20).map((term) => (
          <button
            key={term.id}
            type="button"
            aria-pressed="false"
            className={`min-h-11 max-w-full break-words rounded-lg border border-white/10 px-3 py-2 text-xs text-gray-300 hover:border-indigo-400 hover:text-white ${FOCUS}`}
            onClick={() => onToggle(term.id)}
          >
            {term.label}
          </button>
        ))}
      </div>
      {filtered.length > 20 && (
        <p className="text-xs text-gray-500">
          Showing 20 of {filtered.length.toLocaleString()} terms. Refine your search to see more.
        </p>
      )}
      {!filtered.length && (
        <p className="text-xs text-gray-400">No other terms match this search.</p>
      )}
    </fieldset>
  );
}

function Matches({ state, controller }: ViewProps) {
  const matches = state.matches;
  if (!matches || matches.status === "setup_needed") return null;
  if (["unavailable", "mismatched"].includes(matches.status))
    return (
      <p className={`${BOX} text-sm text-amber-200`}>
        Card sources aren’t ready. Try again after the source sync finishes.
      </p>
    );
  return (
    <section aria-label="Matching cards" className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold text-white">Cards for your strategy</h3>
        <span className="text-sm tabular-nums text-gray-400">
          {matches.total.toLocaleString()} matches
        </span>
      </div>
      <p className="text-xs leading-5 text-gray-500">
        Filtered by your Scryfall searches and ordered by global Commander popularity—not tag count
        or verified synergy. Cards without popularity data remain available. Plan additions without
        changing your deck.
      </p>
      {state.loading && (
        <p role="status" className="text-sm text-gray-400">
          Loading cards…
        </p>
      )}
      {!matches.cards.length && (
        <div className={`${BOX} text-sm leading-7 text-gray-400`}>
          <h4 className="font-medium text-gray-200">No matching cards</h4>Try another direction or
          adjust the terms in Advanced search details.
        </div>
      )}
      <VisualCardGrid>
        {matches.cards.map((card) => (
          <VisualCardTile
            key={card.oracle_id}
            name={card.name}
            imageUri={card.image_uri}
            footer={<MatchDetails card={card} state={state} controller={controller} />}
          />
        ))}
      </VisualCardGrid>
      {matches.next_cursor && (
        <button
          className={SECONDARY}
          disabled={state.loading}
          onClick={() => void controller.next()}
        >
          Next page →
        </button>
      )}
    </section>
  );
}

function MatchDetails({ card, state, controller }: ViewProps & { card: StrategyMatch }) {
  return (
    <article className="space-y-3 text-sm">
      <h4 className="font-semibold leading-6">
        {card.name} <ManaCost cost={card.mana_cost} />
      </h4>
      <p className="text-xs text-gray-400">{card.type_line}</p>
      <details>
        <summary className={`min-h-11 cursor-pointer py-3 text-xs text-indigo-200 ${FOCUS}`}>
          Why this card?
        </summary>
        <p className="whitespace-pre-wrap py-2 text-xs leading-6 text-gray-300">
          {card.oracle_text}
        </p>
        {card.global_popularity_rank !== null && (
          <p className="pb-2 text-xs text-gray-400">
            Global popularity rank: #{card.global_popularity_rank.toLocaleString()}
          </p>
        )}
        <ul className="space-y-1 pb-2 text-xs text-gray-400">
          {card.evidence.map((evidence, index) => (
            <li key={`${evidence.criterion_label}-${index}`}>
              {evidence.query_purpose}: {evidence.criterion_label}
              {evidence.matched_tag_label && evidence.matched_tag_label !== evidence.criterion_label
                ? ` → ${evidence.matched_tag_label}`
                : ""}
            </li>
          ))}
        </ul>
      </details>
      <div className="flex flex-wrap gap-1">
        <button
          className={BUTTON}
          disabled={!!state.planning}
          onClick={() => void controller.plan(card.oracle_id)}
        >
          {state.planning === card.oracle_id ? "Planning…" : "Plan addition"}
        </button>
        <button
          className={SECONDARY}
          disabled={!!state.dismissing}
          onClick={() => void controller.dismiss(card.oracle_id)}
        >
          Dismiss
        </button>
      </div>
    </article>
  );
}
