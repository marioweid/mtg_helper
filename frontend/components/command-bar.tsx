"use client";

import { useState } from "react";
import Link from "next/link";

import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";

interface Props {
  deckId: string;
  buildLabel: string;
  onOpenStats: () => void;
}

/**
 * Sticky command bar pinned to the viewport bottom. Holds the primary deck
 * actions so they stay reachable while the user scrolls a long card list.
 */
export function CommandBar({ deckId, buildLabel, onOpenStats }: Props) {
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const [copyingBuylist, setCopyingBuylist] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const text = await apiClient.exportMoxfield(deckId);
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "deck.txt";
      a.click();
      URL.revokeObjectURL(url);
      toast.push("Exported to deck.txt", "success");
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Export failed", "error");
    } finally {
      setExporting(false);
    }
  }

  async function handleBuylist() {
    setCopyingBuylist(true);
    try {
      const text = await apiClient.exportBuylist(deckId);
      if (!text.trim()) {
        toast.push("Nothing to buy — you own everything", "success");
        return;
      }
      await navigator.clipboard.writeText(text);
      toast.push("Buy list copied to clipboard", "success");
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : "Buy list failed", "error");
    } finally {
      setCopyingBuylist(false);
    }
  }

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-zinc-950/85 backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-3">
        <Link
          href={`/decks/${deckId}/build`}
          className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-center text-sm font-medium text-white transition-colors hover:bg-indigo-500 sm:flex-none"
        >
          {buildLabel}
        </Link>
        <Link
          href={`/decks/${deckId}/playtest`}
          className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-center text-sm text-gray-200 transition-colors hover:border-white/40 hover:text-white sm:flex-none"
        >
          Simulate
        </Link>
        <button
          type="button"
          onClick={onOpenStats}
          className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 transition-colors hover:border-white/40 hover:text-white sm:flex-none"
        >
          Stats
        </button>
        <button
          type="button"
          onClick={() => void handleBuylist()}
          disabled={copyingBuylist}
          className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 transition-colors hover:border-white/40 hover:text-white disabled:opacity-50 sm:flex-none"
          title="Copy missing cards to clipboard (Cardmarket wants format)"
        >
          {copyingBuylist ? "Copying…" : "Buy list"}
        </button>
        <button
          type="button"
          onClick={() => void handleExport()}
          disabled={exporting}
          className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 transition-colors hover:border-white/40 hover:text-white disabled:opacity-50 sm:flex-none"
        >
          {exporting ? "Exporting…" : "Export"}
        </button>
      </div>
    </div>
  );
}
