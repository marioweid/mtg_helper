"use client";

import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import { getStoredAccountId } from "@/lib/account";
import { CardSuggestionCard } from "@/components/card-suggestion";
import type { CardSuggestion, ChatResponse } from "@/lib/types";

type SuggestionStatus = "pending" | "accepted" | "rejected";

interface Message {
  role: "user" | "assistant";
  content: string;
  suggestions?: CardSuggestion[];
}

export default function ChatPage() {
  const params = useParams();
  const deckId = params["id"] as string;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [suggestInput, setSuggestInput] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionResults, setSuggestionResults] = useState<CardSuggestion[]>([]);
  const [suggestionStatuses, setSuggestionStatuses] = useState<Record<string, SuggestionStatus>>({});
  const [petCardNames, setPetCardNames] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const accountId = getStoredAccountId();
    if (!accountId) return;
    apiClient.listPreferences(accountId).then((prefs) => {
      const names = new Set(
        prefs
          .filter((p) => p.preference_type === "pet_card" && p.card_name)
          .map((p) => p.card_name as string),
      );
      setPetCardNames(names);
    }).catch(() => {/* non-critical */});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || sending) return;
    setInput("");
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    try {
      const res: ChatResponse = await apiClient.chat(deckId, msg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, suggestions: res.suggestions },
      ]);
    } catch (err) {
      const errMsg = err instanceof ApiError ? err.message : "Failed to send message";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${errMsg}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleSuggest(e: React.FormEvent) {
    e.preventDefault();
    const prompt = suggestInput.trim();
    if (!prompt || suggesting) return;
    setSuggesting(true);
    setSuggestionResults([]);
    setSuggestionStatuses({});
    try {
      const res = await apiClient.suggestCards(deckId, prompt);
      const seen = new Set<string>();
      const suggestions = res.suggestions.filter((s) => {
        if (seen.has(s.scryfall_id)) return false;
        seen.add(s.scryfall_id);
        return true;
      });
      setSuggestionResults(suggestions);
      const statuses: Record<string, SuggestionStatus> = {};
      for (const s of suggestions) statuses[s.scryfall_id] = "pending";
      setSuggestionStatuses(statuses);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to get suggestions");
    } finally {
      setSuggesting(false);
    }
  }

  async function handleAcceptSuggestion(s: CardSuggestion) {
    setSuggestionStatuses((prev) => ({ ...prev, [s.scryfall_id]: "accepted" }));
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: s.scryfall_id,
        category: s.category,
        added_by: "ai",
        ai_reasoning: s.reasoning,
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      setSuggestionStatuses((prev) => ({ ...prev, [s.scryfall_id]: "pending" }));
    }
  }

  async function handleRejectSuggestion(s: CardSuggestion) {
    setSuggestionStatuses((prev) => ({ ...prev, [s.scryfall_id]: "rejected" }));
    try {
      await apiClient.addFeedback(deckId, {
        card_scryfall_id: s.scryfall_id,
        feedback: "down",
      });
    } catch {
      // Non-critical
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Chat</h1>
        <Link
          href={`/decks/${deckId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          Back to deck
        </Link>
      </div>

      {/* Chat */}
      <div className="rounded-xl border border-white/10 bg-white/5">
        <div className="flex flex-col gap-4 p-4 min-h-[300px] max-h-[50vh] sm:max-h-[500px] overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-8">
              Ask anything about your deck, strategy, or card choices.
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex flex-col gap-2 ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-white/10 text-gray-200"
                }`}
              >
                {msg.content}
              </div>
              {msg.suggestions && msg.suggestions.length > 0 && (
                <InlineSuggestions suggestions={msg.suggestions} deckId={deckId} petCardNames={petCardNames} />
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <form onSubmit={handleSend} className="flex gap-2 border-t border-white/10 p-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your deck..."
            disabled={sending}
            className="flex-1 rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
          >
            {sending ? "..." : "Send"}
          </button>
        </form>
      </div>

      {/* Free-form suggest */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="mb-3 font-semibold text-white">Get Suggestions</h2>
        <form onSubmit={handleSuggest} className="flex gap-2">
          <input
            type="text"
            value={suggestInput}
            onChange={(e) => setSuggestInput(e.target.value)}
            placeholder="e.g. more card draw, cheaper removal..."
            disabled={suggesting}
            className="flex-1 rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={suggesting || !suggestInput.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
          >
            {suggesting ? "..." : "Suggest"}
          </button>
        </form>

        {suggestionResults.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
            {suggestionResults.map((s) => (
              <CardSuggestionCard
                key={s.scryfall_id}
                suggestion={s}
                status={suggestionStatuses[s.scryfall_id] ?? "pending"}
                onAccept={() => void handleAcceptSuggestion(s)}
                onReject={() => void handleRejectSuggestion(s)}
                isPetCard={petCardNames.has(s.name)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function InlineSuggestions({
  suggestions,
  deckId,
  petCardNames,
}: {
  suggestions: CardSuggestion[];
  deckId: string;
  petCardNames: Set<string>;
}) {
  const deduped = suggestions.filter((s, i) => suggestions.findIndex((x) => x.scryfall_id === s.scryfall_id) === i);
  const [statuses, setStatuses] = useState<Record<string, SuggestionStatus>>(() => {
    const s: Record<string, SuggestionStatus> = {};
    for (const c of deduped) s[c.scryfall_id] = "pending";
    return s;
  });

  async function accept(s: CardSuggestion) {
    setStatuses((prev) => ({ ...prev, [s.scryfall_id]: "accepted" }));
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: s.scryfall_id,
        category: s.category,
        added_by: "ai",
        ai_reasoning: s.reasoning,
      });
    } catch {
      setStatuses((prev) => ({ ...prev, [s.scryfall_id]: "pending" }));
    }
  }

  async function reject(s: CardSuggestion) {
    setStatuses((prev) => ({ ...prev, [s.scryfall_id]: "rejected" }));
    try {
      await apiClient.addFeedback(deckId, {
        card_scryfall_id: s.scryfall_id,
        feedback: "down",
      });
    } catch {
      // Non-critical
    }
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {deduped.map((s) => (
        <CardSuggestionCard
          key={s.scryfall_id}
          suggestion={s}
          status={statuses[s.scryfall_id] ?? "pending"}
          onAccept={() => void accept(s)}
          onReject={() => void reject(s)}
          isPetCard={petCardNames.has(s.name)}
        />
      ))}
    </div>
  );
}
