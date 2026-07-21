"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CardHover } from "@/components/card-hover";
import { CardWorkspaceToolbar } from "@/components/card-workspace-toolbar";
import { DeckCompactColumns } from "@/components/deck-compact-columns";
import { DeckGrid } from "@/components/deck-grid";
import { PlannedCutBadge } from "@/components/planned-cut-badge";
import {
  applyDeckFilter,
  DeckFilterBar,
  type DeckFilter,
} from "@/components/deck-filter-bar";
import { STAGE_LABELS } from "@/lib/constants";
import {
  getWorkspaceView,
  setWorkspaceView,
  type CardWorkspaceView,
} from "@/lib/deck-view-prefs";
import { bucketsFor, type CardResponse, type DeckCardItem, totalCardCount } from "@/lib/types";

type GroupMode = "type" | "tag" | "flat";

const GROUP_OPTIONS: readonly { key: GroupMode; label: string }[] = [
  { key: "type", label: "Type" },
  { key: "tag", label: "Tag" },
  { key: "flat", label: "Flat" },
];

const UNDO_WINDOW_MS = 6000;

interface Props {
  cards: DeckCardItem[];
  onRemove: (scryfallId: string) => void | Promise<void>;
  onUndoCut?: (card: DeckCardItem) => void | Promise<void>;
  onCardClick?: (card: DeckCardItem) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  comboCardIds?: Set<string>;
  /** When set, the filter input also searches the card pool and lets the user add matches. */
  onAddCard?: (card: CardResponse) => void | Promise<void>;
  commanderLegal?: boolean;
  workspaceScope?: string;
}

