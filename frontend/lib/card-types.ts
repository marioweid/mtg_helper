import type { DeckCardItem } from "@/lib/types";

export const PRIMARY_TYPES = [
  "Creatures",
  "Sorceries",
  "Instants",
  "Enchantments",
  "Battles",
  "Planeswalkers",
  "Artifacts",
  "Lands",
] as const;

export type PrimaryType = (typeof PRIMARY_TYPES)[number];

const OTHER: PrimaryType | "Other" = "Other";

export function primaryType(card: DeckCardItem): PrimaryType | "Other" {
  const tl = card.type_line ?? "";
  if (tl.includes("Land")) return "Lands";
  if (tl.includes("Creature")) return "Creatures";
  if (tl.includes("Planeswalker")) return "Planeswalkers";
  if (tl.includes("Battle")) return "Battles";
  if (tl.includes("Enchantment")) return "Enchantments";
  if (tl.includes("Artifact")) return "Artifacts";
  if (tl.includes("Sorcery")) return "Sorceries";
  if (tl.includes("Instant")) return "Instants";
  return OTHER;
}

export function groupByPrimaryType(
  cards: DeckCardItem[],
): Record<string, DeckCardItem[]> {
  const groups: Record<string, DeckCardItem[]> = {};
  for (const card of cards) {
    const t = primaryType(card);
    (groups[t] ??= []).push(card);
  }
  return groups;
}

export function sortedPrimaryTypes(
  groups: Record<string, DeckCardItem[]>,
): string[] {
  const ordered = PRIMARY_TYPES.filter((t) => groups[t]?.length);
  const extras = Object.keys(groups).filter(
    (t) => !PRIMARY_TYPES.includes(t as PrimaryType),
  );
  return [...ordered, ...extras];
}
