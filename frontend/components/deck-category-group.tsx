"use client";

import { useState } from "react";
import type { DraggableAttributes } from "@dnd-kit/core";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CardDetailPanel } from "@/components/card-detail-panel";
import { CardHover } from "@/components/card-hover";
import { ManaCost } from "@/components/mana-cost";
import { OwnedBadge } from "@/components/owned-badge";
import { STAGE_LABELS } from "@/lib/constants";
import { bucketReason, bucketsFor, totalCardCount, type DeckCardItem } from "@/lib/types";

interface Props {
  category: string;
  cards: DeckCardItem[];
  deckId?: string;
  draggable?: boolean;
  onRemove?: (scryfallId: string) => void;
  onSetCategories?: (scryfallId: string, categories: string[]) => void | Promise<void>;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  onSwapped?: () => void | Promise<void>;
  petCardNames?: Set<string>;
  comboCardIds?: Set<string>;
}

function isBasicLand(card: DeckCardItem): boolean {
  return !!card.type_line?.includes("Basic Land");
}

function QuantityStepper({
  quantity,
  onSet,
}: {
  quantity: number;
  onSet: (next: number) => void | Promise<void>;
}) {
  return (
    <span
      className="flex shrink-0 items-center gap-1 text-xs"
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={() => void onSet(quantity - 1)}
        aria-label="Decrease quantity"
        className="h-5 w-5 rounded border border-white/15 text-gray-300 hover:border-white/40 hover:text-white"
      >
        −
      </button>
      <span className="w-5 text-center tabular-nums text-gray-100">{quantity}</span>
      <button
        type="button"
        onClick={() => void onSet(quantity + 1)}
        aria-label="Increase quantity"
        className="h-5 w-5 rounded border border-white/15 text-gray-300 hover:border-white/40 hover:text-white"
      >
        +
      </button>
    </span>
  );
}

function DraggableCardRow({
  card,
  children,
}: {
  card: DeckCardItem;
  children: (handle: {
    setNodeRef: (el: HTMLElement | null) => void;
    listeners: Record<string, unknown> | undefined;
    attributes: DraggableAttributes;
    isDragging: boolean;
  }) => React.ReactNode;
}) {
  const { setNodeRef, listeners, attributes, isDragging } = useDraggable({
    id: card.scryfall_id,
  });
  return <>{children({ setNodeRef, listeners, attributes, isDragging })}</>;
}

export function DeckCategoryGroup({
  category,
  cards,
  deckId,
  draggable = false,
  onRemove,
  onSetCategories,
  onSetQuantity,
  onSwapped,
  petCardNames,
  comboCardIds,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const [openCard, setOpenCard] = useState<string | null>(null);
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id: category });

  return (
    <div
      ref={draggable ? setDropRef : undefined}
      className={`rounded-xl border bg-white/5 transition-colors ${
        isOver && draggable
          ? "border-indigo-400 ring-2 ring-indigo-500/40"
          : "border-white/10"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors"
      >
        <h3 className="font-medium text-white capitalize">{category}</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{totalCardCount(cards)}</span>
          <span className="text-gray-500 text-xs">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <ul className="divide-y divide-white/5 border-t border-white/10">
          {cards.map((card) => {
            const isOpen = openCard === card.deck_card_id;
            const tags = bucketsFor(card).filter((t) => t !== "untagged");
            const inner = (handle?: {
              setNodeRef: (el: HTMLElement | null) => void;
              listeners: Record<string, unknown> | undefined;
              attributes: DraggableAttributes;
              isDragging: boolean;
            }) => (
              <li
                key={card.deck_card_id}
                ref={handle?.setNodeRef}
                {...(handle?.attributes ?? {})}
                {...(handle?.listeners ?? {})}
                className={`relative hover:bg-white/5 transition-colors ${
                  handle?.isDragging ? "opacity-50" : ""
                } ${draggable ? "cursor-grab active:cursor-grabbing" : ""}`}
              >
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setOpenCard(isOpen ? null : card.deck_card_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setOpenCard(isOpen ? null : card.deck_card_id);
                    }
                  }}
                  className="flex w-full cursor-pointer items-center gap-3 px-4 py-2 text-left"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate flex items-center gap-1.5">
                      <CardHover name={card.name} imageUri={card.image_uri}>
                        {card.name}
                      </CardHover>
                      {petCardNames?.has(card.name) && (
                        <span className="text-red-400 flex-shrink-0" title="Pet card">♥</span>
                      )}
                      {comboCardIds?.has(card.scryfall_id) && (
                        <span
                          className="flex-shrink-0 text-yellow-300"
                          title="Part of an active or near-complete combo in this deck"
                        >
                          ⚡
                        </span>
                      )}
                    </p>
                    {(tags.length > 0 || card.owned_in.length > 0) && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {tags.map((t) => (
                          <span
                            key={t}
                            className="rounded bg-indigo-900/40 px-1.5 py-0.5 text-[10px] text-indigo-300 capitalize"
                            title={bucketReason(card, t)}
                          >
                            {STAGE_LABELS[t] ?? t}
                          </span>
                        ))}
                        <OwnedBadge owned={card.owned_in} showUnowned={false} />
                      </div>
                    )}
                  </div>
                  {card.mana_cost && (
                    <span className="flex-shrink-0 text-xs text-gray-500">
                      <ManaCost cost={card.mana_cost} />
                    </span>
                  )}
                  {isBasicLand(card) && onSetQuantity ? (
                    <QuantityStepper
                      quantity={card.quantity}
                      onSet={(next) => onSetQuantity(card.scryfall_id, next)}
                    />
                  ) : card.quantity > 1 ? (
                    <span className="shrink-0 text-xs tabular-nums text-gray-400">
                      ×{card.quantity}
                    </span>
                  ) : null}
                  <span className="w-16 text-right text-xs text-gray-300 flex-shrink-0 tabular-nums">
                    {card.price_eur_cents != null
                      ? `€${(card.price_eur_cents / 100).toFixed(2)}`
                      : "—"}
                  </span>
                  <span className="text-gray-600 text-xs flex-shrink-0">{isOpen ? "▴" : "▾"}</span>
                </div>

                {isOpen && (
                  <div className="border-t border-white/5 bg-black/20 px-4 py-3">
                    <CardDetailPanel
                      card={card}
                      {...(deckId ? { deckId } : {})}
                      onRemove={onRemove}
                      onSetCategories={onSetCategories}
                      {...(onSwapped ? { onSwapped } : {})}
                    />
                  </div>
                )}
              </li>
            );
            if (draggable) {
              return (
                <DraggableCardRow key={card.deck_card_id} card={card}>
                  {(handle) => inner(handle)}
                </DraggableCardRow>
              );
            }
            return inner();
          })}
        </ul>
      )}
    </div>
  );
}
