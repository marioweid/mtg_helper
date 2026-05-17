"use client";

import { COLOR_SYMBOLS } from "@/lib/constants";
import type { DeckCardItem } from "@/lib/types";

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

export function DeckFilterBar({ value, onChange, resultCount, totalCount }: Props) {
  function toggleColor(c: string) {
    const has = value.colors.includes(c);
    onChange({
      ...value,
      colors: has ? value.colors.filter((x) => x !== c) : [...value.colors, c],
    });
  }

  const filtered = resultCount !== totalCount;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <input
        type="text"
        value={value.query}
        onChange={(e) => onChange({ ...value, query: e.target.value })}
        placeholder="Filter by name or text…"
        className="min-w-[160px] flex-1 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-sm text-white placeholder-gray-500 focus:border-indigo-400 focus:outline-none"
      />
      <div className="flex items-center gap-1">
        {COLOR_TOGGLES.map((c) => {
          const active = value.colors.includes(c.key);
          const sym = COLOR_SYMBOLS[c.key];
          if (!sym) return null;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => toggleColor(c.key)}
              aria-pressed={active}
              className={`h-7 w-7 rounded-full text-xs font-bold transition-all ${sym.bg} ${sym.text} ${
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
    if (q) {
      const name = c.name.toLowerCase();
      const text = (c.oracle_text ?? "").toLowerCase();
      if (!name.includes(q) && !text.includes(q)) return false;
    }
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
    // Ascending: cheapest first, most valuable last. Unknown prices sort to
    // the end so they don't pretend to be cheap.
    sorted.sort(
      (a, b) =>
        (a.price_eur_cents ?? Number.POSITIVE_INFINITY) -
          (b.price_eur_cents ?? Number.POSITIVE_INFINITY) ||
        a.name.localeCompare(b.name),
    );
  }
  return sorted;
}
