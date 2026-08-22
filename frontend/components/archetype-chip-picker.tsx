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

function normalize(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function keywordMatches(keyword: KeywordChip, query: string): boolean {
  return normalize(keyword.label).includes(query) || normalize(keyword.tag).includes(query);
}

function filteredKeywords(group: KeywordGroup, query: string): KeywordChip[] {
  if (!query || normalize(group.display_name).includes(query)) return group.keywords;
  return group.keywords.filter((keyword) => keywordMatches(keyword, query));
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
  const [openCategories, setOpenCategories] = useState<Set<string>>(new Set());

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
  const labels = useMemo(() => {
    const groups = [...(hubGroups ?? []), ...(keywordGroups ?? [])];
    return new Map(
      groups.flatMap((group) =>
        group.keywords.map((keyword) => [keyword.tag, keyword.label] as const),
      ),
    );
  }, [hubGroups, keywordGroups]);
  const normalizedQuery = normalize(query);
  const adminGroups = useMemo(
    () =>
      (hubGroups ?? [])
        .filter((group) => group.category.startsWith("theme_group:"))
        .flatMap((group) => filteredKeywords(group, normalizedQuery)),
    [hubGroups, normalizedQuery],
  );
  const ungroupedThemes = useMemo(() => {
    const group = (hubGroups ?? []).find((item) => item.category === "ungrouped");
    return group ? filteredKeywords(group, normalizedQuery) : [];
  }, [hubGroups, normalizedQuery]);
  const officialGroups = useMemo(
    () =>
      (keywordGroups ?? [])
        .map((group) => ({ ...group, keywords: filteredKeywords(group, normalizedQuery) }))
        .filter((group) => group.keywords.length > 0),
    [keywordGroups, normalizedQuery],
  );

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

  function setCategoryOpen(category: string, open: boolean) {
    setOpenCategories((current) => {
      const next = new Set(current);
      if (open) next.add(category);
      else next.delete(category);
      return next;
    });
  }

  const loading = hubGroups === null || keywordGroups === null;
  const hasResults =
    adminGroups.length > 0 || ungroupedThemes.length > 0 || officialGroups.length > 0;

  return (
    <div className="space-y-6">
      {loading && <p className="text-sm text-gray-500">Loading themes...</p>}
      {keywordError && <p className="text-sm text-red-600">{keywordError}</p>}
      {value.length > 0 && <SelectedKeywords value={value} labels={labels} onToggle={toggle} />}
      {!loading && (
        <>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-400">
            Find a theme or keyword
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search themes and keywords"
              className="mt-1.5 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2.5 text-sm font-normal normal-case tracking-normal text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none"
            />
          </label>
          {adminGroups.length > 0 && (
            <KeywordSection
              title="Theme groups"
              description="Curated groups managed in the admin panel"
              keywords={adminGroups}
              query={normalizedQuery}
              selected={selected}
              suggested={suggestedSet}
              onToggle={toggle}
            />
          )}
          {ungroupedThemes.length > 0 && (
            <KeywordSection
              title="Ungrouped themes"
              description="Moxfield and Archidekt themes not assigned to a group"
              keywords={ungroupedThemes}
              query={normalizedQuery}
              selected={selected}
              suggested={suggestedSet}
              onToggle={toggle}
            />
          )}
          {officialGroups.length > 0 && (
            <section>
              <SectionHeading
                title="Official keywords"
                description="Ability words, keyword abilities, and keyword actions"
              />
              <div className="space-y-2">
                {officialGroups.map((group) => {
                  const forcedOpen =
                    Boolean(normalizedQuery) ||
                    group.keywords.some((keyword) => selected.has(keyword.tag));
                  return (
                    <OfficialKeywordGroup
                      key={group.category}
                      group={group}
                      open={forcedOpen || openCategories.has(group.category)}
                      query={normalizedQuery}
                      selected={selected}
                      suggested={suggestedSet}
                      onToggle={toggle}
                      onOpenChange={(open) => setCategoryOpen(group.category, open)}
                    />
                  );
                })}
              </div>
            </section>
          )}
          {!hasResults && normalizedQuery && (
            <p className="rounded-lg border border-dashed border-white/15 px-4 py-8 text-center text-sm text-gray-500">
              No themes or keywords match “{query.trim()}”.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h3>
      <p className="mt-1 text-xs text-gray-500">{description}</p>
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
      <SectionHeading title="Selected" description="Click a selected keyword to remove it" />
      <div className="flex flex-wrap gap-2">
        {value.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => onToggle(tag)}
            className="rounded-full bg-blue-600 px-3 py-1 text-sm text-white shadow hover:bg-blue-700"
          >
            {labels.get(tag) ?? tag.replace(/_/g, " ")} ×
          </button>
        ))}
      </div>
    </section>
  );
}

interface KeywordListProps {
  keywords: KeywordChip[];
  query: string;
  selected: Set<string>;
  suggested: Set<string>;
  onToggle: (tag: string) => void;
}

function KeywordSection({
  title,
  description,
  ...listProps
}: KeywordListProps & { title: string; description: string }) {
  return (
    <section>
      <SectionHeading title={title} description={description} />
      <KeywordList {...listProps} />
    </section>
  );
}

function OfficialKeywordGroup({
  group,
  open,
  onOpenChange,
  ...listProps
}: Omit<KeywordListProps, "keywords"> & {
  group: KeywordGroup;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <details
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
      className="rounded-lg border border-white/10 bg-black/15"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-white">
        <span>{group.display_name}</span>
        <span className="text-xs font-normal text-gray-500">{group.keywords.length}</span>
      </summary>
      <div className="border-t border-white/10 p-4">
        <KeywordList keywords={group.keywords} {...listProps} />
      </div>
    </details>
  );
}

function KeywordList({ keywords, query, selected, suggested, onToggle }: KeywordListProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {keywords.map((keyword) => (
        <KeywordButton
          key={keyword.tag}
          keyword={keyword}
          active={selected.has(keyword.tag)}
          suggested={suggested.has(keyword.tag)}
          searchMatch={Boolean(query) && keywordMatches(keyword, query)}
          onToggle={onToggle}
        />
      ))}
    </div>
  );
}

function KeywordButton({
  keyword,
  active,
  suggested,
  searchMatch,
  onToggle,
}: {
  keyword: KeywordChip;
  active: boolean;
  suggested: boolean;
  searchMatch: boolean;
  onToggle: (tag: string) => void;
}) {
  const tone = active
    ? "border-blue-500 bg-blue-500/20 text-blue-100"
    : searchMatch
      ? "border-cyan-400 bg-cyan-500/15 text-cyan-100 ring-1 ring-cyan-400/40"
      : suggested
        ? "border-amber-400/70 bg-amber-500/15 text-amber-100"
        : "border-white/15 bg-white/5 text-gray-300 hover:border-white/30 hover:bg-white/10";
  return (
    <button
      type="button"
      onClick={() => onToggle(keyword.tag)}
      className={`rounded-full border px-3 py-1 text-sm transition ${tone}`}
    >
      {keyword.label}
      {keyword.deck_count ? (
        <span className="ml-1 text-[11px] opacity-70">{formatDeckCount(keyword.deck_count)}</span>
      ) : null}
    </button>
  );
}

function formatDeckCount(count: number): string {
  if (count >= 1000) return `${Math.round(count / 1000)}K`;
  return String(count);
}
