"use client";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const PRIMARY =
  "min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold " +
  `text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;
const SECONDARY =
  "min-h-11 touch-manipulation rounded-lg border border-white/15 px-4 py-2 text-sm " +
  `font-semibold text-gray-100 hover:bg-white/5 disabled:opacity-50 ${FOCUS}`;

export function TutorClearHistory({ busy, onClear }: { busy: boolean; onClear: () => void }) {
  return (
    <details className="rounded-xl border border-red-300/20 p-4">
      <summary className={`cursor-pointer text-sm font-medium text-red-100 ${FOCUS}`}>
        Clear tutor history
      </summary>
      <div className="mt-3 space-y-3" aria-label="Clear tutor history confirmation">
        <p className="text-sm leading-6 text-gray-300">
          Delete every saved Tutor message, chapter, and Lernübergabe for this deck. Guides and
          references remain. Existing operator tracing is not covered.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            className={PRIMARY}
            disabled={busy}
            onClick={(event) => {
              event.currentTarget.closest("details")?.removeAttribute("open");
              onClear();
            }}
          >
            Confirm clear tutor history
          </button>
          <button
            type="button"
            className={SECONDARY}
            disabled={busy}
            onClick={(event) => event.currentTarget.closest("details")?.removeAttribute("open")}
          >
            Cancel clear tutor history
          </button>
        </div>
      </div>
    </details>
  );
}
