import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { StrategyResult } from "@/components/commander-strategy-panel";
import { DiscoverPanel } from "@/components/discover-panel";
import type { DiscoverRun } from "@/lib/discovery-types";

const draft: DiscoverRun = {
  id: "draft",
  status: "completed",
  phase: "done",
  goal: "Draft commander strategy",
  created_at: "2026-10-09",
  source_hash: "source",
  rules_hash: "rules",
  profile: "app-strategy-v1",
  error: null,
  stale: false,
  candidates: [],
  known_cost_microusd: 145,
  held_microusd: 0,
  strategy: {
    goal: "Proposed direction",
    explanation: "Printed ability",
    uncertainties: ["Uncertain"],
  },
};

it("offers a priced draft before an editable goal without automatic deck changes", () => {
  const html = renderToStaticMarkup(<DiscoverPanel deckId="deck" onPlanChanged={() => {}} />);
  expect(html).toContain("What does this commander want to do?");
  expect(html).toContain("Draft commander strategy · up to $0.01");
  expect(html).toContain("Commander-only goal (editable)");
  expect(html).toContain("not changed automatically");
  expect(html).toContain("one separate paid Luna request");
  expect(html).toContain("AI draft · unverified");
});

it("shows the proposed direction, explanation, uncertainty and explicit copy action", () => {
  const html = renderToStaticMarkup(
    <StrategyResult run={draft} busy={false} onUse={() => {}} onInspect={() => {}} />,
  );
  expect(html).toContain("Proposed direction");
  expect(html).toContain("Printed ability");
  expect(html).toContain("Uncertain");
  expect(html).toContain("Inspect strategy trace");
  expect(html).toMatch(/<button[^>]*>Use as goal/);
  expect(html).not.toMatch(/disabled=""[^>]*>Use as goal/);
});

it.each([
  { stale: true },
  { status: "running" as const },
  { status: "unknown" as const, error: "Unknown billing; no further requests" },
  { strategy: null },
])("does not offer usable advice from unavailable drafts: %j", (patch) => {
  const html = renderToStaticMarkup(
    <StrategyResult
      run={{ ...draft, ...patch }}
      busy={false}
      onUse={() => {}}
      onInspect={() => {}}
    />,
  );
  expect(html).toMatch(/disabled=""[^>]*>Use as goal/);
  if (patch.error) expect(html).toContain('role="alert"');
});
