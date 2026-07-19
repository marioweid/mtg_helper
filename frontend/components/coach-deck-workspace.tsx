"use client";

import { useMemo, useState } from "react";

import { CardHover } from "@/components/card-hover";
import { CardSearch } from "@/components/card-search";
import { DeckFitIndicator } from "@/components/deck-fit-indicator";
import { DeckTypeBreakdown } from "@/components/deck-type-breakdown";
import { ManaCost } from "@/components/mana-cost";
import { ManaCurve } from "@/components/mana-curve";
import { STAGE_DEFAULTS, STAGE_LABELS } from "@/lib/constants";
import type { CardResponse, DeckCardItem, DeckManaCurve } from "@/lib/types";

interface Props {
  cards: DeckCardItem[];
  commander?: { type_line: string | null } | null;
  stageTargets: Record<string, number>;
  manaCurve?: DeckManaCurve | null;
  onAddCard: (card: CardResponse) => void | Promise<void>;
  onRemove: (scryfallId: string) => void | Promise<void>;
  onSetQuantity: (scryfallId: string, quantity: number) => void | Promise<void>;
}

type TypeFilter = "all" | "creature" | "instant" | "sorcery" | "artifact" | "enchantment" | "land";

const TYPE_FILTERS: readonly { key: TypeFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "creature", label: "Creatures" },
  { key: "instant", label: "Instants" },
  { key: "sorcery", label: "Sorceries" },
  { key: "artifact", label: "Artifacts" },
  { key: "enchantment", label: "Enchantments" },
  { key: "land", label: "Lands" },
];

const ROLE_STAGES = ["ramp", "draw", "interaction", "lands"] as const;

function isLand(card: DeckCardItem): boolean {
  return card.type_line?.includes("Land") ?? false;
}

function matchesType(card: DeckCardItem, type: TypeFilter): boolean {
  const line = card.type_line ?? "";
  if (type === "all") return true;
  return line.toLowerCase().includes(type);
}

function countStage(cards: DeckCardItem[], stage: string): number {
  if (stage === "lands") {
    return cards.reduce((sum, card) => (isLand(card) ? sum + card.quantity : sum), 0);
  }
  return cards.reduce((sum, card) => {
    if (isLand(card)) return sum;
    const stages = card.categories.length > 0 ? card.categories : card.qualifying_stages;
    return stages.includes(stage) ? sum + card.quantity : sum;
  }, 0);
}

function chipTone(actual: number, target: number): string {
  if (target <= 0) return "border-white/10 bg-white/5 text-gray-300";
  const ratio = actual / target;
  if (ratio < 0.65) return "border-red-400/30 bg-red-500/10 text-red-100";
  if (ratio < 0.9 || ratio > 1.25) return "border-amber-400/30 bg-amber-500/10 text-amber-100";
  return "border-emerald-400/25 bg-emerald-500/10 text-emerald-100";
}

function RoleChips({ cards, targets }: { cards: DeckCardItem[]; targets: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ROLE_STAGES.map((stage) => {
        const actual = countStage(cards, stage);
        const target = targets[stage] ?? STAGE_DEFAULTS[stage] ?? 0;
        return (
          <span
            key={stage}
            className={`rounded-full border px-2 py-0.5 text-[11px] ${chipTone(actual, target)}`}
          >
            {STAGE_LABELS[stage] ?? stage} {actual}/{target}
          </span>
        );
      })}
    </div>
  );
}

function sortCards(a: DeckCardItem, b: DeckCardItem): number {
  const land = Number(isLand(a)) - Number(isLand(b));
  if (land !== 0) return land;
  const cmc = (a.cmc ?? 0) - (b.cmc ?? 0);
  if (cmc !== 0) return cmc;
  return a.name.localeCompare(b.name);
}

