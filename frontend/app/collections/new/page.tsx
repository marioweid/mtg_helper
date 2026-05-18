"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { apiClient, ApiError } from "@/lib/api";

export default function NewCollectionPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please enter a name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiClient.createCollection({ name: name.trim() });
      router.push(`/collections/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_COLLECTION") {
        setError("You already have a collection with that name.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to create collection.");
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <PageHeader
        title="New collection"
        subtitle="Use one collection per binder, box, or online inventory."
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <label className="mb-1.5 block text-sm text-gray-400" htmlFor="name">
            Name
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Paper Binder"
            autoFocus
            className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <p className="mt-2 text-xs text-gray-500">
            Use one collection per binder, box, or online inventory.
          </p>
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
          {submitting ? "Creating..." : "Create Collection"}
        </button>
      </form>
    </div>
  );
}
