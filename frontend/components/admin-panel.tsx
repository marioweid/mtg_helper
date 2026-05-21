"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Job = "sync" | "tag" | "embed" | "refresh-all";

const JOBS: { id: Job; label: string; path: string; description: string }[] = [
  {
    id: "refresh-all",
    label: "Refresh all",
    path: "/api/v1/admin/refresh-all",
    description: "Run sync → tag → embed back-to-back. Use after pulling new Scryfall sets.",
  },
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

type JobStatus = "idle" | "running" | "ok" | "error";

type JobSnapshot = {
  key: Job;
  status: JobStatus;
  phase: string;
  current: number;
  total: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
};

type StatusResponse = {
  sync: JobSnapshot;
  tag: JobSnapshot;
  embed: JobSnapshot;
  refresh_all: JobSnapshot;
};

const STATUS_PATH = "/api/v1/admin/status";
const POLL_INTERVAL_MS = 2000;

const SLOT_BY_ID: Record<Job, keyof StatusResponse> = {
  sync: "sync",
  tag: "tag",
  embed: "embed",
  "refresh-all": "refresh_all",
};

function emptySnapshot(key: Job): JobSnapshot {
  return {
    key,
    status: "idle",
    phase: "",
    current: 0,
    total: 0,
    started_at: null,
    finished_at: null,
    error: null,
    result: null,
  };
}

export function AdminPanel() {
  const [status, setStatus] = useState<StatusResponse>(() => ({
    sync: emptySnapshot("sync"),
    tag: emptySnapshot("tag"),
    embed: emptySnapshot("embed"),
    refresh_all: emptySnapshot("refresh-all"),
  }));
  const [kickoffError, setKickoffError] = useState<Partial<Record<Job, string>>>({});

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(STATUS_PATH);
      if (!res.ok) return;
      const body = (await res.json()) as StatusResponse;
      setStatus(body);
    } catch {
      // Transient — next poll will retry.
    }
  }, []);

  const anyRunning = useMemo(
    () =>
      status.sync.status === "running" ||
      status.tag.status === "running" ||
      status.embed.status === "running" ||
      status.refresh_all.status === "running",
    [status],
  );

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!anyRunning) return;
    const id = setInterval(() => {
      void fetchStatus();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [anyRunning, fetchStatus]);

  async function run(job: Job, path: string) {
    setKickoffError((s) => ({ ...s, [job]: undefined }));
    try {
      const res = await fetch(path, { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          detail?: string;
          error?: { message?: string };
        };
        const msg = body.error?.message ?? body.detail ?? `HTTP ${res.status}`;
        setKickoffError((s) => ({ ...s, [job]: msg }));
        return;
      }
      // Optimistically reflect "running" until the next poll lands.
      setStatus((prev) => ({
        ...prev,
        [SLOT_BY_ID[job]]: {
          ...prev[SLOT_BY_ID[job]],
          status: "running",
          phase: "",
          current: 0,
          total: 0,
          finished_at: null,
          error: null,
          result: null,
        },
      }));
      void fetchStatus();
    } catch (e) {
      setKickoffError((s) => ({
        ...s,
        [job]: e instanceof Error ? e.message : String(e),
      }));
    }
  }

  return (
    <div className="space-y-4">
      {JOBS.map(({ id, label, path, description }) => {
        const snapshot = status[SLOT_BY_ID[id]];
        const running = snapshot.status === "running";
        const percent =
          snapshot.total > 0
            ? Math.min(100, Math.round((snapshot.current / snapshot.total) * 100))
            : null;
        const errorMsg = kickoffError[id] ?? snapshot.error;
        return (
          <div key={id} className="rounded border border-white/10 bg-black/30 p-4">
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

            {(running || snapshot.status === "ok") && snapshot.total > 0 ? (
              <div className="mt-3 space-y-1">
                <div className="h-2 w-full overflow-hidden rounded bg-white/10">
                  <div
                    className="h-full bg-blue-500 transition-all duration-300"
                    style={{ width: `${percent ?? 0}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-gray-400">
                  <span>
                    {snapshot.phase || "starting"}
                    {percent !== null ? ` — ${percent}%` : ""}
                  </span>
                  <span>
                    {snapshot.current.toLocaleString()} / {snapshot.total.toLocaleString()}
                  </span>
                </div>
              </div>
            ) : null}

            {running && snapshot.total === 0 && snapshot.phase ? (
              <p className="mt-3 text-sm text-gray-300">Phase: {snapshot.phase}</p>
            ) : null}

            {snapshot.status === "ok" && snapshot.result ? (
              <pre className="mt-3 overflow-x-auto rounded bg-black/40 p-3 text-xs text-green-300">
                {JSON.stringify(snapshot.result, null, 2)}
              </pre>
            ) : null}

            {errorMsg ? (
              <p className="mt-3 text-sm text-red-400">Error: {errorMsg}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
