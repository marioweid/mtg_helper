"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { CompareResults } from "@/components/compare-results";
import { CompareSidePicker } from "@/components/compare-side-picker";
import { useDeckComparison } from "@/lib/use-deck-comparison";

function CompareWorkspace() {
  const params = useSearchParams();
  const comparison = useDeckComparison(params.toString());
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Compare decks</h1>
        <p className="mt-1 text-sm text-gray-400">
          Compare physical decks, planned decks or snapshots. Planned = physical + additions − cuts.
        </p>
      </header>
      <section className="grid gap-4 md:grid-cols-2">
        <CompareSidePicker
          label="Left"
          decks={comparison.decks}
          value={comparison.left}
          onChange={comparison.setLeft}
        />
        <CompareSidePicker
          label="Right"
          decks={comparison.decks}
          value={comparison.right}
          onChange={comparison.setRight}
        />
      </section>
      <button
        type="button"
        onClick={comparison.swap}
        className={`self-center rounded-lg border border-white/15 px-4 py-2
          text-sm text-gray-300 hover:bg-white/5`}
      >
        Swap sides ⇄
      </button>
      {(comparison.loadError || comparison.error) && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
        >
          {comparison.loadError || comparison.error}
          <button
            type="button"
            onClick={comparison.loadError ? comparison.reload : comparison.retry}
            className="ml-2 underline"
          >
            Retry
          </button>
        </div>
      )}
      {comparison.loading && (
        <p role="status" className="text-sm text-gray-500">
          Comparing…
        </p>
      )}
      {comparison.result && (
        <CompareResults key={JSON.stringify(comparison.result)} result={comparison.result} />
      )}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<p className="p-6 text-gray-400">Loading comparison…</p>}>
      <CompareWorkspace />
    </Suspense>
  );
}
