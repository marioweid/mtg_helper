import { describe, expect, it } from "vitest";

import { ASSISTANT_STARTER_PROMPTS, INITIAL_ASSISTANT_PROMPT } from "./assistant-starter-prompts";

describe("Assistant starter prompts", () => {
  it("starts with an empty draft so no fake user message is shown", () => {
    expect(INITIAL_ASSISTANT_PROMPT).toBe("");
  });

  it("offers concise examples of the supported Assistant actions", () => {
    expect(ASSISTANT_STARTER_PROMPTS).toEqual([
      "Find the weakest cards in this deck.",
      "Suggest upgrades for my main theme.",
      "What should I replace this card with?",
      "Check my mana, draw, and interaction balance.",
    ]);
  });
});
