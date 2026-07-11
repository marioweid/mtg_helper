import { describe, expect, it } from "vitest";

import { resolveSelectedGroup } from "./theme-manager";

const groups = [
  { id: 1, deleted_at: null },
  { id: 2, deleted_at: null },
];

describe("resolveSelectedGroup", () => {
  it("selects the first active group on initial load", () => {
    expect(resolveSelectedGroup(undefined, groups)).toBe(1);
  });

  it("preserves an intentional Ungrouped selection", () => {
    expect(resolveSelectedGroup(null, groups)).toBeNull();
  });

  it("preserves an existing numeric selection", () => {
    expect(resolveSelectedGroup(2, groups)).toBe(2);
  });

  it("falls back to Ungrouped when the selected group disappears", () => {
    expect(resolveSelectedGroup(3, groups)).toBeNull();
  });
});
