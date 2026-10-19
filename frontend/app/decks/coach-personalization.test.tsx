import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => {
  const state: unknown[] = [];
  const effects: Array<() => void | (() => void)> = [];
  return {
    cursor: 0,
    state,
    effects,
    reset() {
      this.cursor = 0;
      this.state.length = 0;
      this.effects.length = 0;
    },
  };
});

const route = vi.hoisted(() => ({ deckId: "deck-1" }));

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  const nextSlot = () => hooks.cursor++;
  return {
    ...react,
    useState<T>(initial: T | (() => T)) {
      const slot = nextSlot();
      if (!(slot in hooks.state)) {
        hooks.state[slot] = typeof initial === "function" ? (initial as () => T)() : initial;
      }
      const setState = (value: T | ((current: T) => T)) => {
        const current = hooks.state[slot] as T;
        hooks.state[slot] =
          typeof value === "function" ? (value as (item: T) => T)(current) : value;
      };
      return [hooks.state[slot] as T, setState];
    },
    useEffect(effect: () => void | (() => void)) {
      const slot = nextSlot();
      if (!(slot in hooks.state)) {
        hooks.state[slot] = true;
        hooks.effects.push(effect);
      }
    },
    useCallback<T extends (...args: never[]) => unknown>(callback: T) {
      nextSlot();
      return callback;
    },
    useMemo<T>(factory: () => T) {
      nextSlot();
      return factory();
    },
    useContext() {
      nextSlot();
      return null;
    },
  };
});

vi.mock("next/navigation", () => ({ useParams: () => ({ id: route.deckId }) }));
vi.mock("next/link", () => ({ default: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/auth", () => ({ auth: async () => ({ idToken: "test-token" }) }));

import CoachPage from "@/app/decks/[id]/coach/page";
import type { CommanderCoachResolvedMode } from "@/lib/types";

const supportedModes = ["doctor", "builder", "mana", "meta", "chat", "replacement"] as const;
type HasOnlySupportedModes =
  Exclude<CommanderCoachResolvedMode, (typeof supportedModes)[number]> extends never
    ? Exclude<(typeof supportedModes)[number], CommanderCoachResolvedMode> extends never
      ? true
      : false
    : false;
const hasOnlySupportedModes: HasOnlySupportedModes = true;

interface EventListener {
  (event: MessageEvent): void;
}

class TestEventSource {
  readonly listeners = new Map<string, EventListener>();
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {}

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener);
  }

  close() {}

  emit(type: string, data: unknown) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

const requests: Array<{ url: string; init: RequestInit | undefined }> = [];
const streams: TestEventSource[] = [];

type TestElement = ReactElement<Record<string, unknown>>;

const deck = {
  id: "deck-1",
  name: "Test Deck",
  description: null,
  bracket: 3,
  stage: "ramp",
  commander_id: "commander-1",
  partner_id: null,
  commander_color_identity: ["G"],
  commander_card: null,
  partner_card: null,
  owner_email: null,
  created_at: "2026-10-18T00:00:00Z",
  updated_at: "2026-10-18T00:00:00Z",
  stage_targets: {},
  suggestion_collection_ids: [],
  archetype_tags: [],
  mana_curve: null,
  cards: [],
  physical_card_count: 1,
  planned_card_count: 1,
  planned_changes: [],
};

function response(data: unknown) {
  return new Response(JSON.stringify({ data }), { status: 200 });
}

async function flush() {
  for (let index = 0; index < 5; index += 1) {
    for (let turn = 0; turn < 12; turn += 1) await Promise.resolve();
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function coachTree(): ReactElement {
  hooks.cursor = 0;
  const page = CoachPage();
  if (!isValidElement(page) || typeof page.type !== "function")
    throw new Error("Assistant did not render");
  const conversation = page.type as (props: Record<string, unknown>) => ReactElement;
  return conversation(page.props as Record<string, unknown>);
}

function asElement(node: ReactNode): TestElement | undefined {
  return isValidElement(node) ? (node as TestElement) : undefined;
}

function findElement(
  node: ReactNode,
  predicate: (element: TestElement) => boolean,
): TestElement | undefined {
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findElement(child, predicate);
      if (found) return found;
    }
    return undefined;
  }
  const element = asElement(node);
  if (!element) return undefined;
  if (predicate(element)) return element;
  return findElement(element.props["children"] as ReactNode, predicate);
}

function text(value: ReactNode): string {
  if (Array.isArray(value)) return value.map(text).join("");
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

beforeEach(() => {
  hooks.reset();
  requests.length = 0;
  streams.length = 0;
  vi.stubGlobal("document", { body: { style: { overflow: "" } } });
  vi.stubGlobal(
    "EventSource",
    class extends TestEventSource {
      constructor(url: string) {
        super(url);
        streams.push(this);
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith("/decks/deck-1")) return response(deck);
      if (url.endsWith("/decks/deck-1/coach/start")) return response({ job_id: "job-1" });
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("keeps the Assistant response modes free of the retired memory mode", () => {
  expect(hasOnlySupportedModes).toBe(true);
  expect(supportedModes).toEqual(["doctor", "builder", "mana", "meta", "chat", "replacement"]);
});

it("loads and streams an Assistant answer without memory traffic while preserving chat history", async () => {
  coachTree();
  for (const effect of hooks.effects) effect();
  await flush();

  let tree = coachTree();
  let markup = renderToStaticMarkup(tree);
  expect(markup).toContain("MTG Assistant");
  expect(markup).toContain("Test Deck");
  expect(markup).not.toMatch(/(Edit|Save).*memory/i);
  expect(requests.map((request) => request.url)).not.toContainEqual(
    expect.stringMatching(/memory/i),
  );

  (
    findElement(tree, (element) => element.type === "textarea")?.props["onChange"] as
      | ((event: unknown) => void)
      | undefined
  )?.({
    target: { value: "How does my deck look?" },
  });
  tree = coachTree();
  (
    findElement(
      tree,
      (element) =>
        element.type === "button" && text(element.props["children"] as ReactNode) === "Send",
    )?.props["onClick"] as (() => void) | undefined
  )?.();
  await flush();
  expect(streams).toHaveLength(1);
  expect(streams[0]?.url).toBe("/api/v1/decks/deck-1/coach/job-1/stream");

  streams[0]?.emit("done", {
    mode: "chat",
    reply: "Add more early ramp.",
    recommendations: [],
    doctor: null,
    replacement: null,
  });
  tree = coachTree();
  markup = renderToStaticMarkup(tree);
  expect(markup).toContain("Add more early ramp.");

  (
    findElement(tree, (element) => element.type === "textarea")?.props["onChange"] as
      | ((event: unknown) => void)
      | undefined
  )?.({
    target: { value: "Which ramp card should I cut?" },
  });
  tree = coachTree();
  (
    findElement(
      tree,
      (element) =>
        element.type === "button" && text(element.props["children"] as ReactNode) === "Send",
    )?.props["onClick"] as (() => void) | undefined
  )?.();
  await flush();

  const turns = requests.filter((request) => request.url.endsWith("/coach/start"));
  expect(turns).toHaveLength(2);
  const followUp = JSON.parse(String(turns[1]?.init?.body));
  expect(followUp.history).toEqual([
    { role: "user", content: "How does my deck look?" },
    { role: "assistant", content: "Add more early ramp." },
  ]);
  expect(requests.map((request) => request.url)).not.toContainEqual(
    expect.stringMatching(/memory/i),
  );
});
