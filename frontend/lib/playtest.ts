import type { DeckCardItem } from "@/lib/types";

export type Color = "W" | "U" | "B" | "R" | "G" | "C";

export const COLORS: readonly Color[] = ["W", "U", "B", "R", "G", "C"];

export interface PlaytestCard {
  uid: string;
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  oracle_text: string | null;
  color_identity: string[];
  image_uri: string | null;
  isLand: boolean;
  produces: Color[];
  isRamp: boolean;
  isDraw: boolean;
  drawCount: number;
  rampProduces: Color[];
}

export interface ManaSource {
  uid: string;
  name: string;
  produces: Color[];
  availableFromTurn: number;
}

export interface ManaCost {
  generic: number;
  colored: Record<Color, number>;
  hasX: boolean;
}

const DRAW_RE = /draw (a|one|two|three|four|five|\d+) cards?/i;
const DRAW_MAX = 5;
const WORD_TO_INT: Record<string, number> = {
  a: 1,
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
};

const BASIC_LAND_PRODUCES: Record<string, Color> = {
  Plains: "W",
  Island: "U",
  Swamp: "B",
  Mountain: "R",
  Forest: "G",
  Wastes: "C",
};

function emptyColored(): Record<Color, number> {
  return { W: 0, U: 0, B: 0, R: 0, G: 0, C: 0 };
}

export function landProduces(card: {
  name: string;
  type_line: string | null;
  color_identity: string[];
}): Color[] {
  // v1 simplification: basics by name, non-basics by color_identity. Ignores
  // ETB-tapped, fetches, filters — enough fidelity for curve/land-count tuning.
  if (!card.type_line?.includes("Land")) return [];
  const basicName = card.name.split(" // ")[0]?.replace(/^(Snow-Covered )/, "") ?? card.name;
  const basic = BASIC_LAND_PRODUCES[basicName];
  if (basic) return [basic];
  const fromIdentity = card.color_identity.filter((c): c is Color =>
    (COLORS as readonly string[]).includes(c),
  );
  return fromIdentity.length > 0 ? fromIdentity : ["C"];
}

export function parseManaCost(cost: string | null): ManaCost {
  const out: ManaCost = { generic: 0, colored: emptyColored(), hasX: false };
  if (!cost) return out;
  const symbols = cost.match(/\{[^}]+\}/g) ?? [];
  for (const raw of symbols) {
    const sym = raw.slice(1, -1).toUpperCase();
    if (sym === "X" || sym === "Y" || sym === "Z") {
      out.hasX = true;
      continue;
    }
    if (/^\d+$/.test(sym)) {
      out.generic += Number.parseInt(sym, 10);
      continue;
    }
    if ((COLORS as readonly string[]).includes(sym)) {
      out.colored[sym as Color] += 1;
      continue;
    }
    // Hybrid like {W/U}: pick the cheaper option by counting one in each, but
    // collapse to a single requirement satisfiable by either. Treat as 1
    // generic that must be paid by one of the listed colors — for the v1
    // castability check, fall back to demanding the first listed color.
    if (sym.includes("/")) {
      const parts = sym.split("/").filter((p) => (COLORS as readonly string[]).includes(p));
      if (parts.length > 0) {
        out.colored[parts[0] as Color] += 1;
        continue;
      }
    }
    // Unknown symbol (phyrexian, snow, etc.) — treat as 1 generic.
    out.generic += 1;
  }
  return out;
}

export function parseDrawCount(oracleText: string | null): number {
  if (!oracleText) return 1;
  const match = DRAW_RE.exec(oracleText);
  if (!match) return 1;
  const token = match[1]!.toLowerCase();
  if (/^\d+$/.test(token)) return Math.min(Number.parseInt(token, 10), DRAW_MAX);
  return WORD_TO_INT[token] ?? 1;
}

function rampProducesFor(card: DeckCardItem): Color[] {
  const identity = card.color_identity.filter((c): c is Color =>
    (COLORS as readonly string[]).includes(c),
  );
  return identity.length > 0 ? identity : ["C"];
}

export function expandDeck(cards: DeckCardItem[]): PlaytestCard[] {
  const out: PlaytestCard[] = [];
  for (const card of cards) {
    const qty = card.quantity ?? 1;
    const isLand = !!card.type_line?.includes("Land");
    const produces = isLand
      ? landProduces({
          name: card.name,
          type_line: card.type_line,
          color_identity: card.color_identity,
        })
      : [];
    const stages = card.qualifying_stages ?? [];
    const isRamp = !isLand && stages.includes("ramp");
    const isDraw = !isLand && stages.includes("draw");
    const drawCount = isDraw ? parseDrawCount(card.oracle_text) : 0;
    const rampProduces = isRamp ? rampProducesFor(card) : [];
    for (let i = 0; i < qty; i += 1) {
      out.push({
        uid: `${card.scryfall_id}:${i}`,
        scryfall_id: card.scryfall_id,
        name: card.name,
        mana_cost: card.mana_cost,
        cmc: card.cmc,
        type_line: card.type_line,
        oracle_text: card.oracle_text,
        color_identity: card.color_identity,
        image_uri: card.image_uri,
        isLand,
        produces,
        isRamp,
        isDraw,
        drawCount,
        rampProduces,
      });
    }
  }
  return out;
}

export function shuffle<T>(arr: readonly T[]): T[] {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const a = out[i]!;
    const b = out[j]!;
    out[i] = b;
    out[j] = a;
  }
  return out;
}

export function canCast(cost: ManaCost, sources: ManaSource[]): boolean {
  const active = sources.filter((s) => s.produces.length > 0);
  const required: Color[] = [];
  for (const color of COLORS) {
    for (let i = 0; i < cost.colored[color]; i += 1) required.push(color);
  }
  const totalNeeded = required.length + cost.generic;
  if (active.length < totalNeeded) return false;

  const used: boolean[] = Array.from({ length: active.length }, () => false);
  if (!assignColored(required, 0, active, used)) return false;

  let generic = cost.generic;
  for (let i = 0; i < active.length && generic > 0; i += 1) {
    if (!used[i]) {
      used[i] = true;
      generic -= 1;
    }
  }
  return generic === 0;
}

function assignColored(
  required: Color[],
  idx: number,
  sources: ManaSource[],
  used: boolean[],
): boolean {
  if (idx >= required.length) return true;
  const color = required[idx]!;
  for (let i = 0; i < sources.length; i += 1) {
    if (used[i]) continue;
    const src = sources[i]!;
    if (!src.produces.includes(color)) continue;
    used[i] = true;
    if (assignColored(required, idx + 1, sources, used)) return true;
    used[i] = false;
  }
  return false;
}

export function manaPoolSummary(sources: ManaSource[]): Record<Color, number> {
  const pool = emptyColored();
  for (const src of sources) {
    for (const c of src.produces) pool[c] += 1;
  }
  return pool;
}

export function landToSource(card: PlaytestCard, currentTurn: number): ManaSource {
  return {
    uid: card.uid,
    name: card.name,
    produces: card.produces,
    availableFromTurn: currentTurn,
  };
}

export function rampToSource(card: PlaytestCard, currentTurn: number): ManaSource {
  return {
    uid: `ramp:${card.uid}`,
    name: card.name,
    produces: card.rampProduces,
    availableFromTurn: currentTurn + 1,
  };
}
