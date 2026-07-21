import type { ReactNode } from "react";

import type { CardWorkspaceView } from "@/lib/deck-view-prefs";

interface Props {
  view: CardWorkspaceView;
  onViewChange: (view: CardWorkspaceView) => void;
  resultCount: number;
  totalCount: number;
  children?: ReactNode;
}

/** Shared controls and visual treatment for deck and collection card workspaces. */
export function CardWorkspaceToolbar({
  view,
  onViewChange,
  resultCount,
  totalCount,
  children,
}: Props) {
  const filtered = resultCount !== totalCount;

  return (
    <section
      aria-label="Card workspace controls"
      className="sticky top-2 z-20 space-y-2 rounded-xl border border-indigo-400/15 bg-zinc-950/90 p-2.5 shadow-xl shadow-black/20 backdrop-blur"
    >
      {children}
      <div className="flex items-center justify-between gap-3 px-1">
        <p className="text-xs tabular-nums text-gray-400" aria-live="polite">
          {filtered ? `${resultCount} of ${totalCount} cards` : `${totalCount} cards`}
        </p>
        <div
          role="group"
          aria-label="Card view"
          className="inline-flex rounded-lg border border-white/10 bg-black/25 p-0.5"
        >
          {(["grid", "list"] as const).map((option) => {
            const active = option === view;
            return (
              <button
                key={option}
                type="button"
                aria-pressed={active}
                onClick={() => onViewChange(option)}
                className={`min-h-11 touch-manipulation rounded-md px-3 text-xs font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                  active
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-gray-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                {option}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
