import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ComparisonPlanDialog,
  ComparisonPlanningPreview,
} from "@/components/comparison-plan-dialog";
import type { ComparisonPlannedChange } from "@/lib/comparison";
import type { ComparisonSideMeta, PlannedDeckChange } from "@/lib/types";

const change: ComparisonPlannedChange = {
  card_id: "forest",
  card_scryfall_id: "forest-printing",
  name: "Forest",
  direction: "addition",
  quantity: 3,
  categories: ["lands"],
};
const deck: ComparisonSideMeta = {
  id: "deck",
  deck_id: "deck",
  kind: "deck",
  deck_name: "Left target",
  label: null,
  stage: "complete",
  bracket: null,
  card_count: 100,
  mana_curve: null,
};
function plan(direction: "addition" | "cut", quantity: number): PlannedDeckChange {
  return {
    id: "plan",
    deck_id: "deck",
    card_id: "forest",
    scryfall_id: "forest-printing",
    name: "Forest",
    image_uri: null,
    direction,
    quantity,
    collection_id: null,
    physical_quantity: 5,
    projected_quantity: 5 + quantity,
    categories: ["lands"],
    added_by: "user",
    ai_reasoning: null,
    owned_in: [],
    created_at: "",
    updated_at: "",
  };
}

describe("comparison planning dialog", () => {
  it("requires confirmation on a chosen target without moving physical cards", () => {
    const html = renderToStaticMarkup(
      <ComparisonPlanDialog
        title="Plan selected additions"
        changes={[change]}
        defaultDeck={deck}
        decks={[]}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain("Target deck");
    expect(html).toContain("Left target");
    expect(html).toContain("Physical cards and binders");
    expect(html).toContain("will not change");
    expect(html).toContain("Confirm plan");
    expect(html).toMatch(/<button[^>]+disabled=""[^>]*>Confirm plan/);
  });

  it("previews matching quantities without doubling them", () => {
    const html = renderToStaticMarkup(
      <ComparisonPlanningPreview changes={[change]} plans={[plan("addition", 2)]} items={[]} />,
    );
    expect(html).toContain("+3 Forest");
    expect(html).toContain("Increase pending addition: 2 → 3");
    const covered = renderToStaticMarkup(
      <ComparisonPlanningPreview changes={[change]} plans={[plan("addition", 4)]} items={[]} />,
    );
    expect(covered).toContain("Already planned: 4 pending addition copies");
  });

  it("warns that an opposite plan will not be overwritten", () => {
    const html = renderToStaticMarkup(
      <ComparisonPlanningPreview changes={[change]} plans={[plan("cut", 1)]} items={[]} />,
    );
    expect(html).toContain("Conflict: 1 pending cut copies; not overwritten");
  });

  it("shows individual failures and successes rather than reporting blanket success", () => {
    const second: ComparisonPlannedChange = {
      ...change,
      card_id: "ring",
      card_scryfall_id: "ring-printing",
      name: "Sol Ring",
      direction: "cut",
      quantity: 1,
    };
    const html = renderToStaticMarkup(
      <ComparisonPlanningPreview
        changes={[change, second]}
        plans={[]}
        items={[
          {
            card_scryfall_id: change.card_scryfall_id,
            status: "planned",
            message: "Pending addition set to 3 copies",
            pending_quantity: 3,
          },
          {
            card_scryfall_id: second.card_scryfall_id,
            status: "failed",
            message: "Planned cut exceeds the physical deck quantity",
            pending_quantity: null,
          },
        ]}
      />,
    );
    expect(html).toContain("1 planned · 0 already planned · 1 failed");
    expect(html).toContain("Pending addition set to 3 copies");
    expect(html).toContain("Planned cut exceeds the physical deck quantity");
  });
});
