"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import { CardHover } from "@/components/card-hover";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { CardSuggestion, ChatTurn } from "@/lib/types";

interface Turn extends ChatTurn {
  suggestions?: CardSuggestion[];
}

export default function DeckChatPage() {
  const params = useParams();
  const deckId = params["id"] as string;
  const toast = useToast();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getChatHistory(deckId)
      .then((data) => {
        if (!cancelled) setTurns(data.turns);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err instanceof ApiError ? err.message : "Failed to load chat history";
        toast.push(msg, "error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deckId, toast]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, sending]);

  const send = useCallback(async () => {
    const text = message.trim();
    if (!text || sending) return;
    setSending(true);
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setMessage("");
    try {
      const res = await apiClient.chatWithDeck(deckId, text);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, suggestions: res.suggestions },
      ]);
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Chat failed", "error");
      setTurns((prev) => prev.slice(0, -1));
      setMessage(text);
    } finally {
      setSending(false);
    }
  }, [deckId, message, sending, toast]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Deck chat</h1>
        <Link
          href={`/decks/${deckId}`}
          className="text-sm text-gray-400 transition-colors hover:text-white"
        >
          ← Back to deck
        </Link>
      </div>

      <div className="flex min-h-[60vh] flex-col gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
        {loading ? (
          <p className="text-center text-sm text-gray-500">Loading conversation…</p>
        ) : turns.length === 0 ? (
          <p className="my-auto text-center text-sm text-gray-500">
            Ask anything about this deck — synergies, cuts, mana base, ramp counts.
          </p>
        ) : (
          turns.map((t, i) => <TurnBubble key={i} turn={t} />)
        )}
        {sending ? (
          <div className="text-xs italic text-gray-500">Assistant is thinking…</div>
        ) : null}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask about this deck…"
          disabled={sending}
          className="flex-1 rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-400 focus:outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={sending || message.trim().length === 0}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function TurnBubble({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-indigo-600 text-white"
            : "border border-white/10 bg-zinc-900/70 text-gray-100"
        }`}
      >
        <p className="whitespace-pre-line">{turn.content}</p>
        {turn.suggestions && turn.suggestions.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {turn.suggestions.map((s) => (
              <CardHover key={s.scryfall_id} name={s.name} imageUri={s.image_uri}>
                <span className="rounded-full border border-indigo-400/40 bg-indigo-900/40 px-2 py-0.5 text-xs text-indigo-100">
                  {s.name}
                </span>
              </CardHover>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
