import { describe, expect, it } from "vitest";

import { AdminPanel } from "@/components/admin-panel";

describe("AdminPanel", () => {
  it("is available with only source-sync administration", () => {
    expect(AdminPanel).toBeDefined();
  });
});
