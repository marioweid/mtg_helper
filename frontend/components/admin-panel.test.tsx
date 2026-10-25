import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AdminPanel } from "@/components/admin-panel";

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useEffect: () => undefined,
  useCallback: <T,>(callback: T) => callback,
  useState: <T,>(initial: T) => [initial, vi.fn()],
}));

describe("admin panel", () => {
  it("renders the Scryfall source controls without retired sync actions", () => {
    const html = renderToStaticMarkup(<AdminPanel />);
    expect(html).toContain("Scryfall catalog");
    expect(html).toContain("Sync Scryfall");
    expect(html).not.toContain("MTGJSON");
    expect(html).not.toContain("Moxfield hub");
  });
});
