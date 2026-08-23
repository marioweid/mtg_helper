import type { CoachHistoryTurn } from "./types";

const MAX_HISTORY_TURNS = 12;
const MAX_HISTORY_CHARACTERS = 12_000;

export interface VisibleCoachTurn {
  role: "user" | "assistant";
  content: string;
}

export function buildCoachHistory(turns: VisibleCoachTurn[]): CoachHistoryTurn[] {
  let history = turns
    .filter((turn) => turn.content.trim().length > 0)
    .slice(-MAX_HISTORY_TURNS)
    .map((turn) => ({ role: turn.role, content: turn.content }));

  while (history.length > 0 && characterCount(history) > MAX_HISTORY_CHARACTERS) {
    history = history.slice(1);
  }
  while (history[0]?.role === "assistant") history = history.slice(1);
  return history;
}

function characterCount(turns: CoachHistoryTurn[]): number {
  return turns.reduce((total, turn) => total + turn.content.length, 0);
}
