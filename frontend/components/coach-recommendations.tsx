import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import type { AnalysisCardHit, ReplacementOption } from "@/lib/types";

interface CoachRecommendationsProps {
  recommendations: ReplacementOption[];
  busy: string | null;
  onAdd: (card: AnalysisCardHit) => void;
}

export function CoachRecommendations({ recommendations, busy, onAdd }: CoachRecommendationsProps) {
  if (recommendations.length === 0) return null;
  return (
    <section className="mt-4 border-t border-white/10 pt-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-indigo-200">
        Recommended cards
      </h3>
      <div className="grid gap-3 lg:grid-cols-2">
        {recommendations.map((option) => (
          <article
            key={option.card.scryfall_id ?? option.card.name}
            className="rounded-xl border border-indigo-400/15 bg-black/20 p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardHover name={option.card.name} className="font-semibold text-white">
                  {option.card.name}
                </CardHover>
                {option.card.type_line && (
                  <div className="mt-1 text-xs text-gray-500">{option.card.type_line}</div>
                )}
              </div>
              {option.card.mana_cost && <ManaCost cost={option.card.mana_cost} />}
            </div>
            <p className="mt-2 text-sm text-gray-300">{option.reason}</p>
            {option.tradeoff && <p className="mt-1 text-xs text-gray-500">{option.tradeoff}</p>}
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-gray-600">
                {option.role_match.replace(/_/g, " ")}
              </span>
              <button
                type="button"
                onClick={() => onAdd(option.card)}
                disabled={busy != null}
                className="rounded-md bg-emerald-600 px-3 py-1 text-xs text-white disabled:opacity-50"
              >
                {busy === `add:${option.card.scryfall_id}` ? "Adding…" : "Add card"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
