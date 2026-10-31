import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ComparisonPlanningSummary } from "@/components/comparison-planning-summary";
import type { ComparisonPlannedChange } from "@/lib/comparison";

function change(direction: "addition" | "cut", quantity: number): ComparisonPlannedChange {
  return {
    card_id: direction,
    card_scryfall_id: direction,
    name: direction,
    direction,
    quantity,
    categories: [],
  };
}

describe("planning swap review", () => {
  it("shows copy balance rather than confusing one row with one copy", () => {
    const html = renderToStaticMarkup(
      <ComparisonPlanningSummary changes={[change("addition", 3), change("cut", 3)]} />,
    );
    expect(html).toContain("+3 copies in · −3 out · net 0");
    expect(html).toContain("Balanced swap selection");
  });

  it("makes an unbalanced selection visible before confirmation", () => {
    const html = renderToStaticMarkup(
      <ComparisonPlanningSummary changes={[change("addition", 3), change("cut", 1)]} />,
    );
    expect(html).toContain("net +2");
    expect(html).toContain("Unbalanced swap selection");
  });

  it("handles no selection and one-direction selections", () => {
    expect(renderToStaticMarkup(<ComparisonPlanningSummary changes={[]} />)).toContain(
      "No changed cards selected for planning",
    );
    expect(
      renderToStaticMarkup(<ComparisonPlanningSummary changes={[change("cut", 2)]} />),
    ).toContain("Cuts only");
    expect(
      renderToStaticMarkup(<ComparisonPlanningSummary changes={[change("addition", 2)]} />),
    ).toContain("Additions only");
  });
});
