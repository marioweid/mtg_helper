import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CoachRecommendations } from "./coach-recommendations";
import type { ReplacementOption } from "../lib/types";

const recommendation = {
  card: {
    scryfall_id: "card-1",
    name: "Skullclamp",
    mana_cost: "{1}",
    type_line: "Artifact — Equipment",
  },
  reason: "Turns Camellia's Squirrels into efficient card draw.",
  role_match: "role_upgrade",
  tradeoff: "Needs a disposable creature.",
} satisfies ReplacementOption;

describe("CoachRecommendations", () => {
  it("renders grounded card advice and tradeoffs", () => {
    const html = renderToStaticMarkup(
      <CoachRecommendations
        recommendations={[recommendation]}
        onAdd={() => undefined}
        busy={null}
      />,
    );

    expect(html).toContain("Skullclamp");
    expect(html).toContain("Turns Camellia&#x27;s Squirrels into efficient card draw.");
    expect(html).toContain("Needs a disposable creature.");
    expect(html).toContain("role upgrade");
  });

  it("renders nothing without recommendations", () => {
    const html = renderToStaticMarkup(
      <CoachRecommendations recommendations={[]} onAdd={() => undefined} busy={null} />,
    );

    expect(html).toBe("");
  });
});
