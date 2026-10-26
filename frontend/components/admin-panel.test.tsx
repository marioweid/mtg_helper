import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AdminPanel } from "@/components/admin-panel";

describe("AdminPanel", () => {
  it("renders the existing Scryfall source sync controls without New Cards analysis controls", () => {
    const markup = renderToStaticMarkup(<AdminPanel />);

    expect(markup).toContain("Sync Scryfall");
    expect(markup).toContain("Publish card facts, printing history, and Oracle tags together.");
    expect(markup).not.toContain("New Cards analysis");
    expect(markup).not.toContain("Analyze next");
    expect(markup).not.toContain("Load more");
  });
});
