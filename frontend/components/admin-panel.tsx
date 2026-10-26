"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminDiscoverPanel } from "@/components/admin-discover-panel";
import { ScryfallPublication, type ScryfallSourceStatus } from "@/components/scryfall-publication";

type Job = { status: "idle" | "running" | "ok" | "error"; error: string | null };
type Status = { sync: Job; refresh_all: Job; scryfall_sources: ScryfallSourceStatus };

const INITIAL: Status = {
  sync: { status: "idle", error: null },
  refresh_all: { status: "idle", error: null },
  scryfall_sources: { status: "unavailable" },
};

export function AdminPanel() {
  const [status, setStatus] = useState<Status>(INITIAL);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const response = await fetch("/api/v1/admin/status");
    if (response.ok) setStatus((await response.json()) as Status);
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [load]);

  async function start(path: string) {
    setError(null);
    try {
      const response = await fetch(path, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start Scryfall refresh.");
    }
  }

  return (
    <div className="space-y-4">
      <AdminDiscoverPanel />
      <ScryfallPublication source={status.scryfall_sources} />
      <section className="rounded border border-white/10 bg-black/30 p-4">
        <h2 className="text-base font-semibold text-white">Scryfall catalog</h2>
        <p className="mt-1 text-sm text-gray-400">
          Publish card facts, printed keywords, and Oracle tags in one source generation.
        </p>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void start("/api/v1/admin/sync-cards")}
            disabled={status.sync.status === "running"}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {status.sync.status === "running" ? "Syncing…" : "Sync Scryfall"}
          </button>
          <button
            type="button"
            onClick={() => void start("/api/v1/admin/refresh-all")}
            disabled={status.refresh_all.status === "running"}
            className="rounded border border-white/20 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {status.refresh_all.status === "running" ? "Refreshing…" : "Apply schema and sync"}
          </button>
        </div>
        {(error ?? status.sync.error ?? status.refresh_all.error) && (
          <p className="mt-3 text-sm text-red-400">
            {error ?? status.sync.error ?? status.refresh_all.error}
          </p>
        )}
      </section>
    </div>
  );
}
