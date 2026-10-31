import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ComparisonGroupToggle,
  ComparisonSelectionToolbar,
} from "@/components/comparison-selection-toolbar";
import type { DeckDiff, DiffEntry } from "@/lib/types";

function row(name: string, left: number, right: number): DiffEntry {
  return {
    card: {
      card_id: name,
      scryfall_id: name,
      name,
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
const diff: DeckDiff = {
  added: [row("New", 0, 2)],
  removed: [row("Old", 1, 0)],
  quantity_changed: [row("Land", 2, 5)],
  common: [row("Same", 1, 1)],
};

describe("comparison selection controls", () => {
  it("offers visible bulk controls with type-versus-copy counts", () => {
    const html = renderToStaticMarkup(
      <ComparisonSelectionToolbar
        diff={diff}
        selected={new Set(["New", "Land", "Old", "Same"])}
        onPreset={() => undefined}
        onClear={() => undefined}
      />,
    );
    expect(html).toContain('aria-label="Comparison selection"');
    expect(html).toContain(">Select all</button>");
    expect(html).toContain("Additions only");
    expect(html).toContain("Cuts only");
    expect(html).toContain("Clear selection");
    expect(html).toContain("4 unique cards selected · +5 copies in · −1 out");
    expect(html).toContain("1 unchanged card selected for export only");
  });

  it("communicates partial and fully selected groups accessibly", () => {
    const entries = [...diff.added, ...diff.removed];
    const partial = renderToStaticMarkup(
      <ComparisonGroupToggle
        label="Added"
        entries={entries}
        selected={new Set(["New"])}
        onToggle={() => undefined}
      />,
    );
    expect(partial).toContain('aria-checked="mixed"');
    expect(partial).toContain("1/2 selected · Select all");
    const full = renderToStaticMarkup(
      <ComparisonGroupToggle
        label="Added"
        entries={entries}
        selected={new Set(["New", "Old"])}
        onToggle={() => undefined}
      />,
    );
    expect(full).toContain('aria-checked="true"');
    expect(full).toContain('checked=""');
    expect(full).toContain("2/2 selected · Clear all");
  });

  it("labels common groups as export only and disables an empty group", () => {
    const common = renderToStaticMarkup(
      <ComparisonGroupToggle
        label="Common"
        entries={diff.common}
        selected={new Set()}
        onToggle={() => undefined}
      />,
    );
    expect(common).toContain("Common (1) · export only");
    const empty = renderToStaticMarkup(
      <ComparisonGroupToggle
        label="Removed"
        entries={[]}
        selected={new Set()}
        onToggle={() => undefined}
      />,
    );
    expect(empty).toContain('disabled=""');
    expect(empty).toContain('aria-checked="false"');
  });

  it("disables presets with no changed cards rather than implying a selection happened", () => {
    const empty = { added: [], removed: [], quantity_changed: [], common: [] };
    const html = renderToStaticMarkup(
      <ComparisonSelectionToolbar
        diff={empty}
        selected={new Set()}
        onPreset={() => undefined}
        onClear={() => undefined}
      />,
    );
    expect(html.match(/disabled=""/g)).toHaveLength(4);
    expect(html).toContain("0 unique cards selected");
  });
});
