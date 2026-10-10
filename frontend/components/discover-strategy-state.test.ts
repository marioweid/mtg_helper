import { Children, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { DiscoverTrace } from "@/components/discover-panel";
import { DiscoverController } from "@/components/discover-state";
import type { DiscoverRun, DiscoverStatus } from "@/lib/discovery-types";

const normal: DiscoverRun = {
  id: "cards",
  status: "completed",
  phase: "done",
  goal: "Existing goal",
  created_at: "2026-10-09",
  source_hash: "source",
  rules_hash: "rules",
  profile: "app-pilot-v1",
  error: null,
  stale: false,
  candidates: [],
  known_cost_microusd: 435,
  held_microusd: 0,
};
const draft: DiscoverRun = {
  ...normal,
  id: "draft",
  profile: "app-strategy-v2",
  strategies: ["Quick setup", "Steady engine", "Patient setup"].map((title) => ({
    title,
    pace: "Fast setup",
    early_game: "Ramp early",
    engine: "Use printed abilities",
    payoff: "Build pressure; finishing line remains open",
    goal: `${title}\nPace: Fast setup\nEarly setup: Ramp early\nEngine: Use printed abilities`,
    explanation: "Printed ability",
    uncertainties: [],
  })),
};
const initial: DiscoverStatus = {
  ready: true,
  reason: null,
  source_hash: "source",
  rules_hash: "rules",
  catalog_updated_at: null,
  goal_seed: "Saved description",
  run: normal,
  strategy_run: null,
  run_cap_microusd: 100000,
  daily_cap_microusd: 1000000,
  reserved_microusd: 67750,
  maximum_calls: 3,
  strategy_cap_microusd: 10000,
  strategy_reserved_microusd: 9800,
  strategy_maximum_calls: 1,
};
const controllers: DiscoverController[] = [];

function response(data: unknown) {
  return new Response(JSON.stringify({ data }));
}
function start() {
  vi.stubGlobal("window", {});
  let status = { ...initial };
  const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async (url) => {
    if (String(url).endsWith("/strategy-drafts")) {
      status = { ...status, strategy_run: draft };
      return response(draft);
    }
    if (String(url).endsWith("/runs")) return response(normal);
    if (String(url).endsWith("/trace")) return response({ profile: "app-strategy-v2" });
    return response(status);
  });
  vi.stubGlobal("fetch", fetch);
  const controller = new DiscoverController("deck", () => {});
  controllers.push(controller);
  controller.start();
  return {
    controller,
    fetch,
    setStatus: (next: DiscoverStatus) => {
      status = next;
    },
  };
}
afterEach(() => {
  controllers.forEach((controller) => controller.stop());
  controllers.length = 0;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it.each(["My original goal", ""])(
  "only explicit Draft charges; review/copy/edit never generate cards (%s)",
  async (originalGoal) => {
    const { controller, fetch } = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    controller.setGoal(originalGoal);
    await controller.draftStrategy();
    expect(controller.getSnapshot().goal).toBe(originalGoal);
    expect(controller.getSnapshot().status?.run?.id).toBe("cards");
    const writes = fetch.mock.calls.filter(([, options]) => options?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(String(writes[0]?.[0])).toContain("/strategy-drafts");
    expect(Object.keys(JSON.parse(writes[0]?.[1]?.body as string))).toEqual(["request_key"]);
    await controller.inspect(true);
    expect(String(fetch.mock.calls.at(-1)?.[0])).toContain("/runs/draft/trace");
    expect(controller.getSnapshot().trace?.["profile"]).toBe("app-strategy-v2");
    controller.useStrategy(1);
    expect(controller.getSnapshot().goal).toBe(draft.strategies?.[1]?.goal);
    expect(controller.getSnapshot().goal).toContain("Ramp early");
    controller.setGoal("My edited draft");
    expect(fetch.mock.calls.filter(([, options]) => options?.method)).toHaveLength(1);
    await controller.generate(null);
    const cardCall = fetch.mock.calls.find(([url]) => String(url).endsWith("/runs"));
    expect(JSON.parse(cardCall?.[1]?.body as string).goal).toBe("My edited draft");
  },
);

it("reuses the draft request key after a lost response", async () => {
  const { controller, fetch } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
  fetch.mockRejectedValueOnce(new Error("Lost response"));
  await controller.draftStrategy();
  const first = fetch.mock.calls.at(-1)?.[1]?.body;
  expect(controller.getSnapshot().error).toBe("Lost response");
  await controller.draftStrategy();
  const calls = fetch.mock.calls.filter(([url]) => String(url).endsWith("/strategy-drafts"));
  expect(calls).toHaveLength(2);
  expect(calls[1]?.[1]?.body).toBe(first);
});

it("does not use stale or incomplete drafts and never copies one on refresh", async () => {
  const { controller, setStatus } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
  controller.setGoal("Keep this");
  for (const candidate of [
    { ...draft, stale: true },
    { ...draft, status: "running" as const },
    { ...draft, profile: "app-strategy-v1" },
    { ...draft, strategies: [] },
  ]) {
    setStatus({ ...initial, strategy_run: candidate });
    await controller.refresh();
    controller.useStrategy(0);
    expect(controller.getSnapshot().goal).toBe("Keep this");
  }
});

it("selects each specific choice for free and rejects invalid choice indexes", async () => {
  const { controller, fetch } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
  await controller.draftStrategy();
  const before = fetch.mock.calls.length;
  for (const index of [0, 1, 2]) {
    controller.useStrategy(index);
    expect(controller.getSnapshot().goal).toBe(draft.strategies?.[index]?.goal);
  }
  const goal = controller.getSnapshot().goal;
  for (const index of [-1, 3, 0.5, NaN]) controller.useStrategy(index);
  expect(controller.getSnapshot().goal).toBe(goal);
  expect(fetch.mock.calls.length).toBe(before);
});

it("serializes draft and recommendation requests while a draft is active", async () => {
  const { controller, fetch, setStatus } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
  setStatus({ ...initial, strategy_run: { ...draft, status: "running" } });
  await controller.refresh();
  await controller.generate(null);
  await controller.draftStrategy();
  expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});

it.each([
  ["app-strategy-v2", true],
  ["app-strategy-v2", false],
  ["app-strategy-v1", true],
  ["app-strategy-v1", false],
] as const)(
  "refreshes %s strategy traces without switching to cards (cards=%s)",
  async (profile, cards) => {
    const { controller, fetch, setStatus } = start();
    await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
    setStatus({ ...initial, run: cards ? normal : null, strategy_run: { ...draft, profile } });
    await controller.refresh();
    await controller.inspect(true);
    const state = { ...controller.getSnapshot(), trace: { profile } };
    const tree = DiscoverTrace({ state, controller });
    expect(renderToStaticMarkup(tree)).toContain("Private commander strategy trace");
    const button = Children.toArray(tree.props.children).find(
      (child) =>
        isValidElement<{ children: string }>(child) &&
        child.props.children === "Refresh trace (no model call)",
    );
    if (!isValidElement<{ disabled: boolean; onClick: () => void }>(button)) {
      throw new Error("Trace refresh action missing");
    }
    expect(button.props.disabled).toBe(false);
    const before = fetch.mock.calls.length;
    button.props.onClick();
    await vi.waitFor(() => expect(fetch.mock.calls.length).toBe(before + 1));
    expect(String(fetch.mock.calls.at(-1)?.[0])).toContain("/runs/draft/trace");
    expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  },
);

it("polls a running draft read-only and stops polling on unmount", async () => {
  vi.useFakeTimers();
  const { controller, fetch } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().status).not.toBeNull());
  const active = { ...draft, status: "running" as const, strategies: [] };
  fetch.mockImplementation(async (url) =>
    response(
      String(url).endsWith("/strategy-drafts") ? active : { ...initial, strategy_run: active },
    ),
  );
  await controller.draftStrategy();
  const before = fetch.mock.calls.length;
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch.mock.calls.length).toBe(before + 1);
  expect(fetch.mock.calls.at(-1)?.[1]?.method).toBeUndefined();
  expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1);
  controller.stop();
  await vi.advanceTimersByTimeAsync(10000);
  expect(fetch.mock.calls.length).toBe(before + 1);
});
