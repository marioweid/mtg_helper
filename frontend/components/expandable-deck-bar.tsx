"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { DeckBrowserPanel } from "@/components/deck-browser-panel";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import { GameChangerBadge } from "@/components/game-changer-badge";
import { ManaCurve } from "@/components/mana-curve";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import { CATEGORY_ORDER, STAGE_DEFAULTS, STAGE_LABELS } from "@/lib/constants";
import { totalCardCount, type CardResponse, type DeckCardItem, type DeckManaCurve } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  onRemove: (scryfallId: string) => void | Promise<void>;
  onUndoCut?: (card: DeckCardItem) => void | Promise<void>;
  onCardClick?: (card: DeckCardItem) => void;
  onSetQuantity?: (scryfallId: string, quantity: number) => void | Promise<void>;
  petCardNames?: Set<string>;
  commander?: {
    type_line: string | null;
    name?: string | null;
    game_changer?: boolean;
  } | null;
  target?: number;
  bracket?: number | null;
  deckId?: string;
  onCardAdded?: () => void;
  stageCounts?: Record<string, number>;
  stageTargets?: Record<string, number>;
  manaCurve?: DeckManaCurve | null;
}

function StageTargetChips({ counts, targets }: {
  counts: Record<string, number>;
  targets: Record<string, number>;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {CATEGORY_ORDER.map((stage) => {
        const count = counts[stage] ?? 0;
        const target = targets[stage] ?? STAGE_DEFAULTS[stage] ?? 10;
        const done = count >= target;
        return (
          <span
            key={stage}
            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium tabular-nums ${
              done
                ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                : "border-white/10 bg-white/5 text-gray-300"
            }`}
          >
            <span className="mr-1 text-gray-400">{STAGE_LABELS[stage] ?? stage}</span>
            {count}/{target}
          </span>
        );
      })}
    </div>
  );
}

function useDeckDrawer() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  const show = useCallback(() => {
    window.history.pushState({ deckBar: true }, "");
    setOpen(true);
  }, []);

  const hide = useCallback(() => {
    if (window.history.state?.deckBar) window.history.back();
    else setOpen(false);
  }, []);

  useEffect(() => {
    const onPop = () => setOpen(false);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      triggerRef.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        hide();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = [...panelRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex='-1'])",
      )];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hide, open]);

  return { open, show, hide, triggerRef, panelRef };
}

export function ExpandableDeckBar(props: Props) {
  const { open, show, hide, triggerRef, panelRef } = useDeckDrawer();
  const toast = useToast();
  const target = props.target ?? 100;
  const count = totalCardCount(props.cards) + (props.commander ? 1 : 0);

  const handleAddCard = useCallback(async (card: CardResponse) => {
    if (!props.deckId) return;
    try {
      await apiClient.addCard(props.deckId, {
        card_scryfall_id: card.scryfall_id,
        quantity: 1,
        added_by: "user",
      });
      toast.push(`Planned ${card.name}`, "success");
      props.onCardAdded?.();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Failed to plan card", "error");
    }
  }, [props.deckId, props.onCardAdded, toast]);

  return (
    <>
      {open ? (
        <DeckDrawer
          {...props}
          target={target}
          panelRef={panelRef}
          onClose={hide}
          onAddCard={handleAddCard}
        />
      ) : null}
      <div
        className="fixed inset-x-0 bottom-0 z-40 border-t border-indigo-400/15 bg-zinc-950/95 shadow-[0_-12px_35px_rgba(0,0,0,0.35)] backdrop-blur"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-white">Your deck</span>
              <span className="text-xs tabular-nums text-gray-400">{count}/{target} cards</span>
            </div>
            <div className="mt-1 hidden overflow-hidden md:block">
              <DeckTypeBreakdown cards={props.cards} target={target} commander={props.commander ?? null} />
            </div>
          </div>
          <GameChangerBadge
            cards={props.cards}
            bracket={props.bracket ?? null}
            commander={props.commander?.name
              ? { name: props.commander.name, game_changer: props.commander.game_changer ?? false }
              : null}
          />
          <button
            ref={triggerRef}
            type="button"
            onClick={show}
            aria-haspopup="dialog"
            aria-expanded={open}
            className="min-h-11 shrink-0 rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white shadow-lg shadow-indigo-950/30 hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            View Deck <span aria-hidden>↑</span>
          </button>
        </div>
      </div>
    </>
  );
}

type DrawerProps = Omit<Props, "target"> & {
  target: number;
  panelRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onAddCard: (card: CardResponse) => void | Promise<void>;
};

function DeckDrawer({ panelRef, onClose, onAddCard, ...props }: DrawerProps) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="deck-drawer-title"
        className="absolute inset-x-0 bottom-0 flex h-[92dvh] flex-col overscroll-contain rounded-t-2xl border border-white/10 bg-zinc-950 pb-[env(safe-area-inset-bottom)] shadow-2xl sm:inset-y-0 sm:left-auto sm:h-full sm:w-[min(760px,72vw)] sm:rounded-l-2xl sm:rounded-tr-none sm:pb-0 lg:w-[min(860px,64vw)]"
      >
        <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3 sm:px-5">
          <div>
            <h2 id="deck-drawer-title" className="text-wrap-balance text-base font-semibold text-white">Deck Workspace</h2>
            <p className="text-xs text-gray-400">Browse, inspect, and adjust without leaving the builder.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close deck workspace"
            className="min-h-11 min-w-11 rounded-full text-xl text-gray-400 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            ×
          </button>
        </header>
        <div className="max-h-[36dvh] shrink-0 overflow-y-auto overscroll-contain border-b border-white/10 bg-white/[0.025] p-3 sm:p-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="space-y-3">
              {props.stageCounts && props.stageTargets ? (
                <StageTargetChips counts={props.stageCounts} targets={props.stageTargets} />
              ) : null}
              <DeckTypeBreakdown
                cards={props.cards}
                target={props.target}
                commander={props.commander ?? null}
              />
            </div>
            {props.manaCurve ? (
              <ManaCurve cards={props.cards} curve={props.manaCurve} compact />
            ) : null}
          </div>
        </div>
        <div className="min-h-0 flex-1 p-3 sm:p-4">
          <DeckBrowserPanel
            cards={props.cards}
            onRemove={props.onRemove}
            {...(props.onUndoCut ? { onUndoCut: props.onUndoCut } : {})}
            {...(props.onCardClick ? { onCardClick: props.onCardClick } : {})}
            {...(props.onSetQuantity ? { onSetQuantity: props.onSetQuantity } : {})}
            {...(props.petCardNames ? { petCardNames: props.petCardNames } : {})}
            {...(props.deckId ? { onAddCard, commanderLegal: true } : {})}
            workspaceScope={`builder:${props.deckId ?? "shared"}`}
          />
        </div>
      </section>
    </div>
  );
}
