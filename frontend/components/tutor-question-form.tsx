"use client";

import type { FormEvent, KeyboardEvent } from "react";

import type { TutorCardFact } from "@/lib/types";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const PRIMARY =
  "min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold " +
  `text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;

interface TutorQuestionFormProps {
  currentCards: TutorCardFact[];
  question: string;
  selectedCard: string;
  busy: boolean;
  answering: boolean;
  onQuestionChange: (question: string) => void;
  onCardChange: (cardName: string) => void;
  onAsk: () => void;
}

export function TutorQuestionForm({
  currentCards,
  question,
  selectedCard,
  busy,
  answering,
  onQuestionChange,
  onCardChange,
  onAsk,
}: TutorQuestionFormProps) {
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
        <button type="submit" className={PRIMARY} disabled={busy || answering || !question.trim()}>
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
  );
}
