import { afterEach, describe, expect, it, vi } from "vitest";
import { DiscoverController } from "@/components/discover-state";
import type { DiscoverRun, DiscoverStatus } from "@/lib/discovery-types";

vi.mock("@/auth", () => ({ auth: async () => ({ idToken: "test-token" }) }));

const run: DiscoverRun = {
  id: "run-1",
  status: "running",
  phase: "plan",
  goal: "Counters",
  created_at: "2026-10-05",
  source_hash: "source",
  rules_hash: "rules",
  profile: "app-pilot-v1",
  error: null,
  stale: false,
  candidates: [],
  known_cost_microusd: 0,
  held_microusd: 67750,
};
const status: DiscoverStatus = {
  ready: true,
  reason: null,
  source_hash: "source",
  rules_hash: "rules",
  catalog_updated_at: null,
  goal_seed: "Counters",
  run: null,
  run_cap_microusd: 100000,
  daily_cap_microusd: 1000000,
  reserved_microusd: 67750,
  maximum_calls: 3,
};
function response(data: unknown) {
  return new Response(JSON.stringify({ data }));
}
const controllers: DiscoverController[] = [];
function start(callback = async () => {}) {
  const controller = new DiscoverController("deck-1", callback);
  controllers.push(controller);
  controller.start();
  return controller;
}
afterEach(() => {
  controllers.forEach((c) => c.stop());
  controllers.length = 0;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Discover controller", () => {
  it("rules pagination pins its source and exact query without touching card browsing or AI", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response(status));
    vi.stubGlobal("fetch", fetch);
    const controller = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    const page = {
      snapshot_hash: "source",
      total: 0,
      cards: [],
      next_cursor: null,
      rule_results: {
        rules_hash: "rules",
        matching_count: 20,
        next_cursor: "123.1",
        truncated: true,
        selected: [],
      },
    };
    fetch.mockResolvedValue(response(page));
    await controller.searchRules("experience");
    await controller.searchRules("", true);
    expect(JSON.parse(fetch.mock.calls.at(-1)?.[1]?.body as string)).toMatchObject({
      snapshot_hash: "source",
      rules_hash: "rules",
      rule_query: { text_all: ["experience"], cursor: "123.1" },
    });
    expect(controller.getSnapshot().page).toBeNull();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/runs"))).toBe(false);
  });
  it("mount, source search, pagination and refresh never generate or mutate", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response(status));
    vi.stubGlobal("fetch", fetch);
    const controller = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    fetch.mockResolvedValueOnce(
      response({
        snapshot_hash: "source",
        rules_hash: "old-rules",
        total: 100,
        next_cursor: "cursor",
        cards: [],
      }),
    );
    await controller.search({ name: "Unknown mechanic" });
    fetch.mockResolvedValueOnce(
      response({ snapshot_hash: "source", total: 100, next_cursor: null, cards: [] }),
    );
    await controller.search({}, true);
    const calls = fetch.mock.calls.map(([url, options]) => [String(url), options?.method]);
    expect(calls).toEqual([
      [expect.stringContaining("/status"), undefined],
      [expect.stringContaining("/preview-query"), "POST"],
      [expect.stringContaining("/preview-query"), "POST"],
    ]);
    const page = JSON.parse(fetch.mock.calls[2]?.[1]?.body as string);
    expect(page).toMatchObject({
      name: "Unknown mechanic",
      snapshot_hash: "source",
      rules_hash: "old-rules",
      cursor: "cursor",
    });
  });

  it("only explicit Generate sends a frozen bounded request; polling is read-only", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response(status));
    vi.stubGlobal("fetch", fetch);
    const controller = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    controller.setGoal("Tokens");
    fetch.mockResolvedValueOnce(response(run)).mockResolvedValue(response({ ...status, run }));
    await controller.generate(null);
    await vi.advanceTimersByTimeAsync(3000);
    const paid = fetch.mock.calls.filter(([url]) => String(url).endsWith("/runs"));
    expect(paid).toHaveLength(1);
    expect(JSON.parse(paid[0]?.[1]?.body as string)).toMatchObject({
      goal: "Tokens",
      constraint: null,
    });
    expect(fetch.mock.calls.at(-1)?.[0]).toEqual(expect.stringContaining("/status"));
    controller.stop();
    const count = fetch.mock.calls.length;
    await vi.advanceTimersByTimeAsync(6000);
    expect(fetch.mock.calls).toHaveLength(count);
  });

  it("a failed Generate retry reuses its request key instead of duplicating spending", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response(status));
    vi.stubGlobal("fetch", fetch);
    const controller = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    fetch.mockRejectedValueOnce(new Error("Response lost"));
    await controller.generate(null);
    expect(controller.getSnapshot().error).toBe("Response lost");
    fetch.mockResolvedValueOnce(response({ ...run, status: "completed" }));
    await controller.generate(null);
    const paid = fetch.mock.calls.filter(([url]) => String(url).endsWith("/runs"));
    expect(JSON.parse(paid[0]?.[1]?.body as string).request_key).toBe(
      JSON.parse(paid[1]?.[1]?.body as string).request_key,
    );
  });

  it("planning is an explicit pending action, separate from generate and feedback", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response({ ...status, run }));
    vi.stubGlobal("fetch", fetch);
    const changed = vi.fn(async () => {});
    const controller = start(changed);
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    fetch.mockResolvedValueOnce(response(true));
    await controller.plan("oracle-1", "run-1");
    expect(changed).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[1]?.[0]).toEqual(
      expect.stringContaining("/run-1/candidates/oracle-1/plan"),
    );
    fetch.mockResolvedValueOnce(response(true));
    await controller.feedback("oracle-1", "incorrect");
    expect(fetch.mock.calls.at(-1)?.[0]).toEqual(expect.stringContaining("/run-1/feedback"));
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/runs"))).toBe(false);
  });
});
