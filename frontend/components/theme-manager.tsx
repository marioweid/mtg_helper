"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type ThemeGroup = {
  id: number;
  slug: string;
  label: string;
  description: string | null;
  sort_order: number;
  enabled: boolean;
  deleted_at: string | null;
};

type SourceTag = {
  source: "moxfield" | "archidekt";
  source_id: string;
  tag: string;
  name: string;
  active: boolean;
  enabled: boolean;
  group_id: number | null;
  last_card_sync_at: string | null;
  card_count: number;
};

type ThemeState = { groups: ThemeGroup[]; source_tags: SourceTag[] };
type GroupSelection = number | null | undefined;
type SelectableGroup = Pick<ThemeGroup, "id" | "deleted_at">;

type ThemeSuggestion = {
  id: number;
  source: "moxfield" | "archidekt";
  source_id: number;
  confidence: number;
  rationale: string | null;
  status: string;
  created_at: string | null;
  reviewed_at: string | null;
  target_slug: string | null;
  target_label: string | null;
  target_description: string | null;
  target_aliases: string[] | null;
  source_name: string | null;
  source_tag: string | null;
};

type ThemeSuggestJob = {
  status: "idle" | "running" | "ok" | "error";
  phase: string;
  error: string | null;
  result: Record<string, unknown> | null;
};

export function resolveSelectedGroup(
  current: GroupSelection,
  groups: SelectableGroup[],
): number | null {
  const activeGroups = groups.filter((group) => !group.deleted_at);
  if (current === undefined) return activeGroups[0]?.id ?? null;
  if (current === null) return null;
  return activeGroups.some((group) => group.id === current) ? current : null;
}

async function mutate(path: string, method: string, body?: unknown): Promise<void> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }
}

