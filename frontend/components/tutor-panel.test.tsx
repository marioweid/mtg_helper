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
  it("renders saved Markdown as headings, emphasis, lists, and tables", () => {
    const content = [
      "## Game plan",
      "",
      "Develop **Yuna** before committing to combat.",
      "",
      "- Protect the engine",
      "- Hold `Counterspell`",
      "",
      "| Stage | Priority |",
      "| --- | --- |",
      "| Early | Ramp |",
    ].join("\n");
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          latest_run: { ...savedRun, guide: { ...savedRun.guide!, content } },
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toMatch(/<h[1-6][^>]*>Game plan<\/h[1-6]>/);
    expect(markup).toContain("<strong>Yuna</strong>");
    expect(markup).toMatch(/<ul[^>]*>/);
    expect(markup).toMatch(/<code[^>]*>Counterspell<\/code>/);
    expect(markup).toMatch(/<table[^>]*>/);
    expect(markup).not.toContain("## Game plan");
  });

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

  it("renders worked-hand Markdown without allowing HTML, unsafe links, or remote images", () => {
    const content = [
      "<script>alert('unsafe')</script>",
      "",
      "<iframe src='https://example.invalid/frame'></iframe>",
      "",
      "[Unsafe](javascript:alert%281%29)",
      "",
      "![Remote image](https://example.invalid/image.png)",
      "",
      "[Rules](https://magic.wizards.com/rules)",
    ].join("\n");
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          latest_run: {
            ...savedRun,
            guide: {
              ...savedRun.guide!,
              content,
              opening_hands: [
                {
                  decision: "keep",
                  cards: Array.from({ length: 7 }, () => "Forest"),
                  explanation: "`Forest` supplies **green** mana.",
                },
              ],
            },
          },
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("<strong>green</strong>");
    expect(markup).toMatch(/<code[^>]*>Forest<\/code>/);
    expect(markup).toContain('href="https://magic.wizards.com/rules"');
    expect(markup).toContain('rel="noopener noreferrer"');
    expect(markup).not.toMatch(/<script|<iframe|<img|href="javascript:/i);
    expect(markup).not.toContain("https://example.invalid/");
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

  it("wraps a detailed saved guide without truncating it", () => {
    const content = "Useful guide detail. ".repeat(4_000);
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          latest_run: { ...savedRun, guide: { ...savedRun.guide!, content } },
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain(content.trim());
    expect(markup).toContain("break-words");
  });
});
