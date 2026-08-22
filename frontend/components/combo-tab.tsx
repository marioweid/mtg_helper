"use client";

import { useEffect, useState } from "react";
import { CardHover } from "@/components/card-hover";
import { ApiError, apiClient } from "@/lib/api";
import type { Combo, ComboListResponse } from "@/lib/types";

interface Props {
  deckId: string;
}

export function ComboTab({ deckId }: Props) {
  const [data, setData] = useState<ComboListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .getDeckCombos(deckId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load combos");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deckId]);

  if (loading) {
    return <div className="py-12 text-center text-sm text-gray-500">Loading combos…</div>;
  }
  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
        {error}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      <ComboSection
        title="Active"
        subtitle="all pieces in deck"
        accent="emerald"
        empty="No active combos yet."
        combos={data.active}
      />
      <ComboSection
        title="Almost there"
        subtitle="1 card away"
        accent="amber"
        empty="No combos one card away — add a piece and check back."
        combos={data.almost_there}
      />
    </div>
  );
}

interface SectionProps {
  title: string;
  subtitle: string;
  accent: "emerald" | "amber";
  empty: string;
  combos: Combo[];
}

const ACCENT_CLASSES: Record<SectionProps["accent"], string> = {
  emerald: "bg-emerald-900/30 text-emerald-300 border-emerald-500/30",
  amber: "bg-amber-900/30 text-amber-300 border-amber-500/30",
};

function ComboSection({ title, subtitle, accent, empty, combos }: SectionProps) {
  return (
    <section>
      <header className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <span className={`rounded border px-2 py-0.5 text-xs ${ACCENT_CLASSES[accent]}`}>
          {combos.length} · {subtitle}
        </span>
      </header>
      {combos.length === 0 ? (
        <p className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-gray-500">
          {empty}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {combos.map((combo) => (
            <li key={combo.id}>
              <ComboRow combo={combo} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ComboRow({ combo }: { combo: Combo }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="rounded-xl border border-white/10 bg-white/5 p-3">
      <div className="flex flex-wrap items-start gap-3">
        {combo.pieces.map((piece, idx) => (
          <PieceCard key={`${combo.id}-${idx}`} piece={piece} />
        ))}
        <div className="flex-1 min-w-[12rem]">
          {combo.produces.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {combo.produces.map((p) => (
                <span
                  key={p}
                  className="rounded bg-indigo-900/40 px-2 py-0.5 text-xs text-indigo-300"
                >
                  {p}
                </span>
              ))}
            </div>
          )}
          {combo.description && (
            <button
              onClick={() => setOpen((o) => !o)}
              className="mt-2 text-xs text-gray-500 hover:text-gray-300"
            >
              {open ? "▴ Hide steps" : "▾ Show how it works"}
            </button>
          )}
          {open && combo.description && (
            <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-gray-300">
              {combo.description}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

function PieceCard({
  piece,
}: {
  piece: { card: { name: string; image_uri: string | null }; in_deck: boolean };
}) {
  const { card, in_deck } = piece;
  return (
    <CardHover
      name={card.name}
      imageUri={card.image_uri}
      className={`flex flex-col items-center gap-1 ${in_deck ? "" : "opacity-70"}`}
    >
      {card.image_uri ? (
        <img
          src={card.image_uri}
          alt={card.name}
          className={`h-24 w-[60px] rounded-[4.5%] object-cover ${
            in_deck ? "ring-1 ring-emerald-500/60" : "ring-1 ring-amber-500/60"
          }`}
        />
      ) : (
        <span className="flex h-24 w-[60px] items-center justify-center rounded border border-white/10 bg-white/5 px-1 text-center text-[10px] text-gray-400">
          {card.name}
        </span>
      )}
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] ${
          in_deck ? "bg-emerald-900/40 text-emerald-300" : "bg-amber-900/40 text-amber-300"
        }`}
      >
        {in_deck ? "in deck" : "needs"}
      </span>
    </CardHover>
  );
}
