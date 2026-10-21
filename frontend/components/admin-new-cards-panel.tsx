"use client";

import { useEffect, useState } from "react";

type Status = {
  process_enabled: boolean;
  automatic_enabled: boolean;
  daily_limit: number;
  calls: number;
  next_reset: string;
  manual_active: boolean;
  automatic_active: boolean;
  cancelled: boolean;
  waiting: number;
  failed: number;
  last_error: string | null;
  source_updated_at?: string | null;
  last_run_at?: string | null;
};

type StatusResponse = { data: Status };

const EMPTY: Status = {
  process_enabled: false,
  automatic_enabled: false,
  daily_limit: 100,
  calls: 0,
  next_reset: "unknown",
  manual_active: false,
  automatic_active: false,
  cancelled: false,
  waiting: 0,
  failed: 0,
  last_error: null,
};

/** Global New Cards controls, deliberately separate from deck-level results. */
export function AdminNewCardsPanel() {
  const [status, setStatus] = useState(EMPTY);
  const [limit, setLimit] = useState("100");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingStart, setConfirmingStart] = useState(false);
  const locked = !status.process_enabled;
  const unsafeToStart = saving || error !== null;

  async function load() {
    const response = await fetch("/api/v1/admin/new-cards");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const next = ((await response.json()) as StatusResponse).data;
    setStatus(next);
    setLimit(String(next.daily_limit));
  }

  useEffect(() => {
    void load().catch((cause: unknown) => setError(String(cause)));
  }, []);

  async function action(path: string, body?: object) {
    setError(null);
    setSaving(true);
    try {
      const response = body
        ? await fetch(path, {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
          })
        : await fetch(path, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next = ((await response.json()) as StatusResponse).data;
      setStatus(next);
      setLimit(String(next.daily_limit));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3"
      aria-label="New Cards controls"
    >
      <h2 className="font-semibold text-white">New Cards global controls</h2>
      <NewCardsStatus status={status} locked={locked} />
      <NewCardsActions
        limit={limit}
        locked={locked}
        saving={saving}
        unsafeToStart={unsafeToStart}
        onLimitChange={setLimit}
        onSave={() =>
          void action("/api/v1/admin/new-cards", {
            automatic_enabled: !status.automatic_enabled,
            daily_limit: Number(limit),
          })
        }
        onStart={() => setConfirmingStart(true)}
        onCancel={() => void action("/api/v1/admin/new-cards/cancel")}
      />
      <StartConfirmation
        confirming={confirmingStart}
        saving={saving}
        unsafeToStart={unsafeToStart}
        onClose={() => setConfirmingStart(false)}
        onConfirm={() => {
          setConfirmingStart(false);
          void action("/api/v1/admin/new-cards/start");
        }}
      />
      {error && <p role="alert">New Cards control failed: {error}</p>}
      {status.last_error && <p role="alert">Last run error: {status.last_error}</p>}
    </section>
  );
}

function NewCardsStatus({ status, locked }: { status: Status; locked: boolean }) {
  return (
    <>
      <p className="text-sm text-gray-300">
        Process execution: {status.process_enabled ? "enabled" : "disabled"}.{" "}
        {locked && "This process cannot make paid calls."}
      </p>
      <p className="text-sm text-gray-300">
        Automatic: {status.automatic_enabled ? "on" : "off"} · Run:{" "}
        {status.manual_active || status.automatic_active ? "active" : "idle"} · Waiting{" "}
        {status.waiting} · Failed {status.failed}
      </p>
      <p className="text-sm text-gray-300">
        Source updated {status.source_updated_at ?? "not available"} · Last run{" "}
        {status.last_run_at ?? "not available"}.
      </p>
      <p className="text-sm text-gray-300">
        Usage: {status.calls} / {status.daily_limit} · UTC reset {status.next_reset}
      </p>
    </>
  );
}

function NewCardsActions({
  limit,
  locked,
  saving,
  unsafeToStart,
  onLimitChange,
  onSave,
  onStart,
  onCancel,
}: {
  limit: string;
  locked: boolean;
  saving: boolean;
  unsafeToStart: boolean;
  onLimitChange: (limit: string) => void;
  onSave: () => void;
  onStart: () => void;
  onCancel: () => void;
}) {
  return (
    <>
      <label className="block text-sm">
        Daily package limit
        <input
          aria-label="Daily package limit"
          className="ml-2 rounded text-black"
          value={limit}
          onChange={(event) => onLimitChange(event.target.value)}
          disabled={locked || saving}
        />
      </label>
      <div className="flex gap-2">
        <button type="button" disabled={locked || saving} onClick={onSave}>
          Save automation
        </button>
        <button type="button" disabled={locked || unsafeToStart} onClick={onStart}>
          Start all
        </button>
        <button type="button" disabled={locked || saving} onClick={onCancel}>
          Cancel run
        </button>
      </div>
    </>
  );
}

function StartConfirmation({
  confirming,
  saving,
  unsafeToStart,
  onClose,
  onConfirm,
}: {
  confirming: boolean;
  saving: boolean;
  unsafeToStart: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (!confirming) return null;
  return (
    <div role="dialog" aria-label="Confirm global New Cards start" className="space-x-2">
      <span>Start all pending Commander checks?</span>
      <button type="button" disabled={unsafeToStart} onClick={onConfirm}>
        Confirm start
      </button>
      <button type="button" disabled={saving} onClick={onClose}>
        Keep waiting
      </button>
    </div>
  );
}
