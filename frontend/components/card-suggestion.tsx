"use client";

import { useState } from "react";

import type { CardSuggestion } from "@/lib/types";

const RARITY_COLORS: Record<string, string> = {
  common: "text-gray-400 bg-gray-800/60",
  uncommon: "text-slate-300 bg-slate-700/60",
  rare: "text-yellow-300 bg-yellow-900/40",
  mythic: "text-orange-400 bg-orange-900/40",
};

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
  const [showDetails, setShowDetails] = useState(false);
  const hasDetails =
    suggestion.oracle_text != null ||
    suggestion.power != null ||
    suggestion.toughness != null ||
    suggestion.rarity != null;

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
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div>
          <p className="font-medium text-white leading-tight flex items-center gap-1.5">
            {suggestion.name}
            {isPetCard && <span className="text-red-400 flex-shrink-0 text-xs" title="Pet card">♥</span>}
          </p>
          {suggestion.mana_cost && (
            <p className="text-xs text-gray-500">{suggestion.mana_cost}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">{suggestion.type_line}</p>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">{suggestion.reasoning}</p>
        {suggestion.highlight_reasons && suggestion.highlight_reasons.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs font-semibold text-amber-400">⚡ Top Pick</span>
            {suggestion.highlight_reasons.map((r) => (
              <span key={r} className="rounded bg-amber-900/30 px-1.5 py-0.5 text-xs text-amber-300">
                {r}
              </span>
            ))}
          </div>
        )}
        {suggestion.synergies.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {suggestion.synergies.slice(0, 3).map((s) => (
              <span key={s} className="rounded bg-indigo-900/40 px-1.5 py-0.5 text-xs text-indigo-300">
                {s}
              </span>
            ))}
          </div>
        )}
        {hasDetails && (
          <div className="mt-auto">
            <button
              onClick={() => setShowDetails((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showDetails ? "Hide details" : "Show details"}
            </button>
            {showDetails && (
              <div className="mt-2 space-y-1.5 border-t border-white/5 pt-2">
                {suggestion.oracle_text && (
                  <p className="text-xs text-gray-400 italic leading-relaxed">
                    {suggestion.oracle_text}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  {suggestion.power != null && suggestion.toughness != null && (
                    <span className="text-xs text-gray-300 font-medium">
                      {suggestion.power}/{suggestion.toughness}
                    </span>
                  )}
                  {suggestion.cmc != null && (
                    <span className="text-xs text-gray-500">MV: {suggestion.cmc}</span>
                  )}
                  {suggestion.rarity && (
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs capitalize ${RARITY_COLORS[suggestion.rarity] ?? "text-gray-400 bg-gray-800/60"}`}
                    >
                      {suggestion.rarity}
                    </span>
                  )}
                </div>
              </div>
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
