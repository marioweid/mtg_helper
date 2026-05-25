"use client";

import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { OwnedBadge } from "@/components/owned-badge";
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
  inCombo?: boolean;
  quantity?: number;
  onQuantityChange?: (quantity: number) => void;
}

function formatEur(cents: number | null): string {
  if (cents == null) return "—";
  return `€${(cents / 100).toFixed(2)}`;
}

const SOURCE_CLASSES: Record<string, string> = {
  Semantic: "bg-indigo-900/40 text-indigo-300",
  Keywords: "bg-violet-900/40 text-violet-300",
  Text: "bg-sky-900/40 text-sky-300",
  EDHREC: "bg-orange-900/40 text-orange-300",
  Moxfield: "bg-cyan-900/40 text-cyan-300",
  Type: "bg-fuchsia-900/40 text-fuchsia-300",
};

export function CardSuggestionCard({
  suggestion,
  status,
  onAccept,
  onReject,
  onRemove,
  onAddBack,
  isPetCard,
  isBasicLand,
  inCombo,
  quantity = 1,
  onQuantityChange,
}: Props) {
  const isHot =
    suggestion.highlight_reasons != null && suggestion.highlight_reasons.length > 0;
  const owned = suggestion.owned_in;
  const sources = suggestion.sources ?? [];

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
      {suggestion.image_uri ? (
        <div className="relative">
          <img
            src={suggestion.image_uri}
            alt={suggestion.name}
            className="block w-full h-auto rounded-[4.5%]"
          />
          {/* Top-left icons: hot + combo */}
          <div className="absolute top-1.5 left-1.5 flex flex-col gap-1">
            {isHot && (
              <span
                className="rounded-full bg-black/70 px-1.5 py-0.5 text-base backdrop-blur"
                title={`Top pick: ${suggestion.highlight_reasons?.join(", ") ?? ""}`}
              >
                🔥
              </span>
            )}
            {inCombo && (
              <span
                className="rounded-full bg-black/70 px-1.5 py-0.5 text-base backdrop-blur"
                title="Completes a potential combo for this deck"
              >
                ⚡
              </span>
            )}
            {isPetCard && (
              <span
                className="rounded-full bg-black/70 px-1.5 py-0.5 text-sm text-red-400 backdrop-blur"
                title="Pet card"
              >
                ♥
              </span>
            )}
          </div>
          {/* Bottom-right: price (kept clear of the card's printed mana cost) */}
          <span
            className="absolute bottom-1.5 right-1.5 rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium text-white backdrop-blur"
            title="Scryfall EUR, nonfoil"
          >
            {formatEur(suggestion.price_eur_cents)}
          </span>
        </div>
      ) : (
        // Image fallback: name + mana cost + type line
        <div className="flex flex-col gap-1 border-b border-white/10 bg-black/30 px-3 py-3">
          <p className="font-medium text-white leading-tight flex items-center gap-1.5 flex-wrap">
            <CardHover name={suggestion.name} imageUri={suggestion.image_uri}>
              {suggestion.name}
            </CardHover>
            {isPetCard && <span className="text-red-400 text-xs" title="Pet card">♥</span>}
            {isHot && <span title="Top pick">🔥</span>}
            {inCombo && <span title="Completes a potential combo">⚡</span>}
          </p>
          {suggestion.mana_cost && (
            <p className="text-xs text-gray-500">
              <ManaCost cost={suggestion.mana_cost} />
            </p>
          )}
          {suggestion.type_line && (
            <p className="text-xs text-gray-400">{suggestion.type_line}</p>
          )}
          <p className="text-xs text-gray-300 mt-1">
            {formatEur(suggestion.price_eur_cents)}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2 p-2">
        {/* Source chips */}
        {sources.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {sources.map((s) => (
              <span
                key={s}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  SOURCE_CLASSES[s] ?? "bg-white/10 text-gray-300"
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {/* Ownership chip */}
        <div className="flex flex-wrap gap-1">
          <OwnedBadge owned={owned} />
        </div>
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
