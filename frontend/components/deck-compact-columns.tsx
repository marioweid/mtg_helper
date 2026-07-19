"use client";

import { CardHover } from "@/components/card-hover";
import { DeckFitIndicator } from "@/components/deck-fit-indicator";
import { ManaCost } from "@/components/mana-cost";
import { PlannedCutBadge } from "@/components/planned-cut-badge";
import { primaryType } from "@/lib/card-types";
import { STAGE_LABELS } from "@/lib/constants";
import { bucketsFor, totalCardCount, type DeckCardItem } from "@/lib/types";

export type GroupBy = "type" | "tag";

interface Props {
  cards: DeckCardItem[];
  groupBy: GroupBy;
  onCardClick?: (card: DeckCardItem) => void;
  onRemove?: (scryfallId: string) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  comboCardIds?: Set<string>;
}

function isBasicLand(card: DeckCardItem): boolean {
  return !!card.type_line?.includes("Basic Land");
}

interface Group {
  key: string;
  label: string;
  items: DeckCardItem[];
}

function buildGroups(cards: DeckCardItem[], groupBy: GroupBy): Group[] {
  const groups = new Map<string, DeckCardItem[]>();
  if (groupBy === "type") {
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
      items: [...items].sort(
        (a, b) => (a.cmc ?? 0) - (b.cmc ?? 0) || a.name.localeCompare(b.name),
      ),
    }))
    .sort((a, b) => b.items.length - a.items.length);
}

function CompactRow({
  card,
  onCardClick,
  onRemove,
  onSetQuantity,
  isPet,
  inCombo,
}: {
  card: DeckCardItem;
  onCardClick?: (card: DeckCardItem) => void;
  onRemove?: (scryfallId: string) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  isPet: boolean;
  inCombo: boolean;
}) {
  const clickable = !!onCardClick;
  const handleRowClick = clickable ? () => onCardClick?.(card) : undefined;
  const showStepper = isBasicLand(card) && !!onSetQuantity;
  return (
    <li
      onClick={handleRowClick}
      className={`group flex items-center gap-2 rounded px-1.5 py-1 text-sm leading-snug hover:bg-white/5 ${
        clickable ? "cursor-pointer" : ""
      }`}
    >
      {showStepper ? (
        <span
          className="flex shrink-0 items-center gap-0.5"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => void onSetQuantity?.(card.scryfall_id, card.quantity - 1)}
            aria-label={`Decrease ${card.name}`}
            className="flex h-5 w-5 items-center justify-center rounded border border-white/15 text-xs text-gray-300 hover:border-white/40 hover:text-white"
          >
            −
          </button>
          <span className="w-6 text-center text-xs tabular-nums text-gray-100">
            {card.quantity}
          </span>
          <button
            type="button"
            onClick={() => void onSetQuantity?.(card.scryfall_id, card.quantity + 1)}
            aria-label={`Increase ${card.name}`}
            className="flex h-5 w-5 items-center justify-center rounded border border-white/15 text-xs text-gray-300 hover:border-white/40 hover:text-white"
          >
            +
          </button>
        </span>
      ) : (
        <span className="w-5 shrink-0 text-right tabular-nums text-gray-500">
          {card.quantity > 1 ? `${card.quantity}` : ""}
        </span>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-1">
        <div className="min-w-0 flex-1 truncate text-gray-100">
          <CardHover name={card.name} imageUri={card.image_uri}>
            {card.name}
          </CardHover>
        </div>
        {isPet && <span className="shrink-0 text-red-400" title="Pet card">♥</span>}
        <DeckFitIndicator card={card} />
        <PlannedCutBadge quantity={card.planned_cut_quantity} />
        {inCombo && (
          <span className="shrink-0 text-yellow-300" title="In a combo">⚡</span>
        )}
      </div>
      {card.mana_cost && (
        <span className="shrink-0 text-xs text-gray-500">
          <ManaCost cost={card.mana_cost} />
        </span>
      )}
      {clickable && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onCardClick?.(card);
          }}
          title={`Edit tags / details for ${card.name}`}
          aria-label={`Edit ${card.name}`}
          className="shrink-0 rounded px-1 text-xs text-gray-500 opacity-0 hover:text-white group-hover:opacity-100 focus:opacity-100"
        >
          ⓘ
        </button>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(card.scryfall_id);
          }}
          title={`Plan cut for ${card.name}`}
          aria-label={`Plan cut for ${card.name}`}
          className="shrink-0 rounded px-1 text-xs text-red-400/70 opacity-0 hover:text-red-300 group-hover:opacity-100 focus:opacity-100"
        >
          ✗
        </button>
      )}
    </li>
  );
}

export function DeckCompactColumns({
  cards,
  groupBy,
  onCardClick,
  onRemove,
  onSetQuantity,
  petCardNames,
  comboCardIds,
}: Props) {
  if (cards.length === 0) {
    return (
      <p className="px-2 py-6 text-center text-xs text-gray-500">No cards.</p>
    );
  }
  const groups = buildGroups(cards, groupBy);

  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
      {groups.map((g) => (
        <section key={g.key} className="min-w-0 break-inside-avoid">
          <header className="mb-1 flex items-baseline justify-between border-b border-white/10 px-1 pb-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-300">
              {g.label}
            </h3>
            <span className="text-xs tabular-nums text-gray-500">
              {totalCardCount(g.items)}
            </span>
          </header>
          <ul className="flex flex-col">
            {g.items.map((card) => (
              <CompactRow
                key={card.deck_card_id}
                card={card}
                {...(onCardClick ? { onCardClick } : {})}
                {...(onRemove ? { onRemove } : {})}
                {...(onSetQuantity ? { onSetQuantity } : {})}
                isPet={petCardNames?.has(card.name) ?? false}
                inCombo={comboCardIds?.has(card.scryfall_id) ?? false}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
