"use client";

import { useReducer, useEffect, useCallback, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import { CardSuggestionCard } from "@/components/card-suggestion";
import { CardSearchResult } from "@/components/card-search-result";
import { DeckCategoryGroup } from "@/components/deck-category-group";
import {
  bucketsFor,
  type CardSuggestion,
  type CardResponse,
  type CollectionResponse,
  type DeckCardItem,
} from "@/lib/types";
import { CATEGORY_ORDER, STAGE_LABELS, STAGE_DEFAULTS, CATEGORY_TARGETS } from "@/lib/constants";

type SuggestionStatus = "pending" | "accepted" | "rejected";

interface StageState {
  suggestions: CardSuggestion[];
  buffer: CardSuggestion[];
  rejectedNames: string[];
  statuses: Record<string, SuggestionStatus>;
  quantities: Record<string, number>;
  loaded: boolean;
  loading: boolean;
  error: string | null;
  target: number;
  unresolved: string[];
  exhausted: boolean;
  offset: number;
}

interface WizardState {
  activeStage: string;
  stages: Record<string, StageState>;
}

type WizardAction =
  | { type: "SET_ACTIVE_STAGE"; stage: string }
  | { type: "LOAD_START"; stage: string }
  | {
      type: "LOAD_SUCCESS";
      stage: string;
      suggestions: CardSuggestion[];
      buffer: CardSuggestion[];
      unresolved: string[];
    }
  | {
      type: "LOAD_MORE_SUCCESS";
      stage: string;
      suggestions: CardSuggestion[];
      buffer: CardSuggestion[];
      unresolved: string[];
    }
  | { type: "LOAD_ERROR"; stage: string; error: string }
  | { type: "SET_STATUS"; stage: string; scryfallId: string; status: SuggestionStatus }
  | { type: "REJECT_AND_REPLACE"; stage: string; scryfallId: string; cardName: string }
  | { type: "SET_TARGET"; stage: string; target: number }
  | { type: "SET_QUANTITY"; stage: string; scryfallId: string; quantity: number }
  | { type: "INVALIDATE_ALL" };

function makeStageState(stage: string): StageState {
  return {
    suggestions: [],
    buffer: [],
    rejectedNames: [],
    statuses: {},
    quantities: {},
    loaded: false,
    loading: false,
    error: null,
    target: STAGE_DEFAULTS[stage] ?? 10,
    unresolved: [],
    exhausted: false,
    offset: 0,
  };
}

function isBasicLand(suggestion: CardSuggestion): boolean {
  return suggestion.type_line?.includes("Basic Land") ?? false;
}

function detectCategory(card: CardResponse, fallback: string): string {
  if (card.type_line?.includes("Land")) return "lands";
  return fallback;
}

const BASIC_LAND_NAMES = ["Forest", "Island", "Plains", "Mountain", "Swamp", "Wastes"] as const;

const COLOR_TO_BASIC: Record<string, string> = {
  W: "Plains",
  U: "Island",
  B: "Swamp",
  R: "Mountain",
  G: "Forest",
};

const PRIMARY_TYPE_OPTIONS = [
  "Creature",
  "Instant",
  "Sorcery",
  "Artifact",
  "Enchantment",
  "Planeswalker",
  "Land",
  "Battle",
] as const;

const SUBTYPE_OPTIONS = [
  "Equipment",
  "Aura",
  "Vehicle",
  "Saga",
  "Background",
  "Class",
  "Food",
  "Treasure",
  "Clue",
] as const;

function basicLandsForIdentity(identity: string): readonly string[] {
  const colors = identity
    .split(",")
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean);
  if (colors.length === 0) return ["Wastes"];
  const allowed = new Set<string>();
  for (const c of colors) {
    const land = COLOR_TO_BASIC[c];
    if (land) allowed.add(land);
  }
  return BASIC_LAND_NAMES.filter((n) => allowed.has(n));
}

function computeStageCounts(cards: DeckCardItem[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const card of cards) {
    const stages =
      card.qualifying_stages && card.qualifying_stages.length > 0
        ? card.qualifying_stages
        : card.categories.length > 0
          ? card.categories
          : ["other"];
    for (const stage of stages) {
      counts[stage] = (counts[stage] ?? 0) + (card.quantity ?? 1);
    }
  }
  return counts;
}

function groupByCategory(cards: DeckCardItem[]): Record<string, DeckCardItem[]> {
  const groups: Record<string, DeckCardItem[]> = {};
  for (const card of cards) {
    for (const cat of bucketsFor(card)) {
      (groups[cat] ??= []).push(card);
    }
  }
  return groups;
}

function sortedCategories(groups: Record<string, DeckCardItem[]>): string[] {
  const ordered = CATEGORY_ORDER.filter((c) => groups[c]?.length);
  const extra = Object.keys(groups).filter((c) => !CATEGORY_ORDER.includes(c));
  return [...ordered, ...extra];
}

