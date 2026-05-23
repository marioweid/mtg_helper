import type { DeckCardItem } from "@/lib/types";

/**
 * WotC Commander Bracket "Game Changers" list. Mirrors
 * ``backend/src/mtg_helper/services/bracket_service.py``. Keep in sync.
 */
export const GAME_CHANGERS: ReadonlySet<string> = new Set([
  "Ancient Tomb",
  "Bolas's Citadel",
  "Chrome Mox",
  "Coalition Victory",
  "Cyclonic Rift",
  "Demonic Tutor",
  "Dockside Extortionist",
  "Drannith Magistrate",
  "Enlightened Tutor",
  "Field of the Dead",
  "Gaea's Cradle",
  "Glacial Chasm",
  "Grim Monolith",
  "Imperial Seal",
  "Jeweled Lotus",
  "Kinnan, Bonder Prodigy",
  "Lion's Eye Diamond",
  "Mana Crypt",
  "Mana Vault",
  "Mox Diamond",
  "Mox Opal",
  "Mystical Tutor",
  "Opposition Agent",
  "Ragavan, Nimble Pilferer",
  "Rhystic Study",
  "Serra's Sanctum",
  "Smothering Tithe",
  "Tergrid, God of Fright",
  "Thassa's Oracle",
  "The One Ring",
  "The Tabernacle at Pendrell Vale",
  "Trouble in Pairs",
  "Underworld Breach",
  "Vampiric Tutor",
  "Winota, Joiner of Forces",
  "Yuriko, the Tiger's Shadow",
]);

const LOWER_GAME_CHANGERS: ReadonlySet<string> = new Set(
  [...GAME_CHANGERS].map((n) => n.toLowerCase()),
);

export function isGameChanger(name: string | null | undefined): boolean {
  if (!name) return false;
  return LOWER_GAME_CHANGERS.has(name.toLowerCase());
}

/** Names from ``cards`` (and optional commander) that are Game Changers, sorted. */
export function findGameChangers(
  cards: readonly DeckCardItem[],
  commanderName?: string | null,
): string[] {
  const matches = new Set<string>();
  for (const c of cards) {
    if (isGameChanger(c.name)) matches.add(c.name);
  }
  if (commanderName && isGameChanger(commanderName)) matches.add(commanderName);
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
