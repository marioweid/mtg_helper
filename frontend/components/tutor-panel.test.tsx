import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { TutorPanelView } from "@/components/tutor-panel";
import type { TutorConversationResponse, TutorRunResponse, TutorStateResponse } from "@/lib/types";

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
const conversation: TutorConversationResponse = {
  chapters: [
    {
      id: "chapter-old",
      sequence: 1,
      mode: "commander",
      teaching_hash: "old-hash",
      composition_hash: "old-composition",
      manifest: { description: "Old counter plan", bracket: 3 },
      current: false,
      handoff: null,
      handoff_status: "none",
      handoff_error: null,
      created_at: "2026-11-01T00:00:00Z",
      turns: [
        {
          id: "turn-old",
          question: "Original full question",
          answer: "Original full answer",
          card_name: "Forest",
          status: "succeeded",
          error: null,
          created_at: "2026-11-01T00:00:00Z",
          finished_at: "2026-11-01T00:01:00Z",
        },
      ],
    },
    {
      id: "chapter-current",
      sequence: 2,
      mode: "commander",
      teaching_hash: "current-hash",
      composition_hash: "current-composition",
      manifest: { description: "Current counter plan", bracket: 3 },
      current: true,
      handoff: "Recheck every old card claim.",
      handoff_status: "ready",
      handoff_error: null,
      created_at: "2026-11-02T00:00:00Z",
      turns: [
        {
          id: "turn-current",
          question: "What should I prioritize?",
          answer: "Develop the current engine first.",
          card_name: null,
          status: "succeeded",
          error: null,
          created_at: "2026-11-02T00:00:00Z",
          finished_at: "2026-11-02T00:01:00Z",
        },
      ],
    },
  ],
};

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
    expect(markup).toContain("Reference deck");
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

  it("labels keyboard-operable reference sources without a premature confirmation", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{ mode: "commander", latest_run: null, last_successful_run: null }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Use current deck as reference");
    expect(markup).toContain("Choose another owned deck");
    expect(markup).toContain("Paste an exported reference list");
    expect(markup).toContain("Reference source URL (optional metadata; never fetched)");
    expect(markup).toContain('aria-label="Reference deck controls"');
    expect(markup).not.toContain("Confirm reference replacement");
  });

  it("renders frozen provenance, quantities, differences, and explicit replacement controls", () => {
    const reference = {
      version: "reference-version-1",
      source: "current_deck" as const,
      source_deck_id: "deck-1",
      source_name: "Frozen learning list",
      source_url: "https://example.invalid/metadata",
      captured_at: "2026-11-02T03:04:05Z",
      commanders: [
        {
          oracle_id: "commander-oracle",
          name: "Hazel of the Rootbloom",
          quantity: 1,
          type_line: "Legendary Creature",
          oracle_text: "Commander text",
        },
      ],
      cards: [
        {
          oracle_id: "forest-oracle",
          name: "Forest",
          quantity: 7,
          type_line: "Basic Land",
          oracle_text: "{T}: Add {G}.",
        },
      ],
    };
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          reference,
          reference_differences: {
            missing: [
              {
                name: "Thassa's Oracle",
                oracle_id: "oracle-card",
                reference_quantity: 1,
                actual_quantity: 0,
              },
            ],
            added: [],
          },
        }}
        referencePreview={{
          preview_id: "preview-1",
          reference,
          differences: {
            missing: [],
            added: [
              {
                name: "Sol Ring",
                oracle_id: "sol-ring",
                reference_quantity: 0,
                actual_quantity: 1,
              },
            ],
          },
        }}
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
        onReferencePreview={vi.fn()}
        onReferenceConfirm={vi.fn()}
        onReferenceCancel={vi.fn()}
        onReferenceRemove={vi.fn()}
      />,
    );

    expect(markup).toContain("Frozen learning list");
    expect(markup).toContain('dateTime="2026-11-02T03:04:05Z"');
    expect(markup).toContain("7 × Forest");
    expect(markup).toContain("Thassa&#x27;s Oracle: reference 1, current 0");
    expect(markup).toContain("Sol Ring: reference 0, current 1");
    expect(markup).toContain("Confirm reference replacement");
    expect(markup).toContain("Cancel reference replacement");
    expect(markup).toContain("Remove reference");
    expect(markup).not.toContain('href="https://example.invalid/metadata"');
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

  it("renders current-list chat, actual card choices, handoff, and clear controls", () => {
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={{
          ...saved,
          current_cards: [
            {
              oracle_id: "forest-oracle",
              name: "Forest",
              quantity: 7,
              type_line: "Basic Land",
              oracle_text: "{T}: Add {G}.",
            },
          ],
        }}
        conversation={conversation}
        question="Explain its purpose and limitations"
        selectedCard="Forest"
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
        onQuestionChange={vi.fn()}
        onCardChange={vi.fn()}
        onAsk={vi.fn()}
        onClearConversation={vi.fn()}
      />,
    );

    expect(markup).toContain("Ask about the current deck");
    expect(markup).toContain('aria-label="Card to explain"');
    expect(markup).toContain("7 × Forest");
    expect(markup).toContain("What should I prioritize?");
    expect(markup).toContain("Develop the current engine first.");
    expect(markup).toContain("Recheck every old card claim.");
    expect(markup).toContain("Current deck chapter");
    expect(markup).toContain("Clear tutor history");
    expect(markup).toContain("Enter to send");
    expect(markup).not.toContain("Mulligan Practice");
  });

  it("shows a selected archive read-only and preserves failed answer text and retry status", () => {
    const failed: TutorConversationResponse = {
      chapters: [
        {
          ...conversation.chapters[0]!,
          turns: [
            {
              ...conversation.chapters[0]!.turns[0]!,
              answer: null,
              status: "failed",
              error: "Tutor answer failed; retry explicitly.",
            },
          ],
        },
      ],
    };
    const markup = renderToStaticMarkup(
      <TutorPanelView
        state={saved}
        conversation={failed}
        selectedChapterId="chapter-old"
        question="Original full question"
        busy={false}
        error={null}
        onMode={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(markup).toContain("Archived chapter 1");
    expect(markup).toContain("read-only");
    expect(markup).toContain("Original full question");
    expect(markup).toContain("Tutor answer failed; retry explicitly.");
    expect(markup).toMatch(/<textarea[^>]*>Original full question<\/textarea>/);
    expect(markup).toContain("Cancel clear tutor history");
  });
});
