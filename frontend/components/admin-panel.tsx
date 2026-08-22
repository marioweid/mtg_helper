"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ThemeManager } from "@/components/theme-manager";

type Job = "sync" | "tag" | "refresh-all";
type JobKey = Job | "mtgjson";

const JOBS: { id: Job; label: string; path: string; description: string }[] = [
  {
    id: "refresh-all",
    label: "Refresh all",
    path: "/api/v1/admin/refresh-all",
    description:
      "Apply schema, sync Scryfall, MTGJSON, Moxfield and Archidekt themes, then re-tag cards.",
  },
  {
    id: "sync",
    label: "Sync cards",
    path: "/api/v1/admin/sync-cards",
    description: "Pull fresh Scryfall bulk data and upsert the cards table.",
  },
  {
    id: "tag",
    label: "Sync hubs",
    path: "/api/v1/admin/sync-moxfield-hubs",
    description: "Refresh stale Moxfield hubs and rebuild theme card membership.",
  },
];

type JobStatus = "idle" | "running" | "ok" | "error";

type JobSnapshot = {
  key: JobKey;
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
  mtgjson: JobSnapshot;
  tag: JobSnapshot;
  refresh_all: JobSnapshot;
};

type MoxfieldHub = {
  id: number;
  tag: string;
  name: string;
  description: string | null;
  active: boolean;
  last_seen_at: string | null;
  synced_at: string | null;
  last_card_sync_at: string | null;
  last_stat_fetch_at: string | null;
  card_count: number;
};

const STATUS_PATH = "/api/v1/admin/status";
const POLL_INTERVAL_MS = 2000;

const SLOT_BY_ID: Record<Job, keyof StatusResponse> = {
  sync: "sync",
  tag: "tag",
  "refresh-all": "refresh_all",
};