function CardRow({
  card,
  onCut,
  isPet,
  inCombo,
}: {
  card: DeckCardItem;
  onCut: () => void;
  isPet: boolean;
  inCombo: boolean;
}) {
  const tags = bucketsFor(card).filter((t) => t !== "untagged");
  const price =
    card.price_eur_cents != null ? `€${(card.price_eur_cents / 100).toFixed(2)}` : "—";
  return (
    <li className="group flex items-start gap-2 border-b border-white/5 px-2 py-1.5 text-xs hover:bg-white/5">
      <span className="mt-0.5 w-6 shrink-0 text-right tabular-nums text-gray-500">
        {card.quantity > 1 ? `${card.quantity}×` : ""}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 truncate">
          <CardHover name={card.name} imageUri={card.image_uri}>
            <span className="truncate text-gray-100">{card.name}</span>
          </CardHover>
          {isPet && (
            <span className="shrink-0 text-red-400" title="Pet card">
              ♥
            </span>
          )}
          {inCombo && (
            <span className="shrink-0 text-yellow-300" title="In a combo">
              ⚡
            </span>
          )}
          <PlannedCutBadge quantity={card.planned_cut_quantity} />
        </div>
        {tags.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-indigo-300/80">
            {tags.map((t) => (
              <span key={t} className="rounded bg-indigo-900/40 px-1 py-px capitalize">
                {STAGE_LABELS[t] ?? t}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5 text-[11px] text-gray-400 tabular-nums">
        <span>{card.cmc != null ? `${card.cmc}` : ""}</span>
        <span>{price}</span>
      </div>
      <button
        type="button"
        onClick={onCut}
        title={`Plan cut for ${card.name}`}
        aria-label={`Plan cut for ${card.name}`}
        className="ml-1 shrink-0 self-center rounded border border-red-500/30 px-1.5 py-0.5 text-[11px] text-red-300 hover:bg-red-500/10"
      >
        ✗
      </button>
    </li>
  );
}

export function DeckBrowserPanel({
  cards,
  onRemove,
  onUndoCut,
  onCardClick,
  onSetQuantity,
  petCardNames,
  comboCardIds,
  onAddCard,
  commanderLegal,
  workspaceScope = "builder",
}: Props) {
  const [filter, setFilter] = useState<DeckFilter>({
    query: "",
    colors: [],
    sort: "default",
  });
  const [group, setGroup] = useState<GroupMode>("type");
  const [view, setView] = useState<CardWorkspaceView>("grid");
  const [lastCut, setLastCut] = useState<DeckCardItem | null>(null);
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setView(getWorkspaceView(workspaceScope) ?? "grid");
  }, [workspaceScope]);

  useEffect(() => {
    return () => {
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current);
    };
  }, []);

  function handleCut(card: DeckCardItem) {
    setLastCut(card);
    if (undoTimerRef.current) clearTimeout(undoTimerRef.current);
    undoTimerRef.current = setTimeout(() => setLastCut(null), UNDO_WINDOW_MS);
    void onRemove(card.scryfall_id);
  }

  function handleUndo() {
    if (!lastCut) return;
    const card = lastCut;
    setLastCut(null);
    if (undoTimerRef.current) clearTimeout(undoTimerRef.current);
    if (onUndoCut) void onUndoCut(card);
  }

  const filtered = useMemo(() => applyDeckFilter(cards, filter), [cards, filter]);
  const total = totalCardCount(cards);

  function handleViewChange(next: CardWorkspaceView) {
    setView(next);
    if (next === "grid" && group === "flat") setGroup("type");
    setWorkspaceView(workspaceScope, next);
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      {lastCut && (
          <div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs">
            <span className="truncate text-gray-300">
              Planned cut for{" "}
              <CardHover name={lastCut.name} imageUri={lastCut.image_uri} className="text-white">
                {lastCut.name}
              </CardHover>
            </span>
            <button
              type="button"
              onClick={handleUndo}
              className="shrink-0 rounded border border-emerald-500/40 px-2 py-0.5 text-[11px] text-emerald-300 hover:bg-emerald-500/10"
            >
              Undo
            </button>
          </div>
      )}

      <CardWorkspaceToolbar
        view={view}
        onViewChange={handleViewChange}
        resultCount={totalCardCount(filtered)}
        totalCount={total}
      >
        <DeckFilterBar
          value={filter}
          onChange={setFilter}
          resultCount={totalCardCount(filtered)}
          totalCount={total}
          {...(onAddCard ? { onAddCard } : {})}
          {...(commanderLegal ? { commanderLegal } : {})}
        />
        <div role="group" aria-label="Group cards by" className="flex flex-wrap gap-1 px-1">
          {GROUP_OPTIONS.filter((option) => view === "list" || option.key !== "flat").map((opt) => {
            const active = group === opt.key;
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => setGroup(opt.key)}
                aria-pressed={active}
                className={`min-h-11 touch-manipulation rounded-lg px-2.5 text-[11px] capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                  active
                    ? "bg-indigo-500/20 text-indigo-200"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                Group: {opt.label}
              </button>
            );
          })}
        </div>
      </CardWorkspaceToolbar>

      <div className="-mr-1 flex-1 overflow-y-auto pr-1">
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-gray-500">No cards match.</p>
        ) : view === "grid" ? (
          <DeckGrid
            cards={filtered}
            onCardClick={(deckCardId) => {
              const card = filtered.find((item) => item.deck_card_id === deckCardId);
              if (card) onCardClick?.(card);
            }}
            onRemove={(scryfallId) => {
              const card = filtered.find((item) => item.scryfall_id === scryfallId);
              if (card) handleCut(card);
            }}
            {...(onSetQuantity ? { onSetQuantity } : {})}
            {...(comboCardIds ? { comboCardIds } : {})}
            groupBy={group === "tag" ? "tag" : "type"}
          />
        ) : group === "flat" ? (
          <ul>
            {filtered.map((card) => (
              <CardRow
                key={card.deck_card_id}
                card={card}
                onCut={() => handleCut(card)}
                isPet={petCardNames?.has(card.name) ?? false}
                inCombo={comboCardIds?.has(card.scryfall_id) ?? false}
              />
            ))}
          </ul>
        ) : (
          <DeckCompactColumns
            cards={filtered}
            groupBy={group}
            onRemove={(scryfallId) => {
              const card = filtered.find((c) => c.scryfall_id === scryfallId);
              if (card) handleCut(card);
            }}
            {...(onCardClick ? { onCardClick } : {})}
            {...(onSetQuantity ? { onSetQuantity } : {})}
            {...(petCardNames ? { petCardNames } : {})}
            {...(comboCardIds ? { comboCardIds } : {})}
          />
        )}
      </div>
    </div>
  );
}
