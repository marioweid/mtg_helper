"use client";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { KeywordChip, KeywordGroup } from "@/lib/types";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  suggested?: string[];
  onMechanicTagsLoaded?: (tags: string[]) => void;
  onHubTagsLoaded?: (tags: string[]) => void;
}

interface BrowserGroup extends KeywordGroup {
  key: string;
  label: string;
  kind: "theme" | "mechanic";
}

function normalize(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function groupMatches(group: BrowserGroup, query: string): boolean {
  if (!query) return true;
  return (
    normalize(group.label).includes(query) ||
    group.keywords.some(
      (keyword) =>
        normalize(keyword.label).includes(query) || normalize(keyword.tag).includes(query),
    )
  );
}

function keywordMatches(keyword: KeywordChip, query: string): boolean {
  return Boolean(
    query &&
      (normalize(keyword.label).includes(query) || normalize(keyword.tag).includes(query)),
  );
}

export function ArchetypeChipPicker({
  value,
  onChange,
  suggested,
  onMechanicTagsLoaded,
  onHubTagsLoaded,
}: Props) {
  const [hubGroups, setHubGroups] = useState<KeywordGroup[] | null>(null);
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[] | null>(null);
  const [keywordError, setKeywordError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [activeGroupKey, setActiveGroupKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setKeywordError(null);
    Promise.all([apiClient.listHubTags(), apiClient.listOfficialKeywords()])
      .then(([hubs, mechanics]) => {
        if (!cancelled) {
          setHubGroups(hubs);
          setKeywordGroups(mechanics);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setHubGroups([]);
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
  const groups = useMemo<BrowserGroup[]>(
    () => [
      ...(hubGroups ?? []).map((group) => ({
        ...group,
        key: `theme:${group.category}`,
        label: group.display_name,
        kind: "theme" as const,
      })),
      ...(keywordGroups ?? []).map((group) => ({
        ...group,
        key: `mechanic:${group.category}`,
        label: `Advanced mechanics — ${group.display_name}`,
        kind: "mechanic" as const,
      })),
    ],
    [hubGroups, keywordGroups],
  );
  const normalizedQuery = normalize(query);
  const filteredGroups = useMemo(
    () => groups.filter((group) => groupMatches(group, normalizedQuery)),
    [groups, normalizedQuery],
  );
  const activeGroup =
    filteredGroups.find((group) => group.key === activeGroupKey) ?? filteredGroups[0] ?? null;
  const labels = useMemo(
    () =>
      new Map(
        groups.flatMap((group) =>
          group.keywords.map((keyword) => [keyword.tag, keyword.label] as const),
        ),
      ),
    [groups],
  );

  useEffect(() => {
    if (activeGroup && activeGroup.key !== activeGroupKey) setActiveGroupKey(activeGroup.key);
  }, [activeGroup, activeGroupKey]);

  useEffect(() => {
    if (hubGroups === null) return;
    onHubTagsLoaded?.(hubGroups.flatMap((group) => group.keywords.map((item) => item.tag)));
  }, [hubGroups, onHubTagsLoaded]);

  useEffect(() => {
    if (keywordGroups === null) return;
    onMechanicTagsLoaded?.(
      keywordGroups.flatMap((group) => group.keywords.map((item) => item.tag)),
    );
  }, [keywordGroups, onMechanicTagsLoaded]);

  function toggle(tag: string) {
    onChange(selected.has(tag) ? value.filter((item) => item !== tag) : [...value, tag]);
  }

  const loading = hubGroups === null || keywordGroups === null;
  return (
    <div className="space-y-6">
      {loading && <p className="text-sm text-gray-500">Loading themes...</p>}
      {keywordError && <p className="text-sm text-red-600">{keywordError}</p>}
      {value.length > 0 && (
        <SelectedKeywords value={value} labels={labels} onToggle={toggle} />
      )}
      {!loading && groups.length > 0 && (
        <section className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Find a group or keyword
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search themes and keywords"
                className="mt-1.5 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2.5 text-sm font-normal normal-case tracking-normal text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none"
              />
            </label>
            <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Top-level group
              <select
                value={activeGroup?.key ?? ""}
                onChange={(event) => setActiveGroupKey(event.target.value)}
                disabled={filteredGroups.length === 0}
                className="mt-1.5 w-full rounded-lg border border-white/15 bg-gray-900 px-3 py-2.5 text-sm font-normal normal-case tracking-normal text-white disabled:opacity-50"
              >
                {filteredGroups.map((group) => {
                  const count = group.keywords.filter((item) => selected.has(item.tag)).length;
                  return (
                    <option key={group.key} value={group.key}>
                      {group.label} ({count}/{group.keywords.length})
                    </option>
                  );
                })}
              </select>
            </label>
          </div>
          {activeGroup ? (
            <KeywordPanel
              group={activeGroup}
              query={normalizedQuery}
              selected={selected}
              suggested={suggestedSet}
              onToggle={toggle}
            />
          ) : (
            <p className="rounded-lg border border-dashed border-white/15 px-4 py-8 text-center text-sm text-gray-500">
              No groups or keywords match “{query.trim()}”.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

function SelectedKeywords({
  value,
  labels,
  onToggle,
}: {
  value: string[];
  labels: Map<string, string>;
  onToggle: (tag: string) => void;
}) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Selected</h3>
      <div className="flex flex-wrap gap-2">
        {value.map((tag) => (
          <button key={tag} type="button" onClick={() => onToggle(tag)} className="rounded-full bg-blue-600 px-3 py-1 text-sm text-white shadow hover:bg-blue-700">
            {labels.get(tag) ?? tag.replace(/_/g, " ")} ×
          </button>
        ))}
      </div>
    </section>
  );
}

function KeywordPanel({
  group,
  query,
  selected,
  suggested,
  onToggle,
}: {
  group: BrowserGroup;
  query: string;
  selected: Set<string>;
  suggested: Set<string>;
  onToggle: (tag: string) => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/15 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">{group.label}</h3>
        <span className="text-xs text-gray-500">{group.keywords.length} keywords</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {group.keywords.map((keyword) => (
          <KeywordButton
            key={keyword.tag}
            keyword={keyword}
            kind={group.kind}
            active={selected.has(keyword.tag)}
            suggested={suggested.has(keyword.tag)}
            searchMatch={keywordMatches(keyword, query)}
            onToggle={onToggle}
          />
        ))}
      </div>
    </div>
  );
}

function KeywordButton({
  keyword,
  kind,
  active,
  suggested,
  searchMatch,
  onToggle,
}: {
  keyword: KeywordChip;
  kind: BrowserGroup["kind"];
  active: boolean;
  suggested: boolean;
  searchMatch: boolean;
  onToggle: (tag: string) => void;
}) {
  const tone = active
    ? kind === "mechanic"
      ? "border-violet-500 bg-violet-500/20 text-violet-100"
      : "border-blue-500 bg-blue-500/20 text-blue-100"
    : searchMatch
      ? "border-cyan-400 bg-cyan-500/15 text-cyan-100 ring-1 ring-cyan-400/40"
      : suggested
        ? "border-amber-400/70 bg-amber-500/15 text-amber-100"
        : "border-white/15 bg-white/5 text-gray-300 hover:border-white/30 hover:bg-white/10";
  return (
    <button type="button" onClick={() => onToggle(keyword.tag)} className={`rounded-full border px-3 py-1 text-sm transition ${tone}`}>
      {keyword.label}
      {keyword.deck_count ? <span className="ml-1 text-[11px] opacity-70">{formatDeckCount(keyword.deck_count)}</span> : null}
    </button>
  );
}

function formatDeckCount(count: number): string {
  if (count >= 1000) return `${Math.round(count / 1000)}K`;
  return String(count);
}
