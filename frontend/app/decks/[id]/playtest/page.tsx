"use client";

import { useCallback, useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { apiClient } from "@/lib/api";
import {
  canCast,
  expandDeck,
  parseManaCost,
  shuffle,
  type PlaytestCard,
} from "@/lib/playtest";
import { Battlefield } from "@/components/playtest/battlefield";
import { HandRow } from "@/components/playtest/hand-row";
import { ManaReadout } from "@/components/playtest/mana-readout";
import { MulliganPrompt } from "@/components/playtest/mulligan-prompt";
import { PlaytestStatsPanel } from "@/components/playtest/stats-panel";

const MAX_TURNS = 4;

type Phase = "loading" | "mulligan" | "bottoming" | "playing" | "done";

interface TurnLog {
  turn: number;
  drew: number;
  played: string[];
  cast: string[];
}

interface GameState {
  phase: Phase;
  error: string | null;
  deckId: string;
  deckName: string;
  onThePlay: boolean;
  library: PlaytestCard[];
  hand: PlaytestCard[];
  bottoming: Set<string>;
  battlefieldLands: PlaytestCard[];
  tappedLands: Set<string>;
  battlefieldOther: PlaytestCard[];
  graveyard: PlaytestCard[];
  turn: number;
  mulliganCount: number;
  landPlayedThisTurn: boolean;
  log: TurnLog[];
}

type Action =
  | { type: "DECK_LOADED"; deckName: string; library: PlaytestCard[]; hand: PlaytestCard[] }
  | { type: "DECK_FAILED"; error: string }
  | { type: "SET_ON_THE_PLAY"; value: boolean }
  | { type: "TAKE_MULLIGAN" }
  | { type: "KEEP_HAND" }
  | { type: "TOGGLE_BOTTOM"; uid: string }
  | { type: "CONFIRM_BOTTOM" }
  | { type: "PLAY_LAND"; uid: string }
  | { type: "TAP_LAND"; uid: string }
  | { type: "CAST"; uid: string }
  | { type: "END_TURN" }
  | { type: "RESTART"; library: PlaytestCard[]; hand: PlaytestCard[] };

function initialState(deckId: string): GameState {
  return {
    phase: "loading",
    error: null,
    deckId,
    deckName: "",
    onThePlay: true,
    library: [],
    hand: [],
    bottoming: new Set(),
    battlefieldLands: [],
    tappedLands: new Set(),
    battlefieldOther: [],
    graveyard: [],
    turn: 0,
    mulliganCount: 0,
    landPlayedThisTurn: false,
    log: [],
  };
}

function drawN(library: PlaytestCard[], n: number): { drawn: PlaytestCard[]; rest: PlaytestCard[] } {
  const drawn = library.slice(0, n);
  const rest = library.slice(n);
  return { drawn, rest };
}

function freshDeal(library: PlaytestCard[]): { hand: PlaytestCard[]; rest: PlaytestCard[] } {
  const shuffled = shuffle(library);
  const { drawn, rest } = drawN(shuffled, 7);
  return { hand: drawn, rest };
}

function handleKeep(state: GameState): GameState {
  if (state.mulliganCount === 0) {
    return startPlay(state);
  }
  return { ...state, phase: "bottoming", bottoming: new Set() };
}

function startPlay(state: GameState): GameState {
  const draw = state.onThePlay ? 0 : 1;
  const { drawn, rest } = drawN(state.library, draw);
  const hand = [...state.hand, ...drawn];
  return {
    ...state,
    phase: "playing",
    library: rest,
    hand,
    turn: 1,
    landPlayedThisTurn: false,
    log: [{ turn: 1, drew: draw, played: [], cast: [] }],
  };
}

function handleConfirmBottom(state: GameState): GameState {
  if (state.bottoming.size !== state.mulliganCount) return state;
  const toBottom = state.hand.filter((c) => state.bottoming.has(c.uid));
  const keptHand = state.hand.filter((c) => !state.bottoming.has(c.uid));
  const library = [...state.library, ...toBottom];
  return startPlay({ ...state, hand: keptHand, library, bottoming: new Set() });
}

function handleMulligan(state: GameState): GameState {
  const fullLibrary = [...state.library, ...state.hand];
  const { hand, rest } = freshDeal(fullLibrary);
  return {
    ...state,
    phase: "mulligan",
    hand,
    library: rest,
    mulliganCount: state.mulliganCount + 1,
    bottoming: new Set(),
  };
}

function handlePlayLand(state: GameState, uid: string): GameState {
  if (state.landPlayedThisTurn) return state;
  const card = state.hand.find((c) => c.uid === uid);
  if (!card || !card.isLand) return state;
  const hand = state.hand.filter((c) => c.uid !== uid);
  const battlefieldLands = [...state.battlefieldLands, card];
  const log = updateLog(state.log, (entry) => ({ ...entry, played: [...entry.played, card.name] }));
  return { ...state, hand, battlefieldLands, landPlayedThisTurn: true, log };
}

function handleCast(state: GameState, uid: string): GameState {
  const card = state.hand.find((c) => c.uid === uid);
  if (!card || card.isLand) return state;
  const cost = parseManaCost(card.mana_cost);
  const untapped = state.battlefieldLands.filter((l) => !state.tappedLands.has(l.uid));
  if (!canCast(cost, untapped)) return state;
  const needed = cost.generic + sumColored(cost.colored);
  const toTap = pickLandsForCost(untapped, cost, needed);
  const tapped = new Set(state.tappedLands);
  for (const land of toTap) tapped.add(land.uid);
  const hand = state.hand.filter((c) => c.uid !== uid);
  const battlefieldOther = card.type_line && /Instant|Sorcery/.test(card.type_line)
    ? state.battlefieldOther
    : [...state.battlefieldOther, card];
  const graveyard = card.type_line && /Instant|Sorcery/.test(card.type_line)
    ? [...state.graveyard, card]
    : state.graveyard;
  const log = updateLog(state.log, (entry) => ({ ...entry, cast: [...entry.cast, card.name] }));
  return { ...state, hand, battlefieldOther, graveyard, tappedLands: tapped, log };
}

function handleEndTurn(state: GameState): GameState {
  if (state.turn >= MAX_TURNS) {
    return { ...state, phase: "done" };
  }
  const nextTurn = state.turn + 1;
  const { drawn, rest } = drawN(state.library, 1);
  return {
    ...state,
    turn: nextTurn,
    library: rest,
    hand: [...state.hand, ...drawn],
    tappedLands: new Set(),
    landPlayedThisTurn: false,
    log: [...state.log, { turn: nextTurn, drew: drawn.length, played: [], cast: [] }],
  };
}

function updateLog(log: TurnLog[], fn: (entry: TurnLog) => TurnLog): TurnLog[] {
  if (log.length === 0) return log;
  const last = log[log.length - 1]!;
  return [...log.slice(0, -1), fn(last)];
}

function sumColored(colored: Record<string, number>): number {
  return Object.values(colored).reduce((a, b) => a + b, 0);
}

function pickLandsForCost(
  untapped: PlaytestCard[],
  cost: { generic: number; colored: Record<string, number> },
  needed: number,
): PlaytestCard[] {
  // Mirror canCast assignment: colored first, then any. Greedy is fine here
  // because canCast already proved the cost is payable.
  const used = new Set<string>();
  const picked: PlaytestCard[] = [];
  for (const [color, count] of Object.entries(cost.colored)) {
    for (let i = 0; i < count; i += 1) {
      const land = untapped.find((l) => !used.has(l.uid) && l.produces.includes(color as never));
      if (land) {
        used.add(land.uid);
        picked.push(land);
      }
    }
  }
  for (const land of untapped) {
    if (picked.length >= needed) break;
    if (!used.has(land.uid)) {
      used.add(land.uid);
      picked.push(land);
    }
  }
  return picked;
}

function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case "DECK_LOADED":
      return {
        ...state,
        phase: "mulligan",
        deckName: action.deckName,
        library: action.library,
        hand: action.hand,
      };
    case "DECK_FAILED":
      return { ...state, phase: "loading", error: action.error };
    case "SET_ON_THE_PLAY":
      return { ...state, onThePlay: action.value };
    case "TAKE_MULLIGAN":
      return handleMulligan(state);
    case "KEEP_HAND":
      return handleKeep(state);
    case "TOGGLE_BOTTOM": {
      const next = new Set(state.bottoming);
      if (next.has(action.uid)) next.delete(action.uid);
      else if (next.size < state.mulliganCount) next.add(action.uid);
      return { ...state, bottoming: next };
    }
    case "CONFIRM_BOTTOM":
      return handleConfirmBottom(state);
    case "PLAY_LAND":
      return handlePlayLand(state, action.uid);
    case "TAP_LAND": {
      const tapped = new Set(state.tappedLands);
      if (tapped.has(action.uid)) tapped.delete(action.uid);
      else tapped.add(action.uid);
      return { ...state, tappedLands: tapped };
    }
    case "CAST":
      return handleCast(state, action.uid);
    case "END_TURN":
      return handleEndTurn(state);
    case "RESTART":
      return {
        ...initialState(state.deckId),
        deckName: state.deckName,
        onThePlay: state.onThePlay,
        phase: "mulligan",
        library: action.library,
        hand: action.hand,
      };
    default:
      return state;
  }
}

