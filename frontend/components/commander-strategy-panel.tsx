"use client";

import type { DiscoverController, DiscoverState } from "@/components/discover-state";
import type { DiscoverRun } from "@/lib/discovery-types";

const BUTTON = "rounded bg-indigo-600 px-3 py-2 text-sm disabled:opacity-40";

interface Props {
  state: DiscoverState;
  controller: DiscoverController;
  onInspect: () => void;
}

export function CommanderStrategyPanel({ state, controller, onInspect }: Props) {
  const run = state.status?.strategy_run;
  const running = state.status?.run?.status === "running" || run?.status === "running";
  const busy = state.generating || state.drafting || running;
  const cap = ((state.status?.strategy_cap_microusd ?? 10000) / 1e6).toFixed(2);
  return (
    <section
      aria-label="Commander strategy draft"
      className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4"
    >
      <h3 className="font-semibold">What does this commander want to do?</h3>
      <p className="text-sm text-gray-300">
        Draft a strategy from the commander&apos;s complete printed facts only. Review it, use it as
        the editable goal below, then explicitly Generate cards. Your existing goal and saved deck
        description are not changed automatically.
      </p>
      <p className="text-sm text-amber-300">
        AI draft · unverified. This is not an assessment of your physical deck. Drafting is one
        separate paid Luna request and shares the Discover daily spending limit.
      </p>
      <button
        type="button"
        className={BUTTON}
        disabled={!state.status?.ready || busy}
        onClick={() => void controller.draftStrategy()}
      >
        Draft commander strategy · up to ${cap}
      </button>
      {run && (
        <StrategyResult
          run={run}
          busy={busy}
          onUse={() => controller.useStrategy()}
          onInspect={onInspect}
        />
      )}
    </section>
  );
}

interface ResultProps {
  run: DiscoverRun;
  busy: boolean;
  onUse: () => void;
  onInspect: () => void;
}

export function StrategyResult({ run, busy, onUse, onInspect }: ResultProps) {
  const usable = run.status === "completed" && !run.stale && !!run.strategy;
  return (
    <div className="space-y-2 text-sm">
      <p role="status">Draft status: {run.status}</p>
      <p>
        Known estimate ${(run.known_cost_microusd / 1e6).toFixed(5)} · held reservation $
        {(run.held_microusd / 1e6).toFixed(5)}. Estimates, not provider-enforced caps.
      </p>
      {run.strategy && (
        <div className="space-y-2">
          <p className="whitespace-pre-wrap text-white">{run.strategy.goal}</p>
          <p className="whitespace-pre-wrap text-gray-300">{run.strategy.explanation}</p>
          <ul className="list-inside list-disc text-amber-300">
            {run.strategy.uncertainties.map((uncertainty, index) => (
              <li key={index}>{uncertainty}</li>
            ))}
          </ul>
        </div>
      )}
      {run.stale && (
        <p className="text-amber-300">Commander or source changed; draft a fresh strategy.</p>
      )}
      {run.error && (
        <p role="alert" className="text-red-300">
          {run.error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={BUTTON} disabled={!usable || busy} onClick={onUse}>
          Use as goal
        </button>
        <button type="button" className={BUTTON} onClick={onInspect}>
          Inspect strategy trace
        </button>
      </div>
    </div>
  );
}
