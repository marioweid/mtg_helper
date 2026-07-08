"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ArchetypeChipPicker } from "@/components/archetype-chip-picker";
import { ManaSymbols } from "@/components/mana-symbols";
import { PageHeader } from "@/components/page-header";
import { apiClient } from "@/lib/api";
import { archetypeLabel, BRACKET_LABELS, COLOR_SYMBOLS } from "@/lib/constants";
import { MECHANIC_TAGS } from "@/lib/mechanics";
import type {
  CommanderSuggestIntent,
  CommanderSuggestion,
  DescribeMessage,
} from "@/lib/types";

type Message = DescribeMessage;
type Rerank = (next: CommanderSuggestIntent) => void;

const COLORS = ["W", "U", "B", "R", "G"] as const;
const TEXT_INPUT_CLASS = [
  "min-w-0 flex-1 rounded-lg border border-white/20 bg-white/5 px-3 py-2",
  "text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none",
].join(" ");
const PRIMARY_BUTTON_CLASS = [
  "rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors",
  "hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50",
].join(" ");
const PANEL_CLASS = "rounded-xl border border-white/10 bg-white/5 p-4";
const COLOR_BUTTON_BASE =
  "inline-flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold transition";
const COMMANDER_CARD_CLASS = [
  "flex min-h-[420px] flex-col overflow-hidden rounded-xl border border-white/10",
  "bg-white/5",
].join(" ");
const COMMANDER_ACTION_CLASS = [
  "mt-auto rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white",
  "transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50",
].join(" ");
const ERROR_CLASS = [
  "mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3",
  "text-sm text-red-400",
].join(" ");
const EMPTY_RESULTS_CLASS = [
  "rounded-xl border border-white/10 bg-white/5 p-8 text-center",
  "text-sm text-gray-500",
].join(" ");
const IMAGE_FALLBACK_CLASS = [
  "flex aspect-[5/7] items-center justify-center bg-white/10 px-4 text-center",
  "text-sm text-gray-400",
].join(" ");

function emptyIntent(): CommanderSuggestIntent {
  return {
    archetype_tags: [],
    mechanic_tags: [],
    traits: [],
    token_types: [],
    color_identity: null,
    excluded_colors: [],
    bracket: 3,
    direction: "",
    must_have: [],
    avoid: [],
  };
}

export default function CommanderSuggestPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [intent, setIntent] = useState<CommanderSuggestIntent>(emptyIntent);
  const [commanders, setCommanders] = useState<CommanderSuggestion[]>([]);
  const [stageTargets, setStageTargets] = useState<Record<string, number> | null>(null);
  const [suggestedName, setSuggestedName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creatingId, setCreatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runTurn(message: string, override: CommanderSuggestIntent | null) {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.suggestCommanders({
        history: messages,
        message,
        intent_override: override,
        limit: 8,
      });
      setIntent(res.intent);
      setCommanders(res.commanders);
      setStageTargets(res.stage_targets);
      setSuggestedName(res.suggested_name);
      updateMessages(message, res.reply);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to suggest commanders.");
    } finally {
      setLoading(false);
    }
  }

  function updateMessages(message: string, reply: string) {
    if (message.trim()) {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: message },
        { role: "assistant", content: reply },
      ]);
    } else if (messages.length === 0) {
      setMessages([{ role: "assistant", content: reply }]);
    }
  }

  function rerank(next: CommanderSuggestIntent) {
    setIntent(next);
    void runTurn("", next);
  }

  async function createDeck(suggestion: CommanderSuggestion) {
    setCreatingId(suggestion.card.scryfall_id);
    setError(null);
    try {
      const deck = await apiClient.createDeck({
        commander_scryfall_id: suggestion.card.scryfall_id,
        name: suggestedName ?? `${suggestion.card.name} Brew`,
        description: intent.direction || null,
        bracket: intent.bracket,
        stage_targets: stageTargets,
        archetype_tags: [...intent.archetype_tags, ...intent.mechanic_tags],
      });
      router.push(`/decks/${deck.id}/build`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deck.");
      setCreatingId(null);
    }
  }

  return (
    <Shell onBack={() => router.push("/decks/new")}>
      <aside className="space-y-4">
        <ConversationPanel
          messages={messages}
          loading={loading}
          onSend={(message) => void runTurn(message, intent)}
        />
        <ColorPanel intent={intent} onChange={rerank} />
        <BracketPanel intent={intent} onChange={rerank} />
        <KeywordPanel intent={intent} onChange={rerank} />
      </aside>
      <CommanderResults
        commanders={commanders}
        error={error}
        creatingId={creatingId}
        onCreate={(suggestion) => void createDeck(suggestion)}
      />
    </Shell>
  );
}

