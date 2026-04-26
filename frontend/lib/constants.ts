export const STAGES = [
  "ramp",
  "interaction",
  "draw",
  "theme",
  "utility",
  "lands",
  "complete",
] as const;

export type Stage = (typeof STAGES)[number];

export const STAGE_LABELS: Record<string, string> = {
  bangers: "Bangers",
  ramp: "Ramp",
  interaction: "Interaction",
  draw: "Card Draw",
  theme: "Theme",
  utility: "Utility",
  lands: "Lands",
  complete: "Complete",
};

export const BRACKET_LABELS: Record<number, string> = {
  1: "Bracket 1 — Casual",
  2: "Bracket 2 — Upgraded",
  3: "Bracket 3 — Optimized",
  4: "Bracket 4 — cEDH",
};

export const CATEGORY_TARGETS: Record<string, [number, number]> = {
  bangers: [10, 15],
  ramp: [10, 12],
  interaction: [8, 10],
  draw: [8, 10],
  theme: [20, 25],
  utility: [5, 8],
  lands: [35, 38],
};

export const STAGE_DEFAULTS: Record<string, number> = {
  bangers: 10,
  ramp: 10,
  interaction: 9,
  draw: 9,
  theme: 22,
  utility: 6,
  lands: 36,
};

export const CATEGORY_ORDER = ["bangers", "ramp", "interaction", "draw", "theme", "utility", "lands"];

export const COLOR_SYMBOLS: Record<string, { label: string; bg: string; text: string }> = {
  W: { label: "W", bg: "bg-yellow-50", text: "text-yellow-800" },
  U: { label: "U", bg: "bg-blue-100", text: "text-blue-800" },
  B: { label: "B", bg: "bg-gray-800", text: "text-gray-100" },
  R: { label: "R", bg: "bg-red-100", text: "text-red-800" },
  G: { label: "G", bg: "bg-green-100", text: "text-green-800" },
  C: { label: "C", bg: "bg-gray-200", text: "text-gray-800" },
};
