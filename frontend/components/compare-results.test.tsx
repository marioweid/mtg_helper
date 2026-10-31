import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CompareResults } from "@/components/compare-results";
import type { DeckCompareResponse, DiffEntry } from "@/lib/types";

const card: DiffEntry = {
  card: {
    card_id: "forest",
    scryfall_id: "forest",
    name: "Forest",
    mana_cost: null,
    cmc: 0,
    type_line: "Basic Land — Forest",
    image_uri: null,
    color_identity: ["G"],
    price_eur_cents: 10,
    owned_in: [],
  },
  left_quantity: 2,
  right_quantity: 5,
  left_categories: [],
  right_categories: [],
};
const meta = {
  id: "deck",
  deck_id: "deck",
  deck_name: "Test deck",
  label: null,
  stage: "complete",
  bracket: null,
  card_count: 104,
  mana_curve: null,
};
const comparison: DeckCompareResponse = {
  left: { ...meta, kind: "deck" },
  right: { ...meta, kind: "planned" },
  diff: { added: [], removed: [], quantity_changed: [card], common: [] },
};

describe("comparison results", () => {
  it("offers incoming, full-side and selected exports with quantity-aware counts", () => {
    const html = renderToStaticMarkup(<CompareResults result={comparison} />);
    expect(html).toContain("3 incoming copies");
    expect(html).toContain("Export full left deck");
    expect(html).toContain("Export full right deck");
    expect(html).toContain("Export selected cards");
    expect(html).toContain('aria-label="Select Forest for export"');
    expect(html).toContain("2 → 5");
  });

  it("labels the planned deck and warns about its total including commanders", () => {
    const html = renderToStaticMarkup(<CompareResults result={comparison} />);
    expect(html).toContain("Planned deck");
    expect(html).toContain("4 cuts still needed");
    expect(html).toContain("104 cards including commanders");
  });

  it("does not imply that historical snapshots froze the commander configuration", () => {
    const html = renderToStaticMarkup(
      <CompareResults result={{ ...comparison, left: { ...comparison.left, kind: "snapshot" } }} />,
    );
    expect(html).toContain("Saved main deck; commanders use the deck");
    expect(html).toContain("current configuration");
  });
});
