import { apiClient } from "@/lib/api";
import type {
  DiscoverRun,
  DiscoverSetup,
  DiscoverTerms,
  StrategyMatches,
  StrategyQuery,
  TermSuggestionRun,
} from "@/lib/discovery-types";

type Client = Pick<
  typeof apiClient,
  | "getDiscoverStatus"
  | "getDiscoverSetup"
  | "getDiscoverTerms"
  | "saveDiscoverStrategy"
  | "getDiscoverMatches"
  | "planDiscoverMatch"
  | "dismissDiscoverMatch"
  | "draftCommanderStrategy"
  | "getDiscoverRun"
  | "suggestDiscoverTerms"
  | "getDiscoverTermSuggestions"
>;
type PollKind = "draft" | "terms";
interface Intent {
  epoch: number;
  version: number;
  prose: string;
  revision: string | null;
  tagIds: string[];
  keywords: string[];
  queries: StrategyQuery[];
}

export interface DiscoverState {
  status: StrategyMatches | null;
  terms: DiscoverTerms | null;
  matches: StrategyMatches | null;
  prose: string;
  tagIds: string[];
  keywords: string[];
  queries: StrategyQuery[];
  editing: boolean;
  manual: boolean;
  selected: number | null;
  advanced: boolean;
  error: string | null;
  draftError: string | null;
  loading: boolean;
  busy: boolean;
  progress: string | null;
  planning: string | null;
  dismissing: string | null;
  dismissedOracleId: string | null;
  drafting: boolean;
  draft: DiscoverRun | null;
  suggestion: TermSuggestionRun | null;
}

/** Owns the complete choose → prepare → save → browse interaction. */
export class DiscoverController {
  private state: DiscoverState = {
    status: null,
    terms: null,
    matches: null,
    prose: "",
    tagIds: [],
    keywords: [],
    queries: [],
    editing: true,
    manual: false,
    selected: null,
    advanced: false,
    error: null,
    draftError: null,
    loading: true,
    busy: false,
    progress: null,
    planning: null,
    dismissing: null,
    dismissedOracleId: null,
    drafting: false,
    draft: null,
    suggestion: null,
  };
  private listeners = new Set<() => void>();
  private live = false;
  private epoch = 0;
  private editorVersion = 0;
  private dirty = false;
  private manualTerms = false;
  private termsForProse: string | null = null;
  private intent: Intent | null = null;
  private started: Promise<void> | null = null;
  private timers: Partial<Record<PollKind, ReturnType<typeof setTimeout>>> = {};
  private polls = { draft: 0, terms: 0 };
  private matchesVersion = 0;

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

  start(): Promise<void> {
    if (this.live) return this.started ?? Promise.resolve();
    this.live = true;
    this.epoch += 1;
    this.started = this.initialize(this.epoch);
    return this.started;
  }

  stop(): void {
    this.live = false;
    this.epoch += 1;
    this.clearTimer("draft");
    this.clearTimer("terms");
    this.intent = null;
  }

  setProse(prose: string): void {
    this.edited();
    this.update({
      prose,
      manual: true,
      selected: null,
      ...(!this.manualTerms ? { tagIds: [], keywords: [], queries: [] } : {}),
    });
  }

  selectDraft(index: number): void {
    const draft = this.state.draft;
    const choice = draft?.strategies?.[index];
    if (draft?.status !== "completed" || draft.stale || !choice) return;
    this.edited();
    this.manualTerms = false;
    this.update({
      prose: choice.goal,
      selected: index,
      manual: false,
      tagIds: [],
      keywords: [],
      queries: [],
    });
  }

  writeOwn(): void {
    this.edited();
    this.update({ manual: true, selected: null });
  }

  async changeStrategy(): Promise<void> {
    this.update({ editing: true, error: null });
    if (!this.state.draft && this.ready()) await this.prepareDraft(true);
  }

  cancelEditing(): void {
    const saved = this.state.status?.strategy;
    if (!saved || this.state.busy) return;
    this.edited();
    this.dirty = false;
    this.manualTerms = false;
    this.update({
      prose: saved.prose,
      queries: saved.queries,
      ...queryTerms(saved.queries),
      editing: false,
      manual: false,
      selected: null,
    });
  }

