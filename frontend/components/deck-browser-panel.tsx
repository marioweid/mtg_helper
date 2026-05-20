"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CardHover } from "@/components/card-hover";
import {
  applyDeckFilter,
  DeckFilterBar,
  type DeckFilter,
} from "@/components/deck-filter-bar";
import { primaryType } from "@/lib/card-types";
import { STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, type DeckCardItem, totalCardCount } from "@/lib/types";

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
  petCardNames?: Set<string>;
  comboCardIds?: Set<string>;
}

function groupCards(
  cards: DeckCardItem[],
  mode: GroupMode,
): { key: string; label: string; items: DeckCardItem[] }[] {
  if (mode === "flat") {
    return [{ key: "all", label: "All", items: cards }];
  }
  const groups = new Map<string, DeckCardItem[]>();
  if (mode === "type") {
    for (const card of cards) {
      const key = primaryType(card);
      const arr = groups.get(key) ?? [];
      arr.push(card);
      groups.set(key, arr);
    }
  } else {
    for (const card of cards) {
      for (const tag of bucketsFor(card)) {
        const arr = groups.get(tag) ?? [];
        arr.push(card);
        groups.set(tag, arr);
      }
    }
  }
  return [...groups.entries()]
    .map(([key, items]) => ({
      key,
      label: STAGE_LABELS[key] ?? key,
      items,
    }))
    .sort((a, b) => b.items.length - a.items.length);
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
        title={`Cut ${card.name}`}
        aria-label={`Cut ${card.name}`}
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
  petCardNames,
  comboCardIds,
}: Props) {
  const [filter, setFilter] = useState<DeckFilter>({
    query: "",
    colors: [],
    sort: "default",
  });
  const [group, setGroup] = useState<GroupMode>("type");
  const [lastCut, setLastCut] = useState<DeckCardItem | null>(null);
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  const groups = useMemo(() => groupCards(filtered, group), [filtered, group]);
  const total = totalCardCount(cards);

  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          role="group"
          aria-label="Group cards by"
          className="inline-flex w-fit overflow-hidden rounded-md border border-white/10 text-[11px]"
        >
          {GROUP_OPTIONS.map((opt) => {
            const active = group === opt.key;
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => setGroup(opt.key)}
                aria-pressed={active}
                className={`px-2.5 py-1 capitalize transition-colors ${
                  active
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {lastCut && (
          <div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs">
            <span className="truncate text-gray-300">
              Cut <span className="text-white">{lastCut.name}</span>
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
      </div>

      <DeckFilterBar
        value={filter}
        onChange={setFilter}
        resultCount={totalCardCount(filtered)}
        totalCount={total}
      />

      <div className="-mr-1 flex-1 overflow-y-auto pr-1">
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-gray-500">No cards match.</p>
        ) : (
          groups.map((g) => (
            <div key={g.key} className="mb-3">
              {group !== "flat" && (
                <div className="sticky top-0 z-[1] flex items-center justify-between bg-zinc-950/95 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 backdrop-blur">
                  <span>{g.label}</span>
                  <span className="text-gray-600">{totalCardCount(g.items)}</span>
                </div>
              )}
              <ul>
                {g.items.map((card) => (
                  <CardRow
                    key={card.deck_card_id}
                    card={card}
                    onCut={() => handleCut(card)}
                    isPet={petCardNames?.has(card.name) ?? false}
                    inCombo={comboCardIds?.has(card.scryfall_id) ?? false}
                  />
                ))}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
