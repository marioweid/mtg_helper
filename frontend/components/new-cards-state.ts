import { apiClient } from "@/lib/api";
import type { NewCardPick, NewCardsResponse } from "@/lib/types";

interface Dismissal {
  oracleId: string;
  name: string;
}

export interface NewCardsState {
  result: NewCardsResponse | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  lastDismissal: Dismissal | null;
  planRefreshError: string | null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected request failure";
}

/** Owns the pilot lifecycle, including invalidation of reads superseded by writes. */
export class NewCardsController {
  private state: NewCardsState = {
    result: null,
    loading: true,
    busy: false,
    error: null,
    lastDismissal: null,
    planRefreshError: null,
  };
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private sequence = 0;
  private active = false;

  constructor(
    private readonly deckId: string,
    private readonly onPlanChanged: () => void | Promise<void>,
  ) {}

  getSnapshot = () => this.state;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Starts a read-only load; only an explicit analyze action can start AI work. */
  start() {
    this.active = true;
    void this.refresh();
  }

  /** Invalidates outstanding requests and cancels polling on tab exit. */
  stop() {
    this.active = false;
    this.sequence += 1;
    clearTimeout(this.timer);
    this.patch({ busy: false, loading: false });
  }

  refresh = () => this.run("Refresh New Cards", () => apiClient.getNewCards(this.deckId));

  analyze = () =>
    this.run("Analyze next eight", () => apiClient.analyzeNewCards(this.deckId), true);

  dismiss = (pick: NewCardPick) =>
    this.run(
      `Dismiss ${pick.name}`,
      () => apiClient.dismissNewCard(this.deckId, pick.oracle_id),
      true,
      () => this.patch({ lastDismissal: { oracleId: pick.oracle_id, name: pick.name } }),
    );

  undo = () => {
    const dismissal = this.state.lastDismissal;
    if (!dismissal) return Promise.resolve();
    return this.run(
      `Undo dismissal of ${dismissal.name}`,
      () => apiClient.undoNewCardDismissal(this.deckId, dismissal.oracleId),
      true,
      () => this.patch({ lastDismissal: null }),
    );
  };

  plan = (pick: NewCardPick) =>
    this.run(
      `Plan addition of ${pick.name}`,
      () => apiClient.planNewCard(this.deckId, pick.oracle_id),
      true,
      () => this.refreshParent(),
    );

  retryPlanRefresh = async () => {
    if (!this.active || this.state.busy) return;
    const token = ++this.sequence;
    clearTimeout(this.timer);
    this.patch({ busy: true, planRefreshError: null });
    await this.refreshParent();
    if (this.isCurrent(token)) {
      this.patch({ busy: false });
      this.schedulePoll();
    }
  };

  private patch(update: Partial<NewCardsState>) {
    this.state = { ...this.state, ...update };
    for (const listener of this.listeners) listener();
  }

  private isCurrent(token: number) {
    return this.active && token === this.sequence;
  }

  private async refreshParent() {
    const token = this.sequence;
    try {
      await this.onPlanChanged();
      if (this.isCurrent(token)) this.patch({ planRefreshError: null });
    } catch (error) {
      if (this.isCurrent(token)) {
        this.patch({
          planRefreshError:
            `Addition planned, but deck refresh failed: ${errorMessage(error)}. ` +
            "Retry deck refresh.",
        });
      }
    }
  }

  private async run(
    operation: string,
    request: () => Promise<NewCardsResponse>,
    mutation = false,
    afterSuccess?: () => void | Promise<void>,
  ) {
    if (!this.active || this.state.busy) return;
    const token = ++this.sequence;
    clearTimeout(this.timer);
    this.patch({ loading: !mutation, busy: mutation });
    try {
      const result = await request();
      if (!this.isCurrent(token)) return;
      this.patch({ result, error: null });
      await afterSuccess?.();
    } catch (error) {
      if (this.isCurrent(token)) {
        this.patch({ error: `${operation} failed: ${errorMessage(error)}. Retry when connected.` });
      }
    } finally {
      if (this.isCurrent(token)) {
        this.patch({ loading: false, busy: false });
        this.schedulePoll();
      }
    }
  }

  private schedulePoll() {
    if (this.state.result?.status === "running") {
      this.timer = setTimeout(() => void this.refresh(), 3000);
    }
  }
}
