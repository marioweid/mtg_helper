import { apiClient } from "@/lib/api";
import { STRATEGY_PROFILE } from "@/lib/discovery-types";
import type {
  DiscoverGenerate,
  DiscoverPage,
  DiscoverPreview,
  DiscoverQuery,
  DiscoverStatus,
} from "@/lib/discovery-types";

type Client = Pick<
  typeof apiClient,
  | "getDiscoverStatus"
  | "draftCommanderStrategy"
  | "generateDiscover"
  | "previewDiscover"
  | "planDiscover"
  | "getDiscoverTrace"
  | "feedbackDiscover"
>;

export interface DiscoverState {
  status: DiscoverStatus | null;
  page: DiscoverPage | null;
  rulesPage: DiscoverPage | null;
  trace: Record<string, unknown> | null;
  error: string | null;
  loading: boolean;
  generating: boolean;
  drafting: boolean;
  browsing: boolean;
  planning: string | null;
  goal: string;
}

export class DiscoverController {
  private state: DiscoverState = {
    status: null,
    page: null,
    rulesPage: null,
    trace: null,
    error: null,
    loading: false,
    generating: false,
    drafting: false,
    browsing: false,
    planning: null,
    goal: "",
  };
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private epoch = 0;
  private live = false;
  private pending: DiscoverGenerate | null = null;
  private pendingDraftKey: string | null = null;
  private goalInitialized = false;
  private preview: DiscoverPreview = {};
  private rulesPreview: DiscoverPreview = {};

  constructor(
    private deckId: string,
    private onPlanChanged: () => void | Promise<void>,
    private api: Client = apiClient,
  ) {}

  getSnapshot = (): DiscoverState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  start(): void {
    this.live = true;
    this.epoch += 1;
    void this.refresh();
  }