function Shell({ children, onBack }: { children: React.ReactNode; onBack: () => void }) {
  return (
    <div className="mx-auto max-w-7xl">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-block text-sm text-gray-500 transition-colors hover:text-gray-300"
      >
        Back
      </button>
      <PageHeader
        title="Suggest a commander"
        subtitle="Describe the deck you want. The top commanders update as the plan sharpens."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(320px,420px)_1fr]">{children}</div>
    </div>
  );
}

function ConversationPanel({
  messages,
  loading,
  onSend,
}: {
  messages: Message[];
  loading: boolean;
  onSend: (message: string) => void;
}) {
  const [input, setInput] = useState("");
  const submit = () => {
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    onSend(message);
  };
  return (
    <section className={PANEL_CLASS}>
      <h2 className="mb-3 text-sm font-semibold text-white">Conversation</h2>
      <MessageList messages={messages} />
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="What do you want to play?"
          disabled={loading}
          className={TEXT_INPUT_CLASS}
        />
        <button
          type="button"
          onClick={submit}
          disabled={loading || !input.trim()}
          className={PRIMARY_BUTTON_CLASS}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </section>
  );
}

function MessageList({ messages }: { messages: Message[] }) {
  if (messages.length === 0) {
    return (
      <p className="mb-3 text-sm text-gray-500">
        Try "graveyard ETB value", "artifact sacrifice", or "big reanimator".
      </p>
    );
  }
  return (
    <div className="mb-3 max-h-80 space-y-3 overflow-y-auto">
      {messages.map((msg, index) => (
        <div
          key={`${msg.role}-${index}`}
          className={`rounded-lg px-3 py-2 text-sm ${
            msg.role === "user" ? "bg-indigo-600 text-white" : "bg-white/10 text-gray-200"
          }`}
        >
          {msg.content}
        </div>
      ))}
    </div>
  );
}

function ColorPanel({ intent, onChange }: { intent: CommanderSuggestIntent; onChange: Rerank }) {
  const selected = useMemo(() => new Set(intent.color_identity ?? []), [intent.color_identity]);
  return (
    <section className={PANEL_CLASS}>
      <h2 className="mb-3 text-sm font-semibold text-white">Color identity</h2>
      <div className="flex flex-wrap gap-2">
        {COLORS.map((color) => (
          <ColorButton
            key={color}
            color={color}
            active={selected.has(color)}
            onClick={() => onChange(toggleColor(intent, color))}
          />
        ))}
      </div>
    </section>
  );
}

function ColorButton({
  color,
  active,
  onClick,
}: {
  color: string;
  active: boolean;
  onClick: () => void;
}) {
  const sym = COLOR_SYMBOLS[color] ?? { bg: "bg-gray-200", text: "text-gray-800", label: color };
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${COLOR_BUTTON_BASE} ${
        active ? `${sym.bg} ${sym.text} ring-2 ring-indigo-400` : "bg-white/10 text-gray-400"
      }`}
      title={color}
    >
      {color}
    </button>
  );
}

function toggleColor(intent: CommanderSuggestIntent, color: string): CommanderSuggestIntent {
  const current = intent.color_identity ?? [];
  const next = current.includes(color)
    ? current.filter((item) => item !== color)
    : [...current, color];
  return { ...intent, color_identity: next.length > 0 ? next : null };
}

function BracketPanel({ intent, onChange }: { intent: CommanderSuggestIntent; onChange: Rerank }) {
  return (
    <section className={PANEL_CLASS}>
      <span className="mb-2 block text-sm font-semibold text-white">Power Level</span>
      <div className="grid grid-cols-2 gap-2">
        {([1, 2, 3, 4] as const).map((bracket) => (
          <button
            key={bracket}
            type="button"
            onClick={() => onChange({ ...intent, bracket })}
            className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
              intent.bracket === bracket
                ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
            }`}
          >
            {BRACKET_LABELS[bracket]}
          </button>
        ))}
      </div>
    </section>
  );
}

