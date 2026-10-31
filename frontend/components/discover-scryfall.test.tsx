import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DiscoverView } from "@/components/discover-panel";
import { DiscoverController, type DiscoverState } from "@/components/discover-state";

function view(patch: Partial<DiscoverState> = {}) {
  const controller = new DiscoverController("deck", () => undefined);
  return renderToStaticMarkup(
    <DiscoverView
      state={{ ...controller.getSnapshot(), loading: false, ...patch }}
      controller={controller}
    />,
  );
}

describe("Strategy-first Discover view", () => {
  it("shows complete strategy choices, not title-only buttons or a setup toolbar", () => {
    const html = view({
      draft: {
        id: "draft",
        status: "completed",
        phase: "plan",
        goal: "",
        created_at: "now",
        source_hash: "source",
        rules_hash: "rules",
        profile: "app-strategy-v2",
        error: null,
        stale: false,
        candidates: [],
        known_cost_microusd: 0,
        held_microusd: 0,
        strategies: [
          {
            title: "Counter engine",
            pace: "Measured",
            early_game: "Develop early mana",
            engine: "Transfer creature counters",
            payoff: "Attack with large creatures",
            goal: "Plan",
            explanation: "Use your commander to keep counters moving",
            uncertainties: ["Not rules verified"],
          },
        ],
      },
    });
    for (const text of [
      "Counter engine",
      "Measured",
      "Develop early mana",
      "Transfer creature counters",
      "Attack with large creatures",
      "Use your commander",
      "Not rules verified",
      "Find cards",
    ])
      expect(html).toContain(text);
    for (const text of [
      "Save strategy",
      "Draft strategy with AI",
      "Suggest source terms",
      "Refresh draft status",
      "Search Oracle-Tags",
    ])
      expect(html).not.toContain(text);
    expect(html).toContain('type="radio"');
  });
  it("renders the entire active strategy as readable content and keeps tags collapsed", () => {
    const prose =
      "Counter Transfer Value\nFirst establish mana, then develop the engine.\nClose with creature pressure.";
    const html = view({
      editing: false,
      prose,
      status: {
        status: "ready",
        source: { status: "ready", card_updated_at: null, tag_updated_at: null, warning: null },
        strategy: {
          prose,
          queries: [
            {
              purpose: "Counters",
              groups: [{ oracle_tag_ids: ["tag"], printed_keywords: [] }],
              card_types_any: ["Creature"],
            },
          ],
          revision: "rev",
          updated_at: "now",
          needs_review: false,
        },
        cards: [],
        total: 0,
        next_cursor: null,
      },
    });
    expect(html).toContain(prose);
    expect(html).toContain("Your strategy");
    expect(html).toContain("Change strategy");
    expect(html).toContain("Advanced search details");
    expect(html).not.toContain("textarea");
    expect(html).not.toContain("Search Oracle-Tags");
  });
});

describe("Optional search details and feedback", () => {
  it("shows source filter grouping and front-face scope without claiming synergy", () => {
    const html = view({
      advanced: true,
      queries: [
        {
          purpose: "Creature support",
          groups: [
            { oracle_tag_ids: [], printed_keywords: ["Flying"] },
            { oracle_tag_ids: [], printed_keywords: ["Vigilance"] },
          ],
          card_types_any: ["Creature"],
        },
      ],
    });
    expect(html).toContain("Creature support");
    expect(html).toContain("AND Vigilance");
    expect(html).toContain("Front-face type");
    expect(html).toContain("override automatic");
  });
  it("mounts at most twenty tag suggestions instead of the full catalog", () => {
    const html = view({
      advanced: true,
      terms: {
        oracle_tags: Array.from({ length: 5000 }, (_, i) => ({
          id: `${i}`,
          slug: `fixture-${i}`,
          label: `Fixture ${i}`,
        })),
        printed_keywords: [],
      },
    });
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(20);
    expect(html).toContain("Refine your search");
    expect(html).not.toContain("Fixture 4999");
  });
  it("keeps undo visible when dismissing the last result", () => {
    const html = view({
      dismissedOracleId: "card",
      matches: {
        status: "ready",
        source: { status: "ready", card_updated_at: null, tag_updated_at: null, warning: null },
        strategy: null,
        cards: [],
        total: 0,
        next_cursor: null,
      },
    });
    expect(html).toContain("Undo dismissal");
    expect(html).toContain("No matching cards");
  });
  it("announces progress without requiring a manual refresh", () => {
    const html = view({ busy: true, progress: "Finding search terms for your strategy…" });
    expect(html).toContain('role="status"');
    expect(html).toContain("Finding search terms");
    expect(html).not.toContain("Refresh term suggestion");
  });
});
