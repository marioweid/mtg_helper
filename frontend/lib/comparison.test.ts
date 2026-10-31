import { describe, expect, it } from "vitest";

import {
  comparisonExportCards,
  comparisonPlanningChanges,
  comparisonSelectionPreset,
  comparisonSelectionTotals,
  toggleComparisonGroup,
} from "@/lib/comparison";
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

describe("comparison planning selections", () => {
  const selected = new Set(["New card", "Cut card", "Increase", "Decrease", "Unchanged"]);

  it("uses only selected incoming deltas for planned additions", () => {
    expect(
      comparisonPlanningChanges(diff, "additions", selected).map((change) => [
        change.name,
        change.direction,
        change.quantity,
      ]),
    ).toEqual([
      ["New card", "addition", 2],
      ["Increase", "addition", 3],
    ]);
    expect(comparisonPlanningChanges(diff, "additions", new Set())).toEqual([]);
  });

  it("includes selected cuts and decreases without treating common cards as changes", () => {
    expect(
      comparisonPlanningChanges(diff, "changes", selected).map((change) => [
        change.name,
        change.direction,
        change.quantity,
      ]),
    ).toEqual([
      ["New card", "addition", 2],
      ["Cut card", "cut", 3],
      ["Increase", "addition", 3],
      ["Decrease", "cut", 3],
    ]);
  });

  it("carries addition categories but excludes commander changes", () => {
    const addition = { ...entry("Ramp", 0, 1), right_categories: ["ramp"] };
    const commander = { ...entry("Commander", 0, 1), right_categories: ["commander"] };
    const result = comparisonPlanningChanges(
      { ...diff, added: [addition, commander] },
      "changes",
      new Set(["Ramp", "Commander"]),
    );
    expect(result).toEqual([
      {
        card_id: "Ramp",
        card_scryfall_id: "Ramp",
        name: "Ramp",
        direction: "addition",
        quantity: 1,
        categories: ["ramp"],
      },
    ]);
  });
});

describe("comparison bulk selection", () => {
  it("selects all changed types but leaves common cards out of bulk presets", () => {
    expect([...comparisonSelectionPreset(diff, "changes")]).toEqual([
      "New card",
      "Cut card",
      "Increase",
      "Decrease",
    ]);
    expect([...comparisonSelectionPreset(diff, "additions")]).toEqual(["New card", "Increase"]);
    expect([...comparisonSelectionPreset(diff, "cuts")]).toEqual(["Cut card", "Decrease"]);
  });

  it("fills a partial group without dropping other selected groups or mutating input", () => {
    const selected = new Set(["Increase", "Unchanged"]);
    const next = toggleComparisonGroup(selected, diff.quantity_changed);
    expect([...next]).toEqual(["Increase", "Unchanged", "Decrease"]);
    expect([...selected]).toEqual(["Increase", "Unchanged"]);
  });

  it("clears only a fully selected group and permits selecting common cards for export", () => {
    const selected = new Set(["Increase", "Decrease", "Unchanged"]);
    expect([...toggleComparisonGroup(selected, diff.quantity_changed)]).toEqual(["Unchanged"]);
    expect([...toggleComparisonGroup(new Set(["New card"]), diff.common)]).toEqual([
      "New card",
      "Unchanged",
    ]);
    expect([...toggleComparisonGroup(selected, [])]).toEqual([...selected]);
  });

  it("distinguishes selected types from incoming/outgoing copy deltas", () => {
    const selected = new Set(["New card", "Increase", "Decrease", "Cut card", "Unchanged"]);
    expect(comparisonSelectionTotals(diff, selected)).toEqual({
      types: 5,
      changedTypes: 4,
      addedCopies: 5,
      removedCopies: 6,
    });
    const empty = { added: [], removed: [], quantity_changed: [], common: [] };
    expect([...comparisonSelectionPreset(empty, "changes")]).toEqual([]);
    expect(comparisonSelectionTotals(diff, new Set())).toEqual({
      types: 0,
      changedTypes: 0,
      addedCopies: 0,
      removedCopies: 0,
    });
  });
});
