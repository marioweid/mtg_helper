import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ComparisonPlanningActions } from "@/components/comparison-planning-actions";
import type { DeckCompareResponse, DiffEntry } from "@/lib/types";

function row(id: string, left: number, right: number): DiffEntry {
  return {
    card: {
      card_id: id,
      scryfall_id: id,
      name: id,
      mana_cost: null,
      cmc: 0,
      type_line: null,
      image_uri: null,
      color_identity: [],
      price_eur_cents: null,
      owned_in: [],
    },
    left_quantity: left,
    right_quantity: right,
    left_categories: [],
    right_categories: [],
  };
}
const meta = {
  id: "deck",
  deck_id: "deck",
  deck_name: "Target",
  label: null,
  stage: "complete",
  bracket: null,
  card_count: 100,
  mana_curve: null,
};
const result: DeckCompareResponse = {
  left: { ...meta, kind: "deck" },
  right: { ...meta, kind: "deck" },
  diff: {
    added: [row("Add", 0, 1)],
    removed: [row("Cut", 1, 0)],
    quantity_changed: [],
    common: [row("Common", 1, 1)],
  },
};

function render(selected: string[]) {
  return renderToStaticMarkup(
    <ComparisonPlanningActions
      result={result}
      decks={[]}
      selected={new Set(selected)}
      onPlanned={() => undefined}
    />,
  );
}

describe("comparison planning actions", () => {
  it("disables both actions when no changed card is selected", () => {
    const html = render(["Common"]);
    expect(html).toMatch(/<button[^>]+disabled=""[^>]*>Plan selected additions/);
    expect(html).toMatch(/<button[^>]+disabled=""[^>]*>Plan selected changes/);
    expect(html).toContain("Common cards and commander");
  });

  it("allows cuts only in the combined changes action", () => {
    const html = render(["Cut"]);
    expect(html).toMatch(/<button[^>]+disabled=""[^>]*>Plan selected additions/);
    const combined = html.match(/<button[^>]*>Plan selected changes<\/button>/)?.[0];
    expect(combined).toBeDefined();
    expect(combined).not.toContain('disabled=""');
  });

  it("enables both actions for an incoming selection", () => {
    expect(render(["Add"])).not.toContain('disabled=""');
  });
});
