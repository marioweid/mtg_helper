"use client";

import { useState } from "react";
import { ApiError, apiClient } from "@/lib/api";
import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { OwnedBadge } from "@/components/owned-badge";
import type { CardSuggestion, ColorStatus, ManaBaseReport, RiskyCard } from "@/lib/types";

interface Props {
  deckId: string;
  onAddCard?: (scryfallId: string) => Promise<void> | void;
}

const COLOR_DOT: Record<string, string> = {
  W: "bg-yellow-200",
  U: "bg-blue-400",
  B: "bg-gray-700",
  R: "bg-red-500",
  G: "bg-green-500",
};

function ColorRow({ color }: { color: ColorStatus }) {
  const deficit = color.deficit > 0;
  const turnRisk = color.turn_deficit > 0;
  return (
    <tr className={deficit || turnRisk ? "bg-red-900/10" : ""}>
      <td className="px-1 py-1">
        <span className="inline-flex items-center gap-1">
          <span className={`h-3 w-3 rounded-full ${COLOR_DOT[color.color] ?? "bg-gray-400"}`} />
          <span className="font-medium text-white">{color.color}</span>
        </span>
      </td>
      <td className="px-1 py-1 tabular-nums text-gray-300">{color.pip_count.toFixed(1)}</td>
      <td
        className="px-1 py-1 tabular-nums text-gray-300"
        title={`Sources / target = ${color.source_count}/${color.target}`}
      >
        {color.source_count}
        <span className="text-gray-600">/{color.target}</span>
      </td>
      <td className="px-1 py-1 tabular-nums">
        {deficit ? (
          <span className="font-medium text-red-300">−{color.deficit}</span>
        ) : (
          <span className="text-emerald-400">ok</span>
        )}
      </td>
      <td
        className="px-1 py-1 tabular-nums text-gray-300"
        title={turnRisk ? `Need ${color.turn_demand} sources by turn` : undefined}
      >
        {color.turn_demand > 0 ? color.turn_demand : "—"}
        {turnRisk && <span className="ml-0.5 text-red-400">⚠</span>}
      </td>
    </tr>
  );
}

function RiskyCardItem({ card }: { card: RiskyCard }) {
  const cost = card.mana_cost ? <ManaCost cost={card.mana_cost} /> : null;
  return (
    <li className="text-xs text-gray-300">
      <CardHover name={card.name} className="text-white">
        {card.name}
      </CardHover>
      {cost && <span className="ml-1 text-gray-400">({cost})</span>}
      <span className="ml-1 text-gray-500">
        — turn {card.cmc} needs {card.sources_required} {card.color} sources, you have{" "}
        {card.sources_available}
      </span>
    </li>
  );
}

function ProducesPips({ colors }: { colors: string[] }) {
  const tokens = colors.length ? colors.map((c) => `{${c}}`).join("") : "{C}";
  return (
    <span title={colors.length ? `Produces ${colors.join("")}` : "Colorless"}>
      <ManaCost cost={tokens} />
    </span>
  );
}

function SuggestionRow({
  card,
  onAdd,
  busy,
}: {
  card: CardSuggestion;
  onAdd?: () => void;
  busy: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-white/10 bg-black/20 px-2 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 truncate text-sm text-gray-100">
          <ProducesPips colors={card.color_identity} />
          <CardHover name={card.name} imageUri={card.image_uri}>
            {card.name}
          </CardHover>
        </div>
        <div className="mt-0.5 flex flex-wrap gap-1 text-xs text-gray-400">
          {card.type_line && <span className="truncate">{card.type_line}</span>}
          {card.mana_cost && (
            <span>
              <ManaCost cost={card.mana_cost} />
            </span>
          )}
          <OwnedBadge owned={card.owned_in} showUnowned={false} />
        </div>
      </div>
      {onAdd && (
        <button
          type="button"
          onClick={onAdd}
          disabled={busy}
          className="shrink-0 rounded border border-emerald-500/40 px-2 py-0.5 text-xs text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
        >
          {busy ? "Planning…" : "Plan addition"}
        </button>
      )}
    </li>
  );
}

