import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CardExportDialog, ExportPreview } from "@/components/card-export-dialog";
import type { CardExportPreview } from "@/lib/types";

const preview: CardExportPreview = {
  rows: [
    {
      card_id: "forest",
      name: "Forest",
      needed_quantity: 5,
      available_quantity: 2,
      export_quantity: 3,
      price_eur_cents: null,
      pulls: [{ id: "binder", name: "Real cards", quantity: 2 }],
    },
  ],
  needed_quantity: 5,
  from_binders_quantity: 2,
  export_quantity: 3,
  known_price_eur_cents: 0,
  unpriced_quantity: 3,
  text: "3 Forest",
};

describe("card exports", () => {
  it("shows exact quantities, pull allocations and missing prices", () => {
    const html = renderToStaticMarkup(<ExportPreview preview={preview} />);
    expect(html).toContain("5 copies needed · 2 from binders · 3 to export");
    expect(html).toContain("Pull: 2 from Real cards");
    expect(html).toContain("3 copies without EUR prices");
    expect(html).toContain("3 Forest");
    expect(html).toContain("Available");
  });

  it("explains an empty result rather than generating an empty file", () => {
    const html = renderToStaticMarkup(
      <ExportPreview preview={{ ...preview, text: "", export_quantity: 0 }} />,
    );
    expect(html).toContain("Nothing to export");
    expect(html).not.toContain("textarea");
  });

  it("provides both text formats and disables actions until the preview is ready", () => {
    const html = renderToStaticMarkup(
      <CardExportDialog title="Export additions" cards={[]} onClose={() => undefined} />,
    );
    expect(html).toContain("MTGO text (.txt)");
    expect(html).toContain("Cardmarket buy list (.txt)");
    expect(html).toContain("None selected = full quantities");
    expect(html).toMatch(/<button[^>]+disabled=""[^>]*>Copy list/);
    expect(html).toContain("Download .txt");
  });
});