export default function PlaytestPage() {
  const params = useParams();
  const deckId = params["id"] as string;
  const [state, dispatch] = useReducer(reducer, deckId, initialState);

  const loadDeck = useCallback(async () => {
    try {
      const deck = await apiClient.getDeck(deckId);
      const expanded = expandDeck(deck.cards);
      const { hand, rest } = freshDeal(expanded);
      dispatch({ type: "DECK_LOADED", deckName: deck.name, library: rest, hand });
    } catch (err) {
      dispatch({
        type: "DECK_FAILED",
        error: err instanceof Error ? err.message : "Failed to load deck",
      });
    }
  }, [deckId]);

  useEffect(() => {
    void loadDeck();
  }, [loadDeck]);

  const untappedLands = useMemo(
    () => state.battlefieldLands.filter((l) => !state.tappedLands.has(l.uid)),
    [state.battlefieldLands, state.tappedLands],
  );

  const castable = useMemo(() => {
    const set = new Set<string>();
    for (const card of state.hand) {
      if (card.isLand) continue;
      const cost = parseManaCost(card.mana_cost);
      if (canCast(cost, untappedLands)) set.add(card.uid);
    }
    return set;
  }, [state.hand, untappedLands]);

  if (state.error) {
    return (
      <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
        {state.error}
      </p>
    );
  }

  if (state.phase === "loading") {
    return <p className="text-sm text-gray-400">Shuffling…</p>;
  }

  const bottomNeeded = state.mulliganCount;

  return (
    <div className="flex flex-col gap-4 pb-16">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <Link
            href={`/decks/${deckId}`}
            className="text-xs text-indigo-400 hover:underline"
          >
            ← {state.deckName || "Deck"}
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-white">Goldfish playtest</h1>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={state.onThePlay}
              disabled={state.phase !== "mulligan"}
              onChange={(e) => dispatch({ type: "SET_ON_THE_PLAY", value: e.target.checked })}
              className="h-3.5 w-3.5"
            />
            On the play
          </label>
          <span>Library: <span className="text-gray-200">{state.library.length}</span></span>
          <span>GY: <span className="text-gray-200">{state.graveyard.length}</span></span>
        </div>
      </header>

      <PlaytestStatsPanel deckId={deckId} />

      {(state.phase === "mulligan" || state.phase === "bottoming") && (
        <MulliganPrompt
          phase={state.phase}
          hand={state.hand}
          mulliganCount={state.mulliganCount}
          bottoming={state.bottoming}
          bottomNeeded={bottomNeeded}
          onKeep={() => dispatch({ type: "KEEP_HAND" })}
          onMulligan={() => dispatch({ type: "TAKE_MULLIGAN" })}
          onToggleBottom={(uid) => dispatch({ type: "TOGGLE_BOTTOM", uid })}
          onConfirmBottom={() => dispatch({ type: "CONFIRM_BOTTOM" })}
        />
      )}

      {(state.phase === "playing" || state.phase === "done") && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="rounded-md bg-indigo-600/20 px-3 py-1 text-sm font-semibold text-indigo-200">
                Turn {state.turn}
              </span>
              <ManaReadout
                untappedLands={untappedLands}
                tappedCount={state.battlefieldLands.length - untappedLands.length}
              />
            </div>
            <div className="flex gap-2">
              {state.phase === "playing" && (
                <button
                  type="button"
                  onClick={() => dispatch({ type: "END_TURN" })}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
                >
                  {state.turn >= MAX_TURNS ? "Finish" : "End turn"}
                </button>
              )}
              <button
                type="button"
                onClick={() => void loadDeck()}
                className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 hover:border-white/40 hover:text-white"
              >
                Restart
              </button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <section className="flex flex-col gap-4">
              <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 text-sm font-medium text-gray-400">
                  Hand ({state.hand.length})
                </h2>
                <HandRow
                  hand={state.hand}
                  castable={castable}
                  canPlayLand={state.phase === "playing" && !state.landPlayedThisTurn}
                  onPlayLand={(uid) => dispatch({ type: "PLAY_LAND", uid })}
                  onCast={(uid) => dispatch({ type: "CAST", uid })}
                />
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 text-sm font-medium text-gray-400">Battlefield</h2>
                <Battlefield
                  lands={state.battlefieldLands}
                  tapped={state.tappedLands}
                  permanents={state.battlefieldOther}
                  onTapLand={(uid) => dispatch({ type: "TAP_LAND", uid })}
                />
              </div>
            </section>

            <aside className="flex flex-col gap-4">
              <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 text-sm font-medium text-gray-400">Turn log</h2>
                <ol className="flex flex-col gap-2 text-xs">
                  {state.log.map((entry) => (
                    <li key={entry.turn} className="rounded-md bg-white/5 px-3 py-2">
                      <div className="font-semibold text-gray-200">Turn {entry.turn}</div>
                      <div className="text-gray-500">
                        Drew {entry.drew} · Lands: {entry.played.length} · Cast: {entry.cast.length}
                      </div>
                      {entry.cast.length > 0 && (
                        <div className="mt-1 text-indigo-300">{entry.cast.join(", ")}</div>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
              {state.phase === "done" && (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
                  Goldfish complete. {state.battlefieldLands.length} lands hit,{" "}
                  {state.log.reduce((sum, e) => sum + e.cast.length, 0)} spells cast across{" "}
                  {MAX_TURNS} turns.
                </div>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