  toggleTag(id: string): void {
    this.edited();
    this.manualTerms = true;
    const tagIds = toggle(this.state.tagIds, id);
    this.update({ tagIds, queries: manualQueries(tagIds, this.state.keywords) });
  }

  toggleKeyword(keyword: string): void {
    this.edited();
    this.manualTerms = true;
    const keywords = toggle(this.state.keywords, keyword);
    this.update({ keywords, queries: manualQueries(this.state.tagIds, keywords) });
  }

  async setAdvanced(advanced: boolean): Promise<void> {
    this.update({ advanced });
    if (!advanced || this.state.terms) return;
    const epoch = this.epoch;
    try {
      const terms = await this.api.getDiscoverTerms(this.deckId);
      if (this.current(epoch)) this.update({ terms });
    } catch (error) {
      if (this.current(epoch)) this.update({ error: message(error) });
    }
  }

  async refresh(): Promise<void> {
    const epoch = this.epoch;
    const version = ++this.matchesVersion;
    this.update({ loading: true });
    try {
      const [status, matches] = await Promise.all([
        this.api.getDiscoverStatus(this.deckId),
        this.api.getDiscoverMatches(this.deckId),
      ]);
      if (this.current(epoch) && version === this.matchesVersion) this.update({ status, matches });
    } catch (error) {
      if (this.current(epoch)) this.update({ error: message(error) });
    } finally {
      if (this.current(epoch)) this.update({ loading: false });
    }
  }

  async tryOtherStrategies(): Promise<void> {
    await this.prepareDraft(false);
  }

  async findCards(): Promise<void> {
    if (this.state.busy) return;
    if (!this.state.prose.trim()) {
      this.update({ error: "Choose a strategy or describe your own first." });
      return;
    }
    const intent = this.captureIntent();
    this.intent = intent;
    this.polls.terms = 0;
    this.update({ busy: true, error: null, progress: "Finding search terms for your strategy…" });
    try {
      if (this.manualTerms) {
        await this.persist(intent);
        return;
      }
      const previous = this.state.suggestion;
      if (previous?.status === "completed" && this.termsForProse === intent.prose) {
        await this.acceptTerms(previous, intent);
        return;
      }
      this.termsForProse = intent.prose;
      this.update({ suggestion: null });
      const suggestion = await this.api.suggestDiscoverTerms(this.deckId, {
        request_key: crypto.randomUUID(),
        prose: intent.prose,
        strategy_revision: intent.revision,
        reuse_latest: !previous || ["running", "completed"].includes(previous.status),
      });
      if (this.currentIntent(intent)) await this.acceptTerms(suggestion, intent);
    } catch (error) {
      this.failIntent(intent, message(error));
    }
  }

  async next(): Promise<void> {
    const cursor = this.state.matches?.next_cursor;
    if (cursor && !this.state.loading) await this.loadMatches(cursor);
  }

  async plan(oracleId: string): Promise<void> {
    if (this.state.planning) return;
    const epoch = this.epoch;
    this.update({ planning: oracleId, error: null });
    try {
      await this.api.planDiscoverMatch(this.deckId, oracleId);
      if (!this.current(epoch)) return;
      await this.onPlanChanged();
      await this.loadMatches();
    } catch (error) {
      if (this.current(epoch)) this.update({ error: message(error) });
    } finally {
      if (this.current(epoch)) this.update({ planning: null });
    }
  }

  async dismiss(oracleId: string, undo = false): Promise<void> {
    if (this.state.dismissing) return;
    const epoch = this.epoch;
    this.update({ dismissing: oracleId, error: null });
    try {
      await this.api.dismissDiscoverMatch(this.deckId, oracleId, undo);
      if (!this.current(epoch)) return;
      this.update({ dismissedOracleId: undo ? null : oracleId });
      await this.loadMatches();
    } catch (error) {
      if (this.current(epoch)) this.update({ error: message(error) });
    } finally {
      if (this.current(epoch)) this.update({ dismissing: null });
    }
  }

  async undoDismissal(): Promise<void> {
    if (this.state.dismissedOracleId) await this.dismiss(this.state.dismissedOracleId, true);
  }

