"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import { ARCHETYPE_GROUPS, archetypeLabel } from "@/lib/constants";
import { MECHANIC_GROUPS } from "@/lib/mechanics";
import type { TribalTag } from "@/lib/types";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  /** Tags pre-suggested by the backend (e.g. aggregated from imported cards). */
  suggested?: string[];
}

/**
 * Pickable chip grid for Moxfield-style archetype keywords plus a tribal
 * subtype autocomplete. The component owns its tribal-list fetch and renders
 * the curated archetype groups from constants.ts.
 *
 * The shape of ``value`` is the canonical tag list — including
 * ``<subtype>_tribal`` tags — that the backend stores on ``decks.archetype_tags``.
 */
export function ArchetypeChipPicker({ value, onChange, suggested }: Props) {
  const [tribal, setTribal] = useState<TribalTag[]>([]);
  const [tribalQuery, setTribalQuery] = useState("");
  const [tribalLoading, setTribalLoading] = useState(false);
  const [tribalError, setTribalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTribalLoading(true);
    apiClient
      .listTribalTags(3)
      .then((tags) => {
        if (!cancelled) setTribal(tags);
      })
      .catch((err) => {
        if (!cancelled) setTribalError(err instanceof Error ? err.message : "Failed to load tribes");
      })
      .finally(() => {
        if (!cancelled) setTribalLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => new Set(value), [value]);

  const toggle = (tag: string) => {
    if (selected.has(tag)) {
      onChange(value.filter((t) => t !== tag));
    } else {
      onChange([...value, tag]);
    }
  };

  // Tribal autocomplete matches: filter by query against subtype display name.
  const tribalMatches = useMemo(() => {
    const q = tribalQuery.trim().toLowerCase();
    if (!q) return tribal.slice(0, 10);
    return tribal.filter((t) => t.subtype.toLowerCase().includes(q)).slice(0, 10);
  }, [tribal, tribalQuery]);

  const suggestedSet = useMemo(() => new Set(suggested ?? []), [suggested]);

  return (
    <div className="space-y-6">
      {value.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Selected
          </h3>
          <div className="flex flex-wrap gap-2">
            {value.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => toggle(tag)}
                className="rounded-full bg-blue-600 px-3 py-1 text-sm text-white shadow hover:bg-blue-700"
              >
                {archetypeLabel(tag)} ✕
              </button>
            ))}
          </div>
        </section>
      )}

      {suggested && suggested.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Suggested from your import
          </h3>
          <div className="flex flex-wrap gap-2">
            {suggested.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => toggle(tag)}
                className={`rounded-full border px-3 py-1 text-sm ${
                  selected.has(tag)
                    ? "border-blue-600 bg-blue-50 text-blue-700"
                    : "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100"
                }`}
              >
                {archetypeLabel(tag)}
              </button>
            ))}
          </div>
        </section>
      )}

      {ARCHETYPE_GROUPS.map((group) => (
        <section key={group.group}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            {group.group}
          </h3>
          <div className="flex flex-wrap gap-2">
            {group.chips.map((chip) => {
              const active = selected.has(chip.tag);
              const isSuggested = suggestedSet.has(chip.tag);
              return (
                <button
                  key={chip.tag}
                  type="button"
                  onClick={() => toggle(chip.tag)}
                  className={`rounded-full border px-3 py-1 text-sm transition ${
                    active
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : isSuggested
                        ? "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100"
                        : "border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50"
                  }`}
                >
                  {chip.label}
                </button>
              );
            })}
          </div>
        </section>
      ))}

      <details className="rounded-lg border border-gray-200 bg-gray-50 open:bg-white">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700">
          All mechanics ({MECHANIC_GROUPS.reduce((n, g) => n + g.chips.length, 0)}) — click to expand
        </summary>
        <div className="space-y-5 border-t border-gray-200 px-3 py-3">
          <p className="text-xs text-gray-500">
            Every printed keyword and mechanic — flying, dredge, cycling, explore, plot, monarch,
            and so on. Picking one filters the corpus to cards that mention the mechanic by name,
            not curated deck archetypes.
          </p>
          {MECHANIC_GROUPS.map((group) => (
            <section key={group.group}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                {group.group}
              </h4>
              <div className="flex flex-wrap gap-2">
                {group.chips.map((chip) => {
                  const active = selected.has(chip.tag);
                  return (
                    <button
                      key={chip.tag}
                      type="button"
                      onClick={() => toggle(chip.tag)}
                      className={`rounded-full border px-3 py-1 text-sm transition ${
                        active
                          ? "border-blue-600 bg-blue-50 text-blue-700"
                          : "border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50"
                      }`}
                    >
                      {chip.label}
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </details>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
          Tribal
        </h3>
        <input
          type="text"
          value={tribalQuery}
          onChange={(e) => setTribalQuery(e.target.value)}
          placeholder="Search a tribe (squirrel, dragon, elf…)"
          className="mb-3 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        {tribalLoading && <p className="text-sm text-gray-500">Loading tribes…</p>}
        {tribalError && <p className="text-sm text-red-600">{tribalError}</p>}
        {!tribalLoading && !tribalError && (
          <div className="flex flex-wrap gap-2">
            {tribalMatches.map((t) => {
              const active = selected.has(t.tag);
              return (
                <button
                  key={t.tag}
                  type="button"
                  onClick={() => toggle(t.tag)}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    active
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : "border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50"
                  }`}
                  title={`${t.card_count} cards`}
                >
                  {t.subtype} <span className="text-gray-400">({t.card_count})</span>
                </button>
              );
            })}
            {tribalMatches.length === 0 && tribalQuery && (
              <p className="text-sm text-gray-500">No matching tribes.</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
