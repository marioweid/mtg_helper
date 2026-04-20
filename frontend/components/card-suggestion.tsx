"use client";

import type { CardSuggestion } from "@/lib/types";

interface Props {
  suggestion: CardSuggestion;
  status: "pending" | "accepted" | "rejected";
  onAccept: () => void;
  onReject: () => void;
  onRemove?: () => void;
  onAddBack?: () => void;
  isPetCard?: boolean;
  isBasicLand?: boolean;
  quantity?: number;
  onQuantityChange?: (quantity: number) => void;
}

function formatEur(cents: number | null): string {
  if (cents == null) return "—";
  return `€${(cents / 100).toFixed(2)}`;
}

function dedupeChips(primary: string[], secondary: string[], cap: number): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const s of [...primary, ...secondary]) {
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(s);
    if (result.length >= cap) break;
  }
  return result;
}

export function CardSuggestionCard({
  suggestion,
  status,
  onAccept,
  onReject,
  onRemove,
  onAddBack,
  isPetCard,
  isBasicLand,
  quantity = 1,
  onQuantityChange,
}: Props) {
  const isHot =
    suggestion.highlight_reasons != null && suggestion.highlight_reasons.length > 0;
  const chips = dedupeChips(
    suggestion.highlight_reasons ?? [],
    suggestion.synergies,
    3,
  );
  const owned = suggestion.owned_in;

  return (
    <div
      className={`flex flex-col rounded-xl border overflow-hidden transition-all ${
        status === "accepted"
          ? "border-green-500/40 bg-green-900/10"
          : status === "rejected"
            ? "border-red-500/20 bg-red-900/5 opacity-50"
            : "border-white/10 bg-white/5"
      }`}
    >
      {suggestion.image_uri && (
        <div className="relative h-40 overflow-hidden">
          <img
            src={suggestion.image_uri}
            alt={suggestion.name}
            className="h-full w-full object-cover object-top"
          />
          <div className="absolute top-1.5 right-1.5 flex gap-1">
            <span
              className="rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium text-white backdrop-blur"
              title="Scryfall EUR, nonfoil"
            >
              {formatEur(suggestion.price_eur_cents)}
            </span>
          </div>
          {isHot && (
            <span
              className="absolute top-1.5 left-1.5 text-base"
              title={`Top pick: ${suggestion.highlight_reasons?.join(", ") ?? ""}`}
            >
              🔥
            </span>
          )}
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div>
          <p className="font-medium text-white leading-tight flex items-center gap-1.5 flex-wrap">
            <span>{suggestion.name}</span>
            {isPetCard && (
              <span className="text-red-400 flex-shrink-0 text-xs" title="Pet card">
                ♥
              </span>
            )}
            {!suggestion.image_uri && isHot && <span title="Top pick">🔥</span>}
          </p>
          {suggestion.mana_cost && (
            <p className="text-xs text-gray-500">{suggestion.mana_cost}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">{suggestion.type_line}</p>
        </div>

        {/* Ownership chip */}
        <div className="flex flex-wrap gap-1">
          {owned.length > 0 ? (
            owned.slice(0, 2).map((c) => (
              <span
                key={c.id}
                className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-xs text-emerald-300"
                title="Owned in this collection"
              >
                ✓ {c.name}
              </span>
            ))
          ) : (
            <span className="rounded bg-gray-800/60 px-1.5 py-0.5 text-xs text-gray-500">
              Unowned
            </span>
          )}
          {owned.length > 2 && (
            <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-xs text-emerald-300">
              +{owned.length - 2}
            </span>
          )}
        </div>

        {/* Oracle text */}
        {suggestion.oracle_text && (
          <p className="text-xs text-gray-400 italic leading-relaxed">
            {suggestion.oracle_text}
          </p>
        )}

        {/* Reasoning */}
        <p className="text-xs text-gray-400 leading-relaxed">{suggestion.reasoning}</p>

        {/* Tags row: synergy/highlight chips + price fallback when no image */}
        {(chips.length > 0 || !suggestion.image_uri) && (
          <div className="mt-auto flex flex-wrap items-center gap-1 border-t border-white/5 pt-2">
            {chips.map((c) => (
              <span
                key={c}
                className={`rounded px-1.5 py-0.5 text-xs ${
                  isHot && suggestion.highlight_reasons?.includes(c)
                    ? "bg-amber-900/30 text-amber-300"
                    : "bg-indigo-900/40 text-indigo-300"
                }`}
              >
                {c}
              </span>
            ))}
            {!suggestion.image_uri && (
              <span className="ml-auto text-xs text-gray-300">
                {formatEur(suggestion.price_eur_cents)}
              </span>
            )}
          </div>
        )}
      </div>
      {status === "pending" && (
        <>
          {isBasicLand && onQuantityChange && (
            <div className="flex items-center justify-center gap-2 border-t border-white/10 py-2">
              <button
                onClick={() => onQuantityChange(Math.max(1, quantity - 1))}
                className="flex h-6 w-6 items-center justify-center rounded bg-white/10 text-gray-300 hover:bg-white/20 transition-colors text-sm"
              >
                −
              </button>
              <input
                type="number"
                min={1}
                max={99}
                value={quantity}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v) && v >= 1 && v <= 99) onQuantityChange(v);
                }}
                className="w-10 rounded bg-white/10 px-1 py-0.5 text-center text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={() => onQuantityChange(Math.min(99, quantity + 1))}
                className="flex h-6 w-6 items-center justify-center rounded bg-white/10 text-gray-300 hover:bg-white/20 transition-colors text-sm"
              >
                +
              </button>
            </div>
          )}
          <div className="flex border-t border-white/10">
            <button
              onClick={onAccept}
              className="flex-1 py-2 text-sm font-medium text-green-400 hover:bg-green-900/20 transition-colors"
            >
              Accept
            </button>
            <div className="w-px bg-white/10" />
            <button
              onClick={onReject}
              className="flex-1 py-2 text-sm font-medium text-red-400 hover:bg-red-900/20 transition-colors"
            >
              Reject
            </button>
          </div>
        </>
      )}
      {status === "accepted" && (
        <div className="flex items-center justify-between border-t border-green-500/20 px-3 py-2">
          <span className="text-xs font-medium text-green-400">
            ✓ Added{isBasicLand && quantity > 1 ? ` ×${quantity}` : ""}
          </span>
          {onRemove && (
            <button
              onClick={onRemove}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Remove
            </button>
          )}
        </div>
      )}
      {status === "rejected" && (
        <div className="flex items-center justify-between border-t border-white/5 px-3 py-2">
          <span className="text-xs text-gray-600">Rejected</span>
          {onAddBack && (
            <button
              onClick={onAddBack}
              className="text-xs text-gray-400 hover:text-green-400 transition-colors"
            >
              Add
            </button>
          )}
        </div>
      )}
    </div>
  );
}
