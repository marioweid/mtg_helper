/**
 * Full printed-mechanic catalog. Mirrors the backend
 * ``_FULL_MECHANIC_PATTERNS`` in ``tag_service.py``; both files must stay in
 * sync. Distinct from ``ARCHETYPE_GROUPS`` (deck-level archetypes); these
 * chips surface cards by printed keyword/mechanic name, exposed in the
 * collapsible "All mechanics" section of the chip picker.
 */

export interface MechanicChip {
  tag: string;
  label: string;
}

export interface MechanicGroup {
  group: string;
  chips: MechanicChip[];
}

export const MECHANIC_GROUPS: MechanicGroup[] = [
  {
    group: "Evergreen / combat keywords",
    chips: [
      { tag: "flying", label: "Flying" },
      { tag: "first_strike", label: "First strike" },
      { tag: "double_strike", label: "Double strike" },
      { tag: "deathtouch", label: "Deathtouch" },
      { tag: "hexproof", label: "Hexproof" },
      { tag: "indestructible", label: "Indestructible" },
      { tag: "lifelink", label: "Lifelink" },
      { tag: "menace", label: "Menace" },
      { tag: "reach", label: "Reach" },
      { tag: "trample", label: "Trample" },
      { tag: "vigilance", label: "Vigilance" },
      { tag: "ward", label: "Ward" },
      { tag: "defender", label: "Defender" },
      { tag: "flash", label: "Flash" },
      { tag: "haste", label: "Haste" },
      { tag: "shroud", label: "Shroud" },
    ],
  },
  {
    group: "Combat / pumping",
    chips: [
      { tag: "annihilator", label: "Annihilator" },
      { tag: "battle_cry", label: "Battle cry" },
      { tag: "exalted", label: "Exalted" },
      { tag: "frenzy", label: "Frenzy" },
      { tag: "rampage", label: "Rampage" },
      { tag: "soulbond", label: "Soulbond" },
      { tag: "undying", label: "Undying" },
      { tag: "persist", label: "Persist" },
      { tag: "mentor", label: "Mentor" },
      { tag: "renown", label: "Renown" },
      { tag: "training_kw", label: "Training" },
    ],
  },
  {
    group: "Graveyard / recursion",
    chips: [
      { tag: "dredge", label: "Dredge" },
      { tag: "scavenge", label: "Scavenge" },
      { tag: "unearth", label: "Unearth" },
      { tag: "embalm", label: "Embalm" },
      { tag: "eternalize", label: "Eternalize" },
      { tag: "encore", label: "Encore" },
      { tag: "threshold", label: "Threshold" },
      { tag: "delirium", label: "Delirium" },
      { tag: "morbid", label: "Morbid" },
      { tag: "flashback", label: "Flashback" },
      { tag: "escape", label: "Escape" },
      { tag: "jump_start", label: "Jump-start" },
      { tag: "disturb", label: "Disturb" },
      { tag: "madness", label: "Madness" },
      { tag: "retrace", label: "Retrace" },
    ],
  },
  {
    group: "Cost / cast mechanics",
    chips: [
      { tag: "cycling", label: "Cycling" },
      { tag: "buyback", label: "Buyback" },
      { tag: "kicker", label: "Kicker" },
      { tag: "suspend", label: "Suspend" },
      { tag: "convoke", label: "Convoke" },
      { tag: "delve", label: "Delve" },
      { tag: "improvise", label: "Improvise" },
      { tag: "affinity", label: "Affinity" },
      { tag: "rebound", label: "Rebound" },
      { tag: "miracle", label: "Miracle" },
      { tag: "foretell", label: "Foretell" },
      { tag: "overload", label: "Overload" },
      { tag: "splice", label: "Splice" },
      { tag: "transmute", label: "Transmute" },
      { tag: "prototype", label: "Prototype" },
      { tag: "casualty", label: "Casualty" },
      { tag: "mutate", label: "Mutate" },
      { tag: "emerge", label: "Emerge" },
      { tag: "bestow", label: "Bestow" },
      { tag: "awaken", label: "Awaken" },
      { tag: "spree", label: "Spree" },
      { tag: "disguise", label: "Disguise" },
      { tag: "cloak", label: "Cloak" },
      { tag: "bargain", label: "Bargain" },
      { tag: "plot", label: "Plot" },
      { tag: "saddle", label: "Saddle" },
      { tag: "surge", label: "Surge" },
    ],
  },
  {
    group: "Counters / power-toughness",
    chips: [
      { tag: "modular", label: "Modular" },
      { tag: "devour", label: "Devour" },
      { tag: "monstrosity", label: "Monstrosity" },
      { tag: "outlast", label: "Outlast" },
      { tag: "fabricate", label: "Fabricate" },
      { tag: "adapt", label: "Adapt" },
      { tag: "evolve", label: "Evolve" },
      { tag: "support", label: "Support" },
      { tag: "level_up", label: "Level up" },
      { tag: "bolster", label: "Bolster" },
      { tag: "reinforce", label: "Reinforce" },
      { tag: "explore", label: "Explore" },
      { tag: "discover", label: "Discover" },
      { tag: "amass", label: "Amass" },
    ],
  },
  {
    group: "Triggers / states / locations",
    chips: [
      { tag: "raid", label: "Raid" },
      { tag: "revolt", label: "Revolt" },
      { tag: "metalcraft", label: "Metalcraft" },
      { tag: "ferocious", label: "Ferocious" },
      { tag: "formidable", label: "Formidable" },
      { tag: "hellbent", label: "Hellbent" },
      { tag: "spell_mastery", label: "Spell mastery" },
      { tag: "constellation", label: "Constellation" },
      { tag: "magecraft", label: "Magecraft" },
      { tag: "undergrowth", label: "Undergrowth" },
      { tag: "monarch", label: "Monarch" },
      { tag: "initiative", label: "Initiative" },
      { tag: "dungeon", label: "Dungeon / venture" },
      { tag: "the_ring", label: "The Ring tempts you" },
      { tag: "addendum", label: "Addendum" },
      { tag: "coven", label: "Coven" },
      { tag: "inspired", label: "Inspired" },
      { tag: "heroic", label: "Heroic" },
      { tag: "domain", label: "Domain" },
      { tag: "descend", label: "Descend" },
      { tag: "eerie", label: "Eerie" },
      { tag: "celebration", label: "Celebration" },
      { tag: "party", label: "Party" },
      { tag: "manifest", label: "Manifest" },
      { tag: "populate", label: "Populate" },
      { tag: "changeling", label: "Changeling" },
    ],
  },
];

export const MECHANIC_TAGS: string[] = MECHANIC_GROUPS.flatMap((g) =>
  g.chips.map((c) => c.tag),
);

export const MECHANIC_LABELS: Record<string, string> = Object.fromEntries(
  MECHANIC_GROUPS.flatMap((g) => g.chips.map((c) => [c.tag, c.label])),
);
