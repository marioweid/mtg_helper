"use client";

import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { TutorMode, TutorStateResponse } from "@/lib/types";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const PRIMARY = `min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;

interface TutorPanelProps {
  deckId: string;
}

interface TutorPanelViewProps {
  state: TutorStateResponse;
  busy: boolean;
  error: string | null;
  onMode: (mode: TutorMode) => void;
  onGenerate: () => void;
}

export function TutorPanel({ deckId }: TutorPanelProps) {
  const [state, setState] = useState<TutorStateResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<TutorStateResponse | null> => {
    try {
      const next = await apiClient.getTutor(deckId);
      setState(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor could not load");
      return null;
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state?.latest_run?.status !== "running") return;
    let active = true;
    let timer = window.setTimeout(poll, 1500);

    async function poll() {
      const next = await load();
      if (active && next?.latest_run?.status === "running") timer = window.setTimeout(poll, 1500);
    }
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [load, state?.latest_run?.status]);

  async function saveMode(mode: TutorMode) {
    setBusy(true);
    try {
      setState(await apiClient.saveTutorSetup(deckId, { mode }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor mode could not save");
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    setBusy(true);
    try {
      setState(await apiClient.generateTutorGuide(deckId, { request_key: crypto.randomUUID() }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guide generation could not start");
    } finally {
      setBusy(false);
    }
  }

  if (!state)
    return (
      <p role="status" className="text-sm text-gray-400">
        Loading Tutor…
      </p>
    );
  return (
    <TutorPanelView
      state={state}
      busy={busy}
      error={error}
      onMode={saveMode}
      onGenerate={generate}
    />
  );
}

export function TutorPanelView({ state, busy, error, onMode, onGenerate }: TutorPanelViewProps) {
  const run = state.latest_run;
  const displayedRun = run?.guide ? run : state.last_successful_run;
  const guide = displayedRun?.guide;
  const outdated = !!displayedRun && !displayedRun.current;
  const generating = run?.status === "running";
  const action = guide ? (outdated ? "Update Guide" : "Generate Guide") : "Generate Guide";
  return (
    <section aria-label="Tutor" className="min-w-0 space-y-5">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight text-white">Tutor</h2>
        <p className="text-sm leading-6 text-gray-400">
          Choose a teaching perspective, then explicitly generate a saved guide for this deck.
        </p>
      </header>
      <fieldset disabled={busy} className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
        <legend className="px-1 text-sm font-medium text-gray-200">Choose a mode</legend>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <ModeOption
            mode="commander"
            label="Commander"
            detail="General multiplayer piloting and the deck’s own strategic identity."
            selected={state.mode === "commander"}
            onSelect={onMode}
          />
          <ModeOption
            mode="cedh"
            label="cEDH"
            detail="Efficient lines, protection windows, and race-versus-grind decisions—not a strength certificate."
            selected={state.mode === "cedh"}
            onSelect={onMode}
          />
        </div>
      </fieldset>
      {error && (
        <p role="alert" className="rounded-xl border border-red-400/20 p-4 text-sm text-red-200">
          {error}
        </p>
      )}
      {state.mode && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={PRIMARY}
            disabled={busy || generating}
            onClick={onGenerate}
          >
            {generating ? "Generating Guide…" : action}
          </button>
          <p className="text-xs leading-5 text-gray-400">
            Generation starts only when you click this button.
          </p>
        </div>
      )}
      {outdated && (
        <p
          role="status"
          className="rounded-xl border border-amber-300/25 p-4 text-sm text-amber-100"
        >
          Outdated: this guide describes an earlier saved deck state.
        </p>
      )}
      {run?.status === "failed" || run?.status === "interrupted" ? (
        <p role="alert" className="rounded-xl border border-red-400/20 p-4 text-sm text-red-200">
          {run.error}
        </p>
      ) : null}
      {guide && (
        <Guide
          title={guide.title}
          content={guide.content}
          openingHands={guide.opening_hands}
          warnings={displayedRun?.evidence?.warnings ?? []}
        />
      )}
    </section>
  );
}

function ModeOption({
  mode,
  label,
  detail,
  selected,
  onSelect,
}: {
  mode: TutorMode;
  label: string;
  detail: string;
  selected: boolean;
  onSelect: (mode: TutorMode) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(mode)}
      className={`min-h-11 rounded-xl border p-4 text-left ${FOCUS} ${selected ? "border-indigo-400 bg-indigo-400/10" : "border-white/10 hover:border-white/30"}`}
    >
      <span className="block font-semibold text-white">{label}</span>
      <span className="mt-1 block text-sm leading-6 text-gray-400">{detail}</span>
    </button>
  );
}

function Guide({
  title,
  content,
  openingHands,
  warnings,
}: {
  title: string;
  content: string;
  openingHands: { decision: string; cards: string[]; explanation: string }[];
  warnings: string[];
}) {
  return (
    <article className="min-w-0 rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-6">
      <h3 className="break-words text-xl font-semibold text-white">{title}</h3>
      {warnings.map((warning) => (
        <p key={warning} className="mt-3 text-sm leading-6 text-amber-200">
          {warning}
        </p>
      ))}
      <div className="mt-4 whitespace-pre-wrap break-words text-sm leading-7 text-gray-200">
        {content}
      </div>
      <div className="mt-5 space-y-3" aria-label="Worked opening hands">
        {openingHands.map((hand) => (
          <section key={hand.decision} className="rounded-xl border border-white/10 p-4">
            <h4 className="font-semibold capitalize text-white">{hand.decision}</h4>
            <p className="mt-1 break-words text-sm leading-6 text-gray-200">
              {hand.cards.join(", ")}
            </p>
            <p className="mt-2 text-sm leading-6 text-gray-400">{hand.explanation}</p>
          </section>
        ))}
      </div>
    </article>
  );
}
