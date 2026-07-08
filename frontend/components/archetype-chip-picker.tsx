"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { KeywordGroup } from "@/lib/types";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  suggested?: string[];
  onMechanicTagsLoaded?: (tags: string[]) => void;
}

export function ArchetypeChipPicker({
  value,
  onChange,
  suggested,
  onMechanicTagsLoaded,
}: Props) {
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[] | null>(null);
  const [keywordError, setKeywordError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setKeywordError(null);
    apiClient
      .listOfficialKeywords()
      .then((groups) => {
        if (!cancelled) setKeywordGroups(groups);
      })
      .catch((err) => {
        if (!cancelled) {
          setKeywordGroups([]);
          setKeywordError(err instanceof Error ? err.message : "Failed to load keywords.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => new Set(value), [value]);
  const suggestedSet = useMemo(() => new Set(suggested ?? []), [suggested]);
  const labels = useMemo(() => {
    const entries = (keywordGroups ?? []).flatMap((group) =>
      group.keywords.map((keyword) => [keyword.tag, keyword.label] as const),
    );
    return new Map<string, string>(entries);
  }, [keywordGroups]);

  useEffect(() => {
    if (keywordGroups === null) return;
    onMechanicTagsLoaded?.(keywordGroups.flatMap((group) => group.keywords.map((kw) => kw.tag)));
  }, [keywordGroups, onMechanicTagsLoaded]);

  function toggle(tag: string) {
    if (selected.has(tag)) {
      onChange(value.filter((item) => item !== tag));
      return;
    }
    onChange([...value, tag]);
  }

  return (
    <div className="space-y-6">
      {keywordGroups === null && <p className="text-sm text-gray-500">Loading MTGJSON keywords...</p>}
      {keywordError && <p className="text-sm text-red-600">{keywordError}</p>}
      {value.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
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
                {labels.get(tag) ?? tag.replace(/_/g, " ")} x
              </button>
            ))}
          </div>
        </section>
      )}
      {(keywordGroups ?? []).map((group) => (
        <section key={group.category}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            {group.display_name}
          </h3>
          <div className="flex flex-wrap gap-2">
            {group.keywords.map((keyword) => {
              const active = selected.has(keyword.tag);
              const isSuggested = suggestedSet.has(keyword.tag);
              return (
                <button
                  key={keyword.tag}
                  type="button"
                  onClick={() => toggle(keyword.tag)}
                  className={`rounded-full border px-3 py-1 text-sm transition ${
                    active
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : isSuggested
                        ? "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100"
                        : "border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50"
                  }`}
                >
                  {keyword.label}
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
