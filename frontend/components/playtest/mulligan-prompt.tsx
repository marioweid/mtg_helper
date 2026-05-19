import type { PlaytestCard } from "@/lib/playtest";

interface Props {
  hand: PlaytestCard[];
  mulliganCount: number;
  bottoming: Set<string>;
  bottomNeeded: number;
  canMulligan: boolean;
  onKeep: () => void;
  onMulligan: () => void;
  onToggleBottom: (uid: string) => void;
  onConfirmBottom: () => void;
  phase: "mulligan" | "bottoming";
}

export function MulliganPrompt({
  hand,
  mulliganCount,
  bottoming,
  bottomNeeded,
  canMulligan,
  onKeep,
  onMulligan,
  onToggleBottom,
  onConfirmBottom,
  phase,
}: Props) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-white">
          {phase === "mulligan" ? "Opening hand" : "Bottom cards"}
        </h3>
        <p className="text-xs text-gray-500">
          Mulligans taken: <span className="font-medium text-gray-300">{mulliganCount}</span>
          {phase === "bottoming" && bottomNeeded > 0 && (
            <>
              {" · "}
              Select <span className="font-medium text-gray-300">{bottomNeeded}</span> to bottom
            </>
          )}
        </p>
      </div>

      <div className="mb-3 flex flex-col gap-1.5">
        {hand.map((card) => {
          const selected = bottoming.has(card.uid);
          const disabled = phase !== "bottoming";
          return (
            <button
              key={card.uid}
              type="button"
              onClick={() => onToggleBottom(card.uid)}
              disabled={disabled}
              className={`flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-left text-sm transition-colors ${
                selected
                  ? "border-rose-500/50 bg-rose-500/15 text-rose-100"
                  : "border-white/10 bg-white/5 text-gray-200"
              } ${disabled ? "cursor-default opacity-90" : "hover:border-white/30"}`}
            >
              <span className="truncate">{card.name}</span>
              <span className="flex items-center gap-2 text-xs text-gray-500">
                {card.mana_cost && <span className="font-mono">{card.mana_cost}</span>}
                <span>{card.type_line ?? ""}</span>
              </span>
            </button>
          );
        })}
      </div>

      {phase === "mulligan" ? (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onKeep}
            className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Keep
          </button>
          <button
            type="button"
            onClick={onMulligan}
            disabled={!canMulligan}
            className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 hover:border-white/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {canMulligan ? "Mulligan" : "Max mulligans"}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onConfirmBottom}
          disabled={bottoming.size !== bottomNeeded}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Bottom {bottoming.size}/{bottomNeeded} and start
        </button>
      )}
    </div>
  );
}
