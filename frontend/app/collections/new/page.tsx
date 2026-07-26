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
  const [linkUrl, setLinkUrl] = useState("");
  const [linkName, setLinkName] = useState("");
  const [linkSubmitting, setLinkSubmitting] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

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

  async function handleLinkSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!linkUrl.trim()) {
      setLinkError("Paste a Moxfield binder link first.");
      return;
    }
    setLinkSubmitting(true);
    setLinkError(null);
    try {
      const result = await apiClient.createCollectionFromUrl({
        url: linkUrl.trim(),
        ...(linkName.trim() ? { name: linkName.trim() } : {}),
      });
      router.push(`/collections/${result.collection.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DUPLICATE_COLLECTION") {
        setLinkError("You already have a collection with the binder's name — pick another.");
      } else {
        setLinkError(err instanceof Error ? err.message : "Import failed.");
      }
      setLinkSubmitting(false);
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

      <div className="my-6 flex items-center gap-3 text-xs text-gray-600">
        <div className="h-px flex-1 bg-white/10" />
        <span>or import from a Moxfield link</span>
        <div className="h-px flex-1 bg-white/10" />
      </div>

      <form onSubmit={handleLinkSubmit} className="flex flex-col gap-6">
        <section className="rounded-xl border border-white/10 bg-white/5 p-6">
          <label className="mb-1.5 block text-sm text-gray-400" htmlFor="binder-url">
            Binder URL
          </label>
          <input
            id="binder-url"
            type="url"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="https://moxfield.com/binders/..."
            spellCheck={false}
            className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <label className="mb-1.5 mt-4 block text-sm text-gray-400" htmlFor="binder-name">
            Collection name <span className="text-gray-600">(optional)</span>
          </label>
          <input
            id="binder-name"
            type="text"
            value={linkName}
            onChange={(e) => setLinkName(e.target.value)}
            placeholder="Defaults to the binder name"
            className="w-full rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <p className="mt-2 text-xs text-gray-500">
            Creates a new collection from a public Moxfield binder. The link is not stored.
          </p>
        </section>

        {linkError && (
          <p className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {linkError}
          </p>
        )}

        <button
          type="submit"
          disabled={linkSubmitting}
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {linkSubmitting ? "Importing..." : "Import Binder"}
        </button>
      </form>
    </div>
  );
}
