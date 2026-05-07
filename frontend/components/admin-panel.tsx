"use client";

import { useState } from "react";

type Job = "sync" | "tag" | "embed";

const JOBS: { id: Job; label: string; path: string; description: string }[] = [
  {
    id: "sync",
    label: "Sync cards",
    path: "/api/v1/admin/sync-cards",
    description: "Pull fresh Scryfall bulk data and upsert the cards table.",
  },
  {
    id: "tag",
    label: "Tag cards",
    path: "/api/v1/admin/tag-cards",
    description: "Re-classify cards with the rule-based tagger.",
  },
  {
    id: "embed",
    label: "Embed cards",
    path: "/api/v1/admin/embed-cards",
    description: "Generate Gemini embeddings for un-embedded cards.",
  },
];

type State =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; body: unknown }
  | { kind: "error"; message: string };

export function AdminPanel() {
  const [states, setStates] = useState<Record<Job, State>>({
    sync: { kind: "idle" },
    tag: { kind: "idle" },
    embed: { kind: "idle" },
  });

  async function run(job: Job, path: string) {
    setStates((s) => ({ ...s, [job]: { kind: "running" } }));
    try {
      const res = await fetch(path, { method: "POST" });
      const body = (await res.json().catch(() => ({}))) as unknown;
      if (!res.ok) {
        const err = body as { detail?: string; error?: { message?: string } };
        const msg = err.error?.message ?? err.detail ?? `HTTP ${res.status}`;
        setStates((s) => ({ ...s, [job]: { kind: "error", message: msg } }));
        return;
      }
      setStates((s) => ({ ...s, [job]: { kind: "ok", body } }));
    } catch (e) {
      setStates((s) => ({
        ...s,
        [job]: { kind: "error", message: e instanceof Error ? e.message : String(e) },
      }));
    }
  }

  return (
    <div className="space-y-4">
      {JOBS.map(({ id, label, path, description }) => {
        const state = states[id];
        const running = state.kind === "running";
        return (
          <div
            key={id}
            className="rounded border border-white/10 bg-black/30 p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-white">{label}</h2>
                <p className="text-sm text-gray-400">{description}</p>
              </div>
              <button
                type="button"
                onClick={() => run(id, path)}
                disabled={running}
                className="flex-shrink-0 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? "Running…" : "Run"}
              </button>
            </div>
            {state.kind === "ok" ? (
              <pre className="mt-3 overflow-x-auto rounded bg-black/40 p-3 text-xs text-green-300">
                {JSON.stringify(state.body, null, 2)}
              </pre>
            ) : null}
            {state.kind === "error" ? (
              <p className="mt-3 text-sm text-red-400">Error: {state.message}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
