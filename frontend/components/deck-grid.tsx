"use client";

import { useId } from "react";
import { VisualCardGrid, VisualCardTile } from "@/components/visual-card-grid";
import { groupByPrimaryType, sortedPrimaryTypes } from "@/lib/card-types";
import { STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, totalCardCount, type DeckCardItem } from "@/lib/types";

const EUR_FORMATTER = new Intl.NumberFormat("en-US", { style: "currency", currency: "EUR" });

interface Props {
  cards: DeckCardItem[];
  onCardClick: (deckCardId: string) => void;
  comboCardIds?: Set<string> | undefined;
  onSetQuantity?: ((scryfallId: string, quantity: number) => void | Promise<void>) | undefined;
  onRemove?: ((scryfallId: string) => void) | undefined;
  groupBy?: "type" | "tag";
  collapsedGroups?: ReadonlySet<string>;
  onToggleGroup?: (groupKey: string) => void;
}

function isBasicLand(card: DeckCardItem): boolean {
  return !!card.type_line?.includes("Basic Land");
}

export function DeckGrid({
  cards,
  onCardClick,
  comboCardIds,
  onSetQuantity,
  onRemove,
  groupBy = "type",
  collapsedGroups,
  onToggleGroup,
}: Props) {
  const groups = buildGridGroups(cards, groupBy);

  if (cards.length === 0) return null;

  return (
    <div className="flex flex-col gap-7">
      {groups.map((group) => (
        <DeckGridSection
          key={group.key}
          type={group.label}
          cards={group.cards}
          onCardClick={onCardClick}
          comboCardIds={comboCardIds}
          onSetQuantity={onSetQuantity}
          onRemove={onRemove}
          collapsed={collapsedGroups?.has(group.key) ?? false}
          {...(onToggleGroup ? { onToggle: () => onToggleGroup(group.key) } : {})}
        />
      ))}
    </div>
  );
}

function buildGridGroups(cards: DeckCardItem[], groupBy: "type" | "tag") {
  if (groupBy === "type") {
    const groups = groupByPrimaryType(cards);
    return sortedPrimaryTypes(groups).map((type) => ({
      key: type,
      label: type,
      cards: groups[type] ?? [],
    }));
  }

  const groups = new Map<string, DeckCardItem[]>();
  for (const card of cards) {
    for (const tag of bucketsFor(card)) {
      groups.set(tag, [...(groups.get(tag) ?? []), card]);
    }
  }
  return [...groups.entries()]
    .map(([key, items]) => ({ key, label: STAGE_LABELS[key] ?? key, cards: items }))
    .sort((a, b) => b.cards.length - a.cards.length || a.label.localeCompare(b.label));
}

interface SectionProps extends Props {
  type: string;
  collapsed: boolean;
  onToggle?: () => void;
}

function DeckGridSection({
  type,
  cards,
  onCardClick,
  comboCardIds,
  onSetQuantity,
  onRemove,
  collapsed,
  onToggle,
}: SectionProps) {
  const contentId = useId();
  if (cards.length === 0) return null;

  return (
    <section>
      <header className="mb-3 border-b border-white/10 pb-2">
        {onToggle ? (
          <button
            type="button"
            aria-expanded={!collapsed}
            aria-controls={contentId}
            onClick={onToggle}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="flex items-center gap-2">
              <span aria-hidden="true" className="text-xs text-gray-500">
                {collapsed ? "▶" : "▼"}
              </span>
              <span className="text-sm font-semibold text-white">{type}</span>
            </span>
            <span className="text-xs tabular-nums text-gray-500">{totalCardCount(cards)}</span>
          </button>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">{type}</span>
            <span className="text-xs tabular-nums text-gray-500">{totalCardCount(cards)}</span>
          </div>
        )}
      </header>
      <div id={contentId} hidden={collapsed}>
        {!collapsed && (
          <VisualCardGrid>
            {cards.map((card) => (
              <VisualCardTile
                key={card.deck_card_id}
                name={card.name}
                imageUri={card.image_uri}
                onOpen={() => onCardClick(card.deck_card_id)}
                badges={
                  <DeckTileBadges card={card} inCombo={comboCardIds?.has(card.scryfall_id)} />
                }
                footer={
                  <DeckTileFooter
                    card={card}
                    onOpen={() => onCardClick(card.deck_card_id)}
                    onSetQuantity={onSetQuantity}
                    onRemove={onRemove}
                  />
                }
              />
            ))}
          </VisualCardGrid>
        )}
      </div>
    </section>
  );
}

function DeckTileBadges({ card, inCombo }: { card: DeckCardItem; inCombo?: boolean | undefined }) {
  return (
    <>
      {card.quantity > 1 ? (
        <span className="absolute right-2 top-2 rounded-full bg-black/80 px-2 py-1 text-xs font-semibold text-white backdrop-blur">
          ×{card.quantity}
        </span>
      ) : null}
      {inCombo ? (
        <span className="absolute left-2 top-2 rounded-full bg-black/80 px-2 py-1 text-xs text-amber-300 backdrop-blur">
          Combo
        </span>
      ) : null}
      {card.price_eur_cents != null ? (
        <span className="absolute bottom-2 left-2 rounded-full bg-black/80 px-2 py-1 text-xs font-medium text-emerald-300 backdrop-blur tabular-nums">
          {EUR_FORMATTER.format(card.price_eur_cents / 100)}
        </span>
      ) : null}
      {card.planned_cut_quantity > 0 ? (
        <span className="absolute bottom-2 right-2 rounded-full bg-red-950/90 px-2 py-1 text-[10px] text-red-200 backdrop-blur">
          Cut ×{card.planned_cut_quantity}
        </span>
      ) : null}
    </>
  );
}

interface FooterProps {
  card: DeckCardItem;
  onOpen: () => void;
  onSetQuantity?: Props["onSetQuantity"];
  onRemove?: Props["onRemove"];
}

function DeckTileFooter({ card, onOpen, onSetQuantity, onRemove }: FooterProps) {
  const showQuantity = isBasicLand(card) && onSetQuantity;
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={onOpen}
        className="block w-full truncate text-left text-sm font-medium text-white hover:text-indigo-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
      >
        {card.name}
      </button>
      <div className="flex min-h-9 items-center justify-between gap-2">
        <span className="truncate text-[11px] text-gray-500">{card.type_line}</span>
        {showQuantity ? (
          <div className="flex shrink-0 items-center rounded-lg border border-white/10 bg-black/25">
            <QuantityButton
              label={`Decrease ${card.name}`}
              onClick={() => void onSetQuantity(card.scryfall_id, card.quantity - 1)}
            >
              −
            </QuantityButton>
            <span className="min-w-7 text-center text-xs tabular-nums text-white">
              {card.quantity}
            </span>
            <QuantityButton
              label={`Increase ${card.name}`}
              onClick={() => void onSetQuantity(card.scryfall_id, card.quantity + 1)}
            >
              +
            </QuantityButton>
          </div>
        ) : onRemove ? (
          <button
            type="button"
            onClick={() => onRemove(card.scryfall_id)}
            aria-label={`Plan cut for ${card.name}`}
            className="min-h-11 shrink-0 touch-manipulation rounded-lg border border-red-500/30 px-2 text-xs text-red-300 hover:bg-red-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Plan Cut
          </button>
        ) : null}
      </div>
    </div>
  );
}

function QuantityButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="min-h-11 min-w-11 touch-manipulation text-gray-300 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400"
    >
      {children}
    </button>
  );
}
