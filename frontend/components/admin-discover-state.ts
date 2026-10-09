import { apiClient } from "@/lib/api";
import type { AccountResponse } from "@/lib/types";

export interface AdminDiscoverState {
  account: AccountResponse | null;
  enabled: boolean | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

export class AdminDiscoverController {
  private state: AdminDiscoverState = {
    account: null,
    enabled: null,
    loading: false,
    saving: false,
    error: null,
  };
  private listeners = new Set<() => void>();
  private live = false;
  private epoch = 0;

  getSnapshot = (): AdminDiscoverState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  start(): void {
    this.live = true;
    this.epoch += 1;
    this.update({ loading: false, saving: false, enabled: null, account: null });
    void this.refresh();
  }

  stop(): void {
    this.live = false;
    this.epoch += 1;
  }

  /** Load this account's effective capability without changing overrides or calling AI. */
  async refresh(): Promise<void> {
    if (!this.live || this.state.loading || this.state.saving) return;
    const epoch = this.epoch;
    this.update({ loading: true, enabled: null, error: null });
    try {
      const [account, capabilities] = await Promise.all([
        apiClient.getMe(),
        apiClient.getCapabilities(),
      ]);
      if (typeof capabilities.recommendations !== "boolean") {
        throw new Error("Discover is unavailable here; deploy the updated backend first.");
      }
      if (this.isCurrent(epoch)) {
        this.update({ account, enabled: capabilities.recommendations });
      }
    } catch (error) {
      if (this.isCurrent(epoch)) {
        this.update({ error: error instanceof Error ? error.message : "Status request failed" });
      }
    } finally {
      if (this.isCurrent(epoch)) this.update({ loading: false });
    }
  }

  /** Persist an explicit override for the loaded account only; never enable globally. */
  async setEnabled(enabled: boolean): Promise<void> {
    const account = this.state.account;
    if (!account || !this.canSave()) return;
    const epoch = this.epoch;
    this.update({ saving: true, error: null });
    try {
      await this.save(account.id, enabled);
      if (this.isCurrent(epoch)) this.update({ enabled });
    } catch (error) {
      if (this.isCurrent(epoch)) {
        const message = error instanceof Error ? error.message : "Access update failed";
        this.update({ enabled: null, error: `${message}. Refresh status before trying again.` });
      }
    } finally {
      if (this.isCurrent(epoch)) this.update({ saving: false });
    }
  }

  private async save(accountId: string, enabled: boolean): Promise<void> {
    const response = await fetch("/api/v1/admin/feature-flags/recommendations", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, account_id: accountId }),
    });
    if (!response.ok) throw new Error(`Could not update Discover access (HTTP ${response.status})`);
    const result = (await response.json()) as Record<string, unknown> | null;
    if (
      result?.["flag"] !== "recommendations" ||
      result["account_id"] !== accountId ||
      result["enabled"] !== enabled
    ) {
      throw new Error("The server did not confirm this account's Discover access");
    }
  }

  private canSave(): boolean {
    return this.live && !this.state.loading && !this.state.saving && this.state.enabled !== null;
  }

  private isCurrent(epoch: number): boolean {
    return this.live && epoch === this.epoch;
  }

  private update(patch: Partial<AdminDiscoverState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
}
