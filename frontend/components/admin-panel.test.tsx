import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AdminPanel } from "@/components/admin-panel";

describe("AdminPanel", () => {
  it("renders the existing Scryfall source sync controls without New Cards analysis controls", () => {
    const markup = renderToStaticMarkup(<AdminPanel />);

    expect(markup).toContain("Sync Scryfall");
    expect(markup).toContain("Scryfall catalog");
    expect(markup).toContain("Publish card facts, printed keywords, and Oracle tags");
    expect(markup).not.toContain("MTGJSON");
    expect(markup).not.toContain("Moxfield hub");
    expect(markup).not.toContain("New Cards analysis");
    expect(markup).not.toContain("Analyze next");
    expect(markup).not.toContain("Load more");
  });
});
