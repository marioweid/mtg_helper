import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AdminNewCardsPanel } from "@/components/admin-new-cards-panel";

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useEffect: () => undefined,
}));

describe("Admin New Cards controls", () => {
  it("ac13 renders a locked process as safe non-triggering global controls", () => {
    const html = renderToStaticMarkup(<AdminNewCardsPanel />);

    expect(html).toContain("Process execution: disabled");
    expect(html).toContain("This process cannot make paid calls.");
    expect(html).toContain('disabled=""');
    expect(html).not.toContain("Analyze next eight");
    expect(html).not.toContain("Daily package limit");
    expect(html).not.toContain("UTC reset");
  });
});
