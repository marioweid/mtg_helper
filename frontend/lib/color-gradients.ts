/**
 * Color-identity → CSS linear-gradient mapping for deck hero banners.
 *
 * Uses inline ``style`` strings rather than Tailwind classes because the
 * gradient is data-driven and Tailwind's JIT can't statically extract
 * dynamic class names.
 */

const COLOR_HEX: Record<string, string> = {
  W: "#f8e7a0",
  U: "#1e4ea8",
  B: "#1a1a1a",
  R: "#b8312c",
  G: "#1e6b3a",
  C: "#6b6b6b",
};

const WUBRG: readonly string[] = ["W", "U", "B", "R", "G"];

function sortWUBRG(colors: string[]): string[] {
  return [...new Set(colors)].sort((a, b) => WUBRG.indexOf(a) - WUBRG.indexOf(b));
}

/**
 * Build a CSS ``linear-gradient`` string for a color-identity array.
 *
 * Empty / unknown colors fall back to a neutral gray gradient. Single-color
 * decks get a single-hue soft gradient; multi-color decks spread stops evenly
 * across the gradient in WUBRG order.
 */
export function colorIdentityGradient(colors: string[]): string {
  const sorted = sortWUBRG(colors.filter((c) => c in COLOR_HEX));
  if (sorted.length === 0) {
    return "linear-gradient(135deg, #2a2a2a 0%, #3a3a3a 50%, #1a1a1a 100%)";
  }
  if (sorted.length === 1) {
    const hex = COLOR_HEX[sorted[0]!]!;
    return `linear-gradient(135deg, ${hex} 0%, ${hex}cc 50%, ${hex}66 100%)`;
  }
  const stops = sorted.map((c, i) => {
    const pct = Math.round((i / (sorted.length - 1)) * 100);
    return `${COLOR_HEX[c]} ${pct}%`;
  });
  return `linear-gradient(135deg, ${stops.join(", ")})`;
}
