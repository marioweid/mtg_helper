import type {
  AccountResponse,
  AccountUpdate,
  BracketValidationResponse,
  BuildResponse,
  Capabilities,
  CardResponse,
  CardSuggestion,
  CoachMemoryResponse,
  CoachMemoryUpdate,
  ComboListResponse,
  CollectionCardAdd,
  CollectionCardItem,
  CollectionCardUpdate,
  CollectionCreate,
  CollectionFromUrlRequest,
  CollectionFromUrlResponse,
  CollectionImportRequest,
  CollectionImportResponse,
  CollectionResponse,
  CollectionUpdate,
  CollectionUrlImportRequest,
  ComparisonKind,
  DeckCardAdd,
  DeckCompareResponse,
  DeckCardResponse,
  DeckCreate,
  DeckDetailResponse,
  DeckImportRequest,
  DeckImportResponse,
  DeckUrlImportRequest,
  DeckResponse,
  DeckRevision,
  DeckRevisionCreate,
  DeckRevisionUpdate,
  DeckSummary,
  DeckUpdate,
  DescribeRequest,
  DescribeResponse,
  FeedbackCreate,
  FeedbackResponse,
  CommanderCoachRequest,
  CommanderCoachResponse,
  CommanderCoachStartResponse,
  CommanderSuggestRequest,
  CommanderSuggestResponse,
  KeywordExtractRequest,
  KeywordExtractResponse,
  KeywordGroup,
  ManaFixResponse,
  OptimizeJobStatus,
  OptimizeRequest,
  OptimizeStartResponse,
  PaginationMeta,
  PlaytestSimulateRequest,
  PlaytestStats,
  PlannedDeckChange,
  PlannedDeckChangeCreate,
  PlannedDeckChangeUpdate,
  PlannedShoppingListRequest,
  SimulationAnalysisResponse,
  PreferenceCreate,
  PreferenceResponse,
  QuickstartRequest,
  QuickstartResponse,
  RankingWeightsResponse,
  RankingWeightsUpdate,
  SnapshotDetailResponse,
  SnapshotResponse,
  SnapshotSummary,
  SuggestResponse,
  SwapRequest,
  SwapResponse,
  TopPicksResponse,
  TopPickSource,
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
    ...(options?.headers as Record<string, string> | undefined),
  };
  // Server-side (RSC) calls bypass the Next proxy and hit BACKEND_ORIGIN
  // directly, so they must inject the bearer token themselves.
  if (typeof window === "undefined" && !headers["authorization"]) {
    const { auth } = await import("@/auth");
    const session = await auth();
    if (session?.idToken) headers["authorization"] = `Bearer ${session.idToken}`;
  }
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

  getCapabilities: () => request<Capabilities>("/capabilities"),

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

  importDeckUrl: (body: DeckUrlImportRequest) =>
    request<DeckImportResponse>("/decks/import-url", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getDeck: (id: string) => request<DeckDetailResponse>(`/decks/${id}`),

  getTopPicks: (deckId: string, source: TopPickSource = "combined") =>
    request<TopPicksResponse>(`/decks/${deckId}/top-picks?source=${source}`),

  getDeckCombos: (id: string) => request<ComboListResponse>(`/decks/${id}/combos`),

  getBracketValidation: (id: string) =>
    request<BracketValidationResponse>(`/decks/${id}/bracket-validation`),

  manaFix: (deckId: string) =>
    request<ManaFixResponse>(`/decks/${deckId}/mana-fix`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  playtestSimulate: (deckId: string, body: PlaytestSimulateRequest = {}) =>
    request<PlaytestStats>(`/decks/${deckId}/playtest/simulate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  playtestAnalyze: (deckId: string, body: PlaytestSimulateRequest = {}) =>
    request<SimulationAnalysisResponse>(`/decks/${deckId}/playtest/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  startOptimizeDeck: (deckId: string, body: OptimizeRequest) =>
    request<OptimizeStartResponse>(`/decks/${deckId}/playtest/optimize`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getOptimizeStatus: (deckId: string, jobId: string) =>
    request<OptimizeJobStatus>(`/decks/${deckId}/playtest/optimize/${jobId}`),

  findSwaps: (deckId: string, cardId: string, body: SwapRequest = {}) =>
    request<SwapResponse>(`/decks/${deckId}/cards/${cardId}/swap`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateDeck: (deckId: string, body: DeckUpdate) =>
    request<DeckResponse>(`/decks/${deckId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  addCardNow: (deckId: string, body: DeckCardAdd) =>
    request<DeckCardResponse>(`/decks/${deckId}/cards`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  planCard: (deckId: string, body: PlannedDeckChangeCreate) =>
    request<PlannedDeckChange | null>(`/decks/${deckId}/planned-changes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  addCard: (deckId: string, body: DeckCardAdd) =>
    request<PlannedDeckChange | null>(`/decks/${deckId}/planned-changes`, {
      method: "POST",
      body: JSON.stringify({ ...body, direction: "addition" }),
    }),

  listPlannedChanges: (deckId: string) =>
    request<PlannedDeckChange[]>(`/decks/${deckId}/planned-changes`),

  exportPlannedShoppingList: async (deckId: string, body: PlannedShoppingListRequest) => {
    const res = await fetch(`${CLIENT_BASE}/decks/${deckId}/planned-changes/shopping-list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const payload = (await res.json().catch(() => ({}))) as {
        detail?: { code?: string; message?: string };
      };
      throw new ApiError(
        payload.detail?.code ?? "EXPORT_FAILED",
        payload.detail?.message ?? "Planned buy list export failed",
      );
    }
    return res.text();
  },

  updatePlannedChange: (deckId: string, planId: string, body: PlannedDeckChangeUpdate) =>
    request<PlannedDeckChange>(`/decks/${deckId}/planned-changes/${planId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  completePlannedChange: (deckId: string, planId: string, quantity = 1) =>
    request<PlannedDeckChange | null>(
      `/decks/${deckId}/planned-changes/${planId}/complete`,
      { method: "POST", body: JSON.stringify({ quantity }) },
    ),

  applyDeckRevision: (deckId: string, body: DeckRevisionCreate) =>
    request<DeckRevision>(`/decks/${deckId}/revisions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listDeckRevisions: (deckId: string) =>
    request<DeckRevision[]>(`/decks/${deckId}/revisions`),

  getDeckRevision: (revisionId: string) =>
    request<DeckRevision>(`/revisions/${revisionId}`),

  updateDeckRevision: (revisionId: string, body: DeckRevisionUpdate) =>
    request<DeckRevision>(`/revisions/${revisionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  cancelPlannedChange: (deckId: string, planId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/planned-changes/${planId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to cancel planned change");
    }),

  deleteDeck: (deckId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204) throw new ApiError("DELETE_FAILED", "Failed to delete deck");
    }),

  updateCardCategories: (deckId: string, scryfallId: string, categories: string[]) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/cards/${scryfallId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ categories }),
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("UPDATE_FAILED", "Failed to update card categories");
    }),

  updateCardQuantity: (deckId: string, scryfallId: string, quantity: number) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/cards/${scryfallId}/quantity`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity }),
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("UPDATE_FAILED", "Failed to update card quantity");
    }),

  removeCardNow: (deckId: string, scryfallId: string) =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/cards/${scryfallId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204) throw new ApiError("DELETE_FAILED", "Failed to remove card");
    }),

  removeCard: (deckId: string, scryfallId: string) =>
    request<PlannedDeckChange | null>(`/decks/${deckId}/planned-changes`, {
      method: "POST",
      body: JSON.stringify({
        card_scryfall_id: scryfallId,
        direction: "cut",
        quantity: 1,
      }),
    }),

  // Snapshots + Comparison
  listSnapshots: (deckId: string) =>
    request<SnapshotSummary[]>(`/decks/${deckId}/snapshots`),

  createSnapshot: (deckId: string, label?: string | null) =>
    request<SnapshotResponse>(`/decks/${deckId}/snapshots`, {
      method: "POST",
      body: JSON.stringify({ label: label ?? null }),
    }),

  getSnapshot: (snapshotId: string) =>
    request<SnapshotDetailResponse>(`/snapshots/${snapshotId}`),

  deleteSnapshot: (snapshotId: string) =>
    fetch(`${CLIENT_BASE}/snapshots/${snapshotId}`, {
      method: "DELETE",
    }).then((res) => {
      if (!res.ok && res.status !== 204)
        throw new ApiError("DELETE_FAILED", "Failed to delete snapshot");
    }),

  compareDecks: (left: { kind: ComparisonKind; id: string }, right: { kind: ComparisonKind; id: string }) => {
    const qs = new URLSearchParams({
      left: left.id,
      left_kind: left.kind,
      right: right.id,
      right_kind: right.kind,
    });
    return request<DeckCompareResponse>(`/decks/compare?${qs.toString()}`);
  },

  // Onboarding
  quickstart: (body: QuickstartRequest) =>
    request<QuickstartResponse>("/onboarding/quickstart", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // AI
  buildStage: (
    deckId: string,
    opts?: {
      stage?: string;
      target?: number;
      offset?: number;
      exclude?: string[];
      collection_ids?: string[];
      max_price_cents?: number | null;
      min_price_cents?: number | null;
      card_types?: string[];
      subtypes?: string[];
      theme_tag?: string | null;
    },
  ) =>
    request<BuildResponse>(`/decks/${deckId}/build`, {
      method: "POST",
      body: JSON.stringify({
        stage: opts?.stage ?? null,
        target: opts?.target ?? null,
        offset: opts?.offset ?? 0,
        exclude: opts?.exclude ?? null,
        collection_ids: opts?.collection_ids ?? null,
        max_price_cents: opts?.max_price_cents ?? null,
        min_price_cents: opts?.min_price_cents ?? null,
        card_types: opts?.card_types && opts.card_types.length > 0 ? opts.card_types : null,
        subtypes: opts?.subtypes && opts.subtypes.length > 0 ? opts.subtypes : null,
        theme_tag: opts?.theme_tag ?? null,
      }),
    }),

  coachDeck: (deckId: string, body: CommanderCoachRequest) =>
    request<CommanderCoachResponse>(`/decks/${deckId}/coach`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  startCoachDeck: (deckId: string, body: CommanderCoachRequest) =>
    request<CommanderCoachStartResponse>(`/decks/${deckId}/coach/start`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getCoachMemory: (deckId: string) =>
    request<CoachMemoryResponse>(`/decks/${deckId}/coach/memory`),

  updateCoachMemory: (deckId: string, body: CoachMemoryUpdate) =>
    request<CoachMemoryResponse>(`/decks/${deckId}/coach/memory`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  suggestCards: (
    deckId: string,
    prompt: string,
    count = 10,
    opts?: {
      collection_ids?: string[];
      max_price_cents?: number | null;
      min_price_cents?: number | null;
      card_types?: string[];
      subtypes?: string[];
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
        card_types: opts?.card_types && opts.card_types.length > 0 ? opts.card_types : null,
        subtypes: opts?.subtypes && opts.subtypes.length > 0 ? opts.subtypes : null,
      }),
    }),

  describeDeck: (body: DescribeRequest) =>
    request<DescribeResponse>("/decks/describe", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  extractKeywords: (body: KeywordExtractRequest) =>
    request<KeywordExtractResponse>("/decks/extract-keywords", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  suggestCommanders: (body: CommanderSuggestRequest) =>
    request<CommanderSuggestResponse>("/decks/suggest-commanders", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listOfficialKeywords: () => request<KeywordGroup[]>("/tags/keywords"),
  listHubTags: () => request<KeywordGroup[]>("/tags/hubs"),

  exportMoxfield: (deckId: string): Promise<string> =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/export/moxfield`).then((res) => {
      if (!res.ok) throw new ApiError("EXPORT_FAILED", "Export failed");
      return res.text();
    }),

  exportBuylist: (deckId: string): Promise<string> =>
    fetch(`${CLIENT_BASE}/decks/${deckId}/export/buylist`).then((res) => {
      if (!res.ok) throw new ApiError("EXPORT_FAILED", "Buy list export failed");
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

  listCollectionCards: (
    id: string,
    params?: {
      limit?: number;
      offset?: number;
      type?: string | null;
      min_price_cents?: number | null;
      max_price_cents?: number | null;
      search?: string | null;
      sort?: "name" | "price" | "quantity";
      direction?: "asc" | "desc";
      group?: "none" | "type" | "set";
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    if (params?.type) qs.set("type", params.type);
    if (params?.min_price_cents != null)
      qs.set("min_price_cents", String(params.min_price_cents));
    if (params?.max_price_cents != null)
      qs.set("max_price_cents", String(params.max_price_cents));
    if (params?.search) qs.set("search", params.search);
    if (params?.sort) qs.set("sort", params.sort);
    if (params?.direction) qs.set("direction", params.direction);
    if (params?.group) qs.set("group", params.group);
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

  importCollectionUrl: (id: string, body: CollectionUrlImportRequest) =>
    request<CollectionImportResponse>(`/collections/${id}/import-url`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  createCollectionFromUrl: (body: CollectionFromUrlRequest) =>
    request<CollectionFromUrlResponse>(`/me/collections/import-url`, {
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
