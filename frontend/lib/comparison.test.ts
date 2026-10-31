import { describe, expect, it } from "vitest";

import { comparisonExportCards } from "@/lib/comparison";
import type { DeckDiff, DiffEntry } from "@/lib/types";

function entry(name: string, left: number, right: number): DiffEntry {
  return {
    card: {
      card_id: name,
      scryfall_id: name,
      name,
      mana_cost: null,
      cmc: null,
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

const diff: DeckDiff = {
  added: [entry("New card", 0, 2)],
  removed: [entry("Cut card", 3, 0)],
  quantity_changed: [entry("Increase", 2, 5), entry("Decrease", 4, 1)],
  common: [entry("Unchanged", 1, 1)],
};

describe("comparison exports", () => {
  it("exports only incoming quantities, including increases", () => {
    expect(comparisonExportCards(diff, "incoming")).toEqual([
      { card_id: "New card", quantity: 2 },
      { card_id: "Increase", quantity: 3 },
    ]);
  });

  it("exports either complete side, without including absent cards", () => {
    const left = comparisonExportCards(diff, "left");
    const right = comparisonExportCards(diff, "right");
    expect(left.reduce((sum, card) => sum + card.quantity, 0)).toBe(10);
    expect(right.reduce((sum, card) => sum + card.quantity, 0)).toBe(9);
    expect(left.some((card) => card.card_id === "New card")).toBe(false);
    expect(right.some((card) => card.card_id === "Cut card")).toBe(false);
  });

  it("exports selected changes in their delta quantities, or common quantities", () => {
    expect(
      comparisonExportCards(diff, "selected", new Set(["Cut card", "Increase", "Unchanged"])),
    ).toEqual([
      { card_id: "Cut card", quantity: 3 },
      { card_id: "Increase", quantity: 3 },
      { card_id: "Unchanged", quantity: 1 },
    ]);
    expect(comparisonExportCards(diff, "selected")).toEqual([]);
  });

  it("handles an identical or empty deck", () => {
    expect(
      comparisonExportCards({ ...diff, added: [], removed: [], quantity_changed: [] }, "incoming"),
    ).toEqual([]);
    expect(
      comparisonExportCards({ added: [], removed: [], quantity_changed: [], common: [] }, "right"),
    ).toEqual([]);
  });
});
