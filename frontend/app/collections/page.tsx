"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import { getOrCreateAccountId } from "@/lib/account";
import { DeleteCollectionButton } from "@/components/delete-collection-button";
import type { CollectionResponse } from "@/lib/types";

export default function CollectionsPage() {
  const [collections, setCollections] = useState<CollectionResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const accountId = await getOrCreateAccountId();
      const items = await apiClient.listCollections(accountId);
      setCollections(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collections.");
      setCollections([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Your Collections</h1>
        <Link
          href="/collections/new"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          New Collection
        </Link>
      </div>

      {error && (
        <p className="mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </p>
      )}

      {collections === null ? (
        <div className="flex items-center justify-center py-20 text-gray-500">Loading...</div>
      ) : collections.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-white/20 py-20 text-center">
          <p className="text-gray-400">No collections yet.</p>
          <Link
            href="/collections/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            Create your first collection
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {collections.map((c) => (
            <CollectionTile key={c.id} collection={c} onDeleted={() => void load()} />
          ))}
        </div>
      )}
    </div>
  );
}

function CollectionTile({
  collection,
  onDeleted,
}: {
  collection: CollectionResponse;
  onDeleted: () => void;
}) {
  return (
    <div className="group relative">
      <Link
        href={`/collections/${collection.id}`}
        className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-5 hover:border-white/20 hover:bg-white/10 transition-all"
      >
        <h2 className="font-semibold text-white leading-tight pr-8">{collection.name}</h2>
        <p className="text-sm text-gray-400">
          {collection.card_count} card{collection.card_count !== 1 ? "s" : ""}
        </p>
        <p className="mt-2 text-xs text-gray-500">
          Created {new Date(collection.created_at).toLocaleDateString()}
        </p>
      </Link>
      <DeleteCollectionButton
        collectionId={collection.id}
        collectionName={collection.name}
        onDeleted={onDeleted}
      />
    </div>
  );
}
