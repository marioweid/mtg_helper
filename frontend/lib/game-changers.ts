import type { DeckCardItem } from "@/lib/types";

/**
 * Names of Game Changer cards in ``cards`` (and optional commander), sorted.
 * Authoritative source is the per-card ``game_changer`` flag synced from
 * Scryfall, so this stays current automatically.
 */
export function findGameChangers(
  cards: readonly DeckCardItem[],
  commander?: { name: string; game_changer: boolean } | null,
): string[] {
  const matches = new Set<string>();
  for (const c of cards) {
    if (c.game_changer) matches.add(c.name);
  }
  if (commander?.game_changer) matches.add(commander.name);
  return [...matches].sort((a, b) => a.localeCompare(b));
}

/**
 * Allowed Game Changer count per bracket. ``null`` means unlimited (bracket 4).
 * Brackets 1 and 2 disallow all; bracket 3 caps at 3.
 */
export function gameChangerLimit(bracket: number | null | undefined): number | null {
  if (bracket == null) return null;
  if (bracket <= 2) return 0;
  if (bracket === 3) return 3;
  return null;
}
