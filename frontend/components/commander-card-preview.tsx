"use client";

import { useEffect, useState } from "react";

import type { CommanderCardSummary } from "@/lib/types";

interface Props {
  commander: CommanderCardSummary | null;
  partner?: CommanderCardSummary | null;
}

/**
 * Compact commander card preview for the deck detail header. Renders the card
 * art as a portrait thumbnail; clicking opens a lightbox with the full card
 * image alongside the printed oracle text so the rules text stays readable.
 */
export function CommanderCardPreview({ commander, partner }: Props) {
  const [open, setOpen] = useState<CommanderCardSummary | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!commander) return null;

  return (
    <>
      <div className="flex shrink-0 gap-2">
        <Thumb card={commander} onOpen={() => setOpen(commander)} />
        {partner ? <Thumb card={partner} onOpen={() => setOpen(partner)} /> : null}
      </div>

      {open ? (
        <button
          type="button"
          onClick={() => setOpen(null)}
          aria-label="Close card preview"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
        >
          <div
            // Stop bubbling so a click on the card body doesn't close the modal —
            // only the surrounding scrim is the dismiss target.
            onClick={(e) => e.stopPropagation()}
            className="max-h-[90vh] w-full max-w-3xl cursor-default overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 text-left shadow-2xl"
          >
            <div className="flex flex-col gap-6 sm:flex-row">
              {open.image_uri ? (
                <img
                  src={open.image_uri}
                  alt={open.name}
                  className="h-auto w-full max-w-xs shrink-0 rounded-xl shadow-lg"
                />
              ) : null}
              <div className="flex flex-col gap-3">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="text-xl font-semibold text-white">{open.name}</h2>
                  {open.mana_cost ? (
                    <span className="text-sm tracking-wider text-gray-400">
                      {open.mana_cost}
                    </span>
                  ) : null}
                </div>
                {open.type_line ? (
                  <p className="text-sm text-gray-400">{open.type_line}</p>
                ) : null}
                {open.oracle_text ? (
                  <p className="whitespace-pre-line text-sm leading-relaxed text-gray-200">
                    {open.oracle_text}
                  </p>
                ) : (
                  <p className="text-sm italic text-gray-500">No oracle text.</p>
                )}
              </div>
            </div>
          </div>
        </button>
      ) : null}
    </>
  );
}

function Thumb({ card, onOpen }: { card: CommanderCardSummary; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${card.name} — click to read card text`}
      className="group relative h-28 w-20 shrink-0 overflow-hidden rounded-lg border border-white/10 bg-zinc-900 transition hover:border-white/30 sm:h-32 sm:w-24"
    >
      {card.image_uri ? (
        <img
          src={card.image_uri}
          alt={card.name}
          className="h-full w-full object-cover object-top transition group-hover:scale-105"
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-2xl text-gray-600">
          🎴
        </span>
      )}
    </button>
  );
}
