"use client";

import { useEffect, useRef, useState } from "react";

import { ManaCost } from "@/components/mana-cost";
import { COLOR_SYMBOLS } from "@/lib/constants";
import { apiClient } from "@/lib/api";
import type { CardResponse, DeckCardItem } from "@/lib/types";

export type SortMode = "default" | "name" | "cmc" | "price";

export interface DeckFilter {
  query: string;
  colors: string[];
  sort: SortMode;
}

interface Props {
  value: DeckFilter;
  onChange: (next: DeckFilter) => void;
  resultCount: number;
  totalCount: number;
  availableColors?: string[];
  /**
   * When provided, the query input doubles as a card-pool search. Matches
   * appear in a floating dropdown; selecting one calls ``onAddCard``.
   */
  onAddCard?: (card: CardResponse) => void | Promise<void>;
  /** Filter pool search to commander-legal cards. Ignored without ``onAddCard``. */
  commanderLegal?: boolean;
}

const COLOR_TOGGLES: readonly { key: string; label: string }[] = [
  { key: "W", label: "W" },
  { key: "U", label: "U" },
  { key: "B", label: "B" },
  { key: "R", label: "R" },
  { key: "G", label: "G" },
  { key: "C", label: "C" },
];

const SORT_OPTIONS: readonly { key: SortMode; label: string }[] = [
  { key: "default", label: "Default" },
  { key: "name", label: "Name" },
  { key: "cmc", label: "CMC" },
  { key: "price", label: "Price" },
];