function getAcceptedCount(stageState: StageState): number {
  let count = 0;
  for (const [id, status] of Object.entries(stageState.statuses)) {
    if (status !== "accepted") continue;
    const suggestion = stageState.suggestions.find((s) => s.scryfall_id === id);
    if (suggestion && isBasicLand(suggestion)) {
      count += stageState.quantities[id] ?? 1;
    } else {
      count += 1;
    }
  }
  return count;
}

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "SET_ACTIVE_STAGE":
      return { ...state, activeStage: action.stage };
    case "LOAD_START":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...state.stages[action.stage]!, loading: true, error: null },
        },
      };
    case "LOAD_SUCCESS": {
      const seen = new Set<string>();
      const deduped = action.suggestions.filter((s) => {
        if (seen.has(s.scryfall_id)) return false;
        seen.add(s.scryfall_id);
        return true;
      });
      const statuses: Record<string, SuggestionStatus> = {};
      for (const s of deduped) statuses[s.scryfall_id] = "pending";
      const bufferIds = new Set(deduped.map((s) => s.scryfall_id));
      const buffer = action.buffer.filter((s) => !bufferIds.has(s.scryfall_id));
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...state.stages[action.stage]!,
            loading: false,
            loaded: true,
            suggestions: deduped,
            buffer,
            rejectedNames: [],
            statuses,
            quantities: {},
            unresolved: action.unresolved,
            exhausted: false,
            offset: deduped.length + buffer.length,
          },
        },
      };
    }
    case "LOAD_MORE_SUCCESS": {
      const existing = state.stages[action.stage]!;
      const existingIds = new Set(existing.suggestions.map((s) => s.scryfall_id));
      const seenNew = new Set<string>();
      const newSuggestions = action.suggestions.filter((s) => {
        if (existingIds.has(s.scryfall_id) || seenNew.has(s.scryfall_id)) return false;
        seenNew.add(s.scryfall_id);
        return true;
      });
      const newStatuses: Record<string, SuggestionStatus> = { ...existing.statuses };
      for (const s of newSuggestions) newStatuses[s.scryfall_id] = "pending";
      const mergedUnresolved = [
        ...existing.unresolved,
        ...action.unresolved.filter((u) => !existing.unresolved.includes(u)),
      ];
      const allIds = new Set([
        ...existingIds,
        ...newSuggestions.map((s) => s.scryfall_id),
      ]);
      const newBuffer = action.buffer.filter((s) => !allIds.has(s.scryfall_id));
      const exhausted = newSuggestions.length === 0 && newBuffer.length === 0;
      const newOffset =
        existing.suggestions.length + newSuggestions.length + newBuffer.length;
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...existing,
            loading: false,
            suggestions: [...existing.suggestions, ...newSuggestions],
            buffer: newBuffer,
            statuses: newStatuses,
            unresolved: mergedUnresolved,
            exhausted,
            offset: newOffset,
          },
        },
      };
    }
    case "LOAD_ERROR":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...state.stages[action.stage]!,
            loading: false,
            error: action.error,
          },
        },
      };
    case "SET_STATUS":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...state.stages[action.stage]!,
            statuses: {
              ...state.stages[action.stage]!.statuses,
              [action.scryfallId]: action.status,
            },
          },
        },
      };
    case "REJECT_AND_REPLACE": {
      const stage = state.stages[action.stage]!;
      const filtered = stage.suggestions.filter((s) => s.scryfall_id !== action.scryfallId);
      const [replacement, ...remainingBuffer] = stage.buffer;
      const newStatuses: Record<string, SuggestionStatus> = { ...stage.statuses };
      delete newStatuses[action.scryfallId];
      if (replacement) newStatuses[replacement.scryfall_id] = "pending";
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...stage,
            suggestions: replacement ? [...filtered, replacement] : filtered,
            buffer: remainingBuffer,
            rejectedNames: [...stage.rejectedNames, action.cardName],
            statuses: newStatuses,
          },
        },
      };
    }
    case "SET_TARGET":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...state.stages[action.stage]!, target: action.target },
        },
      };
    case "SET_QUANTITY": {
      const clamped = Math.min(99, Math.max(1, action.quantity));
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...state.stages[action.stage]!,
            quantities: {
              ...state.stages[action.stage]!.quantities,
              [action.scryfallId]: clamped,
            },
          },
        },
      };
    }
    case "INVALIDATE_ALL": {
      const stages: Record<string, StageState> = {};
      for (const [name, s] of Object.entries(state.stages)) {
        stages[name] = {
          ...makeStageState(name),
          target: s.target,
        };
      }
      return { ...state, stages };
    }
    default:
      return state;
  }
}

function initWizardState(): WizardState {
  const stages: Record<string, StageState> = {};
  for (const s of CATEGORY_ORDER) stages[s] = makeStageState(s);
  return { activeStage: CATEGORY_ORDER[0]!, stages };
}

