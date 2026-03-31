"use client";

import type { CardSuggestion } from "@/lib/types";

interface Props {
  suggestion: CardSuggestion;
  status: "pending" | "accepted" | "rejected";
  onAccept: () => void;
  onReject: () => void;
}

export function CardSuggestionCard({ suggestion, status, onAccept, onReject }: Props) {
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
          <p className="font-medium text-white leading-tight">{suggestion.name}</p>
          {suggestion.mana_cost && (
            <p className="text-xs text-gray-500">{suggestion.mana_cost}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">{suggestion.type_line}</p>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">{suggestion.reasoning}</p>
        {suggestion.synergies.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-auto">
            {suggestion.synergies.slice(0, 3).map((s) => (
              <span key={s} className="rounded bg-indigo-900/40 px-1.5 py-0.5 text-xs text-indigo-300">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
      {status === "pending" && (
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
      )}
      {status === "accepted" && (
        <div className="border-t border-green-500/20 py-2 text-center text-xs font-medium text-green-400">
          Added to deck
        </div>
      )}
      {status === "rejected" && (
        <div className="border-t border-white/5 py-2 text-center text-xs text-gray-600">
          Rejected
        </div>
      )}
    </div>
  );
}
