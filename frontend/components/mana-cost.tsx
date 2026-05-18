import { Fragment, type ReactNode } from "react";

/**
 * Render Magic mana / ability symbols inline. Parses ``{W}``, ``{U}``,
 * ``{T}``, ``{2}``, ``{X}``, hybrid ``{W/U}``, Phyrexian ``{U/P}`` etc. and
 * paints them as small colored pills similar to Scryfall / Moxfield.
 *
 * ``ManaCost`` takes a standalone mana_cost string; ``OracleText`` splits a
 * prose string at every ``{...}`` token and interleaves pills.
 */

const COLOR_CLS: Record<string, string> = {
  W: "bg-yellow-100 text-yellow-900",
  U: "bg-blue-200 text-blue-900",
  B: "bg-zinc-800 text-zinc-100",
  R: "bg-red-200 text-red-900",
  G: "bg-green-200 text-green-900",
  C: "bg-gray-300 text-gray-800",
};

const NEUTRAL_CLS = "bg-gray-300 text-gray-800";

function renderText(symbol: string): string {
  const up = symbol.toUpperCase();
  if (up === "T") return "↷";
  if (up === "Q") return "↶";
  if (up === "S") return "❄";
  if (up === "E") return "⚡";
  return symbol;
}

function symbolClasses(symbol: string): string {
  const up = symbol.toUpperCase();
  if (COLOR_CLS[up]) return COLOR_CLS[up];
  // Hybrid e.g. "W/U" — colour by first half, fall back to neutral.
  if (up.includes("/")) {
    const half = up.split("/")[0] ?? "";
    if (COLOR_CLS[half]) return COLOR_CLS[half];
  }
  return NEUTRAL_CLS;
}

function ManaSymbol({ symbol }: { symbol: string }) {
  return (
    <span
      className={`inline-flex h-[1.1em] min-w-[1.1em] items-center justify-center rounded-full px-1 align-[-0.15em] text-[0.8em] font-bold leading-none shadow-sm ${symbolClasses(symbol)}`}
      aria-label={symbol}
    >
      {renderText(symbol)}
    </span>
  );
}

export function ManaCost({ cost }: { cost: string | null | undefined }) {
  if (!cost) return null;
  const tokens = cost.match(/\{[^}]+\}/g) ?? [];
  if (tokens.length === 0) return <span>{cost}</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-0.5 align-middle">
      {tokens.map((t, i) => (
        <ManaSymbol key={i} symbol={t.slice(1, -1)} />
      ))}
    </span>
  );
}

export function OracleText({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  const segments: ReactNode[] = [];
  const regex = /\{[^}]+\}/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(
        <Fragment key={`t-${key}`}>{text.slice(lastIndex, match.index)}</Fragment>,
      );
      key += 1;
    }
    segments.push(<ManaSymbol key={`s-${key}`} symbol={match[0].slice(1, -1)} />);
    key += 1;
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push(<Fragment key={`t-${key}`}>{text.slice(lastIndex)}</Fragment>);
  }
  return <>{segments}</>;
}
