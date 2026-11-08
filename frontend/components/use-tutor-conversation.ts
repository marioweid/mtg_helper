"use client";

import { useCallback, useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { apiClient } from "@/lib/api";
import type { TutorConversationResponse } from "@/lib/types";

type ErrorState = Dispatch<SetStateAction<string | null>>;

export function useTutorConversation(deckId: string, setError: ErrorState) {
  const [conversation, setConversation] = useState<TutorConversationResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [selectedCard, setSelectedCard] = useState("");
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [pendingTurnId, setPendingTurnId] = useState<string | null>(null);
  const [conversationBusy, setConversationBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await apiClient.getTutorConversation(deckId);
      setConversation(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor conversation could not load");
      return null;
    }
  }, [deckId, setError]);

  useEffect(() => {
    void load();
  }, [load]);
  useConversationPolling({
    conversation,
    pendingTurnId,
    load,
    setQuestion,
    setPendingTurnId,
  });

  async function run(action: () => Promise<TutorConversationResponse>, failure: string) {
    setConversationBusy(true);
    try {
      const next = await action();
      setConversation(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : failure);
      return null;
    } finally {
      setConversationBusy(false);
    }
  }

  async function onAsk() {
    const draft = question.trim();
    if (!draft) return;
    const next = await run(
      () =>
        apiClient.askTutorQuestion(deckId, {
          request_key: crypto.randomUUID(),
          question: draft,
          ...(selectedCard ? { card_name: selectedCard } : {}),
        }),
      "Tutor question could not be sent",
    );
    const pending = next?.chapters
      .flatMap((chapter) => chapter.turns)
      .filter((turn) => turn.status === "running")
      .at(-1);
    setPendingTurnId(pending?.id ?? null);
  }

  async function onClearConversation() {
    const cleared = await run(
      () => apiClient.clearTutorConversation(deckId),
      "Tutor history could not be cleared",
    );
    if (cleared) {
      setSelectedChapterId(null);
      setPendingTurnId(null);
    }
  }

  async function onRetryHandoff(chapterId: string) {
    await run(
      () => apiClient.retryTutorHandoff(deckId, chapterId, { request_key: crypto.randomUUID() }),
      "Lernübergabe retry could not start",
    );
  }

  return {
    conversation,
    question,
    selectedCard,
    selectedChapterId,
    conversationBusy,
    load,
    onQuestionChange: setQuestion,
    onCardChange: setSelectedCard,
    onChapterChange: setSelectedChapterId,
    onAsk,
    onClearConversation,
    onRetryHandoff,
  };
}

function useConversationPolling({
  conversation,
  pendingTurnId,
  load,
  setQuestion,
  setPendingTurnId,
}: {
  conversation: TutorConversationResponse | null;
  pendingTurnId: string | null;
  load: () => Promise<TutorConversationResponse | null>;
  setQuestion: Dispatch<SetStateAction<string>>;
  setPendingTurnId: Dispatch<SetStateAction<string | null>>;
}) {
  useEffect(() => {
    if (!pendingTurnId || !conversation) return;
    const turn = conversation.chapters
      .flatMap((chapter) => chapter.turns)
      .find((candidate) => candidate.id === pendingTurnId);
    if (!turn || turn.status === "running") return;
    if (turn.status === "succeeded") setQuestion("");
    setPendingTurnId(null);
  }, [conversation, pendingTurnId, setPendingTurnId, setQuestion]);

  useEffect(() => {
    if (!hasActiveConversationWork(conversation)) return;
    let mounted = true;
    let timer = window.setTimeout(poll, 1000);
    async function poll() {
      const next = await load();
      if (mounted && hasActiveConversationWork(next)) timer = window.setTimeout(poll, 1000);
    }
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [conversation, load]);
}

function hasActiveConversationWork(conversation: TutorConversationResponse | null): boolean {
  return !!conversation?.chapters.some(
    (chapter) =>
      chapter.handoff_status === "pending" ||
      chapter.handoff_status === "running" ||
      chapter.turns.some((turn) => turn.status === "running"),
  );
}
