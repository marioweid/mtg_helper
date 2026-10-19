import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({ auth: async () => null, signOut: vi.fn() }));

import PreferencesPage from "@/app/preferences/page";
import { Nav } from "@/components/nav";

afterEach(() => vi.unstubAllGlobals());

it("keeps the Preferences link and empty state without settings or network requests", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const html = renderToStaticMarkup(<PreferencesPage />);
  const navigation = renderToStaticMarkup(await Nav());

  expect(navigation).toMatch(/href="\/preferences"[^>]*>Preferences<\/a>/);
  expect(html).toContain("Preferences");
  expect(html).toContain("Nothing in here yet.");
  expect(html).toContain("Profile settings may come in the future.");
  expect(html).not.toContain("Ranking Weights");
  expect(html).not.toContain("Feedback Boosting");
  expect(html).not.toContain("Suggestion Mix");
  expect(html).not.toMatch(/<(form|input|select|textarea|button)\b/i);
  expect(fetch).not.toHaveBeenCalled();
});
