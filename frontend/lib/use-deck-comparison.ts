"use client";

import { useEffect, useState } from "react";

import type { ComparisonSelection } from "@/lib/comparison";
import { apiClient } from "@/lib/api";
import type { ComparisonKind, DeckCompareResponse, DeckSummary } from "@/lib/types";

const EMPTY: ComparisonSelection = { deckId: null, kind: "deck", snapshotId: null };

async function resolveSide(id: string | null, kind: string | null): Promise<ComparisonSelection> {
  if (!id) return EMPTY;
  if (kind === "snapshot") {
    const snapshot = await apiClient.getSnapshot(id);
    return { deckId: snapshot.deck_id, kind, snapshotId: id };
  }
  return { deckId: id, kind: kind === "planned" ? "planned" : "deck", snapshotId: null };
}

function requestSide(side: ComparisonSelection): { kind: ComparisonKind; id: string } {
  return { kind: side.kind, id: (side.kind === "snapshot" ? side.snapshotId : side.deckId)! };
}

export function useDeckComparison(initialQuery: string) {
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [left, setLeft] = useState(EMPTY);
  const [right, setRight] = useState(EMPTY);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    key: "",
    result: null as DeckCompareResponse | null,
    loading: false,
    error: "",
  });
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(initialQuery);
    void Promise.all([
      apiClient.listDecks({ limit: 100 }),
      resolveSide(query.get("left"), query.get("left_kind")),
      resolveSide(query.get("right"), query.get("right_kind")),
    ])
      .then(([items, l, r]) => {
        if (active) {
          setDecks(items);
          setLeft(l);
          setRight(r);
          setLoadError("");
        }
      })
      .catch((err: unknown) => {
        if (active) setLoadError(err instanceof Error ? err.message : "Could not load comparison");
      });
    return () => {
      active = false;
    };
  }, [initialQuery, loadAttempt]);
  const key = JSON.stringify([left, right]);
  useEffect(() => {
    let active = true;
    if (!left.deckId || !right.deckId) return;
    setState({ key, result: null, loading: true, error: "" });
    void apiClient
      .compareDecks(requestSide(left), requestSide(right))
      .then((result) => {
        if (active) setState({ key, result, loading: false, error: "" });
      })
      .catch((err: unknown) => {
        if (active)
          setState({
            key,
            result: null,
            loading: false,
            error: err instanceof Error ? err.message : "Comparison failed",
          });
      });
    return () => {
      active = false;
    };
  }, [left, right, key, attempt]);
  return {
    decks,
    left,
    right,
    setLeft,
    setRight,
    loadError,
    result: state.key === key ? state.result : null,
    loading: Boolean(left.deckId && right.deckId && (state.key !== key || state.loading)),
    error: state.key === key ? state.error : "",
    retry: () => setAttempt((value) => value + 1),
    reload: () => setLoadAttempt((value) => value + 1),
    swap: () => {
      setLeft(right);
      setRight(left);
    },
  };
}
