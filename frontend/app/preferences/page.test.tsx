import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import PreferencesPage from "@/app/preferences/page";

it("renders the Preferences empty state without personalization controls", () => {
  const html = renderToStaticMarkup(<PreferencesPage />);

  expect(html).toContain("Preferences");
  expect(html).toContain("Nothing in here yet.");
  expect(html).toContain("Profile settings may come in the future.");
  expect(html).not.toContain("Ranking Weights");
  expect(html).not.toContain("Feedback Boosting");
  expect(html).not.toContain("Suggestion Mix");
});
