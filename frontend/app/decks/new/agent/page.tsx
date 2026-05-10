"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ArchetypeChipPicker } from "@/components/archetype-chip-picker";
import { CardSearch } from "@/components/card-search";
import { apiClient } from "@/lib/api";
import { BRACKET_LABELS } from "@/lib/constants";
import type { CardResponse, DescribeMessage } from "@/lib/types";

type Phase = "select" | "chat";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function AgentDeckPage() {
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("select");
  const [commander, setCommander] = useState<CardResponse | null>(null);
  const [partner, setPartner] = useState<CardResponse | null>(null);
  const [bracket, setBracket] = useState(3);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const [archetypeTags, setArchetypeTags] = useState<string[]>([]);
  const [stageTargets, setStageTargets] = useState<Record<string, number> | null>(null);
  const [deckName, setDeckName] = useState("");
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function startChat() {
    if (!commander) {
      setError("Pick a commander first.");
      return;
    }
    setError(null);
    setPhase("chat");
    setChatLoading(true);
    try {
      const res = await apiClient.extractKeywords({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        bracket,
        history: [],
        message: "",
      });
      setMessages([{ role: "assistant", content: res.reply }]);
      if (res.archetype_tags.length > 0) setArchetypeTags(res.archetype_tags);
      if (res.done) finalizeFromAgent(res.suggested_name, res.archetype_tags, res.stage_targets);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start agent.");
      setPhase("select");
    } finally {
      setChatLoading(false);
    }
  }

  function finalizeFromAgent(
    suggestedName: string | null,
    tags: string[],
    targets: Record<string, number> | null,
  ) {
    setDeckName(suggestedName ?? (commander ? `${commander.name} Deck` : ""));
    setArchetypeTags(tags);
    setStageTargets(targets);
    setDone(true);
  }

  async function sendMessage() {
    if (!input.trim() || chatLoading || !commander) return;
    const userMsg = input.trim();
    setInput("");

    const nextMessages: Message[] = [...messages, { role: "user", content: userMsg }];
    setMessages(nextMessages);
    setChatLoading(true);
    setError(null);

    const history: DescribeMessage[] = nextMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const res = await apiClient.extractKeywords({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        bracket,
        history: history.slice(0, -1),
        message: userMsg,
      });
      setMessages([...nextMessages, { role: "assistant", content: res.reply }]);
      if (res.archetype_tags.length > 0) setArchetypeTags(res.archetype_tags);
      if (res.done) finalizeFromAgent(res.suggested_name, res.archetype_tags, res.stage_targets);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setChatLoading(false);
    }
  }

  async function createDeck() {
    if (!commander) return;
    setSubmitting(true);
    setError(null);
    try {
      const deck = await apiClient.createDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        name: deckName.trim() || `${commander.name} Deck`,
        bracket,
        stage_targets: stageTargets,
        archetype_tags: archetypeTags,
      });
      router.push(`/decks/${deck.id}/build`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deck.");
      setSubmitting(false);
    }
  }

  if (phase === "select") {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => router.push("/decks/new")}
            className="text-sm text-gray-400 transition-colors hover:text-white"
          >
            ← Back
          </button>
          <h1 className="text-2xl font-bold text-white">Chat with the agent</h1>
        </div>
        <p className="mb-6 text-sm text-gray-400">
          The agent asks 1–3 short questions, then converges on archetype keywords. You can fine-
          tune the chips before creating the deck.
        </p>

        <div className="flex flex-col gap-6">
          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h2 className="mb-4 font-semibold text-white">Commander</h2>
            <CardSearch
              placeholder="Search for your commander..."
              typeFilter="Legendary Creature"
              onSelect={setCommander}
              selected={commander}
              onClear={() => setCommander(null)}
            />
          </section>

          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h2 className="mb-1 font-semibold text-white">Partner Commander</h2>
            <p className="mb-4 text-xs text-gray-500">Optional — only for commanders with Partner</p>
            <CardSearch
              placeholder="Search for partner commander..."
              typeFilter="Legendary Creature"
              onSelect={setPartner}
              selected={partner}
              onClear={() => setPartner(null)}
            />
          </section>

          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <span className="mb-2 block text-sm font-semibold text-white">Power Level</span>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {([1, 2, 3, 4] as const).map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setBracket(b)}
                  className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                    bracket === b
                      ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                      : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                  }`}
                >
                  {BRACKET_LABELS[b]}
                </button>
              ))}
            </div>
          </section>

          {error && (
            <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={() => void startChat()}
            disabled={!commander}
            className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Start chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-3xl flex-col gap-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPhase("select")}
          className="text-sm text-gray-400 transition-colors hover:text-white"
        >
          ← Back
        </button>
        <h1 className="text-xl font-bold text-white">Building {commander?.name} Deck</h1>
        <span className="ml-auto text-xs text-gray-500">Bracket {bracket}</span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user" ? "bg-indigo-600 text-white" : "bg-white/10 text-gray-200"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {chatLoading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-white/10 px-4 py-3">
              <span className="animate-pulse text-sm text-gray-400">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Live keywords {archetypeTags.length > 0 && `(${archetypeTags.length})`}
        </h2>
        {archetypeTags.length === 0 ? (
          <p className="text-xs text-gray-500">
            Keywords will appear here as the agent maps your description.
          </p>
        ) : (
          <ArchetypeChipPicker value={archetypeTags} onChange={setArchetypeTags} />
        )}
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}

      {done ? (
        <div className="flex flex-col gap-3 rounded-xl border border-indigo-500/30 bg-indigo-900/10 p-4">
          <label htmlFor="deck-name" className="text-sm font-semibold text-white">
            Deck name
          </label>
          <input
            id="deck-name"
            type="text"
            value={deckName}
            onChange={(e) => setDeckName(e.target.value)}
            className="rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="button"
            onClick={() => void createDeck()}
            disabled={submitting}
            className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Creating..." : "Create deck & start building"}
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            placeholder="Type your answer..."
            disabled={chatLoading}
            className="flex-1 rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => void sendMessage()}
            disabled={chatLoading || !input.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
