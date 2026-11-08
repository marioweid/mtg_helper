"use client";

import { useCallback, useEffect, useState } from "react";

import { TutorConversation } from "@/components/tutor-conversation";
import { TutorMarkdown } from "@/components/tutor-markdown";
import { apiClient } from "@/lib/api";
import type {
  DeckSummary,
  TutorConversationResponse,
  TutorMode,
  TutorReferenceDifferences,
  TutorReferencePreviewResponse,
  TutorReferenceRequest,
  TutorStateResponse,
} from "@/lib/types";

const FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950";
const PRIMARY =
  "min-h-11 touch-manipulation rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold " +
  `text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50 ${FOCUS}`;

interface TutorPanelProps {
  deckId: string;
}

interface TutorPanelViewProps {
  state: TutorStateResponse;
  busy: boolean;
  error: string | null;
  onMode: (mode: TutorMode) => void;
  onGenerate: () => void;
  referencePreview?: TutorReferencePreviewResponse | null;
  referenceNotice?: string | null;
  ownedDecks?: DeckSummary[];
  onReferencePreview?: (request: TutorReferenceRequest) => void;
  onReferenceConfirm?: () => void;
  onReferenceCancel?: () => void;
  onReferenceRemove?: () => void;
  onOwnedDecksLoad?: () => void;
  conversation?: TutorConversationResponse | null;
  question?: string;
  selectedCard?: string;
  selectedChapterId?: string | null;
  onQuestionChange?: (question: string) => void;
  onCardChange?: (cardName: string) => void;
  onChapterChange?: (chapterId: string) => void;
  onAsk?: () => void;
  onClearConversation?: () => void;
}

