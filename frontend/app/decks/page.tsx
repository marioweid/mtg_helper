import Link from "next/link";
import { apiClient } from "@/lib/api";
import { DeleteDeckButton } from "@/components/delete-deck-button";
import { ManaSymbols } from "@/components/mana-symbols";
import { colorIdentityGradient, colorIdentityShadow } from "@/lib/color-gradients";
import { BRACKET_LABELS, STAGE_LABELS } from "@/lib/constants";
import type { DeckSummary } from "@/lib/types";

async function loadDecks(): Promise<DeckSummary[]> {
  try {
    return await apiClient.listDecks({ limit: 50 });
  } catch {
    return [];
  }
}

function DeckCard({ deck }: { deck: DeckSummary }) {
  const bracket = deck.bracket != null ? BRACKET_LABELS[deck.bracket] : null;
  const stage = STAGE_LABELS[deck.stage] ?? deck.stage;
  const gradient = colorIdentityGradient(deck.commander_color_identity);
  const shadow = colorIdentityShadow(deck.commander_color_identity);

  return (
    <div className="group relative">
      <Link
        href={`/decks/${deck.id}`}
        aria-label={`Open deck ${deck.name}`}
        className="relative flex aspect-[4/5] flex-col overflow-hidden rounded-xl border border-white/10 transition-all duration-200 hover:border-white/30 hover:-translate-y-0.5"
        style={{
          background: deck.commander_image ? "#0b0d12" : gradient,
          boxShadow: shadow,
        }}
      >
        {deck.commander_image ? (
          <img
            src={deck.commander_image}
            alt=""
            aria-hidden
            className="absolute inset-0 h-full w-full object-cover object-top opacity-80 transition-opacity duration-200 group-hover:opacity-95"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-5xl text-white/30">
            🎴
          </div>
        )}

        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent"
        />

        <div className="relative mt-auto flex flex-col gap-1.5 p-4">
          <h2 className="pr-8 font-semibold leading-tight text-white drop-shadow">
            {deck.name}
          </h2>
          <p className="text-xs text-gray-200/90 drop-shadow">{deck.commander_name}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-gray-200">
            <span className="rounded bg-black/55 px-1.5 py-0.5 backdrop-blur">
              {deck.card_count} cards
            </span>
            <span className="rounded bg-black/55 px-1.5 py-0.5 backdrop-blur">{stage}</span>
            {bracket ? (
              <span className="rounded bg-indigo-900/70 px-1.5 py-0.5 text-indigo-100 backdrop-blur">
                {bracket.split("—")[0]?.trim()}
              </span>
            ) : null}
            <ManaSymbols colors={deck.commander_color_identity} />
          </div>
        </div>
      </Link>
      <DeleteDeckButton deckId={deck.id} deckName={deck.name} />
    </div>
  );
}

export default async function DecksPage() {
  const decks = await loadDecks();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Your Decks</h1>
        <div className="flex gap-2">
          <Link
            href="/decks/import"
            className="rounded-lg border border-indigo-500/60 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-600/10 transition-colors"
          >
            Import Deck
          </Link>
          <Link
            href="/decks/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            New Deck
          </Link>
        </div>
      </div>

      {decks.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/20 py-20 text-center">
          <p className="text-gray-400">No decks yet.</p>
          <p className="text-xs text-gray-500">Pick a commander and we&apos;ll build a sample deck in under a minute.</p>
          <div className="mt-2 flex flex-col items-center gap-2 sm:flex-row">
            <Link
              href="/onboarding"
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
            >
              Start here →
            </Link>
            <Link
              href="/decks/new"
              className="rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
            >
              Build manually
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {decks.map((deck) => (
            <DeckCard key={deck.id} deck={deck} />
          ))}
        </div>
      )}
    </div>
  );
}
