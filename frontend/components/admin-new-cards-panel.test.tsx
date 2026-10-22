import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AdminNewCardsPanel, StartConfirmation } from "@/components/admin-new-cards-panel";

const fixture = vi.hoisted(() => ({
  status: null as {
    process_enabled: boolean;
    automatic_enabled: boolean;
    manual_active: boolean;
    automatic_active: boolean;
    cancelled: boolean;
    waiting: number;
    finished: number;
    failed: number;
    last_error: string | null;
  } | null,
}));

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useEffect: () => undefined,
  useState: <T,>(initial: T) => [
    fixture.status &&
    typeof initial === "object" &&
    initial !== null &&
    "process_enabled" in initial
      ? (fixture.status as T)
      : initial,
    vi.fn(),
  ],
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

  it("ac13 displays finished Commander-Konstellationen separately from waiting work", () => {
    fixture.status = {
      process_enabled: true,
      automatic_enabled: true,
      manual_active: false,
      automatic_active: false,
      cancelled: false,
      waiting: 0,
      finished: 1,
      failed: 0,
      last_error: null,
    };
    const html = renderToStaticMarkup(<AdminNewCardsPanel />);

    expect(html).toContain("Run: idle · Waiting 0 · Finished 1 · Failed 0");
    fixture.status = null;
  });

  it("ac13 disables an already-open confirmation when the process becomes locked", () => {
    const html = renderToStaticMarkup(
      <StartConfirmation
        confirming
        locked
        saving={false}
        unsafeToStart={false}
        onClose={() => undefined}
        onConfirm={() => undefined}
      />,
    );

    expect(html).toContain("Confirm global New Cards start");
    expect(html).toContain('disabled=""');
  });
});
