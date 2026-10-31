"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";
import type { ComparisonPlannedChange } from "@/lib/comparison";
import type { DeckDetailResponse, PlannedChangeBatchItem } from "@/lib/types";

function useTargetDeck(deckId: string) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    id: "",
    deck: null as DeckDetailResponse | null,
    loading: true,
    error: "",
  });
  useEffect(() => {
    let active = true;
    setState({ id: deckId, deck: null, loading: true, error: "" });
    void apiClient
      .getDeck(deckId)
      .then((deck) => {
        if (active) setState({ id: deckId, deck, loading: false, error: "" });
      })
      .catch((error: unknown) => {
        if (active)
          setState({
            id: deckId,
            deck: null,
            loading: false,
            error: error instanceof Error ? error.message : "Could not load the target deck",
          });
      });
    return () => {
      active = false;
    };
  }, [deckId, attempt]);
  return {
    deck: state.id === deckId ? state.deck : null,
    error: state.error,
    loading: state.loading || state.id !== deckId,
    reload: () => setAttempt((value) => value + 1),
  };
}

export function useComparisonPlanning(deckId: string, changes: ComparisonPlannedChange[]) {
  const target = useTargetDeck(deckId);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState<PlannedChangeBatchItem[]>([]);
  const failed = items.filter((item) => item.status === "failed");
  async function submit() {
    if (busy || !target.deck) return;
    const pending = items.length
      ? changes.filter((change) =>
          failed.some((item) => item.card_scryfall_id === change.card_scryfall_id),
        )
      : changes;
    if (!pending.length) return;
    setBusy(true);
    setAttempted(true);
    setError("");
    try {
      const result = await apiClient.planComparedChanges(
        deckId,
        pending.map((change) => ({
          card_scryfall_id: change.card_scryfall_id,
          direction: change.direction,
          quantity: change.quantity,
          categories: change.categories,
        })),
      );
      const merged = new Map(
        [...items, ...result.items].map((item) => [item.card_scryfall_id, item]),
      );
      setItems([...merged.values()]);
    } catch (err: unknown) {
      setError(
        `${err instanceof Error ? err.message : "Planning failed"}. ` +
          "Retry is safe: matching pending quantities will not be added twice.",
      );
    } finally {
      setBusy(false);
    }
  }
  return {
    target,
    busy,
    attempted,
    error,
    items,
    submit,
    canSubmit: Boolean(target.deck && !busy && (!items.length || failed.length)),
    submitLabel: items.length
      ? "Retry failed cards"
      : attempted
        ? "Retry planning"
        : "Confirm plan",
  };
}
