import { describe, expect, it } from "vitest";

import { buildCoachHistory } from "./coach-conversation";

describe("buildCoachHistory", () => {
  it("preserves completed role-aware turns without transcript markers", () => {
    const history = buildCoachHistory([
      { role: "user", content: "Keep this Food-first." },
      { role: "assistant", content: "I will prioritize Food engines." },
    ]);

    expect(history).toEqual([
      { role: "user", content: "Keep this Food-first." },
      { role: "assistant", content: "I will prioritize Food engines." },
    ]);
    expect(JSON.stringify(history)).not.toContain("User:");
    expect(JSON.stringify(history)).not.toContain("Assistant:");
  });

  it("keeps at most twelve turns", () => {
    const turns = Array.from({ length: 14 }, (_, index) => ({
      role: index % 2 === 0 ? ("user" as const) : ("assistant" as const),
      content: `turn-${index}`,
    }));

    const history = buildCoachHistory(turns);

    expect(history).toHaveLength(12);
    expect(history[0]?.content).toBe("turn-2");
  });

  it("removes oldest complete pairs to stay within the character budget", () => {
    const turns = Array.from({ length: 12 }, (_, index) => ({
      role: index % 2 === 0 ? ("user" as const) : ("assistant" as const),
      content: `turn-${index}-`.padEnd(2010, "x"),
    }));

    const history = buildCoachHistory(turns);

    expect(history[0]?.role).toBe("user");
    expect(history.at(-1)?.content).toContain("turn-11");
    expect(history.reduce((total, turn) => total + turn.content.length, 0)).toBeLessThanOrEqual(
      12_000,
    );
  });

  it("keeps the newest user turn when role order is irregular", () => {
    const history = buildCoachHistory([
      { role: "user", content: "old-".padEnd(4000, "x") },
      { role: "user", content: "middle-".padEnd(4000, "x") },
      { role: "assistant", content: "answer-".padEnd(4000, "x") },
      { role: "user", content: "newest-user" },
    ]);

    expect(history).toHaveLength(3);
    expect(history[0]?.content).toContain("middle");
    expect(history.at(-1)?.content).toBe("newest-user");
  });
});
