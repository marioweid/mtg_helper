"use client";

import { useState } from "react";
import { apiClient, ApiError } from "@/lib/api";

export function ExportButton({ deckId }: { deckId: string }) {
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const text = await apiClient.exportMoxfield(deckId);
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "deck.txt";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Export failed";
      alert(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-300 hover:border-white/40 hover:text-white transition-colors disabled:opacity-50"
    >
      {loading ? "Exporting..." : "Export to Moxfield"}
    </button>
  );
}
