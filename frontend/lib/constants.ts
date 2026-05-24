import { MECHANIC_LABELS } from "./mechanics";

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
  1: "Bracket 1 — Exhibition",
  2: "Bracket 2 — Core",
  3: "Bracket 3 — Upgraded",
  4: "Bracket 4 — Optimized",
  5: "Bracket 5 — cEDH",
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

/**
 * Curated Moxfield-style archetype keywords grouped by theme. Tag values must
 * match the canonical vocabulary emitted by ``tag_service.classify_card`` so
 * the backend's GIN tag search hits.
 */
export interface ArchetypeChip {
  tag: string;
  label: string;
}

export const ARCHETYPE_GROUPS: { group: string; chips: ArchetypeChip[] }[] = [
  {
    group: "Tokens & Aristocrats",
    chips: [
      { tag: "token", label: "Tokens" },
      { tag: "aristocrats", label: "Aristocrats" },
      { tag: "sacrifice", label: "Sacrifice" },
      { tag: "treasure_matters", label: "Treasure matters" },
      { tag: "food_matters", label: "Food matters" },
      { tag: "clue_matters", label: "Clue matters" },
    ],
  },
  {
    group: "Counters & Anthems",
    chips: [
      { tag: "plus_one_counters", label: "+1/+1 counters" },
      { tag: "proliferate", label: "Proliferate" },
      { tag: "anthem", label: "Anthems" },
      { tag: "infect_toxic", label: "Infect / Toxic" },
    ],
  },
  {
    group: "Voltron & Equipment",
    chips: [
      { tag: "voltron", label: "Voltron" },
      { tag: "equipment", label: "Equipment" },
    ],
  },
  {
    group: "Graveyard",
    chips: [
      { tag: "graveyard", label: "Graveyard / Recursion" },
      { tag: "reanimator", label: "Reanimator" },
      { tag: "mill", label: "Mill" },
    ],
  },
  {
    group: "Lands & Ramp",
    chips: [
      { tag: "landfall", label: "Landfall" },
      { tag: "fast_mana", label: "Fast mana" },
      { tag: "land_destruction", label: "Land destruction" },
    ],
  },
  {
    group: "Spells",
    chips: [
      { tag: "spellslinger", label: "Spellslinger" },
      { tag: "storm", label: "Storm" },
      { tag: "cascade", label: "Cascade" },
      { tag: "wheels", label: "Wheels" },
    ],
  },
  {
    group: "Lifegain & Blink",
    chips: [
      { tag: "lifegain", label: "Lifegain" },
      { tag: "blink", label: "Blink / Flicker" },
      { tag: "energy", label: "Energy" },
    ],
  },
  {
    group: "Control & Stax",
    chips: [
      { tag: "stax", label: "Stax" },
      { tag: "group_hug", label: "Group Hug" },
      { tag: "extra_turn", label: "Extra turns" },
    ],
  },
];

/** Flat list of archetype tag strings — used for membership checks. */
export const ARCHETYPE_TAGS: string[] = ARCHETYPE_GROUPS.flatMap((g) =>
  g.chips.map((c) => c.tag),
);

/** Map a canonical tag back to its display label (falls back to the tag itself). */
export const ARCHETYPE_LABELS: Record<string, string> = Object.fromEntries(
  ARCHETYPE_GROUPS.flatMap((g) => g.chips.map((c) => [c.tag, c.label])),
);

/** Pretty-print a tag chip — handles tribal tags too (e.g. ``squirrel_tribal``). */
export function archetypeLabel(tag: string): string {
  if (ARCHETYPE_LABELS[tag]) return ARCHETYPE_LABELS[tag];
  // Fall back to the mechanic catalog so chips from the "All mechanics"
  // section render with the same pretty label.
  if (MECHANIC_LABELS[tag]) return MECHANIC_LABELS[tag];
  if (tag.endsWith("_tribal")) {
    const sub = tag.slice(0, -"_tribal".length).replace(/_/g, " ");
    return `${sub.charAt(0).toUpperCase()}${sub.slice(1)} tribal`;
  }
  return tag.replace(/_/g, " ");
}
