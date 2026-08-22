"use client";

import { useState } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { CommanderCoachResponse, AnalysisCardHit } from "@/lib/types";

interface Props {
  deckId: string;
}

function CardHitLine({ card }: { card: AnalysisCardHit }) {
  return (
    <span>
      <span className="font-medium text-white">{card.name}</span>
      {card.mana_cost && <span className="ml-1 text-gray-500">{card.mana_cost}</span>}
      {card.type_line && <span className="ml-1 text-gray-500">— {card.type_line}</span>}
    </span>
  );
}

export function CommanderCoachPanel({ deckId }: Props) {
  const [message, setMessage] = useState(
    "Doctor this deck. Tell me what to cut, what to add, and why.",
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CommanderCoachResponse | null>(null);

  async function runCoach() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.coachDeck(deckId, { mode: "auto", message });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "MTG Assistant failed");
    } finally {
      setLoading(false);
    }
  }

  const doctor = result?.doctor ?? null;

  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">MTG Assistant</h2>
          <p className="text-xs text-gray-500">Ask for grounded card and deck advice.</p>
        </div>
        <button
          type="button"
          onClick={() => void runCoach()}
          disabled={loading}
          className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {loading ? "Thinking…" : "Run"}
        </button>
      </div>

      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={3}
        className="w-full rounded border-white/10 bg-black/30 px-2 py-1 text-xs text-gray-100"
      />

      {error && (
        <div className="mt-3 rounded-md border border-red-500/40 px-2 py-1 text-xs text-red-300">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-3 space-y-3 text-xs text-gray-300">
          <div className="rounded-md border border-white/10 bg-black/20 p-2">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-gray-500">
              Assistant reply · {result.mode}
            </div>
            <p>{result.reply}</p>
          </div>

          {doctor && (
            <>
              <section>
                <h3 className="mb-1 font-semibold text-white">Game plan</h3>
                <p className="text-gray-300">{doctor.game_plan}</p>
              </section>

              {doctor.findings.length > 0 && (
                <section>
                  <h3 className="mb-1 font-semibold text-white">Findings</h3>
                  <ul className="space-y-1">
                    {doctor.findings.map((f, i) => (
                      <li key={`${f.title}-${i}`} className="rounded border border-white/10 p-2">
                        <div className="font-medium text-white">
                          [{f.severity}] {f.title}
                        </div>
                        <div>{f.detail}</div>
                        <div className="mt-1 text-gray-500">Evidence: {f.evidence}</div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {doctor.cuts.length > 0 && (
                <section>
                  <h3 className="mb-1 font-semibold text-white">Cuts</h3>
                  <ul className="space-y-1">
                    {doctor.cuts.map((c) => (
                      <li key={c.card_name}>
                        <span className="font-medium text-red-300">{c.card_name}</span>: {c.reason}
                        <span className="ml-1 text-gray-500">({c.confidence})</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {doctor.adds.length > 0 && (
                <section>
                  <h3 className="mb-1 font-semibold text-white">Adds</h3>
                  <ul className="space-y-1">
                    {doctor.adds.map((a) => (
                      <li key={a.card.name}>
                        <CardHitLine card={a.card} />: {a.reason}
                        <span className="ml-1 text-gray-500">({a.confidence})</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {doctor.swaps.length > 0 && (
                <section>
                  <h3 className="mb-1 font-semibold text-white">Swaps</h3>
                  <ul className="space-y-2">
                    {doctor.swaps.map((s, i) => (
                      <li key={i} className="rounded border border-white/10 p-2">
                        <div>
                          Cut: <span className="text-red-300">{s.remove.join(", ")}</span>
                        </div>
                        <div>Add: {s.add.map((card) => card.name).join(", ")}</div>
                        <div className="mt-1 text-gray-400">{s.reason}</div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="text-[11px] text-gray-500">Tool calls: {doctor.tool_call_count}</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
