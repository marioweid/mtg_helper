"use client";

import { useReducer, useEffect, useCallback, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import { cardIdentity } from "@/lib/card-identity";
import { CardSuggestionCard } from "@/components/card-suggestion";
import { CardHover } from "@/components/card-hover";
import { CardDetailModal } from "@/components/card-detail-modal";
import { BuilderFiltersDropdown } from "@/components/builder-filters-dropdown";
import { ExpandableDeckBar } from "@/components/expandable-deck-bar";
import { PlannedChangesPanel } from "@/components/planned-changes-panel";
import {
  type CardSuggestion,
  type CollectionResponse,
  type DeckCardItem,
  type DeckManaCurve,
  type PlannedDeckChange,
} from "@/lib/types";
import { CATEGORY_ORDER, STAGE_LABELS, STAGE_DEFAULTS, CATEGORY_TARGETS } from "@/lib/constants";

type SuggestionStatus = "pending" | "accepted" | "rejected";

const THEME_ETC_TAG = "__etc";

function themeStageKey(tag: string): string {
  return `theme:${tag}`;
}

function apiStageFor(stageKey: string): string {
  return stageKey.startsWith("theme:") ? "theme" : stageKey;
}

function themeTagForStageKey(stageKey: string): string | null {
  return stageKey.startsWith("theme:") ? stageKey.slice("theme:".length) : null;
}

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
  | { type: "INVALIDATE_ALL" }
  | { type: "INVALIDATE_STAGE"; stage: string };

function makeStageState(stage: string): StageState {
  const apiStage = apiStageFor(stage);
  return {
    suggestions: [],
    buffer: [],
    rejectedNames: [],
    statuses: {},
    quantities: {},
    loaded: false,
    loading: false,
    error: null,
    target: STAGE_DEFAULTS[apiStage] ?? 10,
    unresolved: [],
    exhausted: false,
    offset: 0,
  };
}

function isBasicLand(suggestion: CardSuggestion): boolean {
  return suggestion.type_line?.includes("Basic Land") ?? false;
}

function uniqueSuggestions(
  suggestions: CardSuggestion[],
  excluded: ReadonlySet<string> = new Set(),
): CardSuggestion[] {
  const seen = new Set(excluded);
  return suggestions.filter((suggestion) => {
    const identity = cardIdentity(suggestion);
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

const BASIC_LAND_NAMES = ["Forest", "Island", "Plains", "Mountain", "Swamp", "Wastes"] as const;

const COLOR_TO_BASIC: Record<string, string> = {
  W: "Plains",
  U: "Island",
  B: "Swamp",
  R: "Mountain",
  G: "Forest",
};

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

function formatTagLabel(tag: string): string {
  if (tag === THEME_ETC_TAG) return "Etc";
  return tag
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function computeStageCounts(cards: DeckCardItem[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const card of cards) {
    const stages =
      card.categories.length > 0
        ? card.categories
        : card.qualifying_stages && card.qualifying_stages.length > 0
          ? card.qualifying_stages
          : ["other"];
    for (const stage of stages) {
      counts[stage] = (counts[stage] ?? 0) + (card.quantity ?? 1);
    }
  }
  return counts;
}

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "SET_ACTIVE_STAGE":
      return { ...state, activeStage: action.stage };
    case "LOAD_START": {
      const loadingStage = state.stages[action.stage] ?? makeStageState(action.stage);
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...loadingStage, loading: true, error: null },
        },
      };
    }
    case "LOAD_SUCCESS": {
      const deduped = uniqueSuggestions(action.suggestions);
      const statuses: Record<string, SuggestionStatus> = {};
      for (const s of deduped) statuses[cardIdentity(s)] = "pending";
      const bufferIds = new Set(deduped.map(cardIdentity));
      const buffer = uniqueSuggestions(action.buffer, bufferIds);
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...(state.stages[action.stage] ?? makeStageState(action.stage)),
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
      const existingIds = new Set(existing.suggestions.map(cardIdentity));
      const newSuggestions = uniqueSuggestions(action.suggestions, existingIds);
      const newStatuses: Record<string, SuggestionStatus> = { ...existing.statuses };
      for (const s of newSuggestions) newStatuses[cardIdentity(s)] = "pending";
      const mergedUnresolved = [
        ...existing.unresolved,
        ...action.unresolved.filter((u) => !existing.unresolved.includes(u)),
      ];
      const allIds = new Set([...existingIds, ...newSuggestions.map(cardIdentity)]);
      const newBuffer = uniqueSuggestions(action.buffer, allIds);
      const exhausted = newSuggestions.length === 0 && newBuffer.length === 0;
      const newOffset = existing.suggestions.length + newSuggestions.length + newBuffer.length;
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
            ...(state.stages[action.stage] ?? makeStageState(action.stage)),
            loading: false,
            error: action.error,
          },
        },
      };
    case "SET_STATUS": {
      const statusStage = state.stages[action.stage] ?? makeStageState(action.stage);
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...statusStage,
            statuses: {
              ...statusStage.statuses,
              [action.scryfallId]: action.status,
            },
          },
        },
      };
    }
    case "REJECT_AND_REPLACE": {
      const stage = state.stages[action.stage]!;
      const filtered = stage.suggestions.filter((s) => cardIdentity(s) !== action.scryfallId);
      const [replacement, ...remainingBuffer] = stage.buffer;
      const newStatuses: Record<string, SuggestionStatus> = { ...stage.statuses };
      delete newStatuses[action.scryfallId];
      if (replacement) newStatuses[cardIdentity(replacement)] = "pending";
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
    case "SET_TARGET": {
      const targetStage = state.stages[action.stage] ?? makeStageState(action.stage);
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...targetStage, target: action.target },
        },
      };
    }
    case "SET_QUANTITY": {
      const clamped = Math.min(99, Math.max(1, action.quantity));
      const quantityStage = state.stages[action.stage] ?? makeStageState(action.stage);
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...quantityStage,
            quantities: {
              ...quantityStage.quantities,
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
    case "INVALIDATE_STAGE": {
      const current = state.stages[action.stage]!;
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            ...makeStageState(action.stage),
            target: current.target,
          },
        },
      };
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
  const [plannedChanges, setPlannedChanges] = useState<PlannedDeckChange[]>([]);
  const [physicalCardCount, setPhysicalCardCount] = useState(1);
  const [plannedCardCount, setPlannedCardCount] = useState(1);
  const [manaCurve, setManaCurve] = useState<DeckManaCurve | null>(null);
  const [deckCommander, setDeckCommander] = useState<{
    type_line: string | null;
    name: string | null;
  } | null>(null);
  const [deckBracket, setDeckBracket] = useState<number | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [deckColorIdentity, setDeckColorIdentity] = useState("");
  const [basicLandQuantities, setBasicLandQuantities] = useState<Record<string, number>>(() =>
    Object.fromEntries(BASIC_LAND_NAMES.map((n) => [n, 1])),
  );
  const [basicLandAdding, setBasicLandAdding] = useState<Record<string, boolean>>({});
  const [collections, setCollections] = useState<CollectionResponse[]>([]);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>([]);
  const [archetypeTags, setArchetypeTags] = useState<string[]>([]);
  const [selectedThemeTag, setSelectedThemeTag] = useState<string | null>(null);
  const themeTabs = useMemo(() => [...archetypeTags, THEME_ETC_TAG], [archetypeTags]);
  const [maxPriceCents, setMaxPriceCents] = useState<number | null>(null);
  const [minPriceCents, setMinPriceCents] = useState<number | null>(null);
  const [pricePanelDraft, setPricePanelDraft] = useState("");
  const [pricePanelMinDraft, setPricePanelMinDraft] = useState("");
  const [cardTypeFilters, setCardTypeFilters] = useState<string[]>([]);
  const [subtypeFilters, setSubtypeFilters] = useState<string[]>([]);
  const [globalRejectedIds, setGlobalRejectedIds] = useState<Set<string>>(new Set());
  const [globalRejectedNames, setGlobalRejectedNames] = useState<string[]>([]);
  const [comboCardNames, setComboCardNames] = useState<Set<string>>(new Set());

  // Cards that would complete an "almost-there" combo for this deck. Drives
  // the combo (⚡) icon on each suggestion. Refreshed alongside the deck —
  // adding a card may unlock new completions, removing one may close them.
  const refreshCombos = useCallback(async () => {
    try {
      const combos = await apiClient.getDeckCombos(deckId);
      const names = new Set<string>();
      for (const c of combos.almost_there) {
        for (const p of c.pieces) {
          if (!p.in_deck) names.add(p.card.name.toLowerCase());
        }
      }
      setComboCardNames(names);
    } catch {
      /* non-critical: combo discovery is best-effort */
    }
  }, [deckId]);

  const acceptedCardIds = useMemo(
    () =>
      new Set([
        ...deckCards.map(cardIdentity),
        ...plannedChanges.filter((plan) => plan.direction === "addition").map(cardIdentity),
      ]),
    [deckCards, plannedChanges],
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
      setPlannedChanges(deck.planned_changes);
      setPhysicalCardCount(deck.physical_card_count);
      setPlannedCardCount(deck.planned_card_count);
      setManaCurve(deck.mana_curve);
      setDeckCommander(deck.commander_card ?? null);
      setDeckBracket(deck.bracket ?? null);
      setArchetypeTags(deck.archetype_tags);
      setSelectedThemeTag((current) => current ?? deck.archetype_tags[0] ?? null);
    } catch {
      /* non-critical */
    }
    void refreshCombos();
  }, [deckId, refreshCombos]);

  // Fetch deck on mount to derive color identity, initial category counts, and stage targets
  useEffect(() => {
    void refreshCombos();
    apiClient
      .getDeck(deckId)
      .then((deck) => {
        setDeckColorIdentity(deck.commander_color_identity.join(","));
        setDeckCategoryCounts(computeStageCounts(deck.cards));
        setDeckCards(deck.cards);
        setPlannedChanges(deck.planned_changes);
        setPhysicalCardCount(deck.physical_card_count);
        setPlannedCardCount(deck.planned_card_count);
        setManaCurve(deck.mana_curve);
        setDeckCommander(deck.commander_card ?? null);
        setDeckBracket(deck.bracket ?? null);
        setSelectedCollectionIds(deck.suggestion_collection_ids);
        setArchetypeTags(deck.archetype_tags);
        setSelectedThemeTag((current) => current ?? deck.archetype_tags[0] ?? null);
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

  const loadStage = useCallback(
    async (stage: string, themeTagOverride?: string) => {
      const apiStage = apiStageFor(stage);
      const themeTag =
        apiStage === "theme"
          ? (themeTagForStageKey(stage) ??
            themeTagOverride ??
            selectedThemeTag ??
            archetypeTags[0] ??
            THEME_ETC_TAG)
          : null;
      const stageKey = apiStage === "theme" ? themeStageKey(themeTag ?? THEME_ETC_TAG) : stage;
      dispatch({ type: "LOAD_START", stage: stageKey });
      try {
        const exclude = globalRejectedNames.length > 0 ? globalRejectedNames : undefined;
        const result = await apiClient.buildStage(deckId, {
          stage: apiStage,
          target: 80,
          offset: 0,
          ...(exclude ? { exclude } : {}),
          theme_tag: themeTag,
          card_types: cardTypeFilters,
          subtypes: subtypeFilters,
          max_price_cents: maxPriceCents,
          min_price_cents: minPriceCents,
        });
        dispatch({
          type: "LOAD_SUCCESS",
          stage: stageKey,
          suggestions: result.suggestions.slice(0, 40),
          buffer: result.suggestions.slice(40),
          unresolved: result.unresolved,
        });
      } catch (err) {
        dispatch({
          type: "LOAD_ERROR",
          stage: stageKey,
          error: err instanceof ApiError ? err.message : "Failed to generate suggestions",
        });
      }
    },
    [
      deckId,
      archetypeTags,
      selectedThemeTag,
      cardTypeFilters,
      subtypeFilters,
      globalRejectedNames,
      maxPriceCents,
      minPriceCents,
    ],
  );

  const loadMore = useCallback(
    async (stage: string, offset: number, rejectedNames: string[]) => {
      const apiStage = apiStageFor(stage);
      const themeTag =
        apiStage === "theme"
          ? (themeTagForStageKey(stage) ?? selectedThemeTag ?? archetypeTags[0] ?? THEME_ETC_TAG)
          : null;
      const stageKey = apiStage === "theme" ? themeStageKey(themeTag ?? THEME_ETC_TAG) : stage;
      dispatch({ type: "LOAD_START", stage: stageKey });
      try {
        const persistentExclude = [...rejectedNames, ...globalRejectedNames];
        const exclude = persistentExclude.length > 0 ? persistentExclude : undefined;
        const result = await apiClient.buildStage(deckId, {
          stage: apiStage,
          target: 80,
          offset,
          ...(exclude ? { exclude } : {}),
          theme_tag: themeTag,
          card_types: cardTypeFilters,
          subtypes: subtypeFilters,
          max_price_cents: maxPriceCents,
          min_price_cents: minPriceCents,
        });
        dispatch({
          type: "LOAD_MORE_SUCCESS",
          stage: stageKey,
          suggestions: result.suggestions.slice(0, 40),
          buffer: result.suggestions.slice(40),
          unresolved: result.unresolved,
        });
      } catch (err) {
        dispatch({
          type: "LOAD_ERROR",
          stage: stageKey,
          error: err instanceof ApiError ? err.message : "Failed to generate suggestions",
        });
      }
    },
    [
      deckId,
      archetypeTags,
      selectedThemeTag,
      globalRejectedNames,
      cardTypeFilters,
      subtypeFilters,
      maxPriceCents,
      minPriceCents,
    ],
  );

  const preloadThemeTabs = useCallback(
    (force = false) => {
      const tabs = themeTabs.length > 0 ? themeTabs : [THEME_ETC_TAG];
      for (const tag of tabs) {
        const key = themeStageKey(tag);
        const bucket = state.stages[key];
        if (!force && (bucket?.loaded || bucket?.loading)) continue;
        void loadStage("theme", tag);
      }
    },
    [loadStage, state.stages, themeTabs],
  );

  function switchStage(stage: string) {
    dispatch({ type: "SET_ACTIVE_STAGE", stage });
    if (stage === "theme") {
      preloadThemeTabs();
      return;
    }
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

  useEffect(() => {
    if (state.activeStage === "theme") preloadThemeTabs();
  }, [state.activeStage, themeTabs]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when type/subtype filters change (skip the initial render)
  const typeFilterMounted = useRef(false);
  useEffect(() => {
    if (!typeFilterMounted.current) {
      typeFilterMounted.current = true;
      return;
    }
    dispatch({ type: "INVALIDATE_ALL" });
    if (state.activeStage === "theme") preloadThemeTabs(true);
    else void loadStage(state.activeStage);
  }, [cardTypeFilters, subtypeFilters]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when the session-local price filter changes (skip the initial render)
  const priceFilterMounted = useRef(false);
  useEffect(() => {
    if (!priceFilterMounted.current) {
      priceFilterMounted.current = true;
      return;
    }
    dispatch({ type: "INVALIDATE_ALL" });
    if (state.activeStage === "theme") preloadThemeTabs(true);
    else void loadStage(state.activeStage);
  }, [maxPriceCents, minPriceCents]); // eslint-disable-line react-hooks/exhaustive-deps

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

  function selectAllCollections() {
    const allIds = collections.map((c) => c.id);
    if (
      allIds.length === selectedCollectionIds.length &&
      allIds.every((id) => selectedCollectionIds.includes(id))
    ) {
      return;
    }
    void persistSelectedCollections(allIds);
  }

  function toggleOwnedOnly() {
    if (selectedCollectionIds.length > 0) {
      clearAllCollections();
    } else if (collections.length > 0) {
      // Master toggle on with nothing selected: pick all collections by default
      // so the filter is active immediately. Users can deselect individual chips.
      selectAllCollections();
    }
  }

  function reloadAllSuggestions() {
    dispatch({ type: "INVALIDATE_ALL" });
    if (state.activeStage === "theme") preloadThemeTabs(true);
    else void loadStage(state.activeStage);
  }

  function parsePriceInput(raw: string): number | null | "invalid" {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const eur = Number.parseFloat(trimmed);
    if (!Number.isFinite(eur) || eur < 0) return "invalid";
    return eur > 0 ? Math.round(eur * 100) : null;
  }

  function handleSavePriceCap() {
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
    setMaxPriceCents(nextMax);
    setMinPriceCents(nextMin);
  }

  function clearPriceCap() {
    if (maxPriceCents == null && minPriceCents == null) return;
    setPricePanelDraft("");
    setPricePanelMinDraft("");
    setMaxPriceCents(null);
    setMinPriceCents(null);
  }

  function clearAllSuggestionFilters() {
    if (selectedCollectionIds.length > 0) clearAllCollections();
    setPricePanelDraft("");
    setPricePanelMinDraft("");
    setMaxPriceCents(null);
    setMinPriceCents(null);
    setCardTypeFilters([]);
    setSubtypeFilters([]);
  }

  async function handleAccept(stage: string, suggestion: CardSuggestion) {
    const identity = cardIdentity(suggestion);
    dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "accepted" });
    const stageState = state.stages[stage]!;
    const qty = isBasicLand(suggestion) ? (stageState.quantities[identity] ?? 1) : undefined;
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: suggestion.scryfall_id,
        ...(qty !== undefined && { quantity: qty }),
        categories: [],
        added_by: "ai",
        ai_reasoning: suggestion.reasoning,
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add card");
      dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "pending" });
    }
  }

  async function handleReject(stage: string, suggestion: CardSuggestion) {
    const identity = cardIdentity(suggestion);
    dispatch({
      type: "REJECT_AND_REPLACE",
      stage,
      scryfallId: identity,
      cardName: suggestion.name,
    });
    setGlobalRejectedIds((prev) => {
      const next = new Set(prev);
      next.add(identity);
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
    const identity = cardIdentity(suggestion);
    dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "pending" });
    try {
      await apiClient.removeCard(deckId, suggestion.scryfall_id);
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
      dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "accepted" });
    }
  }

  async function handleAddRejected(stage: string, suggestion: CardSuggestion) {
    const identity = cardIdentity(suggestion);
    dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "accepted" });
    const stageState = state.stages[stage]!;
    const qty = isBasicLand(suggestion) ? (stageState.quantities[identity] ?? 1) : undefined;
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
      dispatch({ type: "SET_STATUS", stage, scryfallId: identity, status: "rejected" });
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

  async function handleSetQuantity(scryfallId: string, quantity: number) {
    const card = deckCards.find((item) => item.scryfall_id === scryfallId);
    if (!card || quantity === card.quantity) return;
    try {
      await apiClient.planCard(deckId, {
        card_scryfall_id: scryfallId,
        direction: quantity > card.quantity ? "addition" : "cut",
        quantity: Math.abs(quantity - card.quantity),
        categories: card.categories,
        added_by: card.added_by === "ai" ? "ai" : "user",
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to plan quantity");
    }
  }

  async function handleSetCategories(scryfallId: string, categories: string[]) {
    try {
      await apiClient.updateCardCategories(deckId, scryfallId, categories);
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update categories");
    }
  }

  async function handleUndoCut(card: DeckCardItem) {
    try {
      await apiClient.addCard(deckId, {
        card_scryfall_id: card.scryfall_id,
        quantity: card.quantity,
        categories: card.categories,
        added_by: card.added_by === "ai" ? "ai" : "user",
      });
      void refreshDeck();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to undo cut");
    }
  }

  async function handleRemoveCard(scryfallId: string) {
    try {
      await apiClient.removeCard(deckId, scryfallId);
      void refreshDeck();
      // If card is in current stage suggestions, reset status to pending
      const activeStage = state.stages[activeStageKey];
      if (activeStage) {
        const match = activeStage.suggestions.find((s) => s.scryfall_id === scryfallId);
        if (match) {
          dispatch({ type: "SET_STATUS", stage: activeStageKey, scryfallId, status: "pending" });
        }
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove card");
    }
  }

  const activeThemeTag = selectedThemeTag ?? archetypeTags[0] ?? THEME_ETC_TAG;
  const activeStageKey =
    state.activeStage === "theme" ? themeStageKey(activeThemeTag) : state.activeStage;
  const activeStageState = state.stages[activeStageKey] ?? makeStageState(activeStageKey);
  const stageTargetSummary = useMemo(
    () =>
      Object.fromEntries(
        CATEGORY_ORDER.map((stage) => [
          stage,
          state.stages[stage]?.target ?? STAGE_DEFAULTS[stage] ?? 10,
        ]),
      ),
    [state.stages],
  );

  function isHiddenCrossStage(s: CardSuggestion, status: SuggestionStatus): boolean {
    const identity = cardIdentity(s);
    if (globalRejectedIds.has(identity) && status !== "rejected") return true;
    if (acceptedCardIds.has(identity) && status !== "accepted") return true;
    return false;
  }

  const filteredSuggestions = activeStageState
    ? activeStageState.suggestions.filter((s) => {
        const status = activeStageState.statuses[cardIdentity(s)] ?? "pending";
        if (isHiddenCrossStage(s, status)) return false;
        return true;
      })
    : [];
  return (
    <div className="pb-36">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Build Deck</h1>
        <Link
          href={`/decks/${deckId}`}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          View deck
        </Link>
      </div>

      <div className="mb-4">
        <PlannedChangesPanel
          deckId={deckId}
          plans={plannedChanges}
          physicalCount={physicalCardCount}
          plannedCount={plannedCardCount}
          onChanged={refreshDeck}
        />
      </div>

      <BuilderFiltersDropdown
        collections={collections}
        selectedCollectionIds={selectedCollectionIds}
        minPriceCents={minPriceCents}
        maxPriceCents={maxPriceCents}
        minPriceDraft={pricePanelMinDraft}
        maxPriceDraft={pricePanelDraft}
        cardTypes={cardTypeFilters}
        subtypes={subtypeFilters}
        onToggleOwnedOnly={toggleOwnedOnly}
        onToggleCollection={toggleCollection}
        onSelectAllCollections={selectAllCollections}
        onClearCollections={clearAllCollections}
        onMinPriceDraftChange={setPricePanelMinDraft}
        onMaxPriceDraftChange={setPricePanelDraft}
        onApplyPrice={handleSavePriceCap}
        onClearPrice={clearPriceCap}
        onCardTypesChange={setCardTypeFilters}
        onSubtypesChange={setSubtypeFilters}
        onClearAll={clearAllSuggestionFilters}
      />

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
                    stage: activeStageKey,
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
                    dispatch({ type: "SET_TARGET", stage: activeStageKey, target: v });
                  }
                }}
                className="w-12 rounded-md bg-white/10 px-2 py-1 text-center text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={() =>
                  dispatch({
                    type: "SET_TARGET",
                    stage: activeStageKey,
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
              const range = CATEGORY_TARGETS[state.activeStage];
              if (!range) return null;
              const [min, max] = range;
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

          {state.activeStage === "theme" && themeTabs.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {themeTabs.map((tag) => {
                const active = (selectedThemeTag ?? archetypeTags[0] ?? THEME_ETC_TAG) === tag;
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => {
                      if (active) return;
                      setSelectedThemeTag(tag);
                      const key = themeStageKey(tag);
                      const bucket = state.stages[key];
                      if (!bucket?.loaded && !bucket?.loading) void loadStage("theme", tag);
                    }}
                    className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                      active
                        ? "border-indigo-500 bg-indigo-600 text-white"
                        : "border-white/10 bg-white/5 text-gray-300 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    {formatTagLabel(tag)}
                  </button>
                );
              })}
            </div>
          )}

          {/* Basic Lands (lands tab only) */}
          {state.activeStage === "lands" && (
            <div className="mb-4 rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                Basic Lands
              </p>
              <div className="flex flex-wrap gap-2">
                {basicLandsForIdentity(deckColorIdentity).map((name) => {
                  const current = deckCards.find((c) => c.name === name)?.quantity ?? 0;
                  return (
                    <div
                      key={name}
                      className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5"
                    >
                      <span className="text-xs font-medium text-gray-300 w-14">{name}</span>
                      <span
                        className={`text-xs w-8 text-right tabular-nums ${current > 0 ? "text-green-400" : "text-gray-600"}`}
                        title="Currently in deck"
                      >
                        ×{current}
                      </span>
                      <button
                        onClick={() =>
                          setBasicLandQuantities((prev) => ({
                            ...prev,
                            [name]: Math.max(1, (prev[name] ?? 1) - 1),
                          }))
                        }
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
                        onClick={() =>
                          setBasicLandQuantities((prev) => ({
                            ...prev,
                            [name]: Math.min(99, (prev[name] ?? 1) + 1),
                          }))
                        }
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
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                {filteredSuggestions.map((s) => (
                  <CardSuggestionCard
                    key={cardIdentity(s)}
                    suggestion={s}
                    status={activeStageState.statuses[cardIdentity(s)] ?? "pending"}
                    onAccept={() => void handleAccept(activeStageKey, s)}
                    onReject={() => void handleReject(activeStageKey, s)}
                    onRemove={() => void handleRemoveAccepted(activeStageKey, s)}
                    onAddBack={() => void handleAddRejected(activeStageKey, s)}
                    isPetCard={petCardNames.has(s.name)}
                    isBasicLand={isBasicLand(s)}
                    inCombo={comboCardNames.has(s.name.toLowerCase())}
                    quantity={activeStageState.quantities[cardIdentity(s)] ?? 1}
                    onQuantityChange={(qty) =>
                      dispatch({
                        type: "SET_QUANTITY",
                        stage: activeStageKey,
                        scryfallId: cardIdentity(s),
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
                    {activeStageState.unresolved.map((u, i) => (
                      <span key={u}>
                        {i > 0 ? ", " : ""}
                        <CardHover name={u}>{u}</CardHover>
                      </span>
                    ))}
                  </p>
                </div>
              )}
            </>
          )}

          {/* Generate button (shown when not yet loaded) */}
          {!activeStageState.loading && !activeStageState.loaded && (
            <div className="flex justify-center py-12">
              <button
                onClick={() => void loadStage(activeStageKey)}
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
                      activeStageKey,
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

      <CardDetailModal
        card={
          selectedCardId ? (deckCards.find((c) => c.deck_card_id === selectedCardId) ?? null) : null
        }
        onClose={() => setSelectedCardId(null)}
        deckId={deckId}
        onRemove={async (id) => {
          await handleRemoveCard(id);
          setSelectedCardId(null);
        }}
        onSetCategories={handleSetCategories}
      />

      <ExpandableDeckBar
        cards={deckCards}
        onRemove={handleRemoveCard}
        onUndoCut={handleUndoCut}
        onCardClick={(c) => setSelectedCardId(c.deck_card_id)}
        onSetQuantity={handleSetQuantity}
        petCardNames={petCardNames}
        commander={deckCommander}
        bracket={deckBracket}
        deckId={deckId}
        onCardAdded={() => void refreshDeck()}
        stageCounts={deckCategoryCounts}
        stageTargets={stageTargetSummary}
        manaCurve={manaCurve}
      />
    </div>
  );
}
