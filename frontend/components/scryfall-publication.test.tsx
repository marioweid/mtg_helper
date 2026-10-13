import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { ScryfallPublication, type ScryfallSourceStatus } from "@/components/scryfall-publication";

const current: ScryfallSourceStatus = {
  status: "current",
  tag_count: 4577,
  membership_count: 236707,
  published_at: "2026-10-12T21:30:00Z",
  manifest: {
    oracle_cards: { updated_at: "2026-10-12T21:02:30Z" },
    oracle_tags: { updated_at: "2026-10-12T21:00:35Z" },
  },
};

it("reports both upstream receipt times and the last-good publication, not inferred freshness", () => {
  const html = renderToStaticMarkup(<ScryfallPublication source={current} />);
  expect(html).toContain("Matching card/tag generation");
  expect(html).toContain("4,577 tags");
  expect(html).toContain("236,707 direct memberships");
  expect(html).toContain("Card export updated");
  expect(html).toContain("Tag export updated");
  expect(html).toContain("Published locally");
  expect(html).toContain("Label-consumer replacement is not yet active");
});

it("does not present a missing generation as a successful empty catalog", () => {
  const html = renderToStaticMarkup(<ScryfallPublication source={{ status: "unavailable" }} />);
  expect(html).toContain("No complete Oracle-tag publication");
  expect(html).toContain("Sync Scryfall");
  expect(html).not.toContain("Matching card/tag generation");
});

it("warns when card and tag generations disagree", () => {
  const html = renderToStaticMarkup(
    <ScryfallPublication source={{ ...current, status: "mismatched" }} />,
  );
  expect(html).toContain('role="alert"');
  expect(html).toContain("Card/tag generation mismatch");
  expect(html).not.toContain("Matching card/tag generation");
});
