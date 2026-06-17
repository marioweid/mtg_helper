"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { CardHover } from "@/components/card-hover";
import { CoachDeckWorkspace } from "@/components/coach-deck-workspace";
import { ManaCost } from "@/components/mana-cost";
import { DeckDetailSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import { STAGE_DEFAULTS } from "@/lib/constants";
import type {
  AnalysisCardHit,
  CommanderCoachProgressEvent,
  CommanderCoachResponse,
  CardResponse,
  DeckDetailResponse,
  DoctorSwap,
} from "@/lib/types";

type CoachMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; result: CommanderCoachResponse };

function CardSuggestionTile({
  card,
  onAdd,
  busy,
}: {
  card: AnalysisCardHit;
  onAdd: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-zinc-950 p-3 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <CardHover name={card.name} className="font-semibold text-white">
            {card.name}
          </CardHover>
          {card.type_line && <div className="mt-1 text-xs text-gray-500">{card.type_line}</div>}
        </div>
        {card.mana_cost && <ManaCost cost={card.mana_cost} />}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {(card.tags ?? []).slice(0, 4).map((tag) => (
          <span key={tag} className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px]">
            {tag.replace(/_/g, " ")}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={onAdd}
        disabled={busy}
        className="mt-3 w-full rounded-md bg-emerald-600 px-3 py-1.5 text-xs text-white"
      >
        {busy ? "Adding…" : "Add card"}
      </button>
    </div>
  );
}

function SwapCard({
  swap,
  onCut,
  onAdd,
  onApply,
  busy,
}: {
  swap: DoctorSwap;
  onCut: (name: string) => void;
  onAdd: (card: AnalysisCardHit) => void;
  onApply: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-300">Cut</div>
          <div className="space-y-2">
            {swap.remove.map((name) => (
              <div
                key={name}
                className="flex items-center justify-between gap-2 rounded-lg bg-red-950/20 p-2"
              >
                <CardHover name={name} className="text-sm font-medium text-red-100">
                  {name}
                </CardHover>
                <button
                  type="button"
                  onClick={() => onCut(name)}
                  disabled={busy}
                  className="rounded border border-red-400/40 px-2 py-0.5 text-[11px] text-red-200"
                >
                  Cut
                </button>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-300">
            Add
          </div>
          <div className="space-y-2">
            {swap.add.map((card) => (
              <div
                key={card.scryfall_id ?? card.name}
                className="flex items-center justify-between gap-2 rounded-lg bg-emerald-950/20 p-2"
              >
                <CardHover name={card.name} className="text-sm font-medium text-emerald-100">
                  {card.name}
                </CardHover>
                <button
                  type="button"
                  onClick={() => onAdd(card)}
                  disabled={busy}
                  className="rounded border border-emerald-400/40 px-2 py-0.5 text-[11px]"
                >
                  Add
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
      <p className="mt-3 text-sm text-gray-300">{swap.reason}</p>
      <button
        type="button"
        onClick={onApply}
        disabled={busy}
        className="mt-3 rounded-md bg-indigo-600 px-3 py-1.5 text-xs text-white"
      >
        {busy ? "Applying…" : "Apply exact swap"}
      </button>
    </div>
  );
}

function AssistantMessage({
  result,
  busy,
  onCut,
  onAdd,
  onApply,
}: {
  result: CommanderCoachResponse;
  busy: string | null;
  onCut: (name: string) => void;
  onAdd: (card: AnalysisCardHit) => void;
  onApply: (swap: DoctorSwap) => void;
}) {
  const doctor = result.doctor;
  if (!doctor) {
    return <div className="max-w-3xl rounded-xl border border-white/10 bg-white/5 p-4">{result.reply}</div>;
  }
  return (
    <div className="max-w-5xl space-y-6 rounded-xl border border-white/10 bg-white/5 p-5">
      <section>
        <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">Summary</div>
        <p className="text-gray-200">{doctor.summary}</p>
        <div className="mt-4 mb-1 text-xs uppercase tracking-wide text-gray-500">Game plan</div>
        <p className="text-gray-300">{doctor.game_plan}</p>
        <div className="mt-3 text-xs text-gray-500">Tool calls: {doctor.tool_call_count}</div>
      </section>

      {doctor.findings.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-white">Findings</h2>
          <div className="grid gap-3 xl:grid-cols-2">
            {doctor.findings.map((finding, i) => (
              <div key={`${finding.title}-${i}`} className="rounded-xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase text-gray-500">
                  {finding.category} · {finding.severity}
                </div>
                <h3 className="mt-1 font-semibold text-white">{finding.title}</h3>
                <p className="mt-1 text-sm text-gray-300">{finding.detail}</p>
                <p className="mt-2 text-xs text-gray-500">Evidence: {finding.evidence}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {doctor.swaps.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-white">Suggested swaps</h2>
          <div className="space-y-3">
            {doctor.swaps.map((swap, i) => (
              <SwapCard
                key={i}
                swap={swap}
                busy={busy != null}
                onCut={(name) => void onCut(name)}
                onAdd={(card) => void onAdd(card)}
                onApply={() => void onApply(swap)}
              />
            ))}
          </div>
        </section>
      )}

      {doctor.adds.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-white">Standalone adds</h2>
          <div className="grid gap-3 xl:grid-cols-2">
            {doctor.adds.map((add) => (
              <div key={add.card.scryfall_id ?? add.card.name}>
                <CardSuggestionTile
                  card={add.card}
                  busy={busy === `add:${add.card.scryfall_id}`}
                  onAdd={() => void onAdd(add.card)}
                />
                <p className="mt-2 text-xs text-gray-400">{add.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {doctor.cuts.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-white">Standalone cuts</h2>
          <div className="grid gap-2 xl:grid-cols-2">
            {doctor.cuts.map((cut) => (
              <div key={cut.card_name} className="rounded-xl border border-red-500/20 bg-red-950/10 p-3">
                <div className="flex items-center justify-between gap-2">
                  <CardHover name={cut.card_name} className="font-semibold text-red-100">
                    {cut.card_name}
                  </CardHover>
                  <button
                    type="button"
                    onClick={() => void onCut(cut.card_name)}
                    disabled={busy != null}
                    className="rounded border border-red-400/40 px-2 py-0.5 text-xs"
                  >
                    Cut
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-400">{cut.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default function CoachPage() {
  const params = useParams();
  const toast = useToast();
  const deckId = params["id"] as string;
  const [deck, setDeck] = useState<DeckDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState(
    "Doctor this deck. Tell me what to cut, what to add, and why.",
  );
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<CommanderCoachProgressEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDeck(await apiClient.getDeck(deckId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deck");
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  function transcriptWith(next: string): string {
    const previous = messages
      .slice(-6)
      .map((message) => {
        if (message.role === "user") return `User: ${message.content}`;
        return `Coach: ${message.result.reply}`;
      })
      .join("\n");
    return previous ? `${previous}\nUser: ${next}` : next;
  }

  async function runCoach() {
    const content = prompt.trim();
    if (!content) return;
    const userMessage: CoachMessage = { role: "user", content };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    setProgress([]);
    setError(null);
    try {
      const started = await apiClient.startCoachDeck(deckId, {
        mode: "auto",
        message: transcriptWith(content),
      });
      const events = new EventSource(`/api/v1/decks/${deckId}/coach/${started.job_id}/stream`);
      events.addEventListener("progress", (event) => {
        const data = JSON.parse((event as MessageEvent).data) as CommanderCoachProgressEvent;
        setProgress((prev) => [...prev, data]);
      });
      events.addEventListener("done", (event) => {
        const response = JSON.parse((event as MessageEvent).data) as CommanderCoachResponse;
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: response.reply, result: response },
        ]);
        setPrompt("");
        setLoading(false);
        events.close();
      });
      events.addEventListener("failed", (event) => {
        const data = JSON.parse((event as MessageEvent).data) as { message?: string };
        setError(data.message ?? "Commander Coach failed");
        setLoading(false);
        events.close();
      });
      events.onerror = () => {
        setError("Commander Coach stream disconnected");
        setLoading(false);
        events.close();
      };
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Commander Coach failed");
      setLoading(false);
    }
  }

  async function addSearchCard(card: CardResponse) {
    setBusy(`add:${card.scryfall_id}`);
    try {
      await apiClient.addCard(deckId, { card_scryfall_id: card.scryfall_id, added_by: "user" });
      toast.push(`Added ${card.name}`, "success");
      await load();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to add card", "error");
    } finally {
      setBusy(null);
    }
  }

  async function addCard(card: AnalysisCardHit) {
    if (!card.scryfall_id) {
      toast.push(`${card.name} is missing a card id`, "error");
      return;
    }
    setBusy(`add:${card.scryfall_id}`);
    try {
      await apiClient.addCard(deckId, { card_scryfall_id: card.scryfall_id, added_by: "ai" });
      toast.push(`Added ${card.name}`, "success");
      await load();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to add card", "error");
    } finally {
      setBusy(null);
    }
  }

  async function cutCard(name: string) {
    const card = deck?.cards.find((c) => c.name === name);
    if (!card) {
      toast.push(`${name} is not in this deck`, "error");
      return;
    }
    setBusy(`cut:${card.scryfall_id}`);
    try {
      await apiClient.removeCard(deckId, card.scryfall_id);
      toast.push(`Cut ${name}`, "success");
      await load();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to cut card", "error");
    } finally {
      setBusy(null);
    }
  }

  async function applySwap(swap: DoctorSwap) {
    setBusy(`swap:${swap.remove.join("|")}`);
    try {
      for (const name of swap.remove) {
        const card = deck?.cards.find((c) => c.name === name);
        if (card) await apiClient.removeCard(deckId, card.scryfall_id);
      }
      for (const card of swap.add) {
        if (card.scryfall_id) {
          await apiClient.addCard(deckId, { card_scryfall_id: card.scryfall_id, added_by: "ai" });
        }
      }
      toast.push("Applied swap", "success");
      await load();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to apply swap", "error");
    } finally {
      setBusy(null);
    }
  }

  if (error && !deck) return <p className="text-red-400">{error}</p>;
  if (!deck) return <DeckDetailSkeleton />;

  const stageTargets = { ...STAGE_DEFAULTS, ...deck.stage_targets };

  return (
    <div className="fixed inset-x-0 bottom-0 top-[53px] z-30 flex flex-col overflow-hidden bg-zinc-950">
      <div className="shrink-0 px-2 py-2 sm:px-3 lg:px-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold text-white">Commander Coach</h1>
          <Link href={`/decks/${deck.id}`} className="truncate text-sm text-gray-400 hover:text-white">
            {deck.name}
          </Link>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 px-3 pb-3 sm:px-4 lg:grid-cols-[minmax(0,1fr)_460px] lg:px-6">
        <main className="flex min-h-0 flex-col rounded-2xl border border-white/10 bg-zinc-950/50">
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
            {messages.length === 0 && prompt.trim() && (
              <div className="ml-auto max-w-2xl rounded-2xl bg-indigo-600/20 px-4 py-3 text-sm">
                {prompt}
              </div>
            )}

            {messages.map((message, index) =>
              message.role === "user" ? (
                <div
                  key={index}
                  className="ml-auto max-w-2xl rounded-2xl bg-indigo-600/20 px-4 py-3 text-sm"
                >
                  {message.content}
                </div>
              ) : (
                <AssistantMessage
                  key={index}
                  result={message.result}
                  busy={busy}
                  onCut={cutCard}
                  onAdd={addCard}
                  onApply={applySwap}
                />
              ),
            )}

            {loading && (
              <div className="max-w-2xl rounded-2xl border border-indigo-400/20 bg-indigo-950/20 p-4 text-sm">
                <div className="mb-2 font-medium text-indigo-100">Coach is working…</div>
                <div className="space-y-1 text-xs text-gray-300">
                  {progress.length === 0 ? (
                    <div>Starting…</div>
                  ) : (
                    progress.map((item, index) => <div key={index}>• {item.message}</div>)
                  )}
                </div>
              </div>
            )}

            {messages.length === 0 && !loading && (
              <div className="max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-5">
                <h2 className="font-semibold text-white">Ask the Coach</h2>
                <p className="mt-2 text-sm text-gray-400">
                  Run a deck doctor pass, ask for bangers, or request specific constraints like
                  preserving your commander engine.
                </p>
              </div>
            )}

          </div>

          <div className="border-t border-white/10 p-3">
            <div className="flex gap-2">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm"
                placeholder="Ask the Coach…"
              />
              <button
                type="button"
                onClick={() => void runCoach()}
                disabled={loading}
                className="self-end rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {loading ? "Thinking…" : "Send"}
              </button>
            </div>
            {error && <p className="mt-2 text-sm text-red-300">{error}</p>}
          </div>
        </main>

        <aside className="hidden min-h-0 overflow-hidden rounded-xl border border-white/10 bg-zinc-950/60 p-3 lg:block">
          <CoachDeckWorkspace
            cards={deck.cards}
            commander={deck.commander_card}
            stageTargets={stageTargets}
            manaCurve={deck.mana_curve}
            onRemove={(scryfallId) => void apiClient.removeCard(deck.id, scryfallId).then(load)}
            onSetQuantity={(scryfallId, quantity) =>
              void apiClient.updateCardQuantity(deck.id, scryfallId, quantity).then(load)
            }
            onAddCard={(card) => void addSearchCard(card)}
          />
        </aside>
      </div>
    </div>
  );
}
