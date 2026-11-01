import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { TutorPanelView } from "@/components/tutor-panel";
import type { TutorRunResponse, TutorStateResponse } from "@/lib/types";

const saved: TutorStateResponse = {
  mode: "commander",
  latest_run: {
    id: "run-1",
    status: "succeeded",
    mode: "commander",
    current: false,
    guide: {
      title: "Saved guide",
      content: "Keep interaction available before committing.",
      opening_hands: [],
    },
    evidence: { commanders: [], cards: [], warnings: ["Rules snapshot unavailable."], sources: {} },
    error: null,
    created_at: "2026-11-01T00:00:00Z",
    finished_at: "2026-11-01T00:01:00Z",
  },
  last_successful_run: null,
};
const savedRun = saved.latest_run as TutorRunResponse;

describe("Tutor panel", () => {
  it("keeps a historical guide readable while offering an explicit update", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={saved}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Outdated");
    expect(markup).toContain("Update Guide");
    expect(markup).toContain("Keep interaction available");
    expect(markup).toContain("Rules snapshot unavailable");
    expect(markup).not.toContain("Reference");
    expect(markup).not.toContain("Mulligan Practice");
  });

  it("labels both keyboard-operable mode choices before any guide exists", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{ mode: null, latest_run: null, last_successful_run: null }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Commander");
    expect(markup).toContain("cEDH");
    expect(markup).toContain("Choose a mode");
  });

  it("keeps last-good warnings and freshness after a failed update", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          mode: "commander",
          latest_run: {
            ...savedRun,
            status: "failed",
            current: true,
            guide: null,
            evidence: {
              commanders: [],
              cards: [],
              warnings: ["New-list warning must not replace saved evidence."],
              sources: {},
            },
            error: "Guide generation failed; retry explicitly.",
          },
          last_successful_run: savedRun,
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Outdated");
    expect(markup).toContain("Update Guide");
    expect(markup).toContain("Rules snapshot unavailable");
    expect(markup).not.toContain("New-list warning must not replace saved evidence.");
  });

  it("renders retained source-gap warnings with the guide", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          latest_run: {
            ...savedRun,
            current: true,
            evidence: {
              commanders: [],
              cards: [],
              warnings: ["Combo coverage is unavailable; no missing line is treated as absent."],
              sources: { combos: "timeout: Commander Spellbook" },
            },
          },
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Combo coverage is unavailable");
  });
});
