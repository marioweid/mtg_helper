import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ToastProvider } from "./toast";
import { PlannedChangesPanel } from "./planned-changes-panel";
import type { PlannedDeckChange } from "../lib/types";

const plannedAddition = {
  id: "plan-1",
  deck_id: "deck-1",
  card_id: "card-1",
  scryfall_id: "scryfall-1",
  name: "Sol Ring",
  image_uri: "https://example.test/sol-ring.jpg",
  direction: "addition",
  quantity: 1,
  collection_id: null,
  physical_quantity: 0,
  projected_quantity: 1,
  categories: [],
  added_by: "user",
  ai_reasoning: null,
  owned_in: [],
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
} satisfies PlannedDeckChange;

describe("PlannedChangesPanel", () => {
  it("renders planned card names as card preview triggers", () => {
    const html = renderToStaticMarkup(
      <ToastProvider>
        <PlannedChangesPanel
          deckId="deck-1"
          plans={[plannedAddition]}
          physicalCount={1}
          plannedCount={2}
          onChanged={() => undefined}
        />
      </ToastProvider>,
    );

    expect(html).toMatch(/<span[^>]+role="button"[^>]*>Sol Ring/);
  });
});
