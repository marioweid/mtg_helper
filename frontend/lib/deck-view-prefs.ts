// Per-deck UI preferences (view mode + sort), persisted in localStorage so a
// deck reopens with the layout the user last chose. Values are stored as raw
// strings; callers validate them against their own allowed sets before use.

const VIEW_KEY = (deckId: string) => `deck-view:${deckId}`;
const SORT_KEY = (deckId: string) => `deck-sort:${deckId}`;
const GROUP_KEY = (deckId: string) => `deck-group:${deckId}`;
const WORKSPACE_VIEW_KEY = (scope: string) => `card-workspace-view:${scope}`;
const WORKSPACE_SORT_KEY = (scope: string) => `card-workspace-sort:${scope}`;
const WORKSPACE_GROUP_KEY = (scope: string) => `card-workspace-group:${scope}`;

export type CardWorkspaceView = "grid" | "list";

function read(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode / quota — non-critical */
  }
}

export function getDeckView(deckId: string): string | null {
  return read(VIEW_KEY(deckId));
}

export function setDeckView(deckId: string, mode: string): void {
  write(VIEW_KEY(deckId), mode);
}

export function getDeckSort(deckId: string): string | null {
  return read(SORT_KEY(deckId));
}

export function setDeckSort(deckId: string, sort: string): void {
  write(SORT_KEY(deckId), sort);
}

export function getDeckGroup(deckId: string): string | null {
  return read(GROUP_KEY(deckId));
}

export function setDeckGroup(deckId: string, group: string): void {
  write(GROUP_KEY(deckId), group);
}

export function getWorkspaceView(scope: string): CardWorkspaceView | null {
  const value = read(WORKSPACE_VIEW_KEY(scope));
  return value === "grid" || value === "list" ? value : null;
}

export function setWorkspaceView(scope: string, view: CardWorkspaceView): void {
  write(WORKSPACE_VIEW_KEY(scope), view);
}

export function getWorkspaceSort(scope: string): string | null {
  return read(WORKSPACE_SORT_KEY(scope));
}

export function setWorkspaceSort(scope: string, sort: string): void {
  write(WORKSPACE_SORT_KEY(scope), sort);
}

export function getWorkspaceGroup(scope: string): string | null {
  return read(WORKSPACE_GROUP_KEY(scope));
}

export function setWorkspaceGroup(scope: string, group: string): void {
  write(WORKSPACE_GROUP_KEY(scope), group);
}
