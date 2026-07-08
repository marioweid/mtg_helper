export const STAGES = [
  "theme",
  "ramp",
  "draw",
  "interaction",
  "lands",
  "complete",
] as const;

export type Stage = (typeof STAGES)[number];

export const STAGE_LABELS: Record<string, string> = {
  theme: "Theme",
  ramp: "Ramp",
  draw: "Card Draw",
  interaction: "Interaction",
  lands: "Lands",
  complete: "Complete",
};

export const BRACKET_LABELS: Record<number, string> = {
  1: "Bracket 1 - Exhibition",
  2: "Bracket 2 - Core",
  3: "Bracket 3 - Upgraded",
  4: "Bracket 4 - Optimized",
  5: "Bracket 5 - cEDH",
};

export const CATEGORY_TARGETS: Record<string, [number, number]> = {
  ramp: [12, 12],
  draw: [12, 12],
  interaction: [12, 12],
  lands: [38, 38],
};

export const STAGE_DEFAULTS: Record<string, number> = {
  ramp: 12,
  draw: 12,
  interaction: 12,
  lands: 38,
};

export const CATEGORY_ORDER = ["theme", "ramp", "draw", "interaction", "lands"];

export const COLOR_SYMBOLS: Record<string, { label: string; bg: string; text: string }> = {
  W: { label: "W", bg: "bg-yellow-50", text: "text-yellow-800" },
  U: { label: "U", bg: "bg-blue-100", text: "text-blue-800" },
  B: { label: "B", bg: "bg-gray-800", text: "text-gray-100" },
  R: { label: "R", bg: "bg-red-100", text: "text-red-800" },
  G: { label: "G", bg: "bg-green-100", text: "text-green-800" },
  C: { label: "C", bg: "bg-gray-200", text: "text-gray-800" },
};

export function archetypeLabel(tag: string): string {
  const label = tag.replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
