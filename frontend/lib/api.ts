import type {
  AccountResponse,
  AccountUpdate,
  BuildResponse,
  CardResponse,
  CardSuggestion,
  CollectionCardAdd,
  CollectionCardItem,
  CollectionCardUpdate,
  CollectionCreate,
  CollectionImportRequest,
  CollectionImportResponse,
  CollectionResponse,
  CollectionUpdate,
  DeckCardAdd,
  DeckCardResponse,
  DeckCreate,
  DeckDetailResponse,
  DeckImportRequest,
  DeckImportResponse,
  DeckResponse,
  DeckSummary,
  DeckUpdate,
  DescribeRequest,
  DescribeResponse,
  FeedbackCreate,
  FeedbackResponse,
  PaginationMeta,
  PreferenceCreate,
  PreferenceResponse,
  RankingWeightsResponse,
  RankingWeightsUpdate,
  SuggestResponse,
} from "@/lib/types";

const CLIENT_BASE =
  typeof window !== "undefined"
    ? "/api/v1"
    : `${process.env["BACKEND_ORIGIN"] ?? "http://localhost:8000"}/api/v1`;

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string> | undefined) ?? {}),
  };
  const res = await fetch(`${CLIENT_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as {
      error?: { code?: string; message?: string };
      detail?: { code?: string; message?: string };
    };
    const err = body.error ?? body.detail;
    throw new ApiError(err?.code ?? "UNKNOWN", err?.message ?? res.statusText);
  }
  const json = (await res.json()) as { data: T };
  return json.data;
}

export const apiClient = {
  // Account (authenticated)
  getMe: () => request<AccountResponse>("/me"),

  updateMe: (body: AccountUpdate) =>
    request<AccountResponse>("/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Cards
  searchCards: (params: {
    q?: string;
    type?: string;
    color_identity?: string;
    commander_legal?: boolean;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.type) qs.set("type", params.type);
    if (params.color_identity) qs.set("color_identity", params.color_identity);
    if (params.commander_legal !== undefined)
      qs.set("commander_legal", String(params.commander_legal));
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    return request<CardResponse[]>(`/cards/search?${qs.toString()}`);
  },

  getCard: (scryfallId: string) => request<CardResponse>(`/cards/${scryfallId}`),

  // Decks
  listDecks: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return request<DeckSummary[]>(`/decks${q ? `?${q}` : ""}`);
  },

  createDeck: (body: DeckCreate) =>
    request<DeckResponse>("/decks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  importDeck: (body: DeckImportRequest) =>
    request<DeckImportResponse>("/decks/import", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getDeck: (id: string) => request<DeckDetailResponse>(`/decks/${id}`),

  updateDeck: (deckId: string, body: DeckUpdate) =>
    request<DeckResponse>(`/decks/${deckId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  addCard: (deckId: string, body: DeckCardAdd) =>
    request<DeckCardResponse>(`/decks/${deckId}/cards`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteDeck: (deckId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204) throw new ApiError("DELETE_FAILED", "Failed to delete deck");
    }),

  removeCard: (deckId: string, scryfallId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/cards/${scryfallId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204) throw new ApiError("DELETE_FAILED", "Failed to remove card");
    }),

  // AI
  buildStage: (
    deckId: string,
    opts?: {
      stage?: string;
      target?: number;
      exclude?: string[];
      collection_ids?: string[];
      max_price_cents?: number | null;
      min_price_cents?: number | null;
    },
  ) =>
    request<BuildResponse>(`/decks/${deckId}/build`, {
      method: "POST",
      body: JSON.stringify({
        stage: opts?.stage ?? null,
        target: opts?.target ?? null,
        exclude: opts?.exclude ?? null,
        collection_ids: opts?.collection_ids ?? null,
        max_price_cents: opts?.max_price_cents ?? null,
        min_price_cents: opts?.min_price_cents ?? null,
      }),
    }),

  suggestCards: (
    deckId: string,
    prompt: string,
    count = 10,
    opts?: {
      collection_ids?: string[];
      max_price_cents?: number | null;
      min_price_cents?: number | null;
    },
  ) =>
    request<SuggestResponse>(`/decks/${deckId}/suggest`, {
      method: "POST",
      body: JSON.stringify({
        prompt,
        count,
        collection_ids: opts?.collection_ids ?? null,
        max_price_cents: opts?.max_price_cents ?? null,
        min_price_cents: opts?.min_price_cents ?? null,
      }),
    }),

  describeDeck: (body: DescribeRequest) =>
    request<DescribeResponse>("/decks/describe", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  exportMoxfield: (deckId: string): Promise<string> =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/export/moxfield`).then((res) => {
      if (!res.ok) throw new ApiError("EXPORT_FAILED", "Export failed");
      return res.text();
    }),

  // Feedback
  addFeedback: (deckId: string, body: FeedbackCreate) =>
    request<FeedbackResponse>(`/decks/${deckId}/feedback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listFeedback: (deckId: string) =>
    request<FeedbackResponse[]>(`/decks/${deckId}/feedback`),

  deleteFeedback: (deckId: string, feedbackId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/feedback/${feedbackId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to delete feedback");
    }),

  // Preferences
  createPreference: (body: PreferenceCreate) =>
    request<PreferenceResponse>(`/me/preferences`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listPreferences: () => request<PreferenceResponse[]>(`/me/preferences`),

  deletePreference: (preferenceId: string) =>
    fetch(`${CLIENT_BASE}/me/preferences/${preferenceId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to delete preference");
    }),

  // Collections
  listCollections: () => request<CollectionResponse[]>(`/me/collections`),

  createCollection: (body: CollectionCreate) =>
    request<CollectionResponse>(`/me/collections`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getCollection: (id: string) => request<CollectionResponse>(`/collections/${id}`),

  renameCollection: (id: string, body: CollectionUpdate) =>
    request<CollectionResponse>(`/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteCollection: (id: string) =>
    fetch(`${CLIENT_BASE}/collections/${id}`, { method: "DELETE" }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to delete collection");
    }),

  listCollectionCards: (id: string, params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return fetch(`${CLIENT_BASE}/collections/${id}/cards${q ? `?${q}` : ""}`).then(async (res) => {
      if (!res.ok) throw new ApiError("FETCH_FAILED", "Failed to load cards");
      return (await res.json()) as { data: CollectionCardItem[]; meta: PaginationMeta };
    });
  },

  addCollectionCard: (id: string, body: CollectionCardAdd) =>
    request<CollectionCardItem>(`/collections/${id}/cards`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateCollectionCard: (id: string, cardId: string, body: CollectionCardUpdate) =>
    request<CollectionCardItem>(`/collections/${id}/cards/${cardId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  removeCollectionCard: (id: string, cardId: string) =>
    fetch(`${CLIENT_BASE}/collections/${id}/cards/${cardId}`, { method: "DELETE" }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to remove card");
    }),

  importCollectionCsv: (id: string, body: CollectionImportRequest) =>
    request<CollectionImportResponse>(`/collections/${id}/import`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  exportCollectionCsv: (id: string): Promise<string> =>
    fetch(`${CLIENT_BASE}/collections/${id}/export`).then((res) => {
      if (!res.ok) throw new ApiError("EXPORT_FAILED", "Export failed");
      return res.text();
    }),

  // Ranking Weights
  getRankingWeights: () => request<RankingWeightsResponse>(`/me/ranking-weights`),

  updateRankingWeights: (body: RankingWeightsUpdate) =>
    request<RankingWeightsResponse>(`/me/ranking-weights`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

// Re-export for convenience
export type { CardSuggestion };