export function ThemeManager() {
  const [state, setState] = useState<ThemeState>({ groups: [], source_tags: [] });
  const [selectedGroupId, setSelectedGroupId] = useState<GroupSelection>(undefined);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [newLabel, setNewLabel] = useState("");
  const [suggestions, setSuggestions] = useState<ThemeSuggestion[]>([]);
  const [suggestJob, setSuggestJob] = useState<ThemeSuggestJob>({
    status: "idle",
    phase: "",
    error: null,
    result: null,
  });
  const [suggestError, setSuggestError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/v1/admin/themes");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const next = (await response.json()) as ThemeState;
    setState(next);
    setSelectedGroupId((current) => resolveSelectedGroup(current, next.groups));
  }, []);

  const refreshSuggestions = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/admin/theme-suggestions");
      if (!response.ok) return;
      const body = (await response.json()) as { suggestions: ThemeSuggestion[] };
      setSuggestions(body.suggestions);
    } catch {
      // Transient — next refresh retries.
    }
  }, []);

  const refreshSuggestJob = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/admin/status");
      if (!response.ok) return;
      const body = (await response.json()) as { theme_suggest: ThemeSuggestJob };
      setSuggestJob(body.theme_suggest);
    } catch {
      // Transient — next poll retries.
    }
  }, []);

  useEffect(() => {
    void refresh().catch((reason: unknown) => setError(String(reason)));
    void refreshSuggestions();
    void refreshSuggestJob();
  }, [refresh, refreshSuggestions, refreshSuggestJob]);

  useEffect(() => {
    if (suggestJob.status !== "running") return;
    const id = setInterval(() => {
      void refreshSuggestJob().then(() => {
        if (suggestJob.status !== "running") void refreshSuggestions();
      });
    }, 2000);
    return () => clearInterval(id);
  }, [suggestJob.status, refreshSuggestJob, refreshSuggestions]);

  const visibleTags = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return state.source_tags.filter((tag) => {
      const inSelected =
        selectedGroupId === null ? tag.group_id === null : tag.group_id === selectedGroupId;
      return (
        inSelected &&
        (!needle || `${tag.name} ${tag.tag} ${tag.source}`.toLowerCase().includes(needle))
      );
    });
  }, [query, selectedGroupId, state.source_tags]);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function createGroup() {
    const label = newLabel.trim();
    if (!label) return;
    await run(async () => {
      await mutate("/api/v1/admin/theme-groups", "POST", { label });
      setNewLabel("");
    });
  }

  async function runSuggestions() {
    setSuggestError(null);
    try {
      await mutate("/api/v1/admin/suggest-theme-groups", "POST");
      await refreshSuggestJob();
    } catch (reason) {
      setSuggestError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function decideSuggestion(id: number, action: "apply" | "reject") {
    setSuggestError(null);
    try {
      await mutate(`/api/v1/admin/theme-suggestions/${id}/${action}`, "POST");
      await refreshSuggestions();
      await refresh();
    } catch (reason) {
      setSuggestError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section className="rounded border border-white/10 bg-black/30 p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Theme groups</h2>
          <p className="text-sm text-gray-400">
            Group Moxfield hubs and Archidekt tags without changing code.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void run(() => mutate("/api/v1/admin/sync-archidekt-tags", "POST"))}
            className="rounded border border-white/10 px-3 py-2 text-sm text-blue-300"
          >
            Sync Archidekt
          </button>
          <input
            value={newLabel}
            onChange={(event) => setNewLabel(event.target.value)}
            placeholder="New group name"
            className="rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            onClick={() => void createGroup()}
            className="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          >
            Create
          </button>
        </div>
      </div>

      {error && <p className="mb-3 rounded bg-red-950/60 p-2 text-sm text-red-300">{error}</p>}

      <div className="mb-6 rounded border border-white/10 bg-black/20 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">AI group suggestions</h3>
            <p className="text-sm text-gray-400">
              Draft group assignments for ungrouped hubs, then approve or reject each.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void runSuggestions()}
            disabled={suggestJob.status === "running"}
            className="rounded bg-purple-600 px-3 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {suggestJob.status === "running"
              ? "Drafting…"
              : suggestJob.status === "ok"
                ? "Draft again"
                : "Draft suggestions"}
          </button>
        </div>
        {suggestJob.status === "running" && (
          <p className="mt-2 text-sm text-blue-300">Phase: {suggestJob.phase}</p>
        )}
        {suggestJob.status === "error" && (
          <p className="mt-2 text-sm text-red-300">Draft failed: {suggestJob.error}</p>
        )}
        {suggestJob.status === "ok" && suggestJob.result && (
          <p className="mt-2 text-sm text-green-300">
            Drafted {String(suggestJob.result["suggestions_stored"])} suggestions from{" "}
            {String(suggestJob.result["sources_considered"])} sources.
          </p>
        )}
        {suggestError && (
          <p className="mt-2 text-sm text-red-300">Suggestion error: {suggestError}</p>
        )}
        <div className="mt-3 space-y-2">
          {suggestions.length === 0 ? (
            <p className="text-sm text-gray-500">
              {suggestJob.status === "ok" || suggestJob.status === "running"
                ? "No pending suggestions."
                : "Run a draft pass to see suggestions here."}
            </p>
          ) : (
            suggestions.map((suggestion) => (
              <div
                key={suggestion.id}
                className="flex flex-wrap items-start gap-3 rounded border border-white/10 p-3 text-sm"
              >
                <span
                  className={`rounded px-2 py-1 text-xs ${suggestion.source === "moxfield" ? "bg-purple-950 text-purple-200" : "bg-orange-950 text-orange-200"}`}
                >
                  {suggestion.source}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-white">
                    {suggestion.source_name}{" "}
                    <span className="text-xs text-gray-500">({suggestion.source_tag})</span>
                  </p>
                  <p className="text-xs text-gray-400">
                    → {suggestion.target_label}
                    {suggestion.target_slug ? ` (${suggestion.target_slug})` : ""}
                  </p>
                  {suggestion.target_description && (
                    <p className="mt-1 text-xs text-gray-500">{suggestion.target_description}</p>
                  )}
                  {suggestion.rationale && (
                    <p className="mt-1 text-xs italic text-gray-500">{suggestion.rationale}</p>
                  )}
                  <p className="mt-1 text-xs text-gray-600">
                    Confidence {Math.round(suggestion.confidence * 100)}%
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void decideSuggestion(suggestion.id, "apply")}
                    className="rounded bg-green-700 px-3 py-1.5 text-xs text-white hover:bg-green-600"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => void decideSuggestion(suggestion.id, "reject")}
                    className="rounded bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setSelectedGroupId(null)}
            className={`w-full rounded border px-3 py-2 text-left text-sm ${selectedGroupId === null ? "border-blue-500 bg-blue-950/40" : "border-white/10"}`}
          >
            Ungrouped
          </button>
          {state.groups.map((group) => (
            <div
              key={group.id}
              className={`rounded border border-white/10 p-2 ${group.deleted_at ? "opacity-50" : ""}`}
            >
              <button
                type="button"
                onClick={() => setSelectedGroupId(group.id)}
                className="w-full text-left text-sm text-white"
              >
                {group.label}
              </button>
              <div className="mt-2 flex gap-2 text-xs">
                {group.deleted_at ? (
                  <button
                    type="button"
                    onClick={() =>
                      void run(() =>
                        mutate(`/api/v1/admin/theme-groups/${group.id}/restore`, "POST"),
                      )
                    }
                    className="text-green-300"
                  >
                    Restore
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        const label = window.prompt("Group name", group.label)?.trim();
                        if (label)
                          void run(() =>
                            mutate(`/api/v1/admin/theme-groups/${group.id}`, "PATCH", { label }),
                          );
                      }}
                      className="text-blue-300"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        void run(() =>
                          mutate(`/api/v1/admin/theme-groups/${group.id}`, "PATCH", {
                            enabled: !group.enabled,
                          }),
                        )
                      }
                      className="text-yellow-300"
                    >
                      {group.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          window.confirm(`Delete ${group.label}? Its tags will become ungrouped.`)
                        ) {
                          void run(() =>
                            mutate(`/api/v1/admin/theme-groups/${group.id}`, "PATCH", {
                              delete: true,
                            }),
                          );
                        }
                      }}
                      className="text-red-300"
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        <div>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search source tags"
            className="mb-3 w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
          />
          <div className="max-h-[34rem] space-y-2 overflow-y-auto">
            {visibleTags.map((tag) => (
              <div
                key={`${tag.source}:${tag.source_id}`}
                className="flex flex-wrap items-center gap-3 rounded border border-white/10 p-3 text-sm"
              >
                <span
                  className={`rounded px-2 py-1 text-xs ${tag.source === "moxfield" ? "bg-purple-950 text-purple-200" : "bg-orange-950 text-orange-200"}`}
                >
                  {tag.source}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-white">{tag.name}</p>
                  <p className="text-xs text-gray-500">
                    {tag.tag} · {Number(tag.card_count).toLocaleString()} cards
                  </p>
                </div>
                <select
                  value={tag.group_id ?? ""}
                  onChange={(event) =>
                    void run(() =>
                      mutate("/api/v1/admin/theme-membership", "PUT", {
                        source: tag.source,
                        source_id: Number(tag.source_id),
                        group_id: event.target.value ? Number(event.target.value) : null,
                      }),
                    )
                  }
                  className="rounded border border-white/10 bg-black/40 px-2 py-1 text-white"
                >
                  <option value="">Ungrouped</option>
                  {state.groups
                    .filter((group) => !group.deleted_at)
                    .map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.label}
                      </option>
                    ))}
                </select>
                <button
                  type="button"
                  onClick={() =>
                    void run(() =>
                      mutate(
                        `/api/v1/admin/theme-sources/${tag.source}/${tag.source_id}`,
                        "PATCH",
                        { enabled: !tag.enabled },
                      ),
                    )
                  }
                  className={`rounded px-2 py-1 text-xs ${tag.enabled ? "bg-green-950 text-green-300" : "bg-gray-800 text-gray-400"}`}
                >
                  {tag.enabled ? "Enabled" : "Disabled"}
                </button>
                {tag.source === "archidekt" && (
                  <button
                    type="button"
                    onClick={() =>
                      void run(() =>
                        mutate("/api/v1/admin/sync-archidekt-tag", "POST", {
                          tag_ref: tag.tag,
                          tag_sample_size: 10,
                          baseline_sample_size: 80,
                        }),
                      )
                    }
                    className="rounded border border-white/10 px-2 py-1 text-xs text-blue-300"
                  >
                    Sync
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
