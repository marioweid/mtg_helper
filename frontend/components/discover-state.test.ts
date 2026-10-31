import { afterEach, describe, expect, it, vi } from "vitest";
import { DiscoverController } from "@/components/discover-state";
import type {
  DiscoverRun,
  DiscoverStrategy,
  StrategyMatches,
  TermSuggestionRun,
} from "@/lib/discovery-types";

const empty: StrategyMatches = {
  status: "setup_needed",
  source: { status: "ready", card_updated_at: null, tag_updated_at: null, warning: null },
  strategy: null,
  cards: [],
  next_cursor: null,
  total: 0,
};
const saved: DiscoverStrategy = {
  prose: "Existing strategy",
  queries: [
    {
      purpose: "Counter search",
      groups: [{ oracle_tag_ids: ["tag"], printed_keywords: [] }],
      card_types_any: ["Creature"],
    },
  ],
  revision: "revision",
  updated_at: "now",
  needs_review: false,
};
const choice = {
  title: "Counter engine",
  pace: "Steady",
  early_game: "Develop mana",
  engine: "Transfer counters",
  payoff: "Attack with creatures",
  goal: "Counter engine\nA full strategy",
  explanation: "Use the commander",
  uncertainties: [],
};
function draft(status: DiscoverRun["status"] = "completed"): DiscoverRun {
  return {
    id: "draft",
    status,
    phase: "plan",
    goal: "",
    created_at: "now",
    source_hash: "source",
    rules_hash: "rules",
    profile: "app-strategy-v2",
    error: null,
    stale: false,
    candidates: [],
    strategies: status === "completed" ? [choice] : [],
    known_cost_microusd: 0,
    held_microusd: 0,
  };
}
function suggestion(status: TermSuggestionRun["status"] = "completed"): TermSuggestionRun {
  return {
    id: "terms",
    status,
    error: null,
    queries: saved.queries,
    strategy_revision: null,
    source_hash: "source",
  };
}
type Client = NonNullable<ConstructorParameters<typeof DiscoverController>[2]>;
function api(overrides: Partial<Client> = {}): Client {
  return {
    getDiscoverStatus: async () => empty,
    getDiscoverMatches: async () => empty,
    getDiscoverSetup: async () => ({ draft: null, suggestion: null, prose: null }),
    getDiscoverTerms: async () => ({
      oracle_tags: [{ id: "tag", slug: "tag", label: "Counters" }],
      printed_keywords: ["Flying"],
    }),
    draftCommanderStrategy: async () => draft(),
    getDiscoverRun: async () => draft(),
    suggestDiscoverTerms: async () => suggestion(),
    getDiscoverTermSuggestions: async () => suggestion(),
    saveDiscoverStrategy: async (_deck, body) => ({ ...saved, ...body, revision: "new-revision" }),
    planDiscoverMatch: async () => true,
    dismissDiscoverMatch: async () => true,
    ...overrides,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  return {
    promise: new Promise<T>((done) => {
      resolve = done;
    }),
    resolve,
  };
}
const controllers: DiscoverController[] = [];
function controller(client = api()) {
  const result = new DiscoverController("deck", () => undefined, client);
  controllers.push(result);
  return result;
}
afterEach(() => {
  controllers.splice(0).forEach((c) => c.stop());
  vi.useRealTimers();
});

describe("Strategy-first setup", () => {
  it("prepares one reusable draft on first opening, without loading the tag catalog", async () => {
    const prepare = vi.fn(api().draftCommanderStrategy);
    const catalog = vi.fn(async () => ({ oracle_tags: [], printed_keywords: [] }));
    const c = controller(api({ draftCommanderStrategy: prepare, getDiscoverTerms: catalog }));
    await c.start();
    await c.refresh();
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(prepare.mock.calls[0]?.[1]).toMatchObject({ reuse_latest: true });
    expect(catalog).not.toHaveBeenCalled();
    expect(c.getSnapshot().draft?.strategies?.[0]?.engine).toBe(choice.engine);
  });
  it("restores an existing draft and polls read-only rather than generating again", async () => {
    vi.useFakeTimers();
    const prepare = vi.fn(async () => draft());
    const c = controller(
      api({
        getDiscoverSetup: async () => ({ draft: draft("running"), suggestion: null, prose: null }),
        draftCommanderStrategy: prepare,
      }),
    );
    await c.start();
    await vi.advanceTimersByTimeAsync(3000);
    expect(c.getSnapshot().draft?.status).toBe("completed");
    expect(prepare).not.toHaveBeenCalled();
  });
  it("finds cards through one term request and one save; a double click cannot duplicate either", async () => {
    const delayed = deferred<TermSuggestionRun>();
    const terms = vi.fn(() => delayed.promise);
    const save = vi.fn(
      async (_deck: string, body: Parameters<Client["saveDiscoverStrategy"]>[1]) => ({
        ...saved,
        ...body,
        revision: "new",
      }),
    );
    const c = controller(api({ suggestDiscoverTerms: terms, saveDiscoverStrategy: save }));
    await c.start();
    c.selectDraft(0);
    const finding = c.findCards();
    await c.findCards();
    delayed.resolve(suggestion());
    await finding;
    expect(terms).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]?.[1]).toMatchObject({ prose: choice.goal, queries: saved.queries });
    expect(c.getSnapshot().editing).toBe(false);
  });
});

