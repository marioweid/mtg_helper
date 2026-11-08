"use client";

import type { FormEvent, KeyboardEvent } from "react";

import { TutorMarkdown } from "@/components/tutor-markdown";
import type {
  TutorCardFact,
  TutorChapterResponse,
  TutorConversationResponse,
  TutorTurnResponse,
} from "@/lib/types";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const PRIMARY =
  "min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold " +
  `text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;
const SECONDARY =
  "min-h-11 touch-manipulation rounded-lg border border-white/15 px-4 py-2 text-sm " +
  `font-semibold text-gray-100 hover:bg-white/5 disabled:opacity-50 ${FOCUS}`;

interface TutorConversationProps {
  conversation: TutorConversationResponse | null;
  currentCards: TutorCardFact[];
  question: string;
  selectedCard: string;
  selectedChapterId?: string | null;
  busy: boolean;
  onQuestionChange?: (question: string) => void;
  onCardChange?: (cardName: string) => void;
  onChapterChange?: (chapterId: string) => void;
  onAsk?: () => void;
  onClear?: () => void;
}

export function TutorConversation({
  conversation,
  currentCards,
  question,
  selectedCard,
  selectedChapterId = null,
  busy,
  onQuestionChange = () => {},
  onCardChange = () => {},
  onChapterChange = () => {},
  onAsk = () => {},
  onClear = () => {},
}: TutorConversationProps) {
  const chapters = conversation?.chapters ?? [];
  const selected =
    chapters.find((chapter) => chapter.id === selectedChapterId) ?? chapters.at(-1) ?? null;
  const answering = chapters.some((chapter) =>
    chapter.turns.some((turn) => turn.status === "running"),
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (question.trim() && !busy && !answering) onAsk();
  }

  function keyboardSend(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <section
      aria-label="Tutor conversation"
      className="min-w-0 space-y-4 rounded-2xl border border-white/10 bg-white/[0.025] p-4 sm:p-5"
    >
      <div>
        <h3 className="text-lg font-semibold text-white">Conversation</h3>
        <p className="mt-1 text-sm leading-6 text-gray-400">
          Ask about the current deck. Older chapters stay readable but never supply current card
          facts.
        </p>
      </div>
      {conversation === null ? (
        <p role="status" className="text-sm text-gray-400">
          Loading conversation…
        </p>
      ) : (
        <>
          {chapters.length > 0 && (
            <label className="block text-sm font-medium text-gray-200">
              Conversation chapter
              <select
                aria-label="Conversation chapter"
                className={`mt-2 min-h-11 w-full rounded-lg border border-white/15 bg-gray-950 p-2 ${FOCUS}`}
                value={selected?.id ?? ""}
                onChange={(event) => onChapterChange(event.target.value)}
              >
                {[...chapters].reverse().map((chapter) => (
                  <option key={chapter.id} value={chapter.id}>
                    {chapter.current
                      ? `Current deck chapter ${chapter.sequence}`
                      : `Archived chapter ${chapter.sequence}`}
                  </option>
                ))}
              </select>
            </label>
          )}
          {selected ? (
            <Chapter chapter={selected} />
          ) : (
            <p className="text-sm leading-6 text-gray-400">
              No saved Tutor questions yet. Your first answer starts a current deck chapter.
            </p>
          )}
        </>
      )}
      <form className="min-w-0 space-y-3 border-t border-white/10 pt-4" onSubmit={submit}>
        <h4 className="font-medium text-white">Ask about the current deck</h4>
        <label className="block text-sm text-gray-200">
          Card to explain (optional)
          <select
            aria-label="Card to explain"
            className={`mt-2 min-h-11 w-full rounded-lg border border-white/15 bg-gray-950 p-2 ${FOCUS}`}
            value={selectedCard}
            disabled={busy || answering}
            onChange={(event) => onCardChange(event.target.value)}
          >
            <option value="">Whole deck or follow-up</option>
            {currentCards.map((card) => (
              <option key={`${card.oracle_id ?? "unknown"}-${card.name}`} value={card.name}>
                {card.quantity} × {card.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-gray-200">
          Tutor question
          <textarea
            aria-label="Tutor question"
            className={`mt-2 min-h-28 w-full resize-y rounded-lg border border-white/15 bg-gray-950 p-3 text-sm leading-6 ${FOCUS}`}
            value={question}
            maxLength={8000}
            disabled={busy || answering}
            placeholder="What should I prioritize before trying to win?"
            onChange={(event) => onQuestionChange(event.target.value)}
            onKeyDown={keyboardSend}
          />
        </label>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            type="submit"
            className={PRIMARY}
            disabled={busy || answering || !question.trim()}
          >
            {answering ? "Answering…" : "Send question"}
          </button>
          <p className="text-xs leading-5 text-gray-400">
            Enter to send; Shift+Enter for a new line. Failed answers leave your question here.
          </p>
        </div>
        {answering && (
          <p role="status" aria-live="polite" className="text-sm text-indigo-100">
            The Tutor is answering with the current saved list.
          </p>
        )}
      </form>
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
    </section>
  );
}

function Chapter({ chapter }: { chapter: TutorChapterResponse }) {
  return (
    <article
      aria-label={chapter.current ? "Current deck chapter" : `Archived chapter ${chapter.sequence}`}
      className="min-w-0 space-y-3 rounded-xl border border-white/10 p-4"
    >
      <div>
        <h4 className="font-semibold text-white">
          {chapter.current ? "Current deck chapter" : `Archived chapter ${chapter.sequence}`}
        </h4>
        <p className="mt-1 text-xs leading-5 text-gray-400">
          {chapter.current ? "Current saved teaching context" : "read-only historical context"} ·{" "}
          {chapter.mode === "commander" ? "Commander" : "cEDH"}
        </p>
      </div>
      {chapter.handoff && (
        <div className="rounded-lg bg-indigo-300/5 p-3">
          <h5 className="text-sm font-medium text-indigo-100">Lernübergabe</h5>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-gray-300">
            {chapter.handoff}
          </p>
        </div>
      )}
      {(chapter.handoff_status === "pending" || chapter.handoff_status === "running") && (
        <p role="status" className="text-sm text-indigo-100">
          Preparing the Lernübergabe; current deck facts remain available.
        </p>
      )}
      {chapter.handoff_status === "failed" && (
        <p role="alert" className="text-sm leading-6 text-amber-200">
          {chapter.handoff_error ??
            "Lernübergabe unavailable; current deck facts remain available."}
        </p>
      )}
      {chapter.turns.length === 0 ? (
        <p className="text-sm text-gray-400">No questions in this chapter yet.</p>
      ) : (
        <ol className="space-y-3">
          {chapter.turns.map((turn) => (
            <Turn key={turn.id} turn={turn} />
          ))}
        </ol>
      )}
    </article>
  );
}

function Turn({ turn }: { turn: TutorTurnResponse }) {
  return (
    <li className="min-w-0 space-y-3 rounded-lg bg-white/[0.025] p-3">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          You{turn.card_name ? ` · ${turn.card_name}` : ""}
        </p>
        <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-gray-100">
          {turn.question}
        </p>
      </div>
      {turn.answer && (
        <div className="border-t border-white/10 pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-indigo-200">Tutor</p>
          <div className="mt-1">
            <TutorMarkdown>{turn.answer}</TutorMarkdown>
          </div>
        </div>
      )}
      {turn.status === "running" && (
        <p role="status" className="text-sm text-indigo-100">
          Answering…
        </p>
      )}
      {turn.error && (
        <p role="alert" className="break-words text-sm leading-6 text-red-200">
          {turn.error}
        </p>
      )}
    </li>
  );
}
