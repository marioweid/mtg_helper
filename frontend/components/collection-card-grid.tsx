"use client";

import {
  CollectionDeckSelect,
  CollectionMetadata,
  QuantityControls,
  formatCollectionPrice,
  type CollectionCardActions,
} from "@/components/collection-card-row";
import { VisualCardGrid, VisualCardTile } from "@/components/visual-card-grid";
import type { CollectionCardItem, DeckSummary } from "@/lib/types";

interface Props extends CollectionCardActions {
  cards: CollectionCardItem[];
  decks: DeckSummary[];
}

export function CollectionCardGrid({
  cards,
  decks,
  busy,
  onSetQuantity,
  onRemove,
  onPlanForDeck,
}: Props) {
  return (
    <VisualCardGrid>
      {cards.map((card) => (
        <VisualCardTile
          key={`${card.card_id}-${card.set_code}-${card.collector_number}-${card.foil}`}
          name={card.name}
          imageUri={card.image_uri}
          badges={<CollectionTileBadges card={card} />}
          footer={
            <div className="space-y-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-white">{card.name}</p>
                <p className="truncate text-[11px] text-gray-500">
                  {card.set_code.toUpperCase()} {card.collector_number}
                </p>
                <CollectionMetadata card={card} />
              </div>
              <QuantityControls
                card={card}
                busy={busy}
                onSetQuantity={onSetQuantity}
                onRemove={onRemove}
              />
              <CollectionDeckSelect
                card={card}
                decks={decks}
                busy={busy}
                onPlanForDeck={onPlanForDeck}
              />
            </div>
          }
        />
      ))}
    </VisualCardGrid>
  );
}

function CollectionTileBadges({ card }: { card: CollectionCardItem }) {
  return (
    <>
      <span className="absolute right-2 top-2 rounded-full bg-black/80 px-2 py-1 text-xs font-semibold text-white backdrop-blur">
        ×{card.quantity}
      </span>
      {card.foil ? (
        <span className="absolute left-2 top-2 rounded-full bg-amber-950/90 px-2 py-1 text-xs text-amber-200 backdrop-blur">
          Foil
        </span>
      ) : null}
      {card.purchase_price ? (
        <span className="absolute bottom-2 left-2 rounded-full bg-black/80 px-2 py-1 text-xs font-medium text-emerald-300 backdrop-blur">
          {formatCollectionPrice(card.purchase_price)}
        </span>
      ) : null}
    </>
  );
}
