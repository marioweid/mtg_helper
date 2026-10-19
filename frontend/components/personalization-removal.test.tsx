import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { CardSuggestion } from "@/lib/types";

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
    useReducer<T, Action>(
      reducer: (state: T, action: Action) => T,
      initial: T,
      init?: (value: T) => T,
    ) {
      const slot = nextSlot();
      if (!(slot in hooks.state)) hooks.state[slot] = init ? init(initial) : initial;
      const dispatch = (action: Action) => {
        hooks.state[slot] = reducer(hooks.state[slot] as T, action);
      };
      return [hooks.state[slot] as T, dispatch];
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
    useRef<T>(initial: T) {
      const slot = nextSlot();
      if (!(slot in hooks.state)) hooks.state[slot] = { current: initial };
      return hooks.state[slot] as { current: T };
    },
  };
});

vi.mock("next/navigation", () => ({ useParams: () => ({ id: route.deckId }) }));
vi.mock("next/link", () => ({ default: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/auth", () => ({ auth: async () => ({ idToken: "test-token" }) }));

import BuildPage from "@/app/decks/[id]/build/page";
import { CardSuggestionCard } from "@/components/card-suggestion";

const requests: Array<{ url: string; init: RequestInit | undefined }> = [];

type TestElement = ReactElement<Record<string, unknown>>;

function suggestion(id: string, name: string): CardSuggestion {
  return {
    scryfall_id: id,
    name,
    mana_cost: "{G}",
    type_line: "Creature",
    image_uri: null,
    oracle_text: "A card to replace.",
    power: null,
    toughness: null,
    rarity: "common",
    cmc: 1,
    color_identity: ["G"],
    category: "ramp",
    reasoning: "Source evidence.",
    synergies: ["ramp"],
    highlight_reasons: null,
    price_eur_cents: null,
    owned_in: [],
    qualifying_stages: ["ramp"],
    sources: ["Tags"],
    game_changer: false,
  };
}

const rejected = suggestion("rejected-id", "Rejected Card");
const replacement = suggestion("replacement-id", "Replacement Card");
const initialSuggestions = [
  rejected,
  ...Array.from({ length: 39 }, (_, index) => suggestion(`card-${index}`, `Card ${index}`)),
  replacement,
];

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
    for (let turn = 0; turn < 16; turn += 1) await Promise.resolve();
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function buildTree(): ReturnType<typeof BuildPage> {
  hooks.cursor = 0;
  return BuildPage();
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

function cards(tree: ReactNode) {
  const found: Array<{ props: { suggestion: CardSuggestion; onReject: () => void } }> = [];
  function visit(node: ReactNode): void {
    if (Array.isArray(node)) return node.forEach(visit);
    const element = asElement(node);
    if (!element) return;
    if (element.type === CardSuggestionCard) found.push(element as never);
    visit(element.props["children"] as ReactNode);
  }
  visit(tree);
  return found;
}

function text(value: ReactNode): string {
  if (Array.isArray(value)) return value.map(text).join("");
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

async function mountBuilder(deckId: string) {
  hooks.reset();
  route.deckId = deckId;
  buildTree();
  for (const effect of hooks.effects.splice(0)) effect();
  await vi.waitFor(() => expect(cards(buildTree()).length).toBeGreaterThan(0));
  return buildTree();
}

beforeEach(() => {
  requests.length = 0;
  vi.stubGlobal("window", { matchMedia: () => ({ matches: false }) });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (/\/decks\/deck-[12]$/.test(url)) return response({ ...deck, id: route.deckId });
      if (url.endsWith("/combos")) return response({ active: [], almost_there: [] });
      if (url.endsWith("/me/collections")) return response([]);
      if (url.endsWith("/build"))
        return response({ suggestions: initialSuggestions, unresolved: [] });
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("replaces rejected Builder cards locally, excludes them on reload, and starts fresh after navigation", async () => {
  let tree = await mountBuilder("deck-1");
  expect(cards(tree).map((card) => card.props.suggestion.name)).toContain("Rejected Card");
  const initialMarkup = renderToStaticMarkup(tree);
  expect(initialMarkup).not.toMatch(/pet card|pet-card|♥|❤️/i);

  cards(tree)
    .find((card) => card.props.suggestion.name === "Rejected Card")
    ?.props.onReject();
  tree = buildTree();
  const currentNames = cards(tree).map((card) => card.props.suggestion.name);
  expect(currentNames).not.toContain("Rejected Card");
  expect(currentNames).toContain("Replacement Card");

  (
    findElement(
      tree,
      (element) =>
        element.type === "button" && text(element.props["children"] as ReactNode) === "Load More",
    )?.props["onClick"] as (() => void) | undefined
  )?.();
  await flush();
  const loadMore = requests.filter((request) => request.url.endsWith("/build")).at(-1);
  expect(JSON.parse(String(loadMore?.init?.body)).exclude).toContain("Rejected Card");
  expect(requests.map((request) => request.url)).not.toContainEqual(
    expect.stringMatching(/\/feedback(?:\/|$)|\/me\/preferences|ranking-weights/),
  );

  tree = await mountBuilder("deck-2");
  expect(cards(tree).map((card) => card.props.suggestion.name)).toContain("Rejected Card");
  const freshLoad = requests.filter((request) => request.url.endsWith("/decks/deck-2/build"))[0];
  expect(JSON.parse(String(freshLoad?.init?.body)).exclude).toBeNull();
});