describe("Setup recovery and failure", () => {
  it("resumes pending term work and saves when it completes after reopening", async () => {
    vi.useFakeTimers();
    const save = vi.fn(async () => saved);
    const terms = vi.fn(async () => suggestion());
    const c = controller(
      api({
        getDiscoverSetup: async () => ({
          draft: draft(),
          suggestion: suggestion("running"),
          prose: "Recovered intent",
        }),
        saveDiscoverStrategy: save,
        suggestDiscoverTerms: terms,
      }),
    );
    await c.start();
    expect(c.getSnapshot().prose).toBe("Recovered intent");
    await vi.advanceTimersByTimeAsync(3000);
    expect(save).toHaveBeenCalledTimes(1);
    expect(terms).not.toHaveBeenCalled();
  });
  it("does not save empty AI terms or erase the last-good results", async () => {
    const save = vi.fn(async () => saved);
    const c = controller(
      api({
        getDiscoverStatus: async () => ({ ...empty, strategy: saved }),
        getDiscoverMatches: async () => ({ ...empty, total: 4, strategy: saved }),
        suggestDiscoverTerms: async () => ({
          ...suggestion(),
          strategy_revision: "revision",
          queries: [],
        }),
        saveDiscoverStrategy: save,
      }),
    );
    await c.start();
    await c.changeStrategy();
    c.setProse("Another strategy");
    await c.findCards();
    expect(save).not.toHaveBeenCalled();
    expect(c.getSnapshot().matches?.total).toBe(4);
    expect(c.getSnapshot().error).toContain("search terms");
  });
  it("leaves newer edits untouched when delayed terms return", async () => {
    const delayed = deferred<TermSuggestionRun>();
    const save = vi.fn(async () => saved);
    const c = controller(
      api({ suggestDiscoverTerms: () => delayed.promise, saveDiscoverStrategy: save }),
    );
    await c.start();
    c.setProse("First");
    const finding = c.findCards();
    c.setProse("Newer text");
    delayed.resolve(suggestion());
    await finding;
    expect(c.getSnapshot().prose).toBe("Newer text");
    expect(save).not.toHaveBeenCalled();
  });
});

describe("Saved strategies and manual control", () => {
  it("preserves automatic filters until an explicit manual edit replaces them", async () => {
    const terms = vi.fn(async () => suggestion());
    const c = controller(
      api({
        getDiscoverStatus: async () => ({ ...empty, strategy: saved }),
        suggestDiscoverTerms: terms,
      }),
    );
    await c.start();
    expect(c.getSnapshot().queries).toEqual(saved.queries);
    c.toggleKeyword("Flying");
    await c.findCards();
    expect(terms).not.toHaveBeenCalled();
    expect(c.getSnapshot().status?.strategy?.queries).toEqual([
      {
        purpose: "Manual search",
        groups: [{ oracle_tag_ids: ["tag"], printed_keywords: ["Flying"] }],
        card_types_any: [],
      },
    ]);
    expect(saved.queries[0]?.card_types_any).toEqual(["Creature"]);
  });
  it("opens saved matches without model calls and keeps the full strategy visible", async () => {
    const prepare = vi.fn(async () => draft());
    const c = controller(
      api({
        getDiscoverStatus: async () => ({ ...empty, strategy: saved }),
        draftCommanderStrategy: prepare,
      }),
    );
    await c.start();
    await c.refresh();
    expect(c.getSnapshot().editing).toBe(false);
    expect(c.getSnapshot().prose).toBe(saved.prose);
    expect(prepare).not.toHaveBeenCalled();
  });
  it("uses manually selected advanced criteria without calling AI", async () => {
    const terms = vi.fn(async () => suggestion());
    const c = controller(api({ suggestDiscoverTerms: terms }));
    await c.start();
    c.setProse("My strategy");
    c.toggleKeyword("Flying");
    await c.findCards();
    expect(terms).not.toHaveBeenCalled();
    expect(c.getSnapshot().status?.strategy?.queries[0]?.groups[0]?.printed_keywords).toEqual([
      "Flying",
    ]);
  });
  it("ignores a delayed save response after newer edits and keeps editing open", async () => {
    const delayed = deferred<DiscoverStrategy>();
    const c = controller(api({ saveDiscoverStrategy: () => delayed.promise }));
    await c.start();
    c.setProse("First");
    c.toggleKeyword("Flying");
    const finding = c.findCards();
    c.setProse("Newer text");
    delayed.resolve(saved);
    await finding;
    expect(c.getSnapshot().prose).toBe("Newer text");
    expect(c.getSnapshot().editing).toBe(true);
  });
  it("retains dismissal undo even when the result list becomes empty", async () => {
    const dismiss = vi.fn(api().dismissDiscoverMatch);
    const c = controller(
      api({
        getDiscoverStatus: async () => ({ ...empty, strategy: saved }),
        dismissDiscoverMatch: dismiss,
      }),
    );
    await c.start();
    await c.dismiss("card");
    expect(c.getSnapshot().dismissedOracleId).toBe("card");
    await c.undoDismissal();
    expect(dismiss).toHaveBeenLastCalledWith("deck", "card", true);
    expect(c.getSnapshot().dismissedOracleId).toBeNull();
  });
});

