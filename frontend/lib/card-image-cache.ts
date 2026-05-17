import { apiClient } from "@/lib/api";

const cache = new Map<string, Promise<string | null>>();

/**
 * Resolve a card image URL by name with module-scoped memoization.
 *
 * Uses the existing fuzzy ``/cards/search`` endpoint and keeps the first hit.
 * Network errors and empty results resolve to ``null`` so callers can render a
 * graceful fallback without a try/catch at every call site.
 */
export function getCardImage(name: string): Promise<string | null> {
  const key = name.trim().toLowerCase();
  if (!key) return Promise.resolve(null);
  let entry = cache.get(key);
  if (!entry) {
    entry = apiClient
      .searchCards({ q: name, limit: 1 })
      .then((rows) => rows[0]?.image_uri ?? null)
      .catch(() => null);
    cache.set(key, entry);
  }
  return entry;
}

/** Seed the cache so callers with a known image avoid a redundant fetch. */
export function primeCardImage(name: string, imageUri: string | null): void {
  const key = name.trim().toLowerCase();
  if (!key) return;
  if (!cache.has(key)) cache.set(key, Promise.resolve(imageUri));
}
