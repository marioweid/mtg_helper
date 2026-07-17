import type { DeckCardItem } from "@/lib/types";

const BAND_COLOR = {
  strong: "bg-emerald-400/70",
  solid: "bg-amber-300/60",
  weak: "bg-rose-400/70",
} as const;

export function DeckFitIndicator({ card }: { card: DeckCardItem }) {
  if (card.deck_fit_score == null || card.deck_fit_band == null) return null;
  const details = [
    `Deck fit: ${card.deck_fit_score}/100 (${card.deck_fit_band})`,
    ...(card.deck_fit_reasons ?? []),
  ];
  return (
    <span
      className={`h-1.5 w-1.5 shrink-0 rounded-full ${BAND_COLOR[card.deck_fit_band]}`}
      title={details.join("\n")}
      aria-label={details.join(". ")}
    />
  );
}
