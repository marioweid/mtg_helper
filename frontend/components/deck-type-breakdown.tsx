export interface TypeBreakdownCard {
  type_line: string | null;
  quantity?: number | null;
}

const TYPE_ORDER = [
  "Creatures",
  "Instants",
  "Sorceries",
  "Artifacts",
  "Enchantments",
  "Planeswalkers",
  "Lands",
  "Battles",
] as const;

type TypeLabel = (typeof TYPE_ORDER)[number];

function classify(type_line: string | null): TypeLabel | null {
  const tl = type_line ?? "";
  if (tl.includes("Land")) return "Lands";
  if (tl.includes("Creature")) return "Creatures";
  if (tl.includes("Planeswalker")) return "Planeswalkers";
  if (tl.includes("Battle")) return "Battles";
  if (tl.includes("Enchantment")) return "Enchantments";
  if (tl.includes("Artifact")) return "Artifacts";
  if (tl.includes("Sorcery")) return "Sorceries";
  if (tl.includes("Instant")) return "Instants";
  return null;
}

export function DeckTypeBreakdown({
  cards,
  target,
  commander,
}: {
  cards: TypeBreakdownCard[];
  target?: number;
  /** Commander card. Counts as 1 toward the total and classifies by type. */
  commander?: { type_line: string | null } | null;
}) {
  const counts: Record<string, number> = {};
  let total = 0;
  for (const card of cards) {
    const q = card.quantity ?? 1;
    total += q;
    const label = classify(card.type_line);
    if (label) counts[label] = (counts[label] ?? 0) + q;
  }
  if (commander) {
    total += 1;
    const label = classify(commander.type_line);
    if (label) counts[label] = (counts[label] ?? 0) + 1;
  }
  const visible = TYPE_ORDER.filter((t) => (counts[t] ?? 0) > 0);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="font-semibold text-white tabular-nums">
        {total}
        {target != null && <span className="text-gray-500">/{target}</span>}
        <span className="ml-1 text-gray-500">cards</span>
      </span>
      {visible.map((t) => (
        <span key={t} className="text-gray-300">
          <span className="font-semibold tabular-nums text-white">{counts[t]}</span>{" "}
          <span className="text-gray-400">{t}</span>
        </span>
      ))}
    </div>
  );
}
