"use client";

import Link from "next/link";

import { ManaSymbols } from "@/components/mana-symbols";
import { archetypeLabel } from "@/lib/constants";
import { colorIdentityGradient } from "@/lib/color-gradients";
import type { CommanderCardSummary } from "@/lib/types";

interface DeckHeroProps {
  name: string;
  deckId: string;
  description: string | null;
  commander: CommanderCardSummary | null;
  partner: CommanderCardSummary | null;
  colors: string[];
  cardCount: number;
  stage: string;
  bracket: string | null;
  archetypeTags: string[];
  editingDescription: boolean;
  draftDescription: string;
  savingDescription: boolean;
  deleting: boolean;
  onDraftChange: (value: string) => void;
  onStartEditDescription: () => void;
  onSaveDescription: () => void;
  onCancelEditDescription: () => void;
  onDelete: () => void;
}

export function DeckHero({
  name,
  deckId,
  description,
  commander,
  partner,
  colors,
  cardCount,
  stage,
  bracket,
  archetypeTags,
  editingDescription,
  draftDescription,
  savingDescription,
  deleting,
  onDraftChange,
  onStartEditDescription,
  onSaveDescription,
  onCancelEditDescription,
  onDelete,
}: DeckHeroProps) {
  const gradient = colorIdentityGradient(colors);

  return (
    <section
      aria-label="Deck hero"
      className="relative mb-6 overflow-hidden rounded-2xl border border-white/10 min-h-[260px] sm:min-h-[320px]"
      style={{ background: gradient }}
    >
      {commander?.image_uri ? (
        <img
          src={commander.image_uri}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full object-cover object-top opacity-40 mix-blend-luminosity"
        />
      ) : null}

      <div
        aria-hidden
        className="absolute inset-0"
        style={{ background: gradient, mixBlendMode: "multiply", opacity: 0.55 }}
      />

      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/45 to-black/10"
      />

      {partner?.image_uri ? (
        <img
          src={partner.image_uri}
          alt={partner.name}
          className="absolute right-4 top-4 hidden h-24 w-auto rounded-lg border border-white/20 shadow-xl sm:block sm:h-32"
        />
      ) : null}

      <button
        type="button"
        onClick={onDelete}
        disabled={deleting}
        className="absolute right-3 top-3 z-10 rounded-md border border-red-500/40 bg-black/40 px-2.5 py-1 text-xs text-red-300 backdrop-blur transition-colors hover:border-red-400 hover:text-red-200 disabled:opacity-50"
      >
        {deleting ? "Deleting…" : "Delete deck"}
      </button>

      <div className="relative flex h-full flex-col justify-end gap-3 p-5 sm:p-6">
        <div className="flex flex-col gap-3">
          <h1 className="pr-28 text-2xl font-bold leading-tight text-white drop-shadow sm:text-3xl">
            {name}
          </h1>

          {editingDescription ? (
            <div className="flex flex-col gap-2">
              <textarea
                value={draftDescription}
                onChange={(e) => onDraftChange(e.target.value)}
                rows={3}
                className="w-full max-w-2xl resize-none rounded-lg border border-white/20 bg-black/40 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 backdrop-blur focus:border-indigo-400 focus:outline-none"
                placeholder="Describe the deck strategy..."
              />
              <div className="flex gap-2">
                <button
                  onClick={onSaveDescription}
                  disabled={savingDescription}
                  className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
                >
                  {savingDescription ? "Saving…" : "Save"}
                </button>
                <button
                  onClick={onCancelEditDescription}
                  className="rounded-md border border-white/30 px-3 py-1 text-xs text-gray-200 transition-colors hover:text-white"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex max-w-2xl items-start gap-1.5">
              {description ? (
                <p className="text-sm text-gray-200 drop-shadow">{description}</p>
              ) : (
                <span className="text-sm italic text-gray-300/80">No description</span>
              )}
              <button
                onClick={onStartEditDescription}
                className="ml-1 flex-shrink-0 text-xs text-gray-300 transition-colors hover:text-white"
                title="Edit description"
              >
                ✎
              </button>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded bg-black/50 px-2 py-0.5 text-gray-100 backdrop-blur">
              {stage}
            </span>
            {bracket ? (
              <span className="rounded bg-indigo-900/70 px-2 py-0.5 text-indigo-100 backdrop-blur">
                {bracket}
              </span>
            ) : null}
            <span className="text-gray-200 drop-shadow">{cardCount} cards</span>
            <ManaSymbols colors={colors} />
          </div>

          {archetypeTags.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {archetypeTags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-indigo-500/30 px-2 py-0.5 text-xs text-indigo-100 backdrop-blur"
                >
                  {archetypeLabel(tag)}
                </span>
              ))}
              <Link
                href={`/decks/${deckId}/keywords`}
                className="ml-1 text-xs text-gray-300 transition-colors hover:text-white"
                title="Edit keywords"
              >
                ✎
              </Link>
            </div>
          ) : (
            <div>
              <Link
                href={`/decks/${deckId}/keywords`}
                className="text-xs text-gray-300 transition-colors hover:text-white"
              >
                + Add keywords
              </Link>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