  private async initialize(epoch: number): Promise<void> {
    const version = this.editorVersion;
    this.update({ busy: false, drafting: false, progress: null });
    await this.refresh();
    if (!this.current(epoch)) return;
    const saved = this.state.status?.strategy;
    if (!this.dirty && version === this.editorVersion && saved) {
      this.update({
        prose: saved.prose,
        queries: saved.queries,
        ...queryTerms(saved.queries),
        editing: saved.needs_review,
        manual: saved.needs_review,
      });
    }
    if (!this.ready()) return;
    try {
      const setup = await this.api.getDiscoverSetup(this.deckId);
      if (!this.current(epoch)) return;
      if (setup.draft) this.acceptDraft(setup.draft, epoch);
      if (version !== this.editorVersion) return;
      if (setup.suggestion && setup.prose) await this.restoreIntent(setup);
      else if (!saved && !setup.draft && !this.dirty) await this.prepareDraft(true);
    } catch (error) {
      if (this.current(epoch)) this.update({ draftError: message(error) });
    }
  }

  private async restoreIntent(setup: DiscoverSetup): Promise<void> {
    if (!setup.suggestion || !setup.prose) return;
    this.termsForProse = setup.prose;
    this.update({ prose: setup.prose, editing: true, manual: true, suggestion: setup.suggestion });
    const intent = this.captureIntent();
    this.intent = intent;
    this.update({ busy: true, progress: "Finishing your strategy setup…" });
    try {
      await this.acceptTerms(setup.suggestion, intent);
    } catch (error) {
      this.failIntent(intent, message(error));
    }
  }

  private async prepareDraft(reuse: boolean): Promise<void> {
    if (this.state.drafting || this.state.busy || !this.ready()) return;
    const epoch = this.epoch;
    this.clearTimer("draft");
    this.polls.draft = 0;
    this.update({ drafting: true, draftError: null });
    try {
      const draft = await this.api.draftCommanderStrategy(this.deckId, {
        request_key: crypto.randomUUID(),
        reuse_latest: reuse,
      });
      if (this.current(epoch)) this.acceptDraft(draft, epoch);
    } catch (error) {
      if (this.current(epoch)) this.update({ drafting: false, draftError: message(error) });
    }
  }

  private acceptDraft(draft: DiscoverRun, epoch: number): void {
    const running = draft.status === "running";
    const failed = !running && (draft.status !== "completed" || draft.stale);
    this.update({
      draft,
      drafting: running,
      draftError: failed
        ? "Couldn't prepare strategy ideas. Try other strategies or write your own."
        : null,
    });
    if (running) this.schedule("draft", draft.id, epoch);
  }

  private async acceptTerms(suggestion: TermSuggestionRun, intent: Intent): Promise<void> {
    if (!this.currentIntent(intent)) return;
    this.update({ suggestion });
    if (suggestion.status === "running") {
      this.schedule("terms", suggestion.id, intent.epoch);
      return;
    }
    if (suggestion.status !== "completed" || suggestion.strategy_revision !== intent.revision) {
      this.failIntent(
        intent,
        "Couldn't prepare search terms. Try Find cards again or use Advanced search details.",
      );
      return;
    }
    intent.queries = suggestion.queries;
    Object.assign(intent, queryTerms(suggestion.queries));
    this.update({ queries: intent.queries, ...queryTerms(intent.queries) });
    await this.persist(intent);
  }

  private async persist(intent: Intent): Promise<void> {
    if (!this.currentIntent(intent)) return;
    if (!intent.queries.length) {
      this.failIntent(
        intent,
        "No matching search terms were found. Edit your strategy or choose terms in Advanced search details.",
      );
      return;
    }
    this.update({ progress: "Saving your strategy & finding cards…" });
    const strategy = await this.api.saveDiscoverStrategy(this.deckId, {
      prose: intent.prose,
      queries: intent.queries,
      revision: intent.revision,
    });
    if (!this.current(intent.epoch)) return;
    this.update({ status: this.state.status ? { ...this.state.status, strategy } : null });
    if (!this.currentIntent(intent)) return;
    this.dirty = false;
    this.manualTerms = false;
    this.intent = null;
    this.update({
      prose: strategy.prose,
      queries: strategy.queries,
      ...queryTerms(strategy.queries),
      editing: false,
      busy: false,
      progress: null,
      suggestion: null,
    });
    await this.loadMatches();
  }

