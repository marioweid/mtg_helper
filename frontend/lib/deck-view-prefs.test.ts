import { afterEach, describe, expect, it, vi } from "vitest";

import { getWorkspaceView, setWorkspaceView } from "./deck-view-prefs";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("card workspace preferences", () => {
  it("persists valid grid and list choices by scope", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
      },
    });

    setWorkspaceView("collection:one", "list");

    expect(getWorkspaceView("collection:one")).toBe("list");
    expect(getWorkspaceView("collection:two")).toBeNull();
  });

  it("ignores stale preference values", () => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => "visual-stacks",
        setItem: () => undefined,
      },
    });

    expect(getWorkspaceView("deck:one")).toBeNull();
  });
});
