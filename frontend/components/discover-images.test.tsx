import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { DiscoverResults } from "@/components/discover-panel";
import { DiscoverController } from "@/components/discover-state";
import type { DiscoverCandidate, DiscoverRun, DiscoverStatus } from "@/lib/discovery-types";

const candidate: DiscoverCandidate = {
  oracle_id: "card",
  image_uri: "https://cards.scryfall.io/normal/front/a/b/card.jpg",
  facts: {
    oracle_id: "card",
    name: "Example card",
    mana_cost: "{G}",
    mana_value: 1,
    type_line: "Creature",
    oracle_text: "Source text stays available.",
    keywords: [],
    layout: "normal",
    faces: [],
  },
  state: "assessed",
  assessment: { fit: "support", reason: "AI reason", caveat: "AI caveat", evidence: [] },
  evidence_errors: [],
  recommended: true,
  excluded: false,
};
const run: DiscoverRun = {
  id: "run",
  status: "completed",
  phase: "done",
  goal: "Goal",
  created_at: "date",
  source_hash: "source",
  rules_hash: "rules",
  profile: "app-pilot-v1",
  error: null,
  stale: false,
  candidates: [candidate],
  known_cost_microusd: 0,
  held_microusd: 0,
};
const status: DiscoverStatus = {
  ready: true,
  reason: null,
  source_hash: "source",
  rules_hash: "rules",
  catalog_updated_at: null,
  goal_seed: "",
  run,
  run_cap_microusd: 100000,
  daily_cap_microusd: 1000000,
  reserved_microusd: 67750,
  maximum_calls: 3,
};

function render(card: DiscoverCandidate) {
  const controller = new DiscoverController("deck", () => {});
  return renderToStaticMarkup(
    <DiscoverResults
      controller={controller}
      state={{
        ...controller.getSnapshot(),
        status: { ...status, run: { ...run, candidates: [card] } },
        page: {
          snapshot_hash: "source",
          rules_hash: "rules",
          total: 1,
          next_cursor: null,
          cards: [card],
        },
      }}
    />,
  );
}

it("uses the shared image grid for both recommendations and free source matches", () => {
  const html = render(candidate);
  expect(html.match(/src="https:\/\/cards.scryfall.io/g)).toHaveLength(2);
  expect(html.match(/alt="Example card"/g)).toHaveLength(2);
  expect(html.match(/loading="lazy"/g)).toHaveLength(2);
  expect(html).toContain("Authoritative source facts");
  expect(html).toContain("Source text stays available");
  expect(html).toContain("AI advice: AI reason");
  expect(html).toContain("Plan recommendation");
  expect(html).toContain("Manual source addition");
  expect(html).toContain("current catalog printing");
});

it("keeps readable cards and guarded actions when images are missing or cards excluded", () => {
  const html = render({ ...candidate, image_uri: null, excluded: true });
  expect(html).not.toContain("<img");
  expect(html).toContain("Example card");
  expect(html).toMatch(/disabled=""[^>]*>Plan recommendation/);
  expect(html).toMatch(/disabled=""[^>]*>Manual source addition/);
  expect(html).toContain("Already physical/planned");
});