function KeywordPanel({ intent, onChange }: { intent: CommanderSuggestIntent; onChange: Rerank }) {
  return (
    <section className={PANEL_CLASS}>
      <h2 className="mb-3 text-sm font-semibold text-white">Inferred keywords</h2>
      <ArchetypeChipPicker
        value={[...intent.archetype_tags, ...intent.mechanic_tags]}
        onChange={(tags) =>
          onChange({
            ...intent,
            archetype_tags: tags.filter((tag) => !MECHANIC_TAGS.includes(tag)),
            mechanic_tags: tags.filter((tag) => MECHANIC_TAGS.includes(tag)),
          })
        }
      />
    </section>
  );
}

function CommanderResults({
  commanders,
  error,
  creatingId,
  onCreate,
}: {
  commanders: CommanderSuggestion[];
  error: string | null;
  creatingId: string | null;
  onCreate: (suggestion: CommanderSuggestion) => void;
}) {
  return (
    <main>
      {error && <p className={ERROR_CLASS}>{error}</p>}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Top commanders</h2>
        <span className="text-xs text-gray-500">{commanders.length}/8 shown</span>
      </div>
      {commanders.length === 0 ? (
        <EmptyResults />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {commanders.map((suggestion) => (
            <CommanderCard
              key={suggestion.card.scryfall_id}
              suggestion={suggestion}
              creating={creatingId === suggestion.card.scryfall_id}
              onCreate={() => onCreate(suggestion)}
            />
          ))}
        </div>
      )}
    </main>
  );
}

function EmptyResults() {
  return (
    <div className={EMPTY_RESULTS_CLASS}>
      Tell me what kind of deck you want and I will rank local Commander-legal options.
    </div>
  );
}

function CommanderCard({
  suggestion,
  creating,
  onCreate,
}: {
  suggestion: CommanderSuggestion;
  creating: boolean;
  onCreate: () => void;
}) {
  return (
    <article className={COMMANDER_CARD_CLASS}>
      <CommanderImage suggestion={suggestion} />
      <div className="flex flex-1 flex-col gap-3 p-4">
        <CommanderHeading suggestion={suggestion} />
        <ReasonChips suggestion={suggestion} />
        <p className="line-clamp-4 text-xs leading-relaxed text-gray-400">
          {suggestion.card.oracle_text ?? suggestion.card.type_line ?? "No rules text."}
        </p>
        <button
          type="button"
          onClick={onCreate}
          disabled={creating}
          className={COMMANDER_ACTION_CLASS}
        >
          {creating ? "Creating..." : "Create deck & start building"}
        </button>
      </div>
    </article>
  );
}

function CommanderImage({ suggestion }: { suggestion: CommanderSuggestion }) {
  if (!suggestion.card.image_uri) {
    return (
      <div className={IMAGE_FALLBACK_CLASS}>
        {suggestion.card.name}
      </div>
    );
  }
  return (
    <img
      src={suggestion.card.image_uri}
      alt={suggestion.card.name}
      className="aspect-[5/7] w-full object-cover"
    />
  );
}

function CommanderHeading({ suggestion }: { suggestion: CommanderSuggestion }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-white">{suggestion.card.name}</h3>
      <div className="mt-1 flex items-center justify-between gap-2">
        <ManaSymbols colors={suggestion.card.color_identity} />
        <span className="text-xs text-gray-500">{Math.round(suggestion.score)} pts</span>
      </div>
    </div>
  );
}

function ReasonChips({ suggestion }: { suggestion: CommanderSuggestion }) {
  return (
    <div className="flex flex-wrap gap-1">
      {suggestion.score_reasons.slice(0, 4).map((reason) => (
        <span key={reason} className="rounded-full bg-white/10 px-2 py-1 text-xs text-gray-300">
          {reason}
        </span>
      ))}
      {suggestion.matched_tags.slice(0, 3).map((tag) => (
        <span
          key={tag}
          className="rounded-full bg-indigo-900/40 px-2 py-1 text-xs text-indigo-200"
        >
          {archetypeLabel(tag)}
        </span>
      ))}
    </div>
  );
}
