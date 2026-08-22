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

// Brighter / more saturated tones for glow shadows — the gradient-grade hexes
// (especially the near-black B) wash out as shadows.
const SHADOW_HEX: Record<string, string> = {
  W: "#f3e3a1",
  U: "#3b7be0",
  B: "#6e4ea0",
  R: "#e4493c",
  G: "#34b85a",
  C: "#aab0bc",
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

/**
 * Build a CSS ``box-shadow`` string that glows around an element with the
 * deck's color identity. Each color contributes a tinted glow at a different
 * radial offset so multicolor decks read as a rim of stacked hues rather than
 * one muddy blend.
 *
 * Always layers a black drop shadow underneath for vertical lift. Set
 * ``intensity`` to "subtle" for small tiles where the default reads as too
 * heavy.
 */
export function colorIdentityShadow(
  colors: string[],
  intensity: "subtle" | "normal" = "normal",
): string {
  const subtle = intensity === "subtle";
  const baseDrop = subtle ? "0 6px 18px rgba(0, 0, 0, 0.5)" : "0 12px 32px rgba(0, 0, 0, 0.55)";
  const sorted = sortWUBRG(colors.filter((c) => c in SHADOW_HEX));
  if (sorted.length === 0) return baseDrop;

  const radius = subtle ? 8 : 14;
  const blur = subtle ? 22 : 42;
  const alpha = sorted.length === 1 ? (subtle ? "80" : "cc") : subtle ? "66" : "bb";

  const glows = sorted.map((c, i) => {
    // Spread the glows around the element. Single color sits behind centred;
    // multi-color positions follow the unit circle so each hue gets an edge.
    if (sorted.length === 1) {
      return `0 0 ${blur}px ${SHADOW_HEX[c]}${alpha}`;
    }
    const angle = (i / sorted.length) * Math.PI * 2 - Math.PI / 2;
    const x = Math.round(Math.cos(angle) * radius);
    const y = Math.round(Math.sin(angle) * radius);
    return `${x}px ${y}px ${blur}px ${SHADOW_HEX[c]}${alpha}`;
  });

  return [...glows, baseDrop].join(", ");
}
