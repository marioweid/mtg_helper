"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { DiscoverController, type DiscoverState } from "@/components/discover-state";
import { CommanderStrategyPanel } from "@/components/commander-strategy-panel";
import { ManaCost } from "@/components/mana-cost";
import { VisualCardGrid, VisualCardTile } from "@/components/visual-card-grid";
import type {
  DiscoverCandidate,
  DiscoverFace,
  DiscoverQuery,
  DiscoverRun,
} from "@/lib/discovery-types";

const BOX = "rounded-xl border border-white/10 bg-white/5 p-4 space-y-3";
const BUTTON = "rounded bg-indigo-600 px-3 py-2 text-sm disabled:opacity-40";
const INPUT = "rounded border border-white/20 bg-gray-950 p-2 text-sm";

interface Props {
  deckId: string;
  onPlanChanged: () => void | Promise<void>;
}
interface StateProps {
  state: DiscoverState;
  controller: DiscoverController;
}

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
  const [view, setView] = useState<"results" | "trace">("results");
  useEffect(() => {
    controller.start();
    return () => controller.stop();
  }, [controller]);
  return (
    <section aria-label="Discover" className="space-y-4">
      <PilotBanner />
      <CommanderStrategyPanel
        state={state}
        controller={controller}
        onInspect={() => {
          setView("trace");
          void controller.inspect(true);
        }}
      />
      <DiscoverControls state={state} controller={controller} />
      {state.error && (
        <p role="alert" className="text-red-300">
          {state.error}
        </p>
      )}
      <DiscoverProgress state={state} />
      <div role="tablist" aria-label="Discover views" className="flex gap-2">
        <button
          className={BUTTON}
          role="tab"
          aria-selected={view === "results"}
          onClick={() => setView("results")}
        >
          Results
        </button>
        <button
          className={BUTTON}
          role="tab"
          aria-selected={view === "trace"}
          onClick={() => {
            setView("trace");
            void controller.inspect();
          }}
        >
          Plan &amp; Searches
        </button>
      </div>
      {view === "results" ? (
        <DiscoverResults state={state} controller={controller} />
      ) : (
        <DiscoverTrace state={state} controller={controller} />
      )}
    </section>
  );
}

function PilotBanner() {
  return (
    <div className={BOX}>
      <h2 className="font-semibold">Discover · Experimental</h2>
      <p className="text-amber-300">Commander-only, nonland experiment. AI advice is unverified.</p>
      <p className="text-sm text-gray-300">
        This does not assess your physical deck's balance or interactions. Physical cards and
        planned additions are exclusions, not support. No community rankings are used. Only explicit
        card exclusions and literal filters are enforced; no bracket, price or combo guarantees.
        Partner decks and collection scopes are not yet supported.
      </p>
      <p className="text-sm text-gray-300">
        Opening, searching and refreshing are free of model calls. Draft strategy explicitly starts
        one separate Luna call; Generate cards starts at most three. Planning creates a pending
        addition, never a physical edit. AI can take several minutes; source browsing stays usable.
      </p>
    </div>
  );
}

function DiscoverControls({ state, controller }: StateProps) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [type, setType] = useState("");
  const [keyword, setKeyword] = useState("");
  const [minimum, setMinimum] = useState("");
  const [maximum, setMaximum] = useState("");
  const constraint: DiscoverQuery | null = [text, type, keyword, minimum, maximum].some(Boolean)
    ? {
        purpose: "Explicit user source filters",
        oracle_text_all: text ? [text] : [],
        oracle_text_any: [],
        type_line_any: type ? [type] : [],
        keywords_any: keyword ? [keyword] : [],
        mana_cost_all: [],
        mana_value_min: minimum ? Number(minimum) : null,
        mana_value_max: maximum ? Number(maximum) : null,
      }
    : null;
  const running =
    state.status?.run?.status === "running" || state.status?.strategy_run?.status === "running";
  return (
    <div className={BOX}>
      <label className="block">
        Commander-only goal (editable)
        <textarea
          className={`${INPUT} mt-1 w-full`}
          maxLength={1000}
          value={state.goal}
          onChange={(event) => controller.setGoal(event.target.value)}
        />
      </label>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Filter label="Name (browse only)" value={name} onChange={setName} />
        <Filter label="Oracle text contains (literal)" value={text} onChange={setText} />
        <Filter label="Type contains (literal)" value={type} onChange={setType} />
        <Filter label="Keyword (exact source name)" value={keyword} onChange={setKeyword} />
        <Filter label="Minimum mana value" value={minimum} onChange={setMinimum} numeric />
        <Filter label="Maximum mana value" value={maximum} onChange={setMaximum} numeric />
      </div>
      <p className="text-xs text-gray-400">
        Source filters also constrain the next Generate run. Changing filters never automatically
        starts analysis. Name filters browsing only.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          className={BUTTON}
          disabled={!state.status?.ready || state.browsing}
          onClick={() => void controller.search({ name, query: constraint })}
        >
          Browse source cards
        </button>
        <button
          className={BUTTON}
          disabled={!state.status?.ready || state.generating || state.drafting || running}
          onClick={() => void controller.generate(constraint)}
        >
          Generate · up to ${((state.status?.run_cap_microusd ?? 100000) / 1e6).toFixed(2)}
        </button>
        <button
          className={BUTTON}
          disabled={state.loading}
          onClick={() => void controller.refresh()}
        >
          Refresh status
        </button>
      </div>
    </div>
  );
}

