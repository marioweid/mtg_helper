"use client";

import { useState, useEffect, useRef } from "react";
import { apiClient } from "@/lib/api";
import type { CardResponse } from "@/lib/types";

interface Props {
  placeholder?: string;
  typeFilter?: string;
  onSelect: (card: CardResponse) => void;
  selected?: CardResponse | null;
  onClear?: () => void;
}

export function CardSearch({ placeholder, typeFilter, onSelect, selected, onClear }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CardResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const searchParams: Parameters<typeof apiClient.searchCards>[0] = {
          q: query,
          limit: 10,
        };
        if (typeFilter) searchParams.type = typeFilter;
        const cards = await apiClient.searchCards(searchParams);
        setResults(cards);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [query, typeFilter]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (selected) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-indigo-500/50 bg-indigo-900/20 p-3">
        {selected.image_uri && (
          <img
            src={selected.image_uri}
            alt={selected.name}
            className="h-12 w-9 rounded object-cover"
          />
        )}
        <div className="flex-1 min-w-0">
          <p className="font-medium text-white truncate">{selected.name}</p>
          <p className="text-xs text-gray-400 truncate">{selected.type_line}</p>
        </div>
        {onClear && (
          <button
            onClick={onClear}
            className="text-gray-400 hover:text-white transition-colors text-lg leading-none"
            aria-label="Clear selection"
          >
            ×
          </button>
        )}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder ?? "Search cards..."}
        className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      />
      {loading && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
          ...
        </div>
      )}
      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full rounded-lg border border-white/10 bg-gray-900 shadow-xl overflow-hidden">
          {results.map((card) => (
            <li key={card.scryfall_id}>
              <button
                onClick={() => {
                  onSelect(card);
                  setQuery("");
                  setOpen(false);
                }}
                className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-white/10 transition-colors"
              >
                {card.image_uri && (
                  <img
                    src={card.image_uri}
                    alt={card.name}
                    className="h-10 w-7 rounded object-cover flex-shrink-0"
                  />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white truncate">{card.name}</p>
                  <p className="text-xs text-gray-400 truncate">{card.type_line}</p>
                </div>
                {card.mana_cost && (
                  <span className="ml-auto text-xs text-gray-500 flex-shrink-0">
                    {card.mana_cost}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