export function TutorPanel({ deckId }: TutorPanelProps) {
  const [state, setState] = useState<TutorStateResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referencePreview, setReferencePreview] = useState<TutorReferencePreviewResponse | null>(
    null,
  );
  const [referenceNotice, setReferenceNotice] = useState<string | null>(null);
  const [ownedDecks, setOwnedDecks] = useState<DeckSummary[]>([]);
  const [conversation, setConversation] = useState<TutorConversationResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [selectedCard, setSelectedCard] = useState("");
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [pendingTurnId, setPendingTurnId] = useState<string | null>(null);

  const load = useCallback(async (): Promise<TutorStateResponse | null> => {
    try {
      const next = await apiClient.getTutor(deckId);
      setState(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor could not load");
      return null;
    }
  }, [deckId]);

  const loadConversation = useCallback(async () => {
    try {
      const next = await apiClient.getTutorConversation(deckId);
      setConversation(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor conversation could not load");
      return null;
    }
  }, [deckId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state?.latest_run?.status !== "running") return;
    let active = true;
    let timer = window.setTimeout(poll, 1500);

    async function poll() {
      const next = await load();
      if (active && next?.latest_run?.status === "running") timer = window.setTimeout(poll, 1500);
    }
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [load, state?.latest_run?.status]);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    if (!pendingTurnId || !conversation) return;
    const turn = conversation.chapters
      .flatMap((chapter) => chapter.turns)
      .find((candidate) => candidate.id === pendingTurnId);
    if (!turn || turn.status === "running") return;
    if (turn.status === "succeeded") setQuestion("");
    setPendingTurnId(null);
  }, [conversation, pendingTurnId]);

  useEffect(() => {
    const active = conversation?.chapters.some(
      (chapter) =>
        chapter.handoff_status === "pending" ||
        chapter.handoff_status === "running" ||
        chapter.turns.some((turn) => turn.status === "running"),
    );
    if (!active) return;
    let mounted = true;
    let timer = window.setTimeout(poll, 1000);
    async function poll() {
      const next = await loadConversation();
      const stillActive = next?.chapters.some(
        (chapter) =>
          chapter.handoff_status === "pending" ||
          chapter.handoff_status === "running" ||
          chapter.turns.some((turn) => turn.status === "running"),
      );
      if (mounted && stillActive) timer = window.setTimeout(poll, 1000);
    }
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [conversation, loadConversation]);

  async function saveMode(mode: TutorMode) {
    setBusy(true);
    try {
      setState(await apiClient.saveTutorSetup(deckId, { mode }));
      await loadConversation();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor mode could not save");
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    setBusy(true);
    try {
      setState(await apiClient.generateTutorGuide(deckId, { request_key: crypto.randomUUID() }));
      await loadConversation();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guide generation could not start");
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    const draft = question.trim();
    if (!draft) return;
    setBusy(true);
    try {
      const next = await apiClient.askTutorQuestion(deckId, {
        request_key: crypto.randomUUID(),
        question: draft,
        ...(selectedCard ? { card_name: selectedCard } : {}),
      });
      setConversation(next);
      const pending = next.chapters
        .flatMap((chapter) => chapter.turns)
        .filter((turn) => turn.status === "running")
        .at(-1);
      setPendingTurnId(pending?.id ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor question could not be sent");
    } finally {
      setBusy(false);
    }
  }

  async function clearConversation() {
    setBusy(true);
    try {
      setConversation(await apiClient.clearTutorConversation(deckId));
      setSelectedChapterId(null);
      setPendingTurnId(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tutor history could not be cleared");
    } finally {
      setBusy(false);
    }
  }

  async function previewReference(request: TutorReferenceRequest) {
    setBusy(true);
    try {
      setReferencePreview(await apiClient.previewTutorReference(deckId, request));
      setReferenceNotice(null);
      setError(null);
    } catch (err) {
      setReferencePreview(null);
      setError(err instanceof Error ? err.message : "Reference preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmReference() {
    if (!referencePreview) return;
    setBusy(true);
    try {
      setState(await apiClient.confirmTutorReference(deckId, referencePreview.preview_id));
      setReferencePreview(null);
      setReferenceNotice("Reference saved. Generate or update the guide only when ready.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reference could not be saved");
    } finally {
      setBusy(false);
    }
  }

  async function removeReference() {
    setBusy(true);
    try {
      setState(await apiClient.removeTutorReference(deckId));
      setReferencePreview(null);
      setReferenceNotice("Reference removed. Your deck and saved guide were not changed.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reference could not be removed");
    } finally {
      setBusy(false);
    }
  }

  async function loadOwnedDecks() {
    try {
      setOwnedDecks(
        (await apiClient.listDecks({ limit: 100 })).filter((deck) => deck.id !== deckId),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Owned decks could not load");
    }
  }

  if (error && !state)
    return (
      <section aria-label="Tutor" className="space-y-3">
        <p role="alert" className="rounded-xl border border-red-400/20 p-4 text-sm text-red-200">
          {error}
        </p>
        <button type="button" className={PRIMARY} onClick={() => void load()}>
          Retry Tutor
        </button>
      </section>
    );
  if (!state)
    return (
      <p role="status" className="text-sm text-gray-400">
        Loading Tutor…
      </p>
    );
  return (
    <TutorPanelView
      state={state}
      busy={busy}
      error={error}
      onMode={saveMode}
      onGenerate={generate}
      referencePreview={referencePreview}
      referenceNotice={referenceNotice}
      ownedDecks={ownedDecks}
      onReferencePreview={previewReference}
      onReferenceConfirm={confirmReference}
      onReferenceCancel={() => {
        setReferencePreview(null);
        setReferenceNotice("Reference replacement cancelled; the saved reference is unchanged.");
      }}
      onReferenceRemove={removeReference}
      onOwnedDecksLoad={loadOwnedDecks}
      conversation={conversation}
      question={question}
      selectedCard={selectedCard}
      selectedChapterId={selectedChapterId}
      onQuestionChange={setQuestion}
      onCardChange={setSelectedCard}
      onChapterChange={setSelectedChapterId}
      onAsk={ask}
      onClearConversation={clearConversation}
    />
  );
}

export function TutorPanelView({
  state,
  busy,
  error,
  onMode,
  onGenerate,
  referencePreview = null,
  referenceNotice = null,
  ownedDecks = [],
  onReferencePreview = () => {},
  onReferenceConfirm = () => {},
  onReferenceCancel = () => {},
  onReferenceRemove = () => {},
  onOwnedDecksLoad = () => {},
  conversation = null,
  question = "",
  selectedCard = "",
  selectedChapterId = null,
  onQuestionChange = () => {},
  onCardChange = () => {},
  onChapterChange = () => {},
  onAsk = () => {},
  onClearConversation = () => {},
}: TutorPanelViewProps) {
  const run = state.latest_run;
  const displayedRun = run?.guide ? run : state.last_successful_run;
  const guide = displayedRun?.guide;
  const outdated = !!displayedRun && !displayedRun.current;
  const generating = run?.status === "running";
  const action = guide ? (outdated ? "Update Guide" : "Generate Guide") : "Generate Guide";
  return (
    <section aria-label="Tutor" className="min-w-0 space-y-5">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight text-white">Tutor</h2>
        <p className="text-sm leading-6 text-gray-400">
          Choose a teaching perspective, then explicitly generate a saved guide for this deck.
        </p>
      </header>
      <fieldset disabled={busy} className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
        <legend className="px-1 text-sm font-medium text-gray-200">Choose a mode</legend>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <ModeOption
            mode="commander"
            label="Commander"
            detail="General multiplayer piloting and the deck’s own strategic identity."
            selected={state.mode === "commander"}
            onSelect={onMode}
          />
          <ModeOption
            mode="cedh"
            label="cEDH"
            detail={
              "Efficient lines, protection windows, and race-versus-grind decisions—not a " +
              "strength certificate."
            }
            selected={state.mode === "cedh"}
            onSelect={onMode}
          />
        </div>
      </fieldset>
      <ReferenceControls
        state={state}
        busy={busy}
        preview={referencePreview}
        notice={referenceNotice}
        ownedDecks={ownedDecks}
        onPreview={onReferencePreview}
        onConfirm={onReferenceConfirm}
        onCancel={onReferenceCancel}
        onRemove={onReferenceRemove}
        onOwnedDecksLoad={onOwnedDecksLoad}
      />
      {error && (
        <p role="alert" className="rounded-xl border border-red-400/20 p-4 text-sm text-red-200">
          {error}
        </p>
      )}
      {state.mode && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={PRIMARY}
            disabled={busy || generating}
            onClick={onGenerate}
          >
            {generating ? "Generating Guide…" : action}
          </button>
          <p className="text-xs leading-5 text-gray-400">
            Generation starts only when you click this button.
          </p>
        </div>
      )}
      {outdated && (
        <p
          role="status"
          className="rounded-xl border border-amber-300/25 p-4 text-sm text-amber-100"
        >
          Outdated: this guide describes an earlier saved deck state.
        </p>
      )}
      {run?.status === "failed" || run?.status === "interrupted" ? (
        <p role="alert" className="rounded-xl border border-red-400/20 p-4 text-sm text-red-200">
          {run.error}
        </p>
      ) : null}
      {guide && (
        <Guide
          title={guide.title}
          content={guide.content}
          openingHands={guide.opening_hands}
          warnings={displayedRun?.evidence?.warnings ?? []}
        />
      )}
      {state.mode && (
        <TutorConversation
          conversation={conversation}
          currentCards={state.current_cards ?? []}
          question={question}
          selectedCard={selectedCard}
          selectedChapterId={selectedChapterId}
          busy={busy}
          onQuestionChange={onQuestionChange}
          onCardChange={onCardChange}
          onChapterChange={onChapterChange}
          onAsk={onAsk}
          onClear={onClearConversation}
        />
      )}
    </section>
  );
}

function ReferenceControls({
  state,
  busy,
  preview,
  notice,
  ownedDecks,
  onPreview,
  onConfirm,
  onCancel,
  onRemove,
  onOwnedDecksLoad,
}: {
  state: TutorStateResponse;
  busy: boolean;
  preview: TutorReferencePreviewResponse | null;
  notice: string | null;
  ownedDecks: DeckSummary[];
  onPreview: (request: TutorReferenceRequest) => void;
  onConfirm: () => void;
  onCancel: () => void;
  onRemove: () => void;
  onOwnedDecksLoad: () => void;
}) {
  return (
    <section
      aria-label="Reference deck controls"
      className="min-w-0 space-y-4 rounded-2xl border border-white/10 bg-white/[0.025] p-5"
    >
      <div>
        <h3 className="text-lg font-semibold text-white">Reference deck</h3>
        <p className="mt-1 text-sm leading-6 text-gray-400">
          Optionally freeze a same-commander list for comparison. Reference actions never edit this
          deck or generate a guide.
        </p>
      </div>
      {state.reference && (
        <SavedReference
          reference={state.reference}
          differences={state.reference_differences ?? null}
          busy={busy}
          onRemove={onRemove}
        />
      )}
      <button
        type="button"
        className={PRIMARY}
        disabled={busy}
        onClick={() => onPreview({ source: "current" })}
      >
        Use current deck as reference
      </button>
      <ReferenceSourceForms
        busy={busy}
        ownedDecks={ownedDecks}
        onPreview={onPreview}
        onOwnedDecksLoad={onOwnedDecksLoad}
      />
      {notice && (
        <p role="status" className="text-sm leading-6 text-indigo-100">
          {notice}
        </p>
      )}
      {preview && (
        <ReferencePreview preview={preview} busy={busy} onConfirm={onConfirm} onCancel={onCancel} />
      )}
    </section>
  );
}

function ReferenceSourceForms({
  busy,
  ownedDecks,
  onPreview,
  onOwnedDecksLoad,
}: {
  busy: boolean;
  ownedDecks: DeckSummary[];
  onPreview: (request: TutorReferenceRequest) => void;
  onOwnedDecksLoad: () => void;
}) {
  const [sourceDeckId, setSourceDeckId] = useState("");
  const [text, setText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const metadata = sourceUrl.trim() ? { source_url: sourceUrl.trim() } : {};
  return (
    <div className="space-y-3">
      <details
        className="rounded-xl border border-white/10 p-4"
        onToggle={(event) => {
          if (event.currentTarget.open) onOwnedDecksLoad();
        }}
      >
        <summary className={`cursor-pointer font-medium text-gray-100 ${FOCUS}`}>
          Choose another owned deck
        </summary>
        <div className="mt-3 space-y-3">
          <label htmlFor="tutor-owned-reference" className="block text-sm text-gray-200">
            Owned deck reference
          </label>
          <select
            id="tutor-owned-reference"
            aria-label="Owned deck reference"
            className={`min-h-11 w-full rounded-lg border border-white/15 bg-gray-950 p-2 ${FOCUS}`}
            value={sourceDeckId}
            disabled={busy}
            onChange={(event) => setSourceDeckId(event.target.value)}
            onFocus={onOwnedDecksLoad}
          >
            <option value="">Select an owned deck</option>
            {ownedDecks.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name} — {deck.commander_name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={PRIMARY}
            disabled={busy || !sourceDeckId}
            onClick={() =>
              onPreview({ source: "owned", source_deck_id: sourceDeckId, ...metadata })
            }
          >
            Preview owned deck
          </button>
        </div>
      </details>
      <details className="rounded-xl border border-white/10 p-4">
        <summary className={`cursor-pointer font-medium text-gray-100 ${FOCUS}`}>
          Paste an exported reference list
        </summary>
        <div className="mt-3 space-y-3">
          <label htmlFor="tutor-reference-text" className="block text-sm text-gray-200">
            Reference deck list
          </label>
          <textarea
            id="tutor-reference-text"
            aria-label="Reference deck list"
            className={`min-h-32 w-full resize-y rounded-lg border border-white/15 bg-gray-950 p-3 text-sm ${FOCUS}`}
            placeholder={"1 Commander *CMDR*\n1 Card Name"}
            value={text}
            disabled={busy}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            type="button"
            className={PRIMARY}
            disabled={busy || !text.trim()}
            onClick={() => onPreview({ source: "pasted", text, ...metadata })}
          >
            Preview pasted reference
          </button>
        </div>
      </details>
      <label htmlFor="tutor-reference-url" className="block text-sm text-gray-200">
        Reference source URL (optional metadata; never fetched)
        <input
          id="tutor-reference-url"
          aria-label="Reference source URL"
          className={`mt-2 min-h-11 w-full rounded-lg border border-white/15 bg-gray-950 p-2 ${FOCUS}`}
          type="text"
          value={sourceUrl}
          disabled={busy}
          onChange={(event) => setSourceUrl(event.target.value)}
        />
      </label>
    </div>
  );
}

function SavedReference({
  reference,
  differences,
  busy,
  onRemove,
}: {
  reference: NonNullable<TutorStateResponse["reference"]>;
  differences: TutorReferenceDifferences | null;
  busy: boolean;
  onRemove: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <article aria-label="Saved reference deck" className="min-w-0 rounded-xl bg-white/[0.035] p-4">
      <h4 className="break-words font-semibold text-white">{reference.source_name}</h4>
      <p className="mt-1 text-sm text-gray-300">
        Captured <time dateTime={reference.captured_at}>{reference.captured_at}</time>
      </p>
      <p className="mt-1 break-words text-sm text-gray-400">
        Commanders: {reference.commanders.map((card) => card.name).join(", ")}
      </p>
      {reference.source_url && (
        <p className="mt-1 break-words text-xs text-gray-400">Source URL: {reference.source_url}</p>
      )}
      <ReferenceCards reference={reference} />
      {differences && <DifferenceBrowser differences={differences} />}
      <div className="mt-3 flex flex-wrap gap-2">
        {!confirming ? (
          <button
            type="button"
            className={PRIMARY}
            disabled={busy}
            onClick={() => setConfirming(true)}
          >
            Remove reference
          </button>
        ) : (
          <>
            <button type="button" className={PRIMARY} disabled={busy} onClick={onRemove}>
              Confirm reference removal
            </button>
            <button
              type="button"
              className={PRIMARY}
              disabled={busy}
              onClick={() => setConfirming(false)}
            >
              Cancel reference removal
            </button>
          </>
        )}
      </div>
    </article>
  );
}

function ReferencePreview({
  preview,
  busy,
  onConfirm,
  onCancel,
}: {
  preview: TutorReferencePreviewResponse;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <article
      aria-label="Reference preview"
      className="min-w-0 rounded-xl border border-indigo-300/30 p-4"
    >
      <h4 className="font-semibold text-white">Reference preview</h4>
      <p className="mt-1 text-sm leading-6 text-gray-300">
        Review this frozen candidate. Confirm to replace the saved reference; cancel keeps it.
      </p>
      <ReferenceCards reference={preview.reference} />
      <DifferenceBrowser differences={preview.differences} />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={PRIMARY} disabled={busy} onClick={onConfirm}>
          Confirm reference replacement
        </button>
        <button type="button" className={PRIMARY} disabled={busy} onClick={onCancel}>
          Cancel reference replacement
        </button>
      </div>
    </article>
  );
}

function ReferenceCards({
  reference,
}: {
  reference: NonNullable<TutorStateResponse["reference"]>;
}) {
  return (
    <details className="mt-3">
      <summary className={`cursor-pointer text-sm text-indigo-200 ${FOCUS}`}>
        Browse frozen reference cards (
        {reference.cards.reduce((sum, card) => sum + card.quantity, 0)})
      </summary>
      <ul className="mt-2 space-y-1 text-sm text-gray-300">
        {reference.cards.map((card) => (
          <li key={card.oracle_id ?? card.name} className="break-words">
            {card.quantity} × {card.name}
          </li>
        ))}
      </ul>
    </details>
  );
}

function DifferenceBrowser({ differences }: { differences: TutorReferenceDifferences }) {
  return (
    <details className="mt-3">
      <summary className={`cursor-pointer text-sm text-indigo-200 ${FOCUS}`}>
        Browse reference differences
      </summary>
      <div className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
        <DifferenceList title="Missing from current deck" items={differences.missing} />
        <DifferenceList title="Added since reference" items={differences.added} />
      </div>
    </details>
  );
}

function DifferenceList({
  title,
  items,
}: {
  title: string;
  items: TutorReferenceDifferences["missing"];
}) {
  return (
    <section>
      <h5 className="font-medium text-white">{title}</h5>
      {items.length === 0 ? (
        <p className="mt-1 text-gray-400">None</p>
      ) : (
        <ul className="mt-1 space-y-1 text-gray-300">
          {items.map((item) => (
            <li key={`${item.oracle_id ?? item.name}-${title}`} className="break-words">
              {item.name}: reference {item.reference_quantity}, current {item.actual_quantity}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ModeOption({
  mode,
  label,
  detail,
  selected,
  onSelect,
}: {
  mode: TutorMode;
  label: string;
  detail: string;
  selected: boolean;
  onSelect: (mode: TutorMode) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(mode)}
      className={
        `min-h-11 rounded-xl border p-4 text-left ${FOCUS} ` +
        (selected ? "border-indigo-400 bg-indigo-400/10" : "border-white/10 hover:border-white/30")
      }
    >
      <span className="block font-semibold text-white">{label}</span>
      <span className="mt-1 block text-sm leading-6 text-gray-400">{detail}</span>
    </button>
  );
}

function Guide({
  title,
  content,
  openingHands,
  warnings,
}: {
  title: string;
  content: string;
  openingHands: { decision: string; cards: string[]; explanation: string }[];
  warnings: string[];
}) {
  return (
    <article className="min-w-0 rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-6">
      <h3 className="break-words text-xl font-semibold text-white">{title}</h3>
      {warnings.map((warning) => (
        <p key={warning} className="mt-3 text-sm leading-6 text-amber-200">
          {warning}
        </p>
      ))}
      <div className="mt-4">
        <TutorMarkdown>{content}</TutorMarkdown>
      </div>
      <div className="mt-5 space-y-3" aria-label="Worked opening hands">
        {openingHands.map((hand) => (
          <section key={hand.decision} className="rounded-xl border border-white/10 p-4">
            <h4 className="font-semibold capitalize text-white">{hand.decision}</h4>
            <p className="mt-1 break-words text-sm leading-6 text-gray-200">
              {hand.cards.join(", ")}
            </p>
            <div className="mt-2">
              <TutorMarkdown>{hand.explanation}</TutorMarkdown>
            </div>
          </section>
        ))}
      </div>
    </article>
  );
}