  stop(): void {
    this.live = false;
    this.epoch += 1;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  setGoal(goal: string): void {
    this.goalInitialized = true;
    this.update({ goal });
  }

  private update(patch: Partial<DiscoverState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  private async perform<T>(
    operation: () => Promise<T>,
    apply: (value: T) => Partial<DiscoverState>,
  ) {
    const epoch = this.epoch;
    try {
      const result = await operation();
      if (this.live && epoch === this.epoch) this.update(apply(result));
      return result;
    } catch (error) {
      if (this.live && epoch === this.epoch) {
        this.update({ error: error instanceof Error ? error.message : "Discover request failed" });
      }
      return undefined;
    }
  }

  async refresh(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.update({ loading: true, error: null });
    const epoch = this.epoch;
    const status = await this.perform(
      () => this.api.getDiscoverStatus(this.deckId),
      (status) => ({
        status,
        goal: this.goalInitialized ? this.state.goal : status.run?.goal || status.goal_seed,
      }),
    );
    if (!this.live || epoch !== this.epoch) return;
    if (status) this.goalInitialized = true;
    this.update({ loading: false });
    if (this.running()) {
      this.timer = setTimeout(() => void this.refresh(), 3000);
    }
  }

  private running(): boolean {
    return (
      this.state.status?.run?.status === "running" ||
      this.state.status?.strategy_run?.status === "running"
    );
  }

  private paidActionBlocked(): boolean {
    return (
      !this.live ||
      this.state.drafting ||
      this.state.generating ||
      !this.state.status?.ready ||
      this.running()
    );
  }

  async draftStrategy(): Promise<void> {
    if (this.paidActionBlocked()) return;
    const epoch = this.epoch;
    this.pendingDraftKey ??= crypto.randomUUID();
    const body = { request_key: this.pendingDraftKey };
    this.update({ drafting: true, error: null });
    const result = await this.perform(
      () => this.api.draftCommanderStrategy(this.deckId, body),
      (strategy_run) => ({
        status: this.state.status ? { ...this.state.status, strategy_run } : null,
      }),
    );
    if (!this.live || epoch !== this.epoch) return;
    this.update({ drafting: false });
    if (result) {
      this.pendingDraftKey = null;
      await this.refresh();
    }
  }

  useStrategy(index: number): void {
    const run = this.state.status?.strategy_run;
    const choice = Number.isInteger(index) && index >= 0 ? run?.strategies?.[index] : null;
    if (run?.status === "completed" && !run.stale && run.profile === STRATEGY_PROFILE && choice) {
      this.setGoal(choice.goal);
    }
  }

  async generate(constraint: DiscoverQuery | null): Promise<void> {
    if (this.paidActionBlocked()) return;
    const goal = this.state.goal.trim();
    if (!goal) {
      this.update({ error: "Enter a commander-only goal or draft a strategy first" });
      return;
    }
    if (
      !this.pending ||
      this.pending.goal !== goal ||
      JSON.stringify(this.pending.constraint) !== JSON.stringify(constraint)
    ) {
      this.pending = { request_key: crypto.randomUUID(), goal, constraint, excluded_ids: [] };
    }
    const frozen = this.pending;
    this.update({ generating: true, error: null, trace: null });
    const result = await this.perform(
      () => this.api.generateDiscover(this.deckId, frozen),
      (run) => ({ status: this.state.status ? { ...this.state.status, run } : null }),
    );
    this.update({ generating: false });
    if (result) {
      this.pending = null;
      await this.refresh();
    }
  }

  async search(body: DiscoverPreview, next = false): Promise<void> {
    if (this.state.browsing) return;
    this.preview = next ? this.preview : body;
    const request =
      next && this.state.page
        ? {
            ...this.preview,
            cursor: this.state.page.next_cursor,
            snapshot_hash: this.state.page.snapshot_hash,
            rules_hash: this.state.page.rules_hash,
          }
        : this.preview;
    this.update({ browsing: true, error: null });
    await this.perform(
      () => this.api.previewDiscover(this.deckId, request),
      (page) => ({ page }),
    );
    this.update({ browsing: false });
  }

  async searchRules(term: string, next = false): Promise<void> {
    if (this.state.browsing) return;
    const previous = this.state.rulesPage;
    const query = this.rulesPreview.rule_query;
    const body: DiscoverPreview =
      next && previous?.rule_results && query
        ? {
            ...this.rulesPreview,
            snapshot_hash: previous.snapshot_hash,
            rules_hash: previous.rule_results.rules_hash,
            rule_query: { ...query, cursor: previous.rule_results.next_cursor },
          }
        : {
            rule_query: {
              purpose: "Manual literal rules lookup",
              text_all: [term.trim()],
              text_any: [],
              cursor: null,
            },
          };
    this.rulesPreview = body;
    this.update({ browsing: true, error: null });
    await this.perform(
      () => this.api.previewDiscover(this.deckId, body),
      (rulesPage) => ({ rulesPage }),
    );
    this.update({ browsing: false });
  }

  async plan(oracleId: string, runId: string | null): Promise<void> {
    if (this.state.planning) return;
    this.update({ planning: oracleId, error: null });
    const result = await this.perform(
      () => this.api.planDiscover(this.deckId, oracleId, runId),
      () => ({}),
    );
    if (result) {
      await this.perform(
        async () => {
          await this.onPlanChanged();
          return true;
        },
        () => ({}),
      );
      await this.refresh();
    }
    this.update({ planning: null });
  }

  async inspect(strategy = false): Promise<void> {
    const run = strategy ? this.state.status?.strategy_run : this.state.status?.run;
    if (!run) return;
    await this.perform(
      () => this.api.getDiscoverTrace(this.deckId, run.id),
      (trace) => ({ trace }),
    );
  }

  async feedback(oracleId: string, verdict: "useful" | "incorrect" | "uncertain") {
    const run = this.state.status?.run;
    if (!run) return;
    await this.perform(
      () => this.api.feedbackDiscover(this.deckId, run.id, oracleId, verdict, ""),
      () => ({}),
    );
  }
}
