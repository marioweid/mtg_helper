import { describe, expect, it } from "vitest";

import { coachProgressMessage } from "./coach-progress";

describe("coachProgressMessage", () => {
  it("hides internal and terminal events", () => {
    expect(coachProgressMessage({ event: "memory_loaded", message: "Loaded memory" })).toBeNull();
    expect(coachProgressMessage({ event: "done", message: "Done" })).toBeNull();
  });

  it("maps assistant work to one user-facing status", () => {
    expect(
      coachProgressMessage({
        event: "assistant_thinking",
        message: "MTG Assistant is selecting deterministic tools",
      }),
    ).toBe("Looking over the deck…");
    expect(
      coachProgressMessage({
        event: "assistant_grounding",
        message: "Validating retrieved cards and deck evidence",
      }),
    ).toBe("Checking a few card options…");
  });
});
