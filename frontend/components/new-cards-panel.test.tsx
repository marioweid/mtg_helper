import React, { isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewCardsPanel } from "@/components/new-cards-panel";
import type { NewCardPick, NewCardsResponse } from "@/lib/types";

// No DOM environment is installed. This adapter drives hook scheduling and rerenders while
// retaining the production controller, button handlers, child components and request client.
const lifecycle = vi.hoisted(() => ({
  memo: undefined as unknown,
  memoDeps: [] as unknown[],
  effectDependency: undefined as unknown,
  pendingEffect: undefined as (() => () => void) | undefined,
  cleanup: undefined as (() => void) | undefined,
}));

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useMemo: (factory: () => unknown, deps: unknown[]) => {
    if (deps.some((dep, index) => dep !== lifecycle.memoDeps[index])) {
      lifecycle.memo = factory();
      lifecycle.memoDeps = deps;
    }
    return lifecycle.memo;
  },
  useEffect: (effect: () => () => void, deps: unknown[]) => {
    if (deps[0] !== lifecycle.effectDependency) {
      lifecycle.effectDependency = deps[0];
      lifecycle.pendingEffect = effect;
    }
  },
  useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(),
}));
vi.mock("@/auth", () => ({ auth: async () => ({ idToken: "test-token" }) }));

const pick: NewCardPick = {
  oracle_id: "oracle-1",
  card_id: "card-1",
  scryfall_id: "printing-1",
  name: "New Creature",
  mana_cost: "{G}",
  type_line: "Creature",
  oracle_text: "Source rule text.",
  power: "2",
  toughness: "3",
  faces: [],
  image_uri: null,
  scryfall_uri: "https://scryfall.com/card/test/1",
  released_at: "2026-07-01",
  expires_at: "2026-10-01",
  price_eur_cents: 150,
  label: "strong",
  reason: "Generated reason.",
  caveat: "Supporting card has a pending cut.",
  required_changes: ["Keep the supporting creature."],
  evidence: [{ name: "Physical Support", quote: "Draw a card." }],
};

const result: NewCardsResponse = {
  status: "idle",
  catalog_updated_at: "2026-07-20T23:00:00-02:00",
  analyzed_at: "2026-07-21T00:00:00Z",
  stale: false,
  eligible_count: 12,
  assessed_count: 8,
  remaining_count: 4,
  dismissed_count: 0,
  error: null,
  picks: [pick],
};

const fetchMock = vi.fn<typeof fetch>();
const onPlanChanged = vi.fn<() => Promise<void>>();

