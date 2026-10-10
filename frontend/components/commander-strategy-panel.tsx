"use client";

import type { DiscoverController, DiscoverState } from "@/components/discover-state";
import { STRATEGY_PROFILE } from "@/lib/discovery-types";
import type { CommanderStrategyChoice, DiscoverRun } from "@/lib/discovery-types";

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
      aria-label="Commander strategy choices"
      className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4"
    >
      <h3 className="font-semibold">What does this commander want to do?</h3>
      <p className="text-sm text-gray-300">
        Draft three directions from the commander&apos;s printed facts. Compare their pace, early
        setup/ramp, engine and possible payoff. A direction need not be a complete win condition.
        Choose one as the editable goal, then explicitly Generate cards. Your existing goal and
        saved deck description are not changed automatically.
      </p>
      <p className="text-sm text-amber-300">
        AI drafts · unverified. Pace and payoff are proposals, not proven speed or combo claims.
        This is not an assessment of your physical deck. All three choices use one separate paid
        Luna request and share the Discover daily spending limit.
      </p>
      <button
        type="button"
        className={BUTTON}
        disabled={!state.status?.ready || busy}
        onClick={() => void controller.draftStrategy()}
      >
        Draft 3 commander strategies · up to ${cap}
      </button>
      {run && (
        <StrategyResult
          run={run}
          busy={busy}
          onUse={(index) => controller.useStrategy(index)}
          onInspect={onInspect}
        />
      )}
    </section>
  );
}

interface ResultProps {
  run: DiscoverRun;
  busy: boolean;
  onUse: (index: number) => void;
  onInspect: () => void;
}

export function StrategyResult({ run, busy, onUse, onInspect }: ResultProps) {
  const usable = run.status === "completed" && !run.stale && run.profile === STRATEGY_PROFILE;
  return (
    <div className="space-y-3 text-sm">
      <p role="status">Draft status: {run.status}</p>
      <p>
        Known estimate ${(run.known_cost_microusd / 1e6).toFixed(5)} · held reservation $
        {(run.held_microusd / 1e6).toFixed(5)}. Estimates, not provider-enforced caps.
      </p>
      <div className="grid gap-3 lg:grid-cols-3">
        {run.strategies?.map((choice, index) => (
          <StrategyChoice
            key={index}
            choice={choice}
            disabled={!usable || busy}
            onUse={() => onUse(index)}
          />
        ))}
      </div>
      {!run.strategies?.length && <p>No selectable strategies available yet.</p>}
      {run.stale && (
        <p className="text-amber-300">
          Commander, source or draft protocol changed; draft fresh strategies. Original evidence
          remains in the private trace.
        </p>
      )}
      {run.error && (
        <p role="alert" className="text-red-300">
          {run.error}
        </p>
      )}
      <button type="button" className={BUTTON} onClick={onInspect}>
        Inspect strategy trace
      </button>
    </div>
  );
}

function StrategyChoice({
  choice,
  disabled,
  onUse,
}: {
  choice: CommanderStrategyChoice;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <article className="space-y-3 rounded-lg border border-white/10 p-3">
      <h4 className="font-semibold text-white">{choice.title}</h4>
      <dl className="space-y-2 text-gray-300">
        {[
          ["Pace", choice.pace],
          ["Early setup / ramp", choice.early_game],
          ["Main engine", choice.engine],
          ["Payoff / closing direction", choice.payoff],
        ].map(([label, text]) => (
          <div key={label}>
            <dt className="font-medium text-white">{label}</dt>
            <dd className="whitespace-pre-wrap">{text}</dd>
          </div>
        ))}
      </dl>
      <p className="whitespace-pre-wrap text-gray-300">{choice.explanation}</p>
      <ul className="list-inside list-disc text-amber-300">
        {choice.uncertainties.map((uncertainty, index) => (
          <li key={index}>{uncertainty}</li>
        ))}
      </ul>
      <button
        type="button"
        className={BUTTON}
        aria-label={`Use ${choice.title} as goal`}
        disabled={disabled}
        onClick={onUse}
      >
        Use as goal
      </button>
    </article>
  );
}