function CardRow({
  card,
  onRemove,
  onSetQuantity,
}: {
  card: DeckCardItem;
  onRemove: (scryfallId: string) => void | Promise<void>;
  onSetQuantity: (scryfallId: string, quantity: number) => void | Promise<void>;
}) {
  const chips = (card.categories.length > 0 ? card.categories : card.qualifying_stages).slice(0, 3);

  return (
    <li className="group rounded-lg border border-white/10 bg-white/[0.025] p-2.5">
      <div className="flex gap-2.5">
        {card.image_uri ? (
          <img src={card.image_uri} alt="" className="h-14 w-10 shrink-0 rounded object-cover" />
        ) : (
          <div className="h-14 w-10 shrink-0 rounded bg-zinc-800" />
        )}

        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0">
              <CardHover
                name={card.name}
                imageUri={card.image_uri}
                className="font-medium text-white"
              >
                <span className="flex items-center gap-1.5">
                  <span className="block truncate">{card.name}</span>
                  <DeckFitIndicator card={card} />
                </span>
              </CardHover>
              {card.type_line && (
                <div className="mt-0.5 truncate text-[11px] text-gray-500">{card.type_line}</div>
              )}
            </div>
            <div className="shrink-0 text-xs">
              {card.mana_cost && <ManaCost cost={card.mana_cost} />}
            </div>
          </div>

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="flex min-w-0 flex-wrap gap-1">
              {chips.map((tag) => (
                <span key={tag} className="rounded-full bg-white/5 px-1.5 py-0.5 text-[10px]">
                  {tag.replace(/_/g, " ")}
                </span>
              ))}
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <div className="flex items-center overflow-hidden rounded border border-white/10 text-xs">
                <button
                  type="button"
                  onClick={() => void onSetQuantity(card.scryfall_id, card.quantity - 1)}
                  className="px-1.5 py-0.5 text-gray-300 hover:bg-white/10"
                  aria-label={`Decrease ${card.name}`}
                >
                  −
                </button>
                <span className="min-w-6 px-1.5 py-0.5 text-center tabular-nums text-white">
                  {card.quantity}
                </span>
                <button
                  type="button"
                  onClick={() => void onSetQuantity(card.scryfall_id, card.quantity + 1)}
                  className="px-1.5 py-0.5 text-gray-300 hover:bg-white/10"
                  aria-label={`Increase ${card.name}`}
                >
                  +
                </button>
              </div>
              <button
                type="button"
                onClick={() => void onRemove(card.scryfall_id)}
                className="rounded border border-red-400/30 px-2 py-0.5 text-[11px] text-red-200"
              >
                Plan cut
              </button>
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

export function CoachDeckWorkspace({
  cards,
  commander,
  stageTargets,
  manaCurve,
  onAddCard,
  onRemove,
  onSetQuantity,
}: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<TypeFilter>("all");

  const mainCount = cards.reduce((sum, card) => sum + card.quantity, 0);
  const commanderCount = commander ? 1 : 0;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cards
      .filter((card) => !q || card.name.toLowerCase().includes(q))
      .filter((card) => matchesType(card, type))
      .sort(sortCards);
  }, [cards, query, type]);
  const filteredQuantity = filtered.reduce((sum, card) => sum + card.quantity, 0);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <header className="shrink-0 rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold text-white">Deck workspace</h2>
            <p className="text-[11px] text-gray-500">Manual edits while Coach reasons</p>
          </div>
          <span className="rounded-full bg-white/5 px-2 py-1 text-xs text-gray-300">
            {mainCount}+{commanderCount}/100
          </span>
        </div>

        <RoleChips cards={cards} targets={stageTargets} />

        <details className="mt-2 rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs">
          <summary className="cursor-pointer select-none hover:text-white">Stats / curve</summary>
          <div className="mt-3 space-y-3">
            <DeckTypeBreakdown cards={cards} target={100} commander={commander ?? null} />
            <ManaCurve cards={cards} curve={manaCurve ?? null} compact minimal />
          </div>
        </details>
      </header>

      <section className="shrink-0 rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <CardSearch
          placeholder="+ Plan addition…"
          commanderLegal
          onSelect={(card) => void onAddCard(card)}
        />
        <div className="mt-2 flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter deck…"
            className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-3 py-2 text-sm"
          />
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {TYPE_FILTERS.map((opt) => {
            const active = type === opt.key;
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => setType(opt.key)}
                className={`rounded-full px-2.5 py-1 text-xs ${
                  active ? "bg-indigo-600 text-white" : "bg-white/5 text-gray-300 hover:bg-white/10"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </section>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between px-1 text-xs text-gray-500">
          <span>Deck list</span>
          <span>{filteredQuantity} shown</span>
        </div>
        <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {filtered.map((card) => (
            <CardRow
              key={card.deck_card_id}
              card={card}
              onRemove={onRemove}
              onSetQuantity={onSetQuantity}
            />
          ))}
          {filtered.length === 0 && (
            <li className="rounded-xl border border-dashed border-white/10 p-6 text-center text-sm">
              No cards match this filter.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