  private schedule(kind: PollKind, id: string, epoch: number): void {
    this.clearTimer(kind);
    if (this.polls[kind] >= 110) {
      if (kind === "terms" && this.intent)
        this.failIntent(
          this.intent,
          "Setup is taking longer than expected. Try Find cards again to check it.",
        );
      else
        this.update({
          drafting: false,
          draftError:
            "Strategy ideas are taking longer than expected. Reopen Discover to check them.",
        });
      return;
    }
    this.timers[kind] = setTimeout(() => void this.poll(kind, id, epoch), 3000);
  }

  private async poll(kind: PollKind, id: string, epoch: number): Promise<void> {
    if (!this.current(epoch)) return;
    this.polls[kind] += 1;
    const intent = this.intent;
    try {
      if (kind === "draft") {
        const draft = await this.api.getDiscoverRun(this.deckId, id);
        if (this.current(epoch) && this.state.draft?.id === id) this.acceptDraft(draft, epoch);
      } else if (intent && this.currentIntent(intent)) {
        const suggestion = await this.api.getDiscoverTermSuggestions(this.deckId, id);
        await this.acceptTerms(suggestion, intent);
      }
    } catch (error) {
      if (!this.current(epoch)) return;
      if (kind === "terms" && intent) this.failIntent(intent, message(error));
      else this.update({ drafting: false, draftError: message(error) });
    }
  }

  private async loadMatches(cursor?: string): Promise<void> {
    const epoch = this.epoch;
    const version = ++this.matchesVersion;
    this.update({ loading: true });
    try {
      const matches = await this.api.getDiscoverMatches(this.deckId, cursor);
      if (this.current(epoch) && version === this.matchesVersion) this.update({ matches });
    } catch (error) {
      if (this.current(epoch)) this.update({ error: message(error) });
    } finally {
      if (this.current(epoch)) this.update({ loading: false });
    }
  }

  private captureIntent(): Intent {
    return {
      epoch: this.epoch,
      version: this.editorVersion,
      prose: this.state.prose.trim(),
      revision: this.state.status?.strategy?.revision ?? null,
      tagIds: [...this.state.tagIds],
      keywords: [...this.state.keywords],
      queries: structuredClone(this.state.queries),
    };
  }

  private edited(): void {
    this.editorVersion += 1;
    this.dirty = true;
    this.intent = null;
    this.clearTimer("terms");
    this.update({ editing: true, busy: false, progress: null, error: null });
  }

  private failIntent(intent: Intent, error: string): void {
    if (!this.currentIntent(intent)) return;
    this.intent = null;
    this.update({ busy: false, progress: null, error });
  }

  private currentIntent(intent: Intent): boolean {
    return (
      this.current(intent.epoch) && this.intent === intent && intent.version === this.editorVersion
    );
  }

  private current(epoch: number): boolean {
    return this.live && epoch === this.epoch;
  }

  private ready(): boolean {
    return ["ready", "stale"].includes(this.state.status?.source.status ?? "");
  }

  private clearTimer(kind: PollKind): void {
    clearTimeout(this.timers[kind]);
    delete this.timers[kind];
  }

  private update(patch: Partial<DiscoverState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
}

function message(error: unknown): string {
  const text =
    error instanceof Error ? error.message : "Discover couldn't finish this request. Try again.";
  return /billing|microusd|reconcil|spending|private trace/i.test(text)
    ? "AI couldn't finish setup. Try again or write your own strategy."
    : text;
}

function toggle(items: string[], value: string): string[] {
  return items.includes(value) ? items.filter((item) => item !== value) : [...items, value];
}

function queryTerms(queries: StrategyQuery[]): { tagIds: string[]; keywords: string[] } {
  const groups = queries.flatMap((query) => query.groups);
  return {
    tagIds: [...new Set(groups.flatMap((group) => group.oracle_tag_ids))],
    keywords: [...new Set(groups.flatMap((group) => group.printed_keywords))],
  };
}

function manualQueries(tagIds: string[], keywords: string[]): StrategyQuery[] {
  if (!tagIds.length && !keywords.length) return [];
  return [
    {
      purpose: "Manual search",
      groups: [{ oracle_tag_ids: tagIds, printed_keywords: keywords }],
      card_types_any: [],
    },
  ];
}