export function DeckFilterBar({
  value,
  onChange,
  resultCount,
  totalCount,
  availableColors,
  onAddCard,
  commanderLegal,
}: Props) {
  const [poolResults, setPoolResults] = useState<CardResponse[]>([]);
  const [poolOpen, setPoolOpen] = useState(false);
  const [poolLoading, setPoolLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!onAddCard) return;
    const q = value.query.trim();
    if (q.length < 2) {
      setPoolResults([]);
      setPoolOpen(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setPoolLoading(true);
      try {
        const params: Parameters<typeof apiClient.searchCards>[0] = {
          q,
          limit: 10,
        };
        if (commanderLegal) params.commander_legal = true;
        const cards = await apiClient.searchCards(params);
        setPoolResults(cards);
        setPoolOpen(true);
      } catch {
        setPoolResults([]);
      } finally {
        setPoolLoading(false);
      }
    }, 300);
  }, [value.query, commanderLegal, onAddCard]);

  useEffect(() => {
    if (!onAddCard) return;
    function handleClick(e: MouseEvent) {
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target as Node)) {
        setPoolOpen(false);
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setPoolOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onAddCard]);

  function toggleColor(c: string) {
    const has = value.colors.includes(c);
    onChange({
      ...value,
      colors: has ? value.colors.filter((x) => x !== c) : [...value.colors, c],
    });
  }

  async function handleSelect(card: CardResponse) {
    setPoolOpen(false);
    if (onAddCard) await onAddCard(card);
  }

  const filtered = resultCount !== totalCount;
  const visibleToggles = availableColors
    ? COLOR_TOGGLES.filter((c) => c.key === "C" || availableColors.includes(c.key))
    : COLOR_TOGGLES;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <div ref={searchWrapRef} className="relative min-w-[160px] flex-1">
        <input
          type="text"
          name="deck-card-filter"
          autoComplete="off"
          aria-label={onAddCard ? "Filter deck or search for a card to add" : "Filter deck cards"}
          value={value.query}
          onChange={(e) => onChange({ ...value, query: e.target.value })}
          onFocus={() => {
            if (poolResults.length > 0) setPoolOpen(true);
          }}
          placeholder={onAddCard ? "Filter deck or search to add…" : "Filter by name…"}
          className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1 text-sm text-white placeholder-gray-500 focus-visible:border-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50"
        />
        {onAddCard && poolLoading && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
            …
          </span>
        )}
        {onAddCard && poolOpen && poolResults.length > 0 && (
          <ul className="absolute left-0 right-0 top-full z-50 mt-1 max-h-80 overflow-y-auto rounded-lg border border-white/10 bg-gray-900 shadow-xl">
            {poolResults.map((card) => (
              <li key={card.scryfall_id}>
                <button
                  type="button"
                  onClick={() => void handleSelect(card)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-white/10"
                >
                  {card.image_uri && (
                    <img
                      src={card.image_uri}
                      alt={card.name}
                      width={28}
                      height={40}
                      loading="lazy"
                      className="h-10 w-7 flex-shrink-0 rounded object-cover"
                    />
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-white">{card.name}</p>
                    <p className="truncate text-xs text-gray-400">{card.type_line}</p>
                  </div>
                  {card.mana_cost && (
                    <span className="ml-auto flex-shrink-0 text-xs text-gray-500">
                      <ManaCost cost={card.mana_cost} />
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex items-center gap-1">
        {visibleToggles.map((c) => {
          const active = value.colors.includes(c.key);
          const sym = COLOR_SYMBOLS[c.key];
          if (!sym) return null;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => toggleColor(c.key)}
              aria-pressed={active}
              className={`h-7 w-7 rounded-full text-xs font-bold transition-[transform,opacity,box-shadow] motion-reduce:transition-none ${sym.bg} ${sym.text} ${
                active
                  ? "scale-110 ring-2 ring-white/90 shadow-md"
                  : "opacity-45 hover:opacity-90"
              }`}
              title={`Show only ${c.label} cards`}
            >
              {c.label}
            </button>
          );
        })}
      </div>
      <select
        value={value.sort}
        onChange={(e) => onChange({ ...value, sort: e.target.value as SortMode })}
        className="rounded-md border border-white/10 bg-black/30 px-2 py-1 text-sm text-gray-200 focus:border-indigo-400 focus:outline-none"
        aria-label="Sort cards"
      >
        {SORT_OPTIONS.map((s) => (
          <option key={s.key} value={s.key}>
            Sort: {s.label}
          </option>
        ))}
      </select>
      {filtered ? (
        <button
          type="button"
          onClick={() => onChange({ query: "", colors: [], sort: value.sort })}
          className="text-xs text-gray-400 transition-colors hover:text-white"
        >
          Clear
        </button>
      ) : null}
      <span className="ml-auto text-xs text-gray-500">
        {filtered ? `${resultCount} / ${totalCount}` : `${totalCount} cards`}
      </span>
    </div>
  );
}

export function applyDeckFilter(cards: DeckCardItem[], filter: DeckFilter): DeckCardItem[] {
  const q = filter.query.trim().toLowerCase();
  const filtered = cards.filter((c) => {
    if (q && !c.name.toLowerCase().includes(q)) return false;
    if (filter.colors.length > 0) {
      const ci = c.color_identity ?? [];
      const wantsColorless = filter.colors.includes("C");
      const isColorless = ci.length === 0;
      if (wantsColorless && isColorless) {
        // pass
      } else if (!ci.some((color) => filter.colors.includes(color))) {
        return false;
      }
    }
    return true;
  });

  if (filter.sort === "default") return filtered;
  const sorted = [...filtered];
  if (filter.sort === "name") {
    sorted.sort((a, b) => a.name.localeCompare(b.name));
  } else if (filter.sort === "cmc") {
    sorted.sort((a, b) => (a.cmc ?? 0) - (b.cmc ?? 0) || a.name.localeCompare(b.name));
  } else if (filter.sort === "price") {
    sorted.sort(
      (a, b) =>
        (a.price_eur_cents ?? Number.POSITIVE_INFINITY) -
          (b.price_eur_cents ?? Number.POSITIVE_INFINITY) ||
        a.name.localeCompare(b.name),
    );
  }
  return sorted;
}
