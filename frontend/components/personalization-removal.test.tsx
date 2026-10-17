import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { CardSuggestionCard } from "@/components/card-suggestion";
import { apiClient } from "@/lib/api";
import type { CardSuggestion } from "@/lib/types";

const rejected = {
  scryfall_id: "rejected-id",
  name: "Rejected Card",
  mana_cost: "{G}",
  type_line: "Creature",
  image_uri: null,
  oracle_text: "A card to replace.",
  power: null,
  toughness: null,
  rarity: "common",
  cmc: 1,
  color_identity: ["G"],
  category: "ramp",
  reasoning: "Source evidence.",
  synergies: ["ramp"],
  highlight_reasons: null,
  price_eur_cents: null,
  owned_in: [],
  qualifying_stages: ["ramp"],
  sources: ["Tags"],
  game_changer: false,
} satisfies CardSuggestion;

it("does not expose retired Builder feedback or preference requests", () => {
  expect(apiClient).not.toHaveProperty("submitFeedback");
  expect(apiClient).not.toHaveProperty("getPreferences");
  expect(apiClient).not.toHaveProperty("getRankingWeights");
});

it("renders explicit Builder actions without a personal-preference indicator", () => {
  const html = renderToStaticMarkup(
    <CardSuggestionCard
      suggestion={rejected}
      status="pending"
      onAccept={() => undefined}
      onReject={() => undefined}
      onRemove={() => undefined}
      onAddBack={() => undefined}
      isBasicLand={false}
      inCombo={false}
      quantity={1}
      onQuantityChange={() => undefined}
    />,
  );

  expect(html).toContain("Reject");
  expect(html).not.toContain("pet-card");
  expect(html).not.toContain("Favorite");
});