function Filter({
  label,
  value,
  onChange,
  numeric = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  numeric?: boolean;
}) {
  return (
    <label className="text-sm">
      {label}
      <input
        className={`${INPUT} mt-1 w-full`}
        type={numeric ? "number" : "text"}
        step={numeric ? "any" : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function DiscoverProgress({ state }: { state: DiscoverState }) {
  const run = state.status?.run;
  return (
    <div aria-live="polite" className="text-sm text-gray-300 space-y-1">
      {state.loading && <p role="status">Loading discovery status…</p>}
      {state.generating && <p role="status">Starting an explicitly budgeted run…</p>}
      {state.browsing && <p role="status">Searching local source facts…</p>}
      {state.status && !state.status.ready && <p>{state.status.reason ?? "Source not ready"}</p>}
      {run && (
        <>
          <p>
            Run {run.status} · {run.phase} · {run.candidates.length} shortlisted candidates
          </p>
          <p>
            Known estimate ${(run.known_cost_microusd / 1e6).toFixed(5)} · held reservation $
            {(run.held_microusd / 1e6).toFixed(5)}. Estimates, not provider-enforced caps.
          </p>
          <p>Goal: {run.goal}</p>
          {run.error && (
            <p role="alert" className="text-red-300">
              {run.error}
            </p>
          )}
          {run.stale && (
            <p className="text-amber-300">
              Older strategy/source snapshot. Inspect it or explicitly generate a fresh run;
              automatic regeneration is disabled.
            </p>
          )}
          {run.status === "running" && (
            <p role="status">Analysis running; browsing does not wait.</p>
          )}
        </>
      )}
      <p>
        Catalog: {state.status?.catalog_updated_at ?? "unavailable"} · new-engine daily ceiling $
        {((state.status?.daily_cap_microusd ?? 1000000) / 1e6).toFixed(2)}. Existing New Cards
        analysis uses a separate quota.
      </p>
    </div>
  );
}

export function DiscoverResults({ state, controller }: StateProps) {
  const run = state.status?.run;
  return (
    <div className="space-y-4">
      <div className={BOX}>
        <h3 className="font-medium">AI-assessed independent shortlist</h3>
        <p className="text-sm text-gray-400">
          At most 32 candidates, not exhaustive catalog coverage. Unassessed/failed/uncertain
          matches are not proof of no useful cards.
        </p>
        {!run?.candidates.length && (
          <p>No shortlist available. Browse source cards independently.</p>
        )}
        <VisualCardGrid>
          {run?.candidates.map((card) => (
            <Candidate
              key={card.oracle_id}
              card={card}
              run={run}
              state={state}
              controller={controller}
            />
          ))}
        </VisualCardGrid>
      </div>
      <div className={BOX}>
        <h3 className="font-medium">Local matches · not fit recommendations</h3>
        {state.page && (
          <p>
            {state.page.total} source matches; showing {state.page.cards.length}. Snapshot{" "}
            {state.page.snapshot_hash.slice(0, 12)}
          </p>
        )}
        <VisualCardGrid>
          {state.page?.cards.map((card) => (
            <Candidate
              key={card.oracle_id}
              card={card}
              run={null}
              state={state}
              controller={controller}
            />
          ))}
        </VisualCardGrid>
        {state.page?.next_cursor && (
          <button
            className={BUTTON}
            disabled={state.browsing}
            onClick={() => void controller.search({}, true)}
          >
            Next source page
          </button>
        )}
      </div>
    </div>
  );
}

interface CandidateProps extends StateProps {
  card: DiscoverCandidate;
  run: DiscoverRun | null;
}

function Candidate(props: CandidateProps) {
  return (
    <VisualCardTile
      name={props.card.facts.name}
      imageUri={props.card.image_uri ?? null}
      footer={<CandidateDetails {...props} />}
    />
  );
}

function CandidateDetails({ card, run, state, controller }: CandidateProps) {
  const canRecommend = !!run && card.recommended && !run.stale && !card.excluded;
  return (
    <article className="space-y-2">
      <h4 className="font-semibold">
        {card.facts.name} <ManaCost cost={card.facts.mana_cost} />
      </h4>
      <p className="text-xs text-gray-400">
        Artwork: current catalog printing. Source facts and advice below retain their pinned
        snapshot.
      </p>
      <details>
        <summary className="cursor-pointer text-sm">Authoritative source facts</summary>
        <SourceFacts face={card.facts} />
        {card.facts.faces.map((face, index) => (
          <SourceFacts key={index} face={face} />
        ))}
        <p className="text-sm">
          Mana value {card.facts.mana_value ?? "unknown"} · layout
          {card.facts.layout ?? "unknown"} · keywords{" "}
          {card.facts.keywords?.join(", ") || "none supplied"}
        </p>
        <a
          className="text-sm underline"
          target="_blank"
          rel="noreferrer"
          href={`https://scryfall.com/search?q=oracleid%3A${encodeURIComponent(card.oracle_id)}`}
        >
          View on Scryfall
        </a>
      </details>
      <p className="text-sm">
        {card.state}
        {card.assessment ? ` · ${card.assessment.fit}` : ""}
        {card.recommended ? " · ranked recommendation (unverified)" : ""}
      </p>
      {card.assessment && (
        <div className="text-sm text-gray-300 space-y-1">
          <p>AI advice: {card.assessment.reason}</p>
          <p>Caveat: {card.assessment.caveat}</p>
          {card.assessment.evidence.map((e, i) => (
            <blockquote key={i}>
              {e.key}: “{e.quote}”
            </blockquote>
          ))}
        </div>
      )}
      {card.evidence_errors.length > 0 && (
        <p className="text-amber-300 text-sm">
          Failed grounding: {card.evidence_errors.join(", ")}. Advice not offered as a
          recommendation.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {run && (
          <button
            className={BUTTON}
            disabled={!canRecommend || !!state.planning}
            onClick={() => void controller.plan(card.oracle_id, run.id)}
          >
            Plan recommendation
          </button>
        )}
        <button
          className={BUTTON}
          disabled={card.excluded || !!state.planning}
          onClick={() => void controller.plan(card.oracle_id, null)}
        >
          Manual source addition
        </button>
        {run && (
          <button
            className={BUTTON}
            onClick={() => void controller.feedback(card.oracle_id, "incorrect")}
          >
            Report incorrect
          </button>
        )}
      </div>
      {card.excluded && (
        <p className="text-xs text-gray-400">Already physical/planned or explicitly avoided.</p>
      )}
    </article>
  );
}

function SourceFacts({ face }: { face: DiscoverFace }) {
  return (
    <div className="mt-2 text-sm">
      <p>
        {face.name} <ManaCost cost={face.mana_cost} /> · {face.type_line ?? "unknown type"}
      </p>
      <p className="whitespace-pre-wrap">
        {face.oracle_text ?? "No top-level text supplied; inspect faces."}
      </p>
      {(face.power || face.toughness) && (
        <p>
          Power/toughness {face.power ?? "?"}/{face.toughness ?? "?"}
        </p>
      )}
      {face.loyalty && <p>Loyalty {face.loyalty}</p>}
      {face.defense && <p>Defense {face.defense}</p>}
    </div>
  );
}

function RulesBrowser({ state, controller }: StateProps) {
  const [term, setTerm] = useState("");
  const rules = state.rulesPage?.rule_results;
  return (
    <div className={BOX}>
      <h3>Browse complete rules · no model call</h3>
      <Filter label="Rule text contains (literal)" value={term} onChange={setTerm} />
      <button
        className={BUTTON}
        disabled={!term.trim() || state.browsing || !state.status?.ready}
        onClick={() => void controller.searchRules(term)}
      >
        Search rules
      </button>
      {rules && (
        <>
          <p>
            {rules.matching_count} literal matches; showing {rules.selected.length} complete
            entries. Snapshot {rules.rules_hash.slice(0, 12)}. Ordering is not strategic relevance.
          </p>
          {rules.selected.map((entry) => (
            <details key={entry.key}>
              <summary>{entry.key}</summary>
              <p className="whitespace-pre-wrap text-sm">{entry.text}</p>
            </details>
          ))}
          {rules.next_cursor && (
            <button
              className={BUTTON}
              disabled={state.browsing}
              onClick={() => void controller.searchRules("", true)}
            >
              Next rules page (same query)
            </button>
          )}
        </>
      )}
    </div>
  );
}

export function DiscoverTrace({ state, controller }: StateProps) {
  const profile = state.trace?.["profile"];
  const strategy = typeof profile === "string" && profile.startsWith("app-strategy-");
  return (
    <div className={BOX}>
      <RulesBrowser state={state} controller={controller} />
      <h3>{strategy ? "Private commander strategy trace" : "Private plan/search trace"}</h3>
      <p className="text-sm text-gray-400">
        Private source context, raw answers, attempts and usage. Card runs also include initial and
        replacement plans, actual queries/counts/errors and native rules pages. Dropped initial
        discoveries are not silently retained. Exports may contain your goal; share deliberately.
      </p>
      <button
        className={BUTTON}
        disabled={strategy ? !state.status?.strategy_run : !state.status?.run}
        onClick={() => void controller.inspect(strategy)}
      >
        Refresh trace (no model call)
      </button>
      {state.trace && (
        <>
          <button className={BUTTON} onClick={() => exportTrace(state.trace)}>
            Export private trace
          </button>
          <pre className="max-h-[600px] overflow-auto whitespace-pre-wrap text-xs">
            {JSON.stringify(state.trace, null, 2)}
          </pre>
        </>
      )}
    </div>
  );
}

function exportTrace(trace: Record<string, unknown> | null): void {
  if (!trace) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(trace, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "discover-private-trace.json";
  link.click();
  URL.revokeObjectURL(url);
}