describe("Async setup safeguards", () => {
  it("uses a reusable initial request across Strict Mode remounts", async () => {
    const delayed =
      deferred<ReturnType<Client["getDiscoverSetup"]> extends Promise<infer T> ? T : never>();
    const prepare = vi.fn(api().draftCommanderStrategy);
    const c = controller(
      api({ getDiscoverSetup: () => delayed.promise, draftCommanderStrategy: prepare }),
    );
    const first = c.start();
    c.stop();
    const second = c.start();
    delayed.resolve({ draft: null, suggestion: null, prose: null });
    await Promise.all([first, second]);
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(prepare.mock.calls[0]?.[1].reuse_latest).toBe(true);
  });
  it("never saves after unmount or a mismatched saved-strategy revision", async () => {
    const delayed = deferred<TermSuggestionRun>();
    const save = vi.fn(api().saveDiscoverStrategy);
    const c = controller(
      api({ suggestDiscoverTerms: () => delayed.promise, saveDiscoverStrategy: save }),
    );
    await c.start();
    c.setProse("My direction");
    const finding = c.findCards();
    c.stop();
    delayed.resolve(suggestion());
    await finding;
    expect(save).not.toHaveBeenCalled();
    const other = controller(
      api({
        suggestDiscoverTerms: async () => ({ ...suggestion(), strategy_revision: "changed" }),
        saveDiscoverStrategy: save,
      }),
    );
    await other.start();
    other.setProse("My direction");
    await other.findCards();
    expect(save).not.toHaveBeenCalled();
    expect(other.getSnapshot().error).toContain("search terms");
  });
  it("preserves saved matches after a failed save and lets the user retry without another AI call", async () => {
    const terms = vi.fn(api().suggestDiscoverTerms);
    const save = vi
      .fn(api().saveDiscoverStrategy)
      .mockRejectedValueOnce(new Error("Save unavailable"));
    const c = controller(api({ suggestDiscoverTerms: terms, saveDiscoverStrategy: save }));
    await c.start();
    c.selectDraft(0);
    await c.findCards();
    expect(c.getSnapshot().error).toBe("Save unavailable");
    expect(c.getSnapshot().prose).toBe(choice.goal);
    expect(c.getSnapshot().editing).toBe(true);
    await c.findCards();
    expect(c.getSnapshot().editing).toBe(false);
    expect(terms).toHaveBeenCalledTimes(1);
  });
  it("keeps manually chosen terms when strategy wording changes", async () => {
    const terms = vi.fn(api().suggestDiscoverTerms);
    const c = controller(api({ suggestDiscoverTerms: terms }));
    await c.start();
    c.setProse("First draft");
    c.toggleKeyword("Flying");
    c.setProse("Edited manually");
    await c.findCards();
    expect(terms).not.toHaveBeenCalled();
    expect(c.getSnapshot().status?.strategy?.queries[0]?.groups[0]?.printed_keywords).toEqual([
      "Flying",
    ]);
  });
});

describe("Recovered setup failures", () => {
  it("leaves recovery editable rather than stuck busy when a restored save fails", async () => {
    const c = controller(
      api({
        getDiscoverSetup: async () => ({
          draft: draft(),
          suggestion: suggestion(),
          prose: "Recovered intent",
        }),
        saveDiscoverStrategy: async () => {
          throw new Error("Save unavailable");
        },
      }),
    );
    await c.start();
    expect(c.getSnapshot().busy).toBe(false);
    expect(c.getSnapshot().prose).toBe("Recovered intent");
    expect(c.getSnapshot().error).toBe("Save unavailable");
  });
  it("stops finite read-only polling without generating another strategy request", async () => {
    vi.useFakeTimers();
    const prepare = vi.fn(async () => draft("running"));
    const read = vi.fn(async () => draft("running"));
    const c = controller(api({ draftCommanderStrategy: prepare, getDiscoverRun: read }));
    await c.start();
    await vi.advanceTimersByTimeAsync(333000);
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledTimes(110);
    expect(c.getSnapshot().drafting).toBe(false);
    expect(c.getSnapshot().draftError).toContain("longer than expected");
  });
});