function emptySnapshot(key: JobKey): JobSnapshot {
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

function formatTimestamp(value: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function AdminPanel() {
  const [status, setStatus] = useState<StatusResponse>(() => ({
    sync: emptySnapshot("sync"),
    mtgjson: emptySnapshot("mtgjson"),
    tag: emptySnapshot("tag"),
    refresh_all: emptySnapshot("refresh-all"),
  }));
  const [kickoffError, setKickoffError] = useState<Partial<Record<Job, string>>>({});
  const [manualError, setManualError] = useState<string | null>(null);
  const [hubs, setHubs] = useState<MoxfieldHub[]>([]);
  const [hubRef, setHubRef] = useState("");
  const [hubSampleSize, setHubSampleSize] = useState(10);
  const [baselineSampleSize, setBaselineSampleSize] = useState(80);
  const [deckIds, setDeckIds] = useState("");
  const [baselineDeckIds, setBaselineDeckIds] = useState("");

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

  const fetchHubs = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/admin/moxfield-hubs");
      if (!res.ok) return;
      const body = (await res.json()) as { hubs: MoxfieldHub[] };
      setHubs(body.hubs);
      setHubRef((current) => current || body.hubs[0]?.tag || "");
    } catch {
      // Optional helper data; manual text input still works.
    }
  }, []);

  const anyRunning = useMemo(
    () =>
      status.sync.status === "running" ||
      status.tag.status === "running" ||
      status.refresh_all.status === "running",
    [status],
  );
  const selectedHub = useMemo(
    () =>
      hubs.find((hub) => hub.tag === hubRef || hub.name === hubRef || String(hub.id) === hubRef),
    [hubRef, hubs],
  );

  useEffect(() => {
    void fetchStatus();
    void fetchHubs();
  }, [fetchHubs, fetchStatus]);

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

  function parseDeckIds(value: string): string[] | null {
    const ids = value
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    return ids.length > 0 ? ids : null;
  }

  async function runManualHubSync() {
    const selectedHub = hubRef.trim();
    if (!selectedHub) {
      setManualError("Choose or enter a hub first.");
      return;
    }
    setManualError(null);
    const body = {
      hub_ref: selectedHub,
      hub_sample_size: hubSampleSize,
      baseline_sample_size: baselineSampleSize,
      deck_ids: parseDeckIds(deckIds),
      baseline_deck_ids: parseDeckIds(baselineDeckIds),
    };
    try {
      const res = await fetch("/api/v1/admin/sync-moxfield-hub", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const responseBody = (await res.json().catch(() => ({}))) as {
          detail?: string | { message?: string };
          error?: { message?: string };
        };
        const detail =
          typeof responseBody.detail === "string"
            ? responseBody.detail
            : responseBody.detail?.message;
        setManualError(responseBody.error?.message ?? detail ?? `HTTP ${res.status}`);
        return;
      }
      setStatus((prev) => ({
        ...prev,
        tag: {
          ...prev.tag,
          status: "running",
          phase: "syncing manual hub",
          current: 0,
          total: 1,
          finished_at: null,
          error: null,
          result: null,
        },
      }));
      void fetchStatus();
    } catch (e) {
      setManualError(e instanceof Error ? e.message : String(e));
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

            {errorMsg ? <p className="mt-3 text-sm text-red-400">Error: {errorMsg}</p> : null}
          </div>
        );
      })}
      <ThemeManager />
      <div className="rounded border border-white/10 bg-black/30 p-4">
        <div className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-white">Manual Moxfield hub sync</h2>
              <p className="text-sm text-gray-400">
                Refresh one hub, override sample sizes, or paste exact Moxfield deck IDs.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void runManualHubSync()}
              disabled={status.tag.status === "running"}
              className="flex-shrink-0 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {status.tag.status === "running" ? "Running…" : "Run"}
            </button>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <label className="space-y-1 text-sm">
              <span className="text-gray-300">Hub</span>
              <select
                value={hubRef}
                onChange={(event) => setHubRef(event.target.value)}
                className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white"
              >
                {hubs.map((hub) => (
                  <option key={hub.tag} value={hub.tag}>
                    {hub.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-gray-300">Hub tag/name/id</span>
              <input
                type="text"
                value={hubRef}
                onChange={(event) => setHubRef(event.target.value)}
                placeholder="control"
                className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white placeholder:text-gray-600"
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-gray-300">Hub decks</span>
              <input
                type="number"
                min={1}
                max={200}
                value={hubSampleSize}
                onChange={(event) => setHubSampleSize(Number(event.target.value))}
                className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white"
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-gray-300">Baseline decks</span>
              <input
                type="number"
                min={1}
                max={200}
                value={baselineSampleSize}
                onChange={(event) => setBaselineSampleSize(Number(event.target.value))}
                className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white"
              />
            </label>
          </div>

          {selectedHub ? (
            <div className="grid gap-2 rounded border border-white/10 bg-black/20 p-3 text-xs text-gray-400 md:grid-cols-3">
              <div>
                <span className="block text-gray-500">Last card sync</span>
                <span className="text-gray-200">
                  {formatTimestamp(selectedHub.last_card_sync_at)}
                </span>
              </div>
              <div>
                <span className="block text-gray-500">Catalog seen</span>
                <span className="text-gray-200">{formatTimestamp(selectedHub.last_seen_at)}</span>
              </div>
              <div>
                <span className="block text-gray-500">Cards in hub</span>
                <span className="text-gray-200">
                  {Number(selectedHub.card_count ?? 0).toLocaleString()}
                </span>
              </div>
            </div>
          ) : null}

          <label className="space-y-1 text-sm">
            <span className="text-gray-300">Exact hub deck IDs</span>
            <textarea
              value={deckIds}
              onChange={(event) => setDeckIds(event.target.value)}
              rows={3}
              placeholder="Optional. One publicId per line or comma separated."
              className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white placeholder:text-gray-600"
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="text-gray-300">Exact baseline deck IDs</span>
            <textarea
              value={baselineDeckIds}
              onChange={(event) => setBaselineDeckIds(event.target.value)}
              rows={3}
              placeholder="Optional. Leave empty to sample general Commander decks."
              className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-white placeholder:text-gray-600"
            />
          </label>

          {manualError ? <p className="text-sm text-red-400">Error: {manualError}</p> : null}
        </div>
      </div>
    </div>
  );
}