function respond(data: NewCardsResponse, status = 200) {
  return new Response(JSON.stringify({ data }), { status });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function view(deckId = "deck-1") {
  const tree = NewCardsPanel({ deckId, onPlanChanged });
  if (lifecycle.pendingEffect) {
    lifecycle.cleanup?.();
    lifecycle.cleanup = lifecycle.pendingEffect();
    lifecycle.pendingEffect = undefined;
  }
  return tree;
}

interface ElementProps {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}

function buttons(node: ReactNode): React.ReactElement<ElementProps>[] {
  if (Array.isArray(node)) return node.flatMap(buttons);
  if (!isValidElement<ElementProps>(node)) return [];
  if (typeof node.type === "function") {
    const component = node.type as (props: ElementProps) => ReactNode;
    return buttons(component(node.props));
  }
  if (node.type === "button") return [node];
  return buttons(node.props.children);
}

function click(label: string) {
  const button = buttons(view()).find((item) => item.props.children === label);
  expect(button, `Button ${label} exists`).toBeDefined();
  expect(button?.props.disabled, `Button ${label} enabled`).not.toBe(true);
  button?.props.onClick?.();
}

function html(deckId = "deck-1") {
  return renderToStaticMarkup(view(deckId));
}

async function flush() {
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-07-21T00:00:00Z"));
  lifecycle.memo = undefined;
  lifecycle.memoDeps = [];
  lifecycle.effectDependency = undefined;
  lifecycle.pendingEffect = undefined;
  lifecycle.cleanup = undefined;
  fetchMock.mockReset().mockImplementation(async () => respond(result));
  onPlanChanged.mockReset().mockResolvedValue(undefined);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  lifecycle.cleanup?.();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("New Cards panel lifecycle and HTTP actions", () => {
  it("loads with authenticated GET and separates source facts from advice", async () => {
    html();
    await flush();
    const markup = html();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/v1/decks/deck-1/new-cards");
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      authorization: "Bearer test-token",
    });
    expect(markup).toContain("Experimental pilot");
    expect(markup).toContain("Released, Commander-legal paper cards only");
    expect(markup).toContain("Scryfall catalog updated 2026-07-21");
    expect(markup).toContain("8 of 12 currently eligible cards assessed");
    expect(markup).toContain("Partial coverage");
    expect(markup).toContain("Strong fits");
    expect(markup).not.toContain("Worth testing");
    expect(markup.indexOf("Source rule text.")).toBeLessThan(markup.indexOf("Generated advice"));
    expect(markup).toContain("Power / toughness: 2 / 3");
    expect(markup).toContain("Physical Support");
    expect(markup).toContain("pending cut");
    expect(markup).toContain("Keep the supporting creature.");
    expect(markup).toContain('rel="noopener noreferrer"');
    await vi.advanceTimersByTimeAsync(9000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("analyzes only on click, polls while running, and stops on completion", async () => {
    html();
    await flush();
    fetchMock.mockResolvedValueOnce(respond({ ...result, status: "running" }, 202));
    click("Analyze next eight");
    await flush();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/new-cards/analyze");
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(html()).toContain("Analysis running");
    await vi.advanceTimersByTimeAsync(3000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(html()).not.toContain("Analysis running");
    await vi.advanceTimersByTimeAsync(9000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("ignores a pending read superseded by dismiss and cancels timers on exit", async () => {
    html();
    await flush();
    const oldRead = deferred<Response>();
    fetchMock.mockReturnValueOnce(oldRead.promise);
    click("Refresh status");
    await flush();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/decks/deck-1/new-cards");
    fetchMock.mockResolvedValueOnce(respond({ ...result, status: "running" }));
    click("Dismiss");
    await flush();
    oldRead.resolve(respond({ ...result, picks: [], status: "idle" }));
    await flush();
    expect(html()).toContain("Analysis running");
    lifecycle.cleanup?.();
    await vi.advanceTimersByTimeAsync(9000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

describe("New Cards refresh and dismissal", () => {
  it("does not display responses from the previous deck or after unmount", async () => {
    const oldRead = deferred<Response>();
    fetchMock.mockReturnValueOnce(oldRead.promise);
    html();
    await flush();
    fetchMock.mockResolvedValueOnce(
      respond({ ...result, picks: [], eligible_count: 0, remaining_count: 0 }),
    );
    html("deck-2");
    await flush();
    oldRead.resolve(respond(result));
    await flush();
    expect(html("deck-2")).not.toContain("New Creature");
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/decks/deck-2/new-cards");
    lifecycle.cleanup?.();
    await vi.advanceTimersByTimeAsync(6000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps old picks visibly stale until a network retry succeeds", async () => {
    html();
    await flush();
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    click("Refresh status");
    await flush();
    expect(html()).toContain("New Creature");
    expect(html()).toContain("may be stale");
    expect(html()).toContain("Refresh New Cards failed: offline");
    const retry = deferred<Response>();
    fetchMock.mockReturnValueOnce(retry.promise);
    click("Refresh status");
    await flush();
    expect(html()).toContain("may be stale");
    retry.resolve(respond(result));
    await flush();
    expect(html()).not.toContain("may be stale");
  });

  it("dismisses and undoes only the latest successful dismissal using server state", async () => {
    html();
    await flush();
    const second = { ...pick, oracle_id: "oracle-2", name: "Second Creature" };
    fetchMock.mockResolvedValueOnce(respond({ ...result, picks: [second], dismissed_count: 1 }));
    click("Dismiss");
    await flush();
    expect(html()).toContain("Dismissed New Creature");
    fetchMock.mockResolvedValueOnce(respond({ ...result, picks: [], dismissed_count: 2 }));
    click("Dismiss");
    await flush();
    expect(html()).toContain("Dismissed Second Creature");
    fetchMock.mockResolvedValueOnce(respond({ ...result, picks: [second], dismissed_count: 1 }));
    click("Undo latest dismissal");
    await flush();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/oracle-1/dismiss");
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[3]?.[0]).toContain("/oracle-2/dismiss");
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe("DELETE");
    expect(html()).toContain("Second Creature");
    expect(html()).not.toContain("Undo latest dismissal");
  });
});

describe("New Cards planning and request failures", () => {
  it("awaits parent refresh after planning and offers retry on callback failure", async () => {
    html();
    await flush();
    const parent = deferred<void>();
    onPlanChanged.mockReturnValueOnce(parent.promise);
    fetchMock.mockResolvedValueOnce(respond({ ...result, picks: [] }));
    click("Plan addition");
    await flush();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/oracle-1/plan");
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(onPlanChanged).toHaveBeenCalledTimes(1);
    expect(html()).toContain("Updating New Cards");
    expect(html()).not.toContain("New Creature");
    parent.reject(new Error("parent offline"));
    await flush();
    expect(html()).toContain("Addition planned, but deck refresh failed: parent offline");
    click("Refresh status");
    await flush();
    expect(html()).toContain("Retry deck refresh");
    click("Retry deck refresh");
    await flush();
    expect(onPlanChanged).toHaveBeenCalledTimes(2);
    expect(html()).not.toContain("Retry deck refresh");
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes("/new-cards"))).toBe(true);
  });

  it("shows initial load failure without inventing a no-match result", async () => {
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    html();
    await flush();
    expect(html()).toContain("Refresh New Cards failed: offline");
    expect(html()).not.toContain("No strong fits");
  });

  it.each(["Plan addition", "Dismiss", "Analyze next eight"])(
    "shows failed %s and keeps usable results",
    async (action) => {
      html();
      await flush();
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: { code: "QUOTA", message: "Operation rejected" },
          }),
          { status: 429 },
        ),
      );
      click(action);
      await flush();
      expect(html()).toContain("Operation rejected");
      expect(html()).toContain("New Creature");
      expect(onPlanChanged).not.toHaveBeenCalled();
    },
  );

  it("retains undo on a failed undo request", async () => {
    html();
    await flush();
    fetchMock.mockResolvedValueOnce(respond({ ...result, picks: [] }));
    click("Dismiss");
    await flush();
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    click("Undo latest dismissal");
    await flush();
    expect(html()).toContain("Undo dismissal of New Creature failed: offline");
    expect(html()).toContain("Undo latest dismissal");
  });
});

describe("New Cards in-flight safeguards", () => {
  it("ignores late plan responses on exit and prevents duplicate mutations", async () => {
    html();
    await flush();
    const pendingPlan = deferred<Response>();
    fetchMock.mockReturnValueOnce(pendingPlan.promise);
    const handler = buttons(view()).find((item) => item.props.children === "Plan addition")?.props
      .onClick;
    handler?.();
    handler?.();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    lifecycle.cleanup?.();
    pendingPlan.resolve(respond({ ...result, status: "running", picks: [] }));
    await flush();
    expect(onPlanChanged).not.toHaveBeenCalled();
    expect(html()).toContain("New Creature");
    await vi.advanceTimersByTimeAsync(9000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries polling after network failure and stops on server error", async () => {
    fetchMock.mockResolvedValueOnce(respond({ ...result, status: "running" }));
    html();
    await flush();
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await vi.advanceTimersByTimeAsync(3000);
    expect(html()).toContain("may be stale");
    expect(html()).toContain("offline");
    fetchMock.mockResolvedValueOnce(respond({ ...result, status: "error", error: "Timed out" }));
    await vi.advanceTimersByTimeAsync(3000);
    expect(html()).toContain("Timed out");
    expect(html()).not.toContain("offline");
    await vi.advanceTimersByTimeAsync(9000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows non-Error failures with operation and retry context", async () => {
    fetchMock.mockRejectedValueOnce("unexpected rejection");
    html();
    await flush();
    expect(html()).toContain("Refresh New Cards failed: Unexpected request failure");
    expect(html()).toContain("Retry when connected");
  });
});

describe("New Cards source and empty states", () => {
  it.each([
    [{ status: "unavailable", picks: [] }, "Not ready"],
    [{ status: "error", error: "Model unavailable", picks: [] }, "analysis failed, not a no-match"],
    [{ status: "running", picks: [] }, "analysis is still running"],
    [{ picks: [], stale: true }, "not a no-match result"],
    [{ picks: [] }, "Analyze unassessed cards"],
    [{ picks: [], remaining_count: 0 }, "No strong fits or cards worth testing"],
    [{ picks: [], remaining_count: 0, eligible_count: 0 }, "No released cards"],
  ] satisfies [Partial<NewCardsResponse>, string][])(
    "shows %j accurately",
    async (override, text) => {
      fetchMock.mockResolvedValueOnce(respond({ ...result, ...override }));
      html();
      await flush();
      expect(html()).toContain(text);
    },
  );

  it("renders all faces and worth-testing advice without filler or scores", async () => {
    fetchMock.mockResolvedValueOnce(
      respond({
        ...result,
        picks: [
          {
            ...pick,
            label: "worth_testing",
            faces: [
              pick,
              {
                ...pick,
                name: "Back Face",
                oracle_text: "Back rules.",
                power: null,
                toughness: null,
              },
            ],
            required_changes: [],
            evidence: [],
            price_eur_cents: null,
          },
        ],
      }),
    );
    html();
    await flush();
    const markup = html();
    expect(markup).toContain("Worth testing");
    expect(markup).not.toContain("Strong fits");
    expect(markup).toContain("Back Face");
    expect(markup).toContain("Back rules.");
    expect(markup).toContain("No supporting evidence returned");
    expect(markup).toContain("not a guarantee of fit");
    expect(markup).toContain("Price unavailable");
    expect(markup).not.toContain("score");
  });

  it.each([
    "javascript:alert(1)",
    "https://scryfall.com.evil.test/card/1",
    "http://scryfall.com/card/1",
    "https://user:password@scryfall.com/card/1",
    "not a url",
    "https://scryfall.com:444/card/1",
  ])("does not render unsafe source link %s", async (uri) => {
    fetchMock.mockResolvedValueOnce(
      respond({ ...result, picks: [{ ...pick, scryfall_uri: uri }] }),
    );
    html();
    await flush();
    expect(html()).toContain("Source link unavailable or unsafe");
    expect(html()).not.toContain('target="_blank"');
  });

  it("handles missing and malformed source dates", async () => {
    fetchMock.mockResolvedValueOnce(
      respond({
        ...result,
        catalog_updated_at: null,
        analyzed_at: "bad-date",
        stale: true,
      }),
    );
    html();
    await flush();
    expect(html()).toContain("not available");
    expect(html()).toContain("unknown date");
    expect(html()).toContain("Source or analysis is stale");
  });
});
