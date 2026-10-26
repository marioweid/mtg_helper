import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewCardsPanel } from "@/components/new-cards-panel";
import type { NewCardMatch, NewCardsResponse } from "@/lib/types";

const lifecycle = vi.hoisted(() => ({
  memo: undefined as unknown,
  memoDeps: [] as unknown[],
  effect: undefined as (() => void | (() => void)) | undefined,
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
  useEffect: (effect: () => void | (() => void)) => {
    lifecycle.effect = effect;
  },
  useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(),
}));
vi.mock("@/auth", () => ({ auth: async () => ({ idToken: "synthetic-session" }) }));

const match: NewCardMatch = {
  oracle_id: "oracle-1",
  card_id: "card-1",
  scryfall_id: "printing-1",
  name: "Tag matched card",
  mana_cost: "{G}",
  type_line: "Creature",
  oracle_text: "Source rules text.",
  power: "2",
  toughness: "3",
  faces: [],
  image_uri: "https://cards.scryfall.io/normal/front/a/b/new-card.jpg",
  scryfall_uri: "https://scryfall.com/search?q=oracleid%3Aoracle-1",
  released_at: "2026-10-20",
  expires_at: "2026-12-19",
  price_eur_cents: null,
  matching_tag_count: 1,
  tag_matches: [
    {
      commander_tag_id: "commander-tag",
      commander_tag_label: "Token maker",
      candidate_tag_id: "candidate-tag",
      candidate_tag_label: "Squirrel",
      relation: "descendant",
    },
  ],
};

const ready: NewCardsResponse = {
  status: "ready",
  catalog_updated_at: "2026-10-25T00:00:00Z",
  tag_updated_at: "2026-10-25T00:00:00Z",
  stale: false,
  eligible_count: 1,
  dismissed_count: 0,
  error: null,
  matches: [match],
};

const fetchMock = vi.fn<typeof fetch>();
const onPlanChanged = () => undefined;

function response(data: NewCardsResponse): Response {
  return new Response(JSON.stringify({ data }));
}

function render() {
  const view = <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />;
  const initial = renderToStaticMarkup(view);
  lifecycle.effect?.();
  return initial;
}

async function flush() {
  for (let index = 0; index < 50; index += 1) await Promise.resolve();
}

beforeEach(() => {
  lifecycle.memo = undefined;
  lifecycle.memoDeps = [];
  lifecycle.effect = undefined;
  fetchMock.mockReset().mockResolvedValue(response(ready));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("New Cards tag-match panel", () => {
  it("shows card artwork in the shared grid without duplicating printed rules", async () => {
    render();
    await flush();
    const markup = renderToStaticMarkup(
      <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />,
    );

    expect(markup).toContain(`src="${match.image_uri}"`);
    expect(markup).toContain(`alt="${match.name}"`);
    expect(markup).toContain('loading="lazy"');
    expect(markup).not.toContain(match.oracle_text);
    expect(markup).not.toContain("Power / toughness");
    expect(markup).toContain("Plan addition");
    expect(markup).toContain("Dismiss");
    expect(markup).toContain("View on Scryfall");
  });

  it("keeps tag explanations in hidden tooltips attached to focusable chips", async () => {
    render();
    await flush();
    const markup = renderToStaticMarkup(
      <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />,
    );

    expect(markup).toMatch(/<button[^>]*aria-describedby="([^"]+)"[^>]*>Squirrel<\/button>/);
    expect(markup).toMatch(/role="tooltip"[^>]*hidden=""/);
    const descriptionId = markup.match(/aria-describedby="([^"]+)"/)?.[1];
    expect(descriptionId).toBeTruthy();
    expect(markup).toContain(`id="${descriptionId}"`);
    expect(markup).toContain("descendant candidate tag");
  });

  it("keeps the name and actions usable when artwork is missing", async () => {
    fetchMock.mockResolvedValueOnce(
      response({ ...ready, matches: [{ ...match, image_uri: null }] }),
    );
    render();
    await flush();
    const markup = renderToStaticMarkup(
      <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />,
    );

    expect(markup).not.toContain("<img");
    expect(markup).toContain(match.name);
    expect(markup).toContain("Squirrel");
    expect(markup).not.toContain(match.oracle_text);
    expect(markup).toContain("Plan addition");
    expect(markup).toContain("Dismiss");
  });

  it("renders source-tag provenance from the authenticated New Cards response", async () => {
    render();
    await flush();
    const markup = renderToStaticMarkup(
      <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />,
    );

    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/v1/decks/deck-1/new-cards");
    expect(markup).toContain("New Cards from Scryfall tags");
    expect(markup).toContain("Token maker");
    expect(markup).toContain("descendant candidate tag");
    expect(markup).toContain("Squirrel");
    expect(markup).not.toContain("Generated advice");
    expect(markup).not.toContain("Analyze");
    expect(markup).not.toContain("Load more");
  });

  it("keeps empty results distinct from missing or stale source status", async () => {
    fetchMock.mockResolvedValueOnce(response({ ...ready, matches: [] }));
    render();
    await flush();
    expect(
      renderToStaticMarkup(<NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />),
    ).toContain("No current Scryfall tag matches for this deck.");

    lifecycle.memo = undefined;
    lifecycle.memoDeps = [];
    fetchMock.mockResolvedValueOnce(
      response({
        ...ready,
        status: "source_stale",
        matches: [],
        error: "Scryfall card or tag sources are stale. Run Admin Scryfall sync.",
      }),
    );
    render();
    await flush();
    const markup = renderToStaticMarkup(
      <NewCardsPanel deckId="deck-1" onPlanChanged={onPlanChanged} />,
    );
    expect(markup).toContain("sources are stale");
    expect(markup).not.toContain("No current Scryfall tag matches");
  });
});
