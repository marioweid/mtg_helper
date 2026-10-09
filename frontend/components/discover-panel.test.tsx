import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { DiscoverPanel } from "@/components/discover-panel";

it("labels commander-only uncertainty, free browsing and explicit bounded Generate", () => {
  const html = renderToStaticMarkup(<DiscoverPanel deckId="deck" onPlanChanged={() => {}} />);
  expect(html).toContain("Discover · Experimental");
  expect(html).toContain("AI advice is unverified");
  expect(html).toContain("physical deck&#x27;s balance");
  expect(html).toContain("Browse source cards");
  expect(html).toContain("Generate · up to $0.10");
  expect(html).toContain("Plan &amp; Searches");
  expect(html).toContain("Local matches · not fit recommendations");
});
