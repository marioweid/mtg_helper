"use client";

import Link from "next/link";
import { use, useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import type { CollectionImportResponse } from "@/lib/types";

type Mode = "merge" | "replace";

export default function ImportCollectionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [csv, setCsv] = useState("");
  const [mode, setMode] = useState<Mode>("merge");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CollectionImportResponse | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setCsv(text);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!csv.trim()) {
      setError("Paste or upload a CSV first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiClient.importCollectionCsv(id, { csv, mode });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError && err.code === "PARSE_ERROR") {
        setError(`CSV parse error: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : "Import failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-8 text-2xl font-bold text-white">Import Complete</h1>

        <div className="rounded-xl border border-green-500/30 bg-green-900/10 p-6 mb-4">
          <p className="text-green-400 font-medium text-lg mb-2">
            {result.imported} added · {result.updated} updated
            {result.removed > 0 && ` · ${result.removed} removed`}
          </p>
          <p className="text-xs text-gray-400">Mode: {mode}</p>
        </div>

        {result.unresolved.length > 0 && (
          <div className="rounded-xl border border-yellow-500/30 bg-yellow-900/10 p-5 mb-4">
            <p className="text-yellow-400 text-sm font-medium mb-2">
              {result.unresolved.length} card{result.unresolved.length !== 1 ? "s" : ""} not
              recognized
            </p>
            <ul className="text-xs text-gray-400 list-disc list-inside space-y-0.5 max-h-60 overflow-y-auto">
              {result.unresolved.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-gray-500">
              These names didn&apos;t match any card in the local DB. Fix the names and re-import,
              or sync more cards from the admin panel.
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <Link
            href={`/collections/${id}`}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            Back to Collection
          </Link>
          <button
            onClick={() => {
              setResult(null);
              setCsv("");
            }}
            className="rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
          >
            Import Another
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-8 flex items-center gap-3">
        <Link
          href={`/collections/${id}`}
          className="text-gray-500 hover:text-gray-300 text-sm transition-colors"
        >
          ← Collection
        </Link>
        <h1 className="text-2xl font-bold text-white">Import CSV</h1>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">Moxfield CSV</h2>
          <p className="mb-4 text-xs text-gray-500">
            Upload a Moxfield CSV export, or paste the contents below. Cards are matched by name.
          </p>

          <div className="mb-3">
            <label
              htmlFor="csv-file"
              className="inline-block cursor-pointer rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
            >
              Upload file…
            </label>
            <input
              id="csv-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => void handleFile(e)}
              className="hidden"
            />
          </div>

          <textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            placeholder={`"Count","Name","Edition","Collector Number"\n"1","Sol Ring","c19","255"`}
            rows={18}
            spellCheck={false}
            className="w-full rounded-lg border border-white/20 bg-black/20 px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y font-mono"
          />
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-3 font-semibold text-white">Import Mode</h2>
          <div className="grid grid-cols-2 gap-2">
            {(["merge", "replace"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`rounded-lg border px-3 py-3 text-left text-sm transition-colors ${
                  mode === m
                    ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                    : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                }`}
              >
                <p className="font-medium capitalize">{m}</p>
                <p className="mt-0.5 text-xs text-gray-500">
                  {m === "merge"
                    ? "Add new rows, increment quantity on existing printings."
                    : "Replace the entire collection with the CSV contents."}
                </p>
              </button>
            ))}
          </div>
        </section>

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Importing..." : "Import"}
        </button>
      </form>
    </div>
  );
}