export function ManaFixPanel({ deckId, onAddCard }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ManaBaseReport | null>(null);
  const [suggestions, setSuggestions] = useState<CardSuggestion[]>([]);
  const [adding, setAdding] = useState<string | null>(null);

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.manaFix(deckId);
      setReport(res.report);
      setSuggestions(res.suggestions);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to analyze mana base");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(scryfallId: string) {
    if (!onAddCard) return;
    setAdding(scryfallId);
    try {
      await onAddCard(scryfallId);
      setSuggestions((prev) => prev.filter((s) => s.scryfall_id !== scryfallId));
    } finally {
      setAdding(null);
    }
  }

  const hasDeficit = (report?.colors ?? []).some((c) => c.deficit > 0);
  const allRisky: RiskyCard[] = (report?.colors ?? []).flatMap((c) => c.risky_cards);

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-medium text-gray-200">Mana base</div>
          <div className="text-xs text-gray-500">
            Pips vs colored sources. Flags colors below target.
          </div>
        </div>
        <button
          type="button"
          onClick={() => void handleAnalyze()}
          disabled={loading}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Analyzing…" : report ? "Refresh" : "Analyze"}
        </button>
      </div>

      {error && (
        <div className="mt-2 rounded border border-red-500/40 bg-red-900/20 px-2 py-1 text-xs text-red-300">
          {error}
        </div>
      )}

      {report && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
            <span>
              <span className="text-gray-300">{report.total_lands}</span> lands
            </span>
            <span className="text-gray-600">·</span>
            <span>
              recommended <span className="text-gray-300">{report.recommended_lands}</span>
            </span>
            {report.land_delta !== 0 && (
              <span
                className={
                  report.land_delta > 0
                    ? "rounded bg-amber-900/30 px-1.5 py-0.5 text-amber-300"
                    : "rounded bg-amber-900/30 px-1.5 py-0.5 text-amber-300"
                }
              >
                {report.land_delta > 0
                  ? `+${report.land_delta} lands`
                  : `${report.land_delta} lands`}
              </span>
            )}
            <span className="text-gray-600">·</span>
            <span>
              avg CMC <span className="text-gray-300">{report.avg_cmc.toFixed(2)}</span>
            </span>
            <span className="text-gray-600">·</span>
            <span>
              <span className="text-gray-300">{report.ramp_count}</span> ramp
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead className="text-left text-gray-500">
                <tr>
                  <th className="px-1 py-1 font-normal">Col</th>
                  <th className="px-1 py-1 font-normal" title="Colored pips on non-land cards">
                    Pips
                  </th>
                  <th className="px-1 py-1 font-normal" title="Sources you have / target">
                    Src/Tgt
                  </th>
                  <th className="px-1 py-1 font-normal" title="Shortfall vs target">
                    Def
                  </th>
                  <th
                    className="px-1 py-1 font-normal"
                    title="Sources needed for the hardest pip requirement on curve"
                  >
                    Turn
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {report.colors.map((c) => (
                  <ColorRow key={c.color} color={c} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-1 text-[11px] text-gray-500">
            {report.total_colored_pips.toFixed(1)} colored pips
          </div>
        </div>
      )}

      {report && allRisky.length > 0 && (
        <details className="mt-3 rounded-md border border-white/10 bg-black/20 px-2 py-1.5">
          <summary className="cursor-pointer text-xs text-gray-400">
            Risky cards ({allRisky.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {allRisky.map((r) => (
              <RiskyCardItem key={`${r.card_id}-${r.color}`} card={r} />
            ))}
          </ul>
        </details>
      )}

      {report && !hasDeficit && (
        <div className="mt-2 text-xs text-emerald-400">
          All colors hit their targets — no fixes suggested.
        </div>
      )}

      {report && hasDeficit && suggestions.length > 0 && (
        <>
          <div className="mt-3 text-xs text-gray-500">Suggested lands:</div>
          <ul className="mt-1 space-y-1.5">
            {suggestions.map((s) => (
              <SuggestionRow
                key={s.scryfall_id}
                card={s}
                {...(onAddCard ? { onAdd: () => void handleAdd(s.scryfall_id) } : {})}
                busy={adding === s.scryfall_id}
              />
            ))}
          </ul>
        </>
      )}

      {report && hasDeficit && suggestions.length === 0 && !loading && (
        <div className="mt-2 text-xs text-gray-400">
          No land candidates found within the deck's color identity.
        </div>
      )}
    </div>
  );
}