export default function BuildPage() {
  const params = useParams();
  const deckId = params["id"] as string;

  const [petCardNames, setPetCardNames] = useState<Set<string>>(new Set());
  const [state, dispatch] = useReducer(wizardReducer, undefined, initWizardState);
  const [deckCategoryCounts, setDeckCategoryCounts] = useState<Record<string, number>>({});
  const [deckCards, setDeckCards] = useState<DeckCardItem[]>([]);
  const [deckListOpen, setDeckListOpen] = useState(false);
  const [deckColorIdentity, setDeckColorIdentity] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchType, setSearchType] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<CardResponse[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchAdded, setSearchAdded] = useState<Set<string>>(new Set());
  const [promptInput, setPromptInput] = useState("");
  const [promptSuggestions, setPromptSuggestions] = useState<CardSuggestion[]>([]);
  const [promptStatuses, setPromptStatuses] = useState<Record<string, SuggestionStatus>>({});
  const [promptQuantities, setPromptQuantities] = useState<Record<string, number>>({});
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [basicLandQuantities, setBasicLandQuantities] = useState<Record<string, number>>(
    () => Object.fromEntries(BASIC_LAND_NAMES.map((n) => [n, 1])),
  );
  const [basicLandAdding, setBasicLandAdding] = useState<Record<string, boolean>>({});
  const [collections, setCollections] = useState<CollectionResponse[]>([]);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>([]);
  const [collectionPanelOpen, setCollectionPanelOpen] = useState(false);
  const [maxPriceCents, setMaxPriceCents] = useState<number | null>(null);
  const [minPriceCents, setMinPriceCents] = useState<number | null>(null);
  const [pricePanelOpen, setPricePanelOpen] = useState(false);
  const [pricePanelDraft, setPricePanelDraft] = useState("");
  const [pricePanelMinDraft, setPricePanelMinDraft] = useState("");
  const [savingPriceCap, setSavingPriceCap] = useState(false);
  const [cardTypeFilters, setCardTypeFilters] = useState<string[]>([]);
  const [subtypeFilters, setSubtypeFilters] = useState<string[]>([]);
  const [typePanelOpen, setTypePanelOpen] = useState(false);
  const totalTypeFilters = cardTypeFilters.length + subtypeFilters.length;
  const [globalRejectedIds, setGlobalRejectedIds] = useState<Set<string>>(new Set());
  const [globalRejectedNames, setGlobalRejectedNames] = useState<string[]>([]);

  const acceptedScryfallIds = useMemo(
    () => new Set(deckCards.map((c) => c.scryfall_id)),
    [deckCards],
  );

  useEffect(() => {
    apiClient
      .listPreferences()
      .then((prefs) => {
        const names = new Set(
          prefs
            .filter((p) => p.preference_type === "pet_card" && p.card_name)
            .map((p) => p.card_name as string),
        );
        setPetCardNames(names);
      })
      .catch(() => {
        /* non-critical */
      });
  }, []);

  const refreshDeck = useCallback(async () => {
    try {
      const deck = await apiClient.getDeck(deckId);
      setDeckCategoryCounts(computeStageCounts(deck.cards));
      setDeckCards(deck.cards);
    } catch {
      /* non-critical */
    }
  }, [deckId]);

  // Fetch deck on mount to derive color identity, initial category counts, and stage targets
  useEffect(() => {
    apiClient
      .getDeck(deckId)
      .then((deck) => {
        setDeckColorIdentity(deck.commander_color_identity.join(","));
        setDeckCategoryCounts(computeStageCounts(deck.cards));
        setDeckCards(deck.cards);
        setSelectedCollectionIds(deck.suggestion_collection_ids);
        setMaxPriceCents(deck.max_price_cents ?? null);
        setPricePanelDraft(deck.max_price_cents ? (deck.max_price_cents / 100).toFixed(2) : "");
        setMinPriceCents(deck.min_price_cents ?? null);
        setPricePanelMinDraft(
          deck.min_price_cents ? (deck.min_price_cents / 100).toFixed(2) : "",
        );
        // Apply AI-suggested stage targets if present
        if (deck.stage_targets && Object.keys(deck.stage_targets).length > 0) {
          for (const [stage, target] of Object.entries(deck.stage_targets)) {
            dispatch({ type: "SET_TARGET", stage, target });
          }
        }
        void apiClient
          .listCollections()
          .then(setCollections)
          .catch(() => setCollections([]));
      })
      .catch(() => {
        /* non-critical */
      });
  }, [deckId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced card search
  useEffect(() => {
    if (!searchQuery.trim() && !searchType) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => {
      setSearchLoading(true);
      apiClient
        .searchCards({
          ...(searchQuery.trim() && { q: searchQuery.trim() }),
          ...(searchType && { type: searchType }),
          commander_legal: true,
          ...(deckColorIdentity && { color_identity: deckColorIdentity }),
          limit: 20,
        })
        .then((results) => setSearchResults(results))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, searchType, deckColorIdentity]);

  const loadStage = useCallback(
    async (stage: string) => {
      dispatch({ type: "LOAD_START", stage });
      try {
        const exclude = globalRejectedNames.length > 0 ? globalRejectedNames : undefined;
        const result = await apiClient.buildStage(deckId, {
          stage,
          target: 80,
          offset: 0,
          ...(exclude ? { exclude } : {}),
          card_types: cardTypeFilters,
          subtypes: subtypeFilters,
        });
        dispatch({
          type: "LOAD_SUCCESS",
          stage,
          suggestions: result.suggestions.slice(0, 40),
          buffer: result.suggestions.slice(40),
          unresolved: result.unresolved,
        });
      } catch (err) {
        dispatch({
          type: "LOAD_ERROR",
          stage,
          error: err instanceof ApiError ? err.message : "Failed to generate suggestions",
        });
      }
    },
    [deckId, cardTypeFilters, subtypeFilters, globalRejectedNames],
  );

  const loadMore = useCallback(
    async (stage: string, offset: number, rejectedNames: string[]) => {
      dispatch({ type: "LOAD_START", stage });
      try {
        const persistentExclude = [...rejectedNames, ...globalRejectedNames];
        const exclude = persistentExclude.length > 0 ? persistentExclude : undefined;
        const result = await apiClient.buildStage(deckId, {
          stage,
          target: 80,
          offset,
          ...(exclude ? { exclude } : {}),
          card_types: cardTypeFilters,
          subtypes: subtypeFilters,
        });
        dispatch({
          type: "LOAD_MORE_SUCCESS",
          stage,
          suggestions: result.suggestions.slice(0, 40),
          buffer: result.suggestions.slice(40),
          unresolved: result.unresolved,
        });
      } catch (err) {
        dispatch({
          type: "LOAD_ERROR",
          stage,
          error: err instanceof ApiError ? err.message : "Failed to generate suggestions",
        });
      }
    },
    [deckId, globalRejectedNames, cardTypeFilters, subtypeFilters],
  );

  function switchStage(stage: string) {
    dispatch({ type: "SET_ACTIVE_STAGE", stage });
    const stageState = state.stages[stage];
    if (stageState && !stageState.loaded && !stageState.loading) {
      void loadStage(stage);
    }
  }

  // Auto-load the first stage on mount
  useEffect(() => {
    const firstStage = CATEGORY_ORDER[0]!;
    const firstState = state.stages[firstStage];
    if (firstState && !firstState.loaded && !firstState.loading) {
      void loadStage(firstStage);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when type/subtype filters change (skip the initial render)
  const typeFilterMounted = useRef(false);
  useEffect(() => {
    if (!typeFilterMounted.current) {
      typeFilterMounted.current = true;
      return;
    }
    dispatch({ type: "INVALIDATE_ALL" });
    void loadStage(state.activeStage);
  }, [cardTypeFilters, subtypeFilters]); // eslint-disable-line react-hooks/exhaustive-deps

  async function persistSelectedCollections(next: string[]) {
    setSelectedCollectionIds(next);
    try {
      await apiClient.updateDeck(deckId, { suggestion_collection_ids: next });
      reloadAllSuggestions();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save collection filter");
    }
  }

  function toggleCollection(id: string) {
    const next = selectedCollectionIds.includes(id)
      ? selectedCollectionIds.filter((x) => x !== id)
      : [...selectedCollectionIds, id];
    void persistSelectedCollections(next);
  }

  function clearAllCollections() {
    if (selectedCollectionIds.length === 0) return;
    void persistSelectedCollections([]);
  }

  function reloadAllSuggestions() {
    dispatch({ type: "INVALIDATE_ALL" });
    void loadStage(state.activeStage);
  }

  function parsePriceInput(raw: string): number | null | "invalid" {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const eur = Number.parseFloat(trimmed);
    if (!Number.isFinite(eur) || eur < 0) return "invalid";
    return eur > 0 ? Math.round(eur * 100) : null;
  }

  async function handleSavePriceCap() {
    const nextMax = parsePriceInput(pricePanelDraft);
    const nextMin = parsePriceInput(pricePanelMinDraft);
    if (nextMax === "invalid" || nextMin === "invalid") {
      alert("Enter positive numbers or leave blank to clear.");
      return;
    }
    if (nextMin != null && nextMax != null && nextMin > nextMax) {
      alert("Minimum price must not exceed the maximum.");
      return;
    }
    setSavingPriceCap(true);
    try {
      await apiClient.updateDeck(deckId, {
        max_price_cents: nextMax ?? 0,
        min_price_cents: nextMin ?? 0,
      });
      setMaxPriceCents(nextMax);
      setMinPriceCents(nextMin);
      reloadAllSuggestions();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save price filter");
    } finally {
      setSavingPriceCap(false);
    }
  }

  function clearPriceCap() {
    if (maxPriceCents == null && minPriceCents == null) return;
    setPricePanelDraft("");
    setPricePanelMinDraft("");
    void (async () => {
      setSavingPriceCap(true);
      try {
        await apiClient.updateDeck(deckId, { max_price_cents: 0, min_price_cents: 0 });
        setMaxPriceCents(null);
        setMinPriceCents(null);
        reloadAllSuggestions();
      } catch (err) {
        alert(err instanceof Error ? err.message : "Failed to clear price filter");
      } finally {
        setSavingPriceCap(false);
      }
    })();
  }

  async function handleAccept(stage: string, suggestion: CardSuggestion) {
    dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "accepted" });
    const stageState = state.stages[stage]!;
    const qty = isBasicLand(suggestion) ? (stageState.quantities[suggestion.scryfall_id] ?? 1) : undefined;
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        ...(qty !== undefined && { quantity: qty }),
        categories: [suggestion.category],
        added_by: "ai",
        ai_reasoning: suggestion.reasoning,
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "pending" });
    }
  }

  async function handleReject(stage: string, suggestion: CardSuggestion) {
    dispatch({
      type: "REJECT_AND_REPLACE",
      stage,
      scryfallId: suggestion.scryfall_id,
      cardName: suggestion.name,
    });
    setGlobalRejectedIds((prev) => {
      const next = new Set(prev);
      next.add(suggestion.scryfall_id);
      return next;
    });
    setGlobalRejectedNames((prev) =>
      prev.includes(suggestion.name) ? prev : [...prev, suggestion.name],
    );
    try {
      await apiClient.addFeedback(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        feedback: "reject",
      });
    } catch {
      /* non-critical */
    }
  }

  async function handleRemoveAccepted(stage: string, suggestion: CardSuggestion) {
    dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "pending" });
    try {
      await apiClient.removeCard(deckId, suggestion.scryfall_id);
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
      dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "accepted" });
    }
  }

  async function handleAddRejected(stage: string, suggestion: CardSuggestion) {
    dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "accepted" });
    const stageState = state.stages[stage]!;
    const qty = isBasicLand(suggestion) ? (stageState.quantities[suggestion.scryfall_id] ?? 1) : undefined;
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        ...(qty !== undefined && { quantity: qty }),
        categories: [suggestion.category],
        added_by: "ai",
        ai_reasoning: suggestion.reasoning,
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      dispatch({ type: "SET_STATUS", stage, scryfallId: suggestion.scryfall_id, status: "rejected" });
    }
  }

  async function handleSearchAdd(card: CardResponse) {
    setSearchAdded((prev) => new Set([...prev, card.scryfall_id]));
    const category = detectCategory(card, state.activeStage);
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        categories: [category],
        added_by: "user",
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      setSearchAdded((prev) => {
        const next = new Set(prev);
        next.delete(card.scryfall_id);
        return next;
      });
    }
  }

  async function handleBasicLandAdd(name: string) {
    const quantity = basicLandQuantities[name] ?? 1;
    setBasicLandAdding((prev) => ({ ...prev, [name]: true }));
    try {
      const results = await apiClient.searchCards({ q: name, commander_legal: true, limit: 1 });
      const card = results[0];
      if (!card) throw new Error(`${name} not found`);
      await apiClient.addCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        quantity,
        categories: ["lands"],
        added_by: "user",
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : `Failed to add ${name}`);
    } finally {
      setBasicLandAdding((prev) => ({ ...prev, [name]: false }));
    }
  }

  async function handlePromptSubmit() {
    if (!promptInput.trim()) return;
    setPromptLoading(true);
    setPromptSuggestions([]);
    setPromptStatuses({});
    setPromptQuantities({});
    try {
      const result = await apiClient.suggestCards(deckId, promptInput.trim(), 10, {
        card_types: cardTypeFilters,
        subtypes: subtypeFilters,
      });
      setPromptSuggestions(result.suggestions);
      const statuses: Record<string, SuggestionStatus> = {};
      for (const s of result.suggestions) statuses[s.scryfall_id] = "pending";
      setPromptStatuses(statuses);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to get suggestions");
    } finally {
      setPromptLoading(false);
    }
  }

  async function handlePromptAccept(suggestion: CardSuggestion) {
    setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "accepted" }));
    const qty = isBasicLand(suggestion) ? (promptQuantities[suggestion.scryfall_id] ?? 1) : undefined;
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        ...(qty !== undefined && { quantity: qty }),
        categories: [suggestion.category],
        added_by: "ai",
        ai_reasoning: suggestion.reasoning,
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "pending" }));
    }
  }

  async function handlePromptReject(suggestion: CardSuggestion) {
    setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "rejected" }));
    setGlobalRejectedIds((prev) => {
      const next = new Set(prev);
      next.add(suggestion.scryfall_id);
      return next;
    });
    setGlobalRejectedNames((prev) =>
      prev.includes(suggestion.name) ? prev : [...prev, suggestion.name],
    );
    try {
      await apiClient.addFeedback(deckId, { card_scryfall_id: suggestion.scryfall_id, feedback: "down" });
    } catch {
      /* non-critical */
    }
  }

  async function handlePromptRemove(suggestion: CardSuggestion) {
    setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "pending" }));
    try {
      await apiClient.removeCard(deckId, suggestion.scryfall_id);
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
      setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "accepted" }));
    }
  }

  async function handleRemoveCard(scryfallId: string) {
    try {
      await apiClient.removeCard(deckId, scryfallId);
      void refreshDeck();
      // If card is in current stage suggestions, reset status to pending
      const activeStage = state.stages[state.activeStage];
      if (activeStage) {
        const match = activeStage.suggestions.find((s) => s.scryfall_id === scryfallId);
        if (match) {
          dispatch({ type: "SET_STATUS", stage: state.activeStage, scryfallId, status: "pending" });
        }
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
    }
  }

  async function handlePromptAddBack(suggestion: CardSuggestion) {
    setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "accepted" }));
    const qty = isBasicLand(suggestion) ? (promptQuantities[suggestion.scryfall_id] ?? 1) : undefined;
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        ...(qty !== undefined && { quantity: qty }),
        categories: [suggestion.category],
        added_by: "ai",
        ai_reasoning: suggestion.reasoning,
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      setPromptStatuses((prev) => ({ ...prev, [suggestion.scryfall_id]: "rejected" }));
    }
  }

  const activeStageState = state.stages[state.activeStage];

  function isHiddenCrossStage(s: CardSuggestion, status: SuggestionStatus): boolean {
    if (globalRejectedIds.has(s.scryfall_id) && status !== "rejected") return true;
    if (acceptedScryfallIds.has(s.scryfall_id) && status !== "accepted") return true;
    return false;
  }

  const filteredSuggestions = activeStageState
    ? activeStageState.suggestions.filter((s) => {
        const status = activeStageState.statuses[s.scryfall_id] ?? "pending";
        if (isHiddenCrossStage(s, status)) return false;
        return true;
      })
    : [];
  const filteredPromptSuggestions = promptSuggestions.filter((s) => {
    const status = promptStatuses[s.scryfall_id] ?? "pending";
    if (isHiddenCrossStage(s, status)) return false;
    return true;
  });

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Build Deck</h1>
        <Link href={`/decks/${deckId}`} className="text-sm text-gray-400 hover:text-white transition-colors">
          View deck
        </Link>
      </div>

      {/* Collection filter panel */}
      {collections.length > 0 && (
        <details
          open={collectionPanelOpen}
          onToggle={(e) => setCollectionPanelOpen((e.target as HTMLDetailsElement).open)}
          className="mb-4 rounded-xl border border-white/10 bg-white/5"
        >
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white hover:bg-white/5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span>Build using collection only</span>
              {selectedCollectionIds.length > 0 && (
                <span className="rounded-full bg-indigo-600/40 px-2 py-0.5 text-xs text-indigo-200">
                  {selectedCollectionIds.length} active
                </span>
              )}
            </span>
            <span className="text-xs text-gray-400">{collectionPanelOpen ? "▲" : "▼"}</span>
          </summary>
          <div className="border-t border-white/10 px-4 py-3">
            <p className="mb-3 text-xs text-gray-400">
              When any collections are checked, suggestions are restricted to cards you own in those
              collections. Uncheck all to disable filtering.
            </p>
            <ul className="flex flex-col gap-1">
              {collections.map((c) => {
                const checked = selectedCollectionIds.includes(c.id);
                return (
                  <li key={c.id}>
                    <label className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-gray-200 hover:bg-white/5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleCollection(c.id)}
                        className="h-4 w-4 rounded border-white/20 bg-white/10 accent-indigo-500"
                      />
                      <span className="flex-1">{c.name}</span>
                      <span className="text-xs text-gray-500">{c.card_count} cards</span>
                    </label>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                onClick={reloadAllSuggestions}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
              >
                Reload suggestions
              </button>
              {selectedCollectionIds.length > 0 && (
                <button
                  type="button"
                  onClick={clearAllCollections}
                  className="text-xs text-gray-400 hover:text-white transition-colors"
                >
                  Clear all
                </button>
              )}
              <span className="text-xs text-gray-500">
                Refetches the active stage and clears cached suggestions for other stages.
              </span>
            </div>
          </div>
        </details>
      )}

      {/* Price cap panel */}
      <details
        open={pricePanelOpen}
        onToggle={(e) => setPricePanelOpen((e.target as HTMLDetailsElement).open)}
        className="mb-4 rounded-xl border border-white/10 bg-white/5"
      >
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white hover:bg-white/5 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <span>Price range (EUR)</span>
            {(minPriceCents != null || maxPriceCents != null) && (
              <span className="rounded-full bg-indigo-600/40 px-2 py-0.5 text-xs text-indigo-200">
                {minPriceCents != null ? `€${(minPriceCents / 100).toFixed(2)}` : "€0.00"}
                {" – "}
                {maxPriceCents != null ? `€${(maxPriceCents / 100).toFixed(2)}` : "∞"}
              </span>
            )}
          </span>
          <span className="text-xs text-gray-400">{pricePanelOpen ? "▲" : "▼"}</span>
        </summary>
        <div className="border-t border-white/10 px-4 py-3">
          <p className="mb-3 text-xs text-gray-400">
            Restrict suggestions to a nonfoil Scryfall EUR price range. Leave either side blank to
            omit that bound (min blank = €0, max blank = no cap). Cards without a EUR price are
            excluded. Saving reloads all stages.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-gray-400">
              Min €
              <input
                type="number"
                min="0"
                step="0.01"
                value={pricePanelMinDraft}
                onChange={(e) => setPricePanelMinDraft(e.target.value)}
                placeholder="0.00"
                className="w-24 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-gray-400">
              Max €
              <input
                type="number"
                min="0"
                step="0.01"
                value={pricePanelDraft}
                onChange={(e) => setPricePanelDraft(e.target.value)}
                placeholder="blank = no cap"
                className="w-32 rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              />
            </label>
            <button
              type="button"
              onClick={() => void handleSavePriceCap()}
              disabled={savingPriceCap}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
            >
              {savingPriceCap ? "Saving…" : "Save & reload"}
            </button>
            {(maxPriceCents != null || minPriceCents != null) && (
              <button
                type="button"
                onClick={clearPriceCap}
                disabled={savingPriceCap}
                className="text-xs text-gray-400 hover:text-white transition-colors disabled:opacity-50"
              >
                Clear range
              </button>
            )}
          </div>
        </div>
      </details>

      {/* Type filter panel */}
      <details
        open={typePanelOpen}
        onToggle={(e) => setTypePanelOpen((e.target as HTMLDetailsElement).open)}
        className="mb-4 rounded-xl border border-white/10 bg-white/5"
      >
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-white hover:bg-white/5 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <span>Card type filter</span>
            {totalTypeFilters > 0 && (
              <span className="rounded-full bg-indigo-600/40 px-2 py-0.5 text-xs text-indigo-200">
                {totalTypeFilters} active
              </span>
            )}
          </span>
          <span className="text-xs text-gray-400">{typePanelOpen ? "▲" : "▼"}</span>
        </summary>
        <div className="border-t border-white/10 px-4 py-3 space-y-4">
          <p className="text-xs text-gray-400">
            Restrict suggestions by primary type and/or subtype. Cards must match at least one
            selection in every active group (e.g. Creature + Equipment = creature-equipment hybrids).
            Triggers a refetch.
          </p>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Primary type
            </div>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
              {PRIMARY_TYPE_OPTIONS.map((t) => {
                const active = cardTypeFilters.includes(t);
                return (
                  <label
                    key={t}
                    className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                      active
                        ? "border-indigo-500 bg-indigo-600/30 text-indigo-100"
                        : "border-white/10 text-gray-300 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() =>
                        setCardTypeFilters((prev) =>
                          active ? prev.filter((x) => x !== t) : [...prev, t],
                        )
                      }
                      className="h-3 w-3 accent-indigo-500"
                    />
                    {t}
                  </label>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Subtype
            </div>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
              {SUBTYPE_OPTIONS.map((t) => {
                const active = subtypeFilters.includes(t);
                return (
                  <label
                    key={t}
                    className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                      active
                        ? "border-indigo-500 bg-indigo-600/30 text-indigo-100"
                        : "border-white/10 text-gray-300 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() =>
                        setSubtypeFilters((prev) =>
                          active ? prev.filter((x) => x !== t) : [...prev, t],
                        )
                      }
                      className="h-3 w-3 accent-indigo-500"
                    />
                    {t}
                  </label>
                );
              })}
            </div>
          </div>

          {totalTypeFilters > 0 && (
            <button
              type="button"
              onClick={() => {
                setCardTypeFilters([]);
                setSubtypeFilters([]);
              }}
              className="text-xs text-gray-400 underline-offset-2 hover:text-white hover:underline"
            >
              Clear all filters
            </button>
          )}
        </div>
      </details>

      {/* Stage tab bar */}
      <div className="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-white/5 p-1">
        {CATEGORY_ORDER.map((stage) => {
          const s = state.stages[stage];
          const deckCount = deckCategoryCounts[stage] ?? 0;
          const target = s?.target ?? STAGE_DEFAULTS[stage] ?? 10;
          const done = deckCount >= target;
          const isActive = state.activeStage === stage;
          return (
            <button
              key={stage}
              onClick={() => switchStage(stage)}
              className={`flex flex-shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:bg-white/10 hover:text-white"
              }`}
            >
              {done && <span className="text-green-400 text-xs">✓</span>}
              {STAGE_LABELS[stage] ?? stage}
              <span className={`text-xs ${done ? "text-green-400" : "text-gray-500"}`}>
                {deckCount}/{target}
              </span>
            </button>
          );
        })}
      </div>

      {/* Active stage panel */}
      {activeStageState && (
        <div>
          {/* Target stepper */}
          <div className="mb-4 flex items-center gap-3">
            <span className="text-sm text-gray-400">Target:</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() =>
                  dispatch({
                    type: "SET_TARGET",
                    stage: state.activeStage,
                    target: Math.max(1, activeStageState.target - 1),
                  })
                }
                className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 text-gray-300 hover:bg-white/20 transition-colors"
              >
                −
              </button>
              <input
                type="number"
                min={1}
                max={99}
                value={activeStageState.target}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v) && v >= 1 && v <= 99) {
                    dispatch({ type: "SET_TARGET", stage: state.activeStage, target: v });
                  }
                }}
                className="w-12 rounded-md bg-white/10 px-2 py-1 text-center text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={() =>
                  dispatch({
                    type: "SET_TARGET",
                    stage: state.activeStage,
                    target: Math.min(99, activeStageState.target + 1),
                  })
                }
                className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 text-gray-300 hover:bg-white/20 transition-colors"
              >
                +
              </button>
            </div>
            <span className="text-sm text-gray-500">
              {deckCategoryCounts[state.activeStage] ?? 0} / {activeStageState.target} in deck
            </span>
            {(() => {
              const [min, max] = CATEGORY_TARGETS[state.activeStage] ?? [0, 0];
              return (
                <span className="text-xs text-gray-600">
                  (recommended {min}–{max})
                </span>
              );
            })()}
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {(minPriceCents != null || maxPriceCents != null) && (
                <span className="rounded-md border border-amber-500/30 bg-amber-900/20 px-2 py-1 text-xs text-amber-200">
                  €{minPriceCents != null ? (minPriceCents / 100).toFixed(2) : "0.00"}
                  {" – "}
                  {maxPriceCents != null ? `€${(maxPriceCents / 100).toFixed(2)}` : "∞"} per card
                </span>
              )}
              {selectedCollectionIds.length > 0 && (
                <span className="rounded-md border border-indigo-500/30 bg-indigo-900/30 px-2 py-1 text-xs text-indigo-200">
                  Filtered to {selectedCollectionIds.length} collection
                  {selectedCollectionIds.length === 1 ? "" : "s"}
                </span>
              )}
            </div>
          </div>

          {/* Basic Lands (lands tab only) */}
          {state.activeStage === "lands" && (
            <div className="mb-4 rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">Basic Lands</p>
              <div className="flex flex-wrap gap-2">
                {basicLandsForIdentity(deckColorIdentity).map((name) => {
                  const current =
                    deckCards.find((c) => c.name === name)?.quantity ?? 0;
                  return (
                  <div key={name} className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5">
                    <span className="text-xs font-medium text-gray-300 w-14">{name}</span>
                    <span
                      className={`text-xs w-8 text-right tabular-nums ${current > 0 ? "text-green-400" : "text-gray-600"}`}
                      title="Currently in deck"
                    >
                      ×{current}
                    </span>
                    <button
                      onClick={() => setBasicLandQuantities((prev) => ({ ...prev, [name]: Math.max(1, (prev[name] ?? 1) - 1) }))}
                      className="flex h-5 w-5 items-center justify-center rounded bg-white/10 text-gray-300 hover:bg-white/20 text-xs"
                    >
                      −
                    </button>
                    <input
                      type="number"
                      min={1}
                      max={99}
                      value={basicLandQuantities[name] ?? 1}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (!isNaN(v) && v >= 1 && v <= 99)
                          setBasicLandQuantities((prev) => ({ ...prev, [name]: v }));
                      }}
                      className="w-8 rounded bg-white/10 px-1 py-0.5 text-center text-xs text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={() => setBasicLandQuantities((prev) => ({ ...prev, [name]: Math.min(99, (prev[name] ?? 1) + 1) }))}
                      className="flex h-5 w-5 items-center justify-center rounded bg-white/10 text-gray-300 hover:bg-white/20 text-xs"
                    >
                      +
                    </button>
                    <button
                      onClick={() => void handleBasicLandAdd(name)}
                      disabled={basicLandAdding[name]}
                      className="ml-1 rounded bg-indigo-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                    >
                      {basicLandAdding[name] ? "…" : "Add"}
                    </button>
                  </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Card Search */}
          <div className="mb-4">
            <button
              onClick={() => setSearchOpen((v) => !v)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <span>Search cards</span>
              <span className="text-xs">{searchOpen ? "▲" : "▼"}</span>
            </button>
            {searchOpen && (
              <div className="mt-2 rounded-xl border border-white/10 bg-white/5 p-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by name..."
                  className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-white
                    placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[
                    "Creature",
                    "Instant",
                    "Sorcery",
                    "Artifact",
                    "Enchantment",
                    "Planeswalker",
                    "Land",
                  ].map((t) => {
                    const active = searchType === t;
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setSearchType(active ? null : t)}
                        className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                          active
                            ? "border-indigo-500 bg-indigo-600/40 text-indigo-100"
                            : "border-white/10 text-gray-400 hover:border-white/20 hover:text-white"
                        }`}
                      >
                        {t}
                      </button>
                    );
                  })}
                  {searchType && (
                    <button
                      type="button"
                      onClick={() => setSearchType(null)}
                      className="rounded-full px-2.5 py-0.5 text-xs text-gray-500 hover:text-white"
                    >
                      Clear
                    </button>
                  )}
                </div>
                {searchLoading && <p className="mt-2 text-xs text-gray-500">Searching...</p>}
                {!searchLoading && searchResults.length > 0 && (
                  <div className="mt-2 max-h-64 space-y-1.5 overflow-y-auto">
                    {searchResults.map((card) => (
                      <CardSearchResult
                        key={card.scryfall_id}
                        card={card}
                        onAdd={() => void handleSearchAdd(card)}
                        added={searchAdded.has(card.scryfall_id)}
                      />
                    ))}
                  </div>
                )}
                {!searchLoading &&
                  (searchQuery.trim() || searchType) &&
                  searchResults.length === 0 && (
                    <p className="mt-2 text-xs text-gray-500">No results.</p>
                  )}
              </div>
            )}
          </div>

          {/* Custom Prompt Suggestions */}
          <div className="mb-4">
            <button
              onClick={() => setPromptOpen((v) => !v)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <span>Suggest cards</span>
              <span className="text-xs">{promptOpen ? "▲" : "▼"}</span>
            </button>
            {promptOpen && (
              <div className="mt-2 rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={promptInput}
                    onChange={(e) => setPromptInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handlePromptSubmit();
                    }}
                    placeholder="e.g. token doublers, graveyard recursion..."
                    className="flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm text-white
                      placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <button
                    onClick={() => void handlePromptSubmit()}
                    disabled={promptLoading || !promptInput.trim()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white
                      hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
                  >
                    Suggest
                  </button>
                </div>
                {promptLoading && (
                  <p className="mt-3 text-xs text-gray-500">Generating suggestions...</p>
                )}
                {!promptLoading && promptSuggestions.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                      Custom Suggestions
                    </p>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
                      {filteredPromptSuggestions.map((s) => (
                        <CardSuggestionCard
                          key={s.scryfall_id}
                          suggestion={s}
                          status={promptStatuses[s.scryfall_id] ?? "pending"}
                          onAccept={() => void handlePromptAccept(s)}
                          onReject={() => void handlePromptReject(s)}
                          onRemove={() => void handlePromptRemove(s)}
                          onAddBack={() => void handlePromptAddBack(s)}
                          isPetCard={petCardNames.has(s.name)}
                          isBasicLand={isBasicLand(s)}
                          quantity={promptQuantities[s.scryfall_id] ?? 1}
                          onQuantityChange={(qty) =>
                            setPromptQuantities((prev) => ({ ...prev, [s.scryfall_id]: qty }))
                          }
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Error */}
          {activeStageState.error && (
            <p className="mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
              {activeStageState.error}
            </p>
          )}

          {/* Loading (initial only — keep grid visible during load-more) */}
          {activeStageState.loading && !activeStageState.loaded && (
            <div className="flex items-center justify-center py-20 text-gray-500">
              Generating suggestions...
            </div>
          )}

          {/* Suggestions grid */}
          {activeStageState.loaded && activeStageState.suggestions.length > 0 && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
                {filteredSuggestions.map((s) => (
                  <CardSuggestionCard
                    key={s.scryfall_id}
                    suggestion={s}
                    status={activeStageState.statuses[s.scryfall_id] ?? "pending"}
                    onAccept={() => void handleAccept(state.activeStage, s)}
                    onReject={() => void handleReject(state.activeStage, s)}
                    onRemove={() => void handleRemoveAccepted(state.activeStage, s)}
                    onAddBack={() => void handleAddRejected(state.activeStage, s)}
                    isPetCard={petCardNames.has(s.name)}
                    isBasicLand={isBasicLand(s)}
                    quantity={activeStageState.quantities[s.scryfall_id] ?? 1}
                    onQuantityChange={(qty) =>
                      dispatch({
                        type: "SET_QUANTITY",
                        stage: state.activeStage,
                        scryfallId: s.scryfall_id,
                        quantity: qty,
                      })
                    }
                  />
                ))}
              </div>

              {activeStageState.unresolved.length > 0 && (
                <div className="mt-4 rounded-lg border border-yellow-500/20 bg-yellow-900/10 px-4 py-3">
                  <p className="text-xs text-yellow-400">
                    Unresolved cards (not found in database):{" "}
                    {activeStageState.unresolved.join(", ")}
                  </p>
                </div>
              )}
            </>
          )}

          {/* Generate button (shown when not yet loaded) */}
          {!activeStageState.loading && !activeStageState.loaded && (
            <div className="flex justify-center py-12">
              <button
                onClick={() => void loadStage(state.activeStage)}
                className="rounded-lg bg-indigo-600 px-6 py-2.5 font-medium text-white hover:bg-indigo-500 transition-colors"
              >
                Generate Suggestions
              </button>
            </div>
          )}

          {/* Load More button (shown after initial load) */}
          {activeStageState.loaded && (
            <div className="mt-6 flex items-center justify-end gap-3">
              {activeStageState.loading && (
                <span className="text-xs text-gray-500">Loading more…</span>
              )}
              {activeStageState.exhausted ? (
                <span className="text-xs text-gray-500">No more suggestions for this stage.</span>
              ) : (
                <button
                  onClick={() =>
                    void loadMore(
                      state.activeStage,
                      activeStageState.offset,
                      activeStageState.rejectedNames,
                    )
                  }
                  disabled={activeStageState.loading}
                  className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-400 hover:bg-white/5 hover:text-white transition-colors disabled:opacity-50"
                >
                  Load More
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Current Deck — collapsible card list with remove */}
      {deckCards.length > 0 && (
        <div className="mt-8 border-t border-white/10 pt-6">
          <button
            onClick={() => setDeckListOpen((v) => !v)}
            className="flex w-full items-center justify-between text-sm font-medium text-gray-300 hover:text-white transition-colors"
          >
            <span>Current Deck ({deckCards.length} cards)</span>
            <span className="text-xs text-gray-500">{deckListOpen ? "▲" : "▼"}</span>
          </button>
          {deckListOpen && (
            <div className="mt-3 flex flex-col gap-3">
              {sortedCategories(groupByCategory(deckCards)).map((cat) => (
                <DeckCategoryGroup
                  key={cat}
                  category={cat}
                  cards={groupByCategory(deckCards)[cat] ?? []}
                  onRemove={handleRemoveCard}
                  petCardNames={petCardNames}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
