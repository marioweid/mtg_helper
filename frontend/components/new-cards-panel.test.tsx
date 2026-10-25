import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const panel = readFileSync(
  fileURLToPath(new URL("./new-cards-panel.tsx", import.meta.url)),
  "utf8",
);

describe("New Cards tag matches", () => {
  it("renders transparent Scryfall tag explanations without AI controls", () => {
    expect(panel).toContain("New Cards from Scryfall tags");
    expect(panel).toContain("Commander tag");
    expect(panel).toContain("candidate tag");
    expect(panel).not.toContain("GeneratedAdvice");
    expect(panel).not.toContain("Analyze");
    expect(panel).not.toContain("Load more");
  });

  it("keeps source failures distinct from an empty match result", () => {
    expect(panel).toContain('result.status !== "ready"');
    expect(panel).toContain("No current Scryfall tag matches for this deck.");
  });
});
