import type { CommanderCoachProgressEvent } from "./types";

const PROGRESS_MESSAGES: Record<string, string> = {
  assistant_thinking: "Looking over the deck…",
  assistant_grounding: "Checking a few card options…",
};

export function coachProgressMessage(event: CommanderCoachProgressEvent): string | null {
  return PROGRESS_MESSAGES[event.event] ?? null;
}
