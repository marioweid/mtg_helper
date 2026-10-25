"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { PrintedKeywordChip, SourceTagChip } from "@/lib/types";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  suggested?: string[];
  onMechanicTagsLoaded?: (tags: string[]) => void;
  onOracleTagsLoaded?: (tags: string[]) => void;
}

export function ArchetypeChipPicker({
  value,
  onChange,
  suggested,
  onMechanicTagsLoaded,
  onOracleTagsLoaded,
}: Props) {
  const [tags, setTags] = useState<SourceTagChip[] | null>(null);
  const [keywords, setKeywords] = useState<PrintedKeywordChip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set(value), [value]);
  const suggestedSet = useMemo(() => new Set(suggested), [suggested]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([apiClient.listOracleTags(), apiClient.listPrintedKeywords()])
      .then(([sourceTags, sourceKeywords]) => {
        if (cancelled) return;
        setTags(sourceTags);
        setKeywords(sourceKeywords);
        onOracleTagsLoaded?.(sourceTags.map((tag) => tag.id));
        onMechanicTagsLoaded?.(sourceKeywords.map((keyword) => keyword.keyword));
      })
      .catch((reason: unknown) => {
        if (!cancelled)
          setError(reason instanceof Error ? reason.message : "Failed to load source labels.");
      });
    return () => {
      cancelled = true;
    };
  }, [onOracleTagsLoaded, onMechanicTagsLoaded]);

  const normalized = query.trim().toLocaleLowerCase();
  const visibleTags = (tags ?? []).filter((tag) =>
    `${tag.label} ${tag.slug}`.toLocaleLowerCase().includes(normalized),
  );
  const visibleKeywords = (keywords ?? []).filter((keyword) =>
    keyword.keyword.toLocaleLowerCase().includes(normalized),
  );
  const labels = new Map<string, string>([
    ...(tags ?? []).map((tag) => [tag.id, tag.label] as const),
    ...(keywords ?? []).map((keyword) => [keyword.keyword, keyword.keyword] as const),
  ]);
  const toggle = (item: string) =>
    onChange(selected.has(item) ? value.filter((value) => value !== item) : [...value, item]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (tags === null || keywords === null)
    return <p className="text-sm text-gray-500">Loading Scryfall labels...</p>;
  return (
    <div className="space-y-5">
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search Oracle tags and printed keywords"
        className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white"
      />
      {value.length > 0 && (
        <ChipSection
          title="Selected"
          items={value.map((item) => ({ id: item, label: labels.get(item) ?? item }))}
          selected={selected}
          suggested={suggestedSet}
          toggle={toggle}
        />
      )}
      <ChipSection
        title="Scryfall Oracle tags"
        items={visibleTags.map((tag) => ({ id: tag.id, label: tag.label }))}
        selected={selected}
        suggested={suggestedSet}
        toggle={toggle}
      />
      <ChipSection
        title="Printed keywords"
        items={visibleKeywords.map((keyword) => ({ id: keyword.keyword, label: keyword.keyword }))}
        selected={selected}
        suggested={suggestedSet}
        toggle={toggle}
      />
    </div>
  );
}

function ChipSection({
  title,
  items,
  selected,
  suggested,
  toggle,
}: {
  title: string;
  items: { id: string; label: string }[];
  selected: Set<string>;
  suggested: Set<string>;
  toggle: (item: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h3>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => toggle(item.id)}
            className={`rounded-full border px-3 py-1 text-sm ${selected.has(item.id) ? "border-blue-500 bg-blue-500/20 text-blue-100" : suggested.has(item.id) ? "border-amber-400/70 bg-amber-500/15 text-amber-100" : "border-white/15 bg-white/5 text-gray-300"}`}
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}
