"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { KeywordGroup } from "@/lib/types";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  suggested?: string[];
  onMechanicTagsLoaded?: (tags: string[]) => void;
  onEdhrecTagsLoaded?: (tags: string[]) => void;
}

export function ArchetypeChipPicker({
  value,
  onChange,
  suggested,
  onMechanicTagsLoaded,
  onEdhrecTagsLoaded,
}: Props) {
  const [edhrecGroups, setEdhrecGroups] = useState<KeywordGroup[] | null>(null);
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[] | null>(null);
  const [keywordError, setKeywordError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setKeywordError(null);
    Promise.all([apiClient.listEdhrecTags(), apiClient.listOfficialKeywords()])
      .then(([edhrec, mechanics]) => {
        if (!cancelled) {
          setEdhrecGroups(edhrec);
          setKeywordGroups(mechanics);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setEdhrecGroups([]);
          setKeywordGroups([]);
          setKeywordError(err instanceof Error ? err.message : "Failed to load tags.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => new Set(value), [value]);
  const suggestedSet = useMemo(() => new Set(suggested ?? []), [suggested]);
  const labels = useMemo(() => {
    const entries = [...(edhrecGroups ?? []), ...(keywordGroups ?? [])].flatMap((group) =>
      group.keywords.map((keyword) => [keyword.tag, keyword.label] as const),
    );
    return new Map<string, string>(entries);
  }, [edhrecGroups, keywordGroups]);

  useEffect(() => {
    if (edhrecGroups === null) return;
    onEdhrecTagsLoaded?.(edhrecGroups.flatMap((group) => group.keywords.map((kw) => kw.tag)));
  }, [edhrecGroups, onEdhrecTagsLoaded]);

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
      {(edhrecGroups === null || keywordGroups === null) && (
        <p className="text-sm text-gray-500">Loading EDHREC themes...</p>
      )}
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
      {(edhrecGroups ?? []).map((group) => (
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
                  {keyword.deck_count ? (
                    <span className="ml-1 text-[11px] opacity-70">
                      {formatDeckCount(keyword.deck_count)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </section>
      ))}
      {(keywordGroups ?? []).map((group) => (
        <section key={`mechanic-${group.category}`}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Advanced mechanics - {group.display_name}
          </h3>
          <div className="flex flex-wrap gap-2">
            {group.keywords.map((keyword) => {
              const active = selected.has(keyword.tag);
              return (
                <button
                  key={keyword.tag}
                  type="button"
                  onClick={() => toggle(keyword.tag)}
                  className={`rounded-full border px-3 py-1 text-sm transition ${
                    active
                      ? "border-violet-600 bg-violet-50 text-violet-700"
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

function formatDeckCount(count: number): string {
  if (count >= 1000) return `${Math.round(count / 1000)}K`;
  return String(count);
}
