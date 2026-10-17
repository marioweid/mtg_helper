import { expect, it } from "vitest";

import { apiClient } from "@/lib/api";

it("does not expose persistent Assistant-memory client requests", () => {
  expect(apiClient).not.toHaveProperty("getCoachMemory");
  expect(apiClient).not.toHaveProperty("updateCoachMemory");
});
