import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CardWorkspaceToolbar } from "./card-workspace-toolbar";
import { CollectionCardGrid } from "./collection-card-grid";
import { DeckGrid } from "./deck-grid";
import { ExpandableDeckBar } from "./expandable-deck-bar";
import { ToastProvider } from "./toast";
import type { CollectionCardItem, DeckCardItem } from "../lib/types";

const deckCard = {
  deck_card_id: "deck-card-1",
  card_id: "card-1",
  scryfall_id: "scryfall-1",
  name: "Sol Ring",
  mana_cost: "{1}",
  cmc: 1,
  type_line: "Artifact",
  oracle_text: null,
  color_identity: [],
  image_uri: "https://example.test/sol-ring.jpg",
  rarity: "uncommon",
  quantity: 1,
  categories: ["ramp"],
  added_by: "user",
  ai_reasoning: null,
  qualifying_stages: [],
  role_reasons: {},
  tags: [],
  hub_tags: [],
  mtgjson_tags: [],
  price_eur_cents: 150,
  owned_in: [],
  game_changer: false,
  planned_cut_quantity: 0,
} satisfies DeckCardItem;

const collectionCard = {
  card_id: "card-1",
  scryfall_id: "scryfall-1",
  name: "Sol Ring",
  set_code: "cmm",
  collector_number: "396",
  image_uri: "https://example.test/sol-ring.jpg",
  color_identity: [],
  type_line: "Artifact",
  quantity: 2,
  foil: true,
  condition: "NM",
  language: "en",
  tags: ["trade"],
  purchase_price: "1.20",
  last_modified: null,
} satisfies CollectionCardItem;

describe("card workspaces", () => {
  it("renders an accessible grid/list control with the selected view", () => {
    const html = renderToStaticMarkup(
      <CardWorkspaceToolbar
        view="grid"
        onViewChange={() => undefined}
        resultCount={8}
        totalCount={10}
      />,
    );

    expect(html).toContain('aria-label="Card view"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("8 of 10 cards");
  });

  it("renders deck cards as artwork-first tiles with direct cut actions", () => {
    const html = renderToStaticMarkup(
      <DeckGrid
        cards={[deckCard]}
        onCardClick={() => undefined}
        onRemove={() => undefined}
      />,
    );

    expect(html).toContain("Artifact");
    expect(html).toContain("Sol Ring");
    expect(html).toContain("Plan Cut");
    expect(html).toContain("€1.50");
  });

  it("renders collection inventory metadata and quantity controls in the grid", () => {
    const html = renderToStaticMarkup(
      <CollectionCardGrid
        cards={[collectionCard]}
        decks={[]}
        busy={false}
        onSetQuantity={() => undefined}
        onRemove={() => undefined}
        onPlanForDeck={() => undefined}
      />,
    );

    expect(html).toContain("Foil");
    expect(html).toContain("NM");
    expect(html).toContain("€1.20");
    expect(html).toContain("Increase Sol Ring");
  });

  it("renders the closed builder bar as an explicit dialog trigger", () => {
    const html = renderToStaticMarkup(
      <ToastProvider>
        <ExpandableDeckBar cards={[deckCard]} onRemove={() => undefined} />
      </ToastProvider>,
    );

    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).toContain("View Deck");
    expect(html).toContain("1/100 cards");
  });
});
