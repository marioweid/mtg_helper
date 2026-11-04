import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TutorStateResponse } from "@/lib/types";

const lifecycle = vi.hoisted(() => ({
  effects: [] as (() => void | (() => void))[],
  state: [] as unknown[],
  stateIndex: 0,
}));
const api = vi.hoisted(() => ({ getTutor: vi.fn() }));

vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useCallback: (callback: () => unknown) => callback,
  useEffect: (effect: () => void | (() => void)) => lifecycle.effects.push(effect),
  useState: <T,>(initial: T) => {
    const index = lifecycle.stateIndex++;
    return [(lifecycle.state[index] ?? initial) as T, vi.fn()];
  },
}));
vi.mock("@/lib/api", () => ({ apiClient: api }));

import { TutorPanel } from "@/components/tutor-panel";

const running: TutorStateResponse = {
  mode: "commander",
  latest_run: {
    id: "run-1",
    status: "running",
    mode: "commander",
    current: true,
    guide: null,
    evidence: null,
    error: null,
    created_at: "2026-11-01T00:00:00Z",
    finished_at: null,
  },
  last_successful_run: null,
};

describe("Tutor panel polling", () => {
  const timers: (() => Promise<void>)[] = [];

  beforeEach(() => {
    lifecycle.effects = [];
    lifecycle.state = [running, false, null];
    lifecycle.stateIndex = 0;
    api.getTutor.mockReset();
    vi.stubGlobal("window", {
      clearTimeout: vi.fn(),
      setTimeout: (callback: () => Promise<void>) => {
        timers.push(callback);
        return timers.length;
      },
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("polls through repeated running states and stops when the run succeeds", async () => {
    api.getTutor.mockResolvedValueOnce(running).mockResolvedValueOnce({
      ...running,
      latest_run: { ...running.latest_run, status: "succeeded" },
    });
    renderToStaticMarkup(<TutorPanel deckId="deck-1" />);
    const stop = lifecycle.effects[1]?.();

    await timers.shift()?.();
    expect(timers).toHaveLength(1);
    await timers.shift()?.();
    expect(api.getTutor).toHaveBeenCalledTimes(2);
    expect(timers).toHaveLength(0);
    stop?.();
  });

  it("clears the scheduled poll on unmount", () => {
    renderToStaticMarkup(<TutorPanel deckId="deck-1" />);
    const stop = lifecycle.effects[1]?.();

    stop?.();
    expect(window.clearTimeout).toHaveBeenCalledTimes(1);
  });

  it("renders an initial load failure with an explicit retry", () => {
    lifecycle.state = [null, false, "Deck not found"];
    lifecycle.stateIndex = 0;

    const markup = renderToStaticMarkup(<TutorPanel deckId="deck-1" />);

    expect(markup).toContain("Deck not found");
    expect(markup).toContain("Retry Tutor");
    expect(markup).not.toContain("Loading Tutor");
  });
});
