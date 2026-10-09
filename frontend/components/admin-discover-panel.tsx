"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import {
  AdminDiscoverController,
  type AdminDiscoverState,
} from "@/components/admin-discover-state";

const BUTTON =
  "rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 " +
  "disabled:cursor-not-allowed disabled:opacity-50";

export function AdminDiscoverPanel() {
  const controller = useMemo(() => new AdminDiscoverController(), []);
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  useEffect(() => {
    controller.start();
    return () => controller.stop();
  }, [controller]);
  return (
    <AdminDiscoverControls
      state={state}
      onRefresh={() => void controller.refresh()}
      onToggle={(enabled) => void controller.setEnabled(enabled)}
    />
  );
}

interface ControlsProps {
  state: AdminDiscoverState;
  onRefresh: () => void;
  onToggle: (enabled: boolean) => void;
}

export function AdminDiscoverControls({ state, onRefresh, onToggle }: ControlsProps) {
  const busy = state.loading || state.saving;
  const status = state.enabled === null ? "Unknown" : state.enabled ? "Enabled" : "Disabled";
  return (
    <section
      aria-label="Discover access"
      aria-busy={busy}
      className="space-y-3 rounded border border-white/10 bg-black/30 p-4"
    >
      <div>
        <h2 className="text-base font-semibold text-white">Discover · Experimental</h2>
        <p className="text-sm text-gray-400">
          Enable the Discover tab for your signed-in account only. Other accounts are unchanged.
        </p>
      </div>
      <p role="status" className="text-sm text-gray-300">
        {state.account ? `${state.account.display_name} · ` : "Your account · "}
        {state.loading ? "Loading status…" : state.saving ? "Saving…" : status}
      </p>
      <p className="text-sm text-amber-300">
        Enabling and browsing do not call AI. Generate makes paid requests (up to $0.10/run,
        $1/account/day estimate guards). Verify provider pricing and source readiness before
        generating. Disabling stops future stages; an in-flight request may still bill.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={busy || !state.account || state.enabled === null}
          onClick={() => onToggle(!state.enabled)}
        >
          {state.enabled ? "Disable for my account" : "Enable for my account"}
        </button>
        <button type="button" className={BUTTON} disabled={busy} onClick={onRefresh}>
          Refresh status
        </button>
      </div>
      {state.enabled && (
        <p className="text-sm text-green-300">
          Open a deck (reload if already open) and select Discover · Experimental.
        </p>
      )}
      {state.error && (
        <p role="alert" className="text-sm text-red-400">
          {state.error}
        </p>
      )}
    </section>
  );
}
