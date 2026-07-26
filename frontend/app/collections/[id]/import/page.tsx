"use client";

import Link from "next/link";
import { use, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { apiClient, ApiError } from "@/lib/api";
import type { CollectionImportFormat, CollectionImportResponse } from "@/lib/types";

type Mode = "merge" | "replace";
type Source = "csv" | "link";

const SOURCE_COPY: Record<Source, { label: string; hint: string }> = {
  csv: { label: "CSV", hint: "Upload or paste a Moxfield / ManaBox export." },
  link: { label: "Moxfield link", hint: "Paste a public binder URL." },
};

const FORMAT_COPY: Record<
  CollectionImportFormat,
  { label: string; description: string; placeholder: string }
> = {
  moxfield: {
    label: "Moxfield",
    description: "Upload a Moxfield CSV export, or paste the contents below.",
    placeholder: `"Count","Name","Edition","Collector Number"\n"1","Sol Ring","c19","255"`,
  },
  manabox: {
    label: "ManaBox",
    description: "Upload a ManaBox collection CSV export, or paste the contents below.",
    placeholder:
      "Name,Set code,Collector number,Foil,Quantity,Scryfall ID\n" +
      "Sol Ring,C19,221,normal,1,d1d2c466-3f2a-4dd5-96f7-ffd69a7a81ee",
  },
};

export default function ImportCollectionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [source, setSource] = useState<Source>("csv");
  const [csv, setCsv] = useState("");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<Mode>("merge");
  const [format, setFormat] = useState<CollectionImportFormat>("moxfield");
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
    if (source === "csv" && !csv.trim()) {
      setError("Paste or upload a CSV first.");
      return;
    }
    if (source === "link" && !url.trim()) {
      setError("Paste a Moxfield binder link first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res =
        source === "csv"
          ? await apiClient.importCollectionCsv(id, { csv, mode, format })
          : await apiClient.importCollectionUrl(id, { url: url.trim(), mode });
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
        <PageHeader title="Import complete" />


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
              setUrl("");
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
      <Link
        href={`/collections/${id}`}
        className="mb-4 inline-block text-sm text-gray-500 transition-colors hover:text-gray-300"
      >
        ← Collection
      </Link>
      <PageHeader
        title="Import cards"
        subtitle="Import from a CSV export or a public Moxfield binder link. Merge adds to what's already here; replace wipes first."
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-3 font-semibold text-white">Source</h2>
          <div className="grid grid-cols-2 gap-2">
            {(Object.keys(SOURCE_COPY) as Source[]).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={source === option}
                onClick={() => {
                  setSource(option);
                  setError(null);
                }}
                className={`rounded-lg border px-3 py-3 text-left text-sm transition-colors ${
                  source === option
                    ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                    : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                }`}
              >
                <p className="font-medium">{SOURCE_COPY[option].label}</p>
                <p className="mt-0.5 text-xs text-gray-500">{SOURCE_COPY[option].hint}</p>
              </button>
            ))}
          </div>
        </section>

        {source === "link" && (
          <section className="rounded-xl border border-white/10 bg-white/5 p-6">
            <h2 className="mb-1 font-semibold text-white">Moxfield binder link</h2>
            <p className="mb-4 text-xs text-gray-500">
              Public binders only. The link is not stored — re-import later to refresh.
            </p>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://moxfield.com/binders/..."
              spellCheck={false}
              className="w-full rounded-lg border border-white/20 bg-black/20 px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </section>
        )}

        {source === "csv" && (
          <>
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-3 font-semibold text-white">CSV Format</h2>
          <div className="grid grid-cols-2 gap-2">
            {(Object.keys(FORMAT_COPY) as CollectionImportFormat[]).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={format === option}
                onClick={() => {
                  setFormat(option);
                  setError(null);
                }}
                className={`rounded-lg border px-3 py-3 text-left text-sm transition-colors ${
                  format === option
                    ? "border-indigo-500 bg-indigo-900/40 text-indigo-300"
                    : "border-white/10 bg-white/5 text-gray-400 hover:border-white/20"
                }`}
              >
                <span className="font-medium">{FORMAT_COPY[option].label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-1 font-semibold text-white">{FORMAT_COPY[format].label} CSV</h2>
          <p className="mb-4 text-xs text-gray-500">{FORMAT_COPY[format].description}</p>

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
            placeholder={FORMAT_COPY[format].placeholder}
            rows={18}
            spellCheck={false}
            className="w-full rounded-lg border border-white/20 bg-black/20 px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y font-mono"
          />
        </section>
          </>
        )}

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
