import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { StrategyResult } from "@/components/commander-strategy-panel";
import { DiscoverPanel } from "@/components/discover-panel";
import type { CommanderStrategyChoice, DiscoverRun } from "@/lib/discovery-types";

const choice: CommanderStrategyChoice = {
  title: "Quick setup",
  pace: "Fast start",
  early_game: "Ramp before the commander",
  engine: "Develop the printed ability engine",
  payoff: "Value into pressure; finish remains open",
  goal: "Full editable plan",
  explanation: "Printed ability",
  uncertainties: ["Uncertain"],
};
const draft: DiscoverRun = {
  id: "draft",
  status: "completed",
  phase: "done",
  goal: "Draft commander strategy",
  created_at: "2026-10-09",
  source_hash: "source",
  rules_hash: "rules",
  profile: "app-strategy-v2",
  error: null,
  stale: false,
  candidates: [],
  known_cost_microusd: 145,
  held_microusd: 0,
  strategies: [
    choice,
    { ...choice, title: "Steady engine" },
    { ...choice, title: "Patient setup" },
  ],
};

it("offers three directions in one priced request, before an editable goal", () => {
  const html = renderToStaticMarkup(<DiscoverPanel deckId="deck" onPlanChanged={() => {}} />);
  expect(html).toContain("What does this commander want to do?");
  expect(html).toContain("Draft 3 commander strategies · up to $0.01");
  expect(html).toContain("Commander-only goal (editable)");
  expect(html).toContain("not changed automatically");
  expect(html).toContain("one separate paid");
  expect(html).toContain("AI drafts · unverified");
  expect(html).toContain("need not be a complete win condition");
});

it("shows each phase and an individually named copy action for every choice", () => {
  const html = renderToStaticMarkup(
    <StrategyResult run={draft} busy={false} onUse={() => {}} onInspect={() => {}} />,
  );
  for (const text of [
    "Quick setup",
    "Steady engine",
    "Patient setup",
    "Early setup / ramp",
    "Main engine",
    "Payoff / closing direction",
    "Printed ability",
    "Uncertain",
    "Inspect strategy trace",
  ]) {
    expect(html).toContain(text);
  }
  expect(html.match(/>Use as goal/g)).toHaveLength(3);
  expect(html).toContain('aria-label="Use Quick setup as goal"');
  expect(html).not.toMatch(/disabled=""[^>]*>Use as goal/);
});

it.each([
  { stale: true },
  { status: "running" as const },
  { status: "unknown" as const, error: "Unknown billing; no further requests" },
  { profile: "app-strategy-v1" },
])("does not offer usable advice from unavailable drafts: %j", (patch) => {
  const html = renderToStaticMarkup(
    <StrategyResult
      run={{ ...draft, ...patch }}
      busy={false}
      onUse={() => {}}
      onInspect={() => {}}
    />,
  );
  expect(html.match(/disabled=""[^>]*>Use as goal/g)).toHaveLength(3);
  if (patch.error) expect(html).toContain('role="alert"');
});

it("keeps trace inspection without pretending archived or empty drafts have choices", () => {
  const html = renderToStaticMarkup(
    <StrategyResult
      run={{ ...draft, strategies: [], stale: true }}
      busy={false}
      onUse={() => {}}
      onInspect={() => {}}
    />,
  );
  expect(html).toContain("No selectable strategies available yet");
  expect(html).toContain("Original evidence");
  expect(html).toContain("Inspect strategy trace");
  expect(html).not.toContain(">Use as goal");
});
