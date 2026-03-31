import Link from "next/link";
import { apiClient } from "@/lib/api";
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

  return (
    <Link
      href={`/decks/${deck.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10 transition-all"
    >
      <div className="relative h-40 overflow-hidden bg-gray-900">
        {deck.commander_image ? (
          <img
            src={deck.commander_image}
            alt={deck.commander_name}
            className="h-full w-full object-cover object-top opacity-80 group-hover:opacity-100 transition-opacity"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-gray-600">
            <span className="text-4xl">🎴</span>
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">
        <h2 className="font-semibold text-white leading-tight">{deck.name}</h2>
        <p className="text-sm text-gray-400">{deck.commander_name}</p>
        <div className="mt-auto flex items-center justify-between pt-2 text-xs text-gray-500">
          <span>{deck.card_count} cards</span>
          <span className="rounded bg-white/10 px-2 py-0.5">{stage}</span>
          {bracket && (
            <span className="text-indigo-400">{bracket.split("—")[0]?.trim()}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default async function DecksPage() {
  const decks = await loadDecks();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Your Decks</h1>
        <Link
          href="/decks/new"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          New Deck
        </Link>
      </div>

      {decks.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-white/20 py-20 text-center">
          <p className="text-gray-400">No decks yet.</p>
          <Link
            href="/decks/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            Build your first deck
          </Link>
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
