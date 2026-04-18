"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CardSearch } from "@/components/card-search";
import { apiClient } from "@/lib/api";
import { getOrCreateAccountId } from "@/lib/account";
import { BRACKET_LABELS } from "@/lib/constants";
import type { CardResponse, CollectionResponse, DescribeMessage } from "@/lib/types";

type CollectionMode = "off" | "inherit" | "on";

type Phase = "select" | "chat" | "confirm";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function NewDeckPage() {
  const router = useRouter();

  // Phase 1: selection state
  const [phase, setPhase] = useState<Phase>("select");
  const [commander, setCommander] = useState<CardResponse | null>(null);
  const [partner, setPartner] = useState<CardResponse | null>(null);
  const [bracket, setBracket] = useState(3);

  // Phase 2: chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // Phase 3: confirm state
  const [deckName, setDeckName] = useState("");
  const [description, setDescription] = useState("");
  const [stageTargets, setStageTargets] = useState<Record<string, number> | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Collection override state
  const [collectionMode, setCollectionMode] = useState<CollectionMode>("inherit");
  const [collectionId, setCollectionId] = useState("");
  const [collectionThreshold, setCollectionThreshold] = useState<number | null>(null);
  const [collections, setCollections] = useState<CollectionResponse[]>([]);

  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function loadCollections() {
      try {
        const id = await getOrCreateAccountId();
        if (!id) return;
        const cols = await apiClient.listCollections(id);
        setCollections(cols);
      } catch {
        // Collections are optional; silently skip.
      }
    }
    void loadCollections();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function startChat() {
    if (!commander) {
      setError("Please select a commander.");
      return;
    }
    setError(null);
    setPhase("chat");
    setChatLoading(true);
    try {
      const res = await apiClient.describeDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        bracket,
        history: [],
        message: "",
      });
      setMessages([{ role: "assistant", content: res.reply }]);
      if (res.done) {
        handleAgentDone(res.suggested_name, res.description, res.stage_targets);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start agent.");
      setPhase("select");
    } finally {
      setChatLoading(false);
    }
  }

  function handleAgentDone(
    suggestedName: string | null,
    desc: string | null,
    targets: Record<string, number> | null,
  ) {
    setDeckName(suggestedName ?? (commander ? `${commander.name} Deck` : ""));
    setDescription(desc ?? "");
    setStageTargets(targets);
    setPhase("confirm");
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
      const res = await apiClient.describeDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        bracket,
        history: history.slice(0, -1), // last message is the current user message
        message: userMsg,
      });
      setMessages([...nextMessages, { role: "assistant", content: res.reply }]);
      if (res.done) {
        handleAgentDone(res.suggested_name, res.description, res.stage_targets);
      }
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
      const ownerId = await getOrCreateAccountId();
      const deck = await apiClient.createDeck({
        commander_scryfall_id: commander.scryfall_id,
        partner_scryfall_id: partner?.scryfall_id ?? null,
        name: deckName.trim() || `${commander.name} Deck`,
        description: description.trim() || null,
        bracket,
        owner_id: ownerId || null,
        stage_targets: stageTargets,
        collection_mode: collectionMode,
        collection_id: collectionMode === "on" && collectionId ? collectionId : null,
        collection_threshold: collectionMode === "on" ? collectionThreshold : null,
      });
      router.push(`/decks/${deck.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deck.");
      setSubmitting(false);
    }
  }

  if (phase === "select") {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-2xl font-bold text-white">New Deck</h1>

        <div className="flex flex-col gap-6">
          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h2 className="mb-4 font-semibold text-white">Commander</h2>
            <CardSearch
              placeholder="Search for your commander..."
              typeFilter="Legendary Creature"
              onSelect={(card) => setCommander(card)}
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
                  className={`rounded-lg border px-3 py-2 text-xs text-left transition-colors ${
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
            onClick={startChat}
            disabled={!commander}
            className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Start Building
          </button>
        </div>
      </div>
    );
  }

  if (phase === "chat") {
    return (
      <div className="mx-auto max-w-2xl flex flex-col h-[calc(100vh-8rem)]">
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setPhase("select")}
            className="text-sm text-gray-400 hover:text-white transition-colors"
          >
            ← Back
          </button>
          <h1 className="text-xl font-bold text-white">
            Building {commander?.name} Deck
          </h1>
          <span className="ml-auto text-xs text-gray-500">Bracket {bracket}</span>
        </div>

        <div className="flex-1 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-4 flex flex-col gap-4 min-h-0">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-white/10 text-gray-200"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex justify-start">
              <div className="bg-white/10 rounded-xl px-4 py-3">
                <span className="text-gray-400 text-sm animate-pulse">Thinking...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {error && (
          <p className="mt-2 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-2 text-sm text-red-400">
            {error}
          </p>
        )}

        <div className="mt-3 flex gap-2">
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
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </div>
    );
  }

  // phase === "confirm"
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-2 text-2xl font-bold text-white">Confirm Your Deck</h1>
      <p className="mb-8 text-sm text-gray-400">
        Review the strategy the agent synthesized. Edit anything before creating.
      </p>

      <div className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <div className="flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm text-gray-400" htmlFor="deck-name">
                Deck Name
              </label>
              <input
                id="deck-name"
                type="text"
                value={deckName}
                onChange={(e) => setDeckName(e.target.value)}
                className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm text-gray-400" htmlFor="deck-description">
                Strategy
              </label>
              <textarea
                id="deck-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={5}
                className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
              />
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Collection Filter</h2>
          <p className="mb-4 text-xs text-gray-500">
            Restrict AI suggestions to cards in a collection when building this deck.
          </p>
          <div className="mb-4 grid grid-cols-3 gap-2">
            {(["off", "inherit", "on"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setCollectionMode(mode)}
                className={`rounded-lg border px-3 py-2 text-xs capitalize transition-colors ${
                  collectionMode === mode
                    ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                    : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                }`}
              >
                {mode === "inherit" ? "Inherit (use account default)" : mode}
              </button>
            ))}
          </div>
          {collectionMode === "on" && (
            <div className="flex flex-col gap-4">
              <label className="block">
                <span className="text-sm font-medium text-white">Collection</span>
                <select
                  value={collectionId}
                  onChange={(e) => setCollectionId(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-gray-900 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">— Pick one —</option>
                  {collections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.card_count})
                    </option>
                  ))}
                </select>
              </label>
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-sm font-medium text-white">
                    Min score (blank = inherit)
                  </span>
                  <span className="w-10 text-right text-sm tabular-nums text-indigo-300">
                    {collectionThreshold === null ? "—" : collectionThreshold.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={collectionThreshold === null ? 0 : Math.round(collectionThreshold * 100)}
                  onChange={(e) => setCollectionThreshold(Number(e.target.value) / 100)}
                  className="w-full accent-indigo-500"
                />
                <button
                  type="button"
                  onClick={() => setCollectionThreshold(null)}
                  className="mt-1 text-xs text-gray-500 hover:text-white transition-colors"
                >
                  Clear (inherit from account)
                </button>
              </div>
            </div>
          )}
        </section>

        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>
            {commander?.name} · Bracket {bracket}
            {partner ? ` · Partner: ${partner.name}` : ""}
          </span>
          <button
            type="button"
            onClick={() => setPhase("chat")}
            className="text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            ← Back to chat
          </button>
        </div>

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={() => void createDeck()}
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Creating..." : "Create Deck & Start Building"}
        </button>
      </div>
    </div>
  );
}
