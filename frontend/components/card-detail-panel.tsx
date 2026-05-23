"use client";

import { OracleText } from "@/components/mana-cost";
import { SwapPanel } from "@/components/swap-panel";
import { CATEGORY_ORDER, STAGE_LABELS } from "@/lib/constants";
import type { DeckCardItem } from "@/lib/types";

interface Props {
  card: DeckCardItem;
  deckId?: string | undefined;
  onRemove?: ((scryfallId: string) => void | Promise<void>) | undefined;
  onSetCategories?:
    | ((scryfallId: string, categories: string[]) => void | Promise<void>)
    | undefined;
  onSwapped?: (() => void | Promise<void>) | undefined;
  showImage?: boolean | undefined;
}

const CATEGORY_OPTIONS = CATEGORY_ORDER;

/**
 * Shared detail surface for a deck card — image, type line, oracle text,
 * category chip editor (manual + auto-tagged states), and remove button.
 *
 * Used by both ``DeckCategoryGroup`` (inline list expansion) and
 * ``CardDetailModal`` (grid view). The ``showImage`` flag controls whether
 * the card art appears; the list view sets it to false to keep rows compact.
 */
export function CardDetailPanel({
  card,
  deckId,
  onRemove,
  onSetCategories,
  onSwapped,
  showImage,
}: Props) {
  function toggleCategory(cat: string) {
    if (!onSetCategories) return;
    const has = card.categories.includes(cat);
    const next = has
      ? card.categories.filter((c) => c !== cat)
      : [...card.categories, cat];
    void onSetCategories(card.scryfall_id, next);
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      {showImage && card.image_uri ? (
        <img
          src={card.image_uri}
          alt={card.name}
          className="h-auto w-full max-w-[220px] flex-shrink-0 rounded-[4.5%] shadow-lg"
        />
      ) : null}
      <div className="flex flex-1 flex-col gap-3">
        {card.type_line ? (
          <p className="text-xs text-gray-500">{card.type_line}</p>
        ) : null}
        {card.oracle_text ? (
          <p className="whitespace-pre-line text-xs leading-relaxed text-gray-300">
            <OracleText text={card.oracle_text} />
          </p>
        ) : (
          <p className="text-xs italic text-gray-600">No oracle text.</p>
        )}

        {onSetCategories ? (
          <div>
            <p className="mb-1.5 text-xs uppercase tracking-wide text-gray-500">
              Categories
              <span className="ml-2 normal-case tracking-normal text-gray-600">
                {card.categories.length > 0
                  ? "(explicit picks override auto tags — clear all to revert)"
                  : "(dotted = auto from card text — click to override)"}
              </span>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {CATEGORY_OPTIONS.map((opt) => {
                const active = card.categories.includes(opt);
                const hasExplicit = card.categories.length > 0;
                const auto =
                  !active && !hasExplicit && card.qualifying_stages.includes(opt);
                const cls = active
                  ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                  : auto
                    ? "border-dashed border-gray-600 bg-white/5 text-gray-400 hover:border-gray-400"
                    : "border-white/10 bg-white/5 text-gray-500 hover:border-white/20 hover:text-gray-300";
                return (
                  <button
                    key={opt}
                    onClick={() => toggleCategory(opt)}
                    className={`rounded border px-2 py-0.5 text-xs transition-colors ${cls}`}
                    title={
                      auto
                        ? "Auto-tagged from card text — click to make explicit"
                        : undefined
                    }
                  >
                    {STAGE_LABELS[opt] ?? opt}
                    {auto ? <span className="ml-1 text-[10px] text-gray-500">auto</span> : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {deckId ? (
          <SwapPanel
            deckId={deckId}
            sourceCardId={card.card_id}
            sourceScryfallId={card.scryfall_id}
            sourceName={card.name}
            {...(onSwapped ? { onSwapped } : {})}
          />
        ) : null}

        {onRemove ? (
          <div className="flex">
            <button
              onClick={() => onRemove(card.scryfall_id)}
              className="ml-auto rounded border border-red-500/40 px-2 py-1 text-xs text-red-400 transition-colors hover:border-red-500/70 hover:text-red-300"
              aria-label={`Remove ${card.name}`}
            >
              Remove
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
