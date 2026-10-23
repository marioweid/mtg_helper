import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ArchetypeChipPicker } from "@/components/archetype-chip-picker";

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useEffect: () => undefined,
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => [initial, vi.fn()],
}));

describe("Scryfall tag picker", () => {
  it("renders only Scryfall source labels while the catalog is loading", () => {
    const html = renderToStaticMarkup(
      <ArchetypeChipPicker value={[]} onChange={() => undefined} />,
    );
    expect(html).toContain("Loading Scryfall labels...");
    expect(html).not.toContain("Moxfield");
    expect(html).not.toContain("MTGJSON");
  });
});
