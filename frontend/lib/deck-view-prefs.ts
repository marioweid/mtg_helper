// Per-deck UI preferences (view mode + sort), persisted in localStorage so a
// deck reopens with the layout the user last chose. Values are stored as raw
// strings; callers validate them against their own allowed sets before use.

const VIEW_KEY = (deckId: string) => `deck-view:${deckId}`;
const SORT_KEY = (deckId: string) => `deck-sort:${deckId}`;

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
